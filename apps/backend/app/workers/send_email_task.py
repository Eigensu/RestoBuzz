"""
Celery tasks for dispatching email campaigns via Resend.

Architecture:
- dispatch_email_campaign_task: splits campaign into chunks and sends individual messages
- send_single_email_task: sends one email with rate limiting, suppression checks, and retries
"""
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from celery import Task
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.services.resend_client import render_template, send_email, ResendSendError
from app.services.email_suppression import is_email_suppressed
from app.services.rate_limiter import acquire_token

logger = get_logger(__name__)


def _get_async_redis():
    from redis.asyncio import from_url
    from app.config import settings
    return from_url(settings.redis_url, decode_responses=True)


@celery_app.task(bind=True, name="app.workers.send_email_task.dispatch_email_campaign_task")
def dispatch_email_campaign_task(self: Task, campaign_id: str) -> None:
    """Master dispatcher: transitions campaign to 'sending' and enqueues individual email tasks."""
    asyncio.run(_dispatch(campaign_id))


async def _dispatch(campaign_id: str) -> None:
    db = get_fresh_db()
    job = await db.email_campaign_jobs.find_one({"_id": ObjectId(campaign_id)})
    if not job:
        logger.error("email_dispatch_job_not_found", campaign_id=campaign_id)
        return

    # Check if cancelled before starting
    if job["status"] == "cancelled":
        return

    await db.email_campaign_jobs.update_one(
        {"_id": ObjectId(campaign_id)},
        {"$set": {"status": "sending", "started_at": datetime.now(timezone.utc)}},
    )

    cursor = db.email_logs.find(
        {"campaign_id": ObjectId(campaign_id), "status": "queued"}
    )
    count = 0
    async for msg in cursor:
        send_single_email_task.apply_async(
            args=[str(msg["_id"])],
            queue="email",
        )
        count += 1

    logger.info("email_dispatch_complete", campaign_id=campaign_id, enqueued=count)

    # If nothing was queued (edge case), mark completed immediately
    if count == 0:
        await db.email_campaign_jobs.update_one(
            {"_id": ObjectId(campaign_id)},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )


@celery_app.task(
    bind=True,
    name="app.workers.send_email_task.send_single_email_task",
    max_retries=3,
    default_retry_delay=30,
)
def send_single_email_task(self: Task, email_log_id: str) -> None:
    """Send a single email: suppression check → rate limit → render → send → record."""
    asyncio.run(_send_one(self, email_log_id))


async def _send_one(task: Task, email_log_id: str) -> None:
    db = get_fresh_db()
    redis = _get_async_redis()

    try:
        now = datetime.now(timezone.utc)

        # Atomic claim — prevent duplicate worker processing
        msg = await db.email_logs.find_one_and_update(
            {"_id": ObjectId(email_log_id), "status": "queued"},
            {"$set": {"status": "sending", "updated_at": now}},
            return_document=True,
        )
        if not msg:
            logger.info("email_already_claimed", id=email_log_id)
            return

        campaign_id = msg["campaign_id"]

        # Fetch campaign for template snapshot
        job = await db.email_campaign_jobs.find_one({"_id": campaign_id})
        if not job:
            await _fail_email(db, email_log_id, "Campaign not found")
            return

        # Check if campaign was cancelled mid-flight
        if job["status"] == "cancelled":
            await db.email_logs.update_one(
                {"_id": ObjectId(email_log_id)},
                {"$set": {"status": "queued", "updated_at": datetime.now(timezone.utc)}},
            )
            return

        # Suppression check
        if await is_email_suppressed(db, msg["recipient_email"]):
            await _fail_email(db, email_log_id, "Email is suppressed")
            await db.email_campaign_jobs.update_one(
                {"_id": campaign_id}, {"$inc": {"failed_count": 1}}
            )
            return

        # Rate limit (centralized via Redis)
        from app.config import settings
        allowed = await acquire_token(
            redis,
            waba_id="resend",
            capacity=settings.resend_rate_limit,
            refill_rate=settings.resend_rate_limit,
        )
        if not allowed:
            await db.email_logs.update_one(
                {"_id": ObjectId(email_log_id)},
                {"$set": {"status": "queued", "updated_at": datetime.now(timezone.utc)}},
            )
            task.retry(countdown=1)
            return

        # Render template from snapshot
        snapshot = job.get("template_snapshot", {})
        template_html = snapshot.get("html", "")
        variables_schema = snapshot.get("variables_schema", [])

        # Build variable dict: contact-specific + fallbacks
        render_vars = {}
        for v in variables_schema:
            key = v["key"]
            contact_val = msg.get("template_variables", {}).get(key)
            if contact_val is not None:
                render_vars[key] = contact_val
            elif v.get("fallback_value") is not None:
                render_vars[key] = v["fallback_value"]

        try:
            rendered_html = render_template(template_html, render_vars)
        except Exception as e:
            await _fail_email(db, email_log_id, f"Template render error: {e}")
            await db.email_campaign_jobs.update_one(
                {"_id": campaign_id}, {"$inc": {"failed_count": 1}}
            )
            return

        # Send via Resend
        try:
            resend_id = send_email(
                to=msg["recipient_email"],
                subject=snapshot.get("subject", job.get("subject", "")),
                html=rendered_html,
                from_email=job.get("from_email"),
                reply_to=job.get("reply_to"),
                tags={"campaign_id": str(campaign_id)},
            )

            await db.email_logs.update_one(
                {"_id": ObjectId(email_log_id)},
                {
                    "$set": {
                        "status": "sent",
                        "resend_email_id": resend_id,
                        "updated_at": datetime.now(timezone.utc),
                    },
                    "$push": {
                        "status_history": {
                            "status": "sent",
                            "timestamp": datetime.now(timezone.utc),
                            "meta": {"resend_id": resend_id},
                        }
                    },
                },
            )
            await db.email_campaign_jobs.update_one(
                {"_id": campaign_id}, {"$inc": {"sent_count": 1}}
            )

            # Auto-complete check
            await _check_completion(db, campaign_id)

            logger.info(
                "email_sent",
                id=email_log_id,
                resend_id=resend_id,
                to=msg["recipient_email"],
            )

        except ResendSendError as e:
            retry_count = msg.get("retry_count", 0)
            if retry_count < 3:
                countdown = 30 * (4 ** retry_count)
                await db.email_logs.update_one(
                    {"_id": ObjectId(email_log_id)},
                    {
                        "$set": {"status": "queued", "updated_at": datetime.now(timezone.utc)},
                        "$inc": {"retry_count": 1},
                    },
                )
                task.retry(countdown=countdown, exc=e)
            else:
                await _fail_email(db, email_log_id, e.message)
                await db.email_campaign_jobs.update_one(
                    {"_id": campaign_id}, {"$inc": {"failed_count": 1}}
                )
                await _check_completion(db, campaign_id)

    finally:
        await redis.aclose()


async def _fail_email(db, email_log_id: str, reason: str) -> None:
    now = datetime.now(timezone.utc)
    await db.email_logs.update_one(
        {"_id": ObjectId(email_log_id)},
        {
            "$set": {
                "status": "failed",
                "error_reason": reason,
                "updated_at": now,
            },
            "$push": {
                "status_history": {
                    "status": "failed",
                    "timestamp": now,
                    "meta": {"reason": reason},
                }
            },
        },
    )


async def _check_completion(db, campaign_id) -> None:
    """Auto-transition campaign to completed/partial_failure when all messages are processed."""
    updated_job = await db.email_campaign_jobs.find_one({"_id": campaign_id})
    if not updated_job:
        return

    processed = (
        updated_job.get("sent_count", 0)
        + updated_job.get("failed_count", 0)
    )
    total = updated_job.get("total_count", 0)

    if processed >= total and updated_job["status"] == "sending":
        final_status = "completed"
        if updated_job.get("failed_count", 0) > 0:
            final_status = "partial_failure"

        await db.email_campaign_jobs.update_one(
            {"_id": campaign_id, "status": "sending"},
            {
                "$set": {
                    "status": final_status,
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )
