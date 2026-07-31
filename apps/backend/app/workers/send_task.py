import asyncio
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from celery import Task
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.core.redlock import RedLock
from app.services.meta_api import send_template_message, MetaAPIError
from app.services.rate_limiter import acquire_token
from app.services.suppression import is_suppressed
from app.services.deduplication import mark_seen
import redis as sync_redis

logger = get_logger(__name__)

_PUSH = "$push"  # reused in update operations to avoid duplicate literal warnings

_redis_state = {"client": None}


def _get_redis():
    if _redis_state["client"] is None:
        from app.config import settings

        _redis_state["client"] = sync_redis.from_url(
            settings.redis_url, decode_responses=True
        )
    return _redis_state["client"]


def _get_async_redis():
    from redis.asyncio import from_url
    from app.config import settings

    return from_url(settings.redis_url, decode_responses=True)


@celery_app.task(bind=True, name="app.workers.send_task.dispatch_campaign_task")
def dispatch_campaign_task(_task: Task, job_id: str) -> None:
    asyncio.run(_dispatch(job_id))


async def _dispatch(job_id: str) -> None:
    db = get_fresh_db()
    try:
        job = await db.campaign_jobs.find_one({"_id": ObjectId(job_id)})
        if not job:
            logger.error("dispatch_job_not_found", job_id=job_id)
            return

        if job.get("status") in {"cancelled", "paused"}:
            logger.info("dispatch_skipped", job_id=job_id, status=job.get("status"))
            return

        await db.campaign_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)}},
        )

        queue = "utility" if job["priority"] == "UTILITY" else "marketing"
        cursor = db.message_logs.find({"job_id": ObjectId(job_id), "status": "queued"})

        async for msg in cursor:
            send_message_task.apply_async(
                args=[str(msg["_id"])],
                queue=queue,
            )

        logger.info("dispatch_complete", job_id=job_id, queue=queue)

        # Mark completed if nothing was queued (all already sent/failed)
        remaining = await db.message_logs.count_documents(
            {"job_id": ObjectId(job_id), "status": "queued"}
        )
        if remaining == 0:
            await db.campaign_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc),
                    }
                },
            )
    finally:
        db.client.close()


@celery_app.task(
    bind=True,
    name="app.workers.send_task.send_message_task",
    max_retries=3,
    default_retry_delay=30,
)
def send_message_task(self: Task, message_log_id: str) -> None:
    asyncio.run(_send(self, message_log_id))


async def _send(task: Task, message_log_id: str) -> None:
    db = get_fresh_db()
    redis = _get_async_redis()

    try:
        async with RedLock(redis, message_log_id, ttl_ms=60_000):
            # Atomic claim
            now = datetime.now(timezone.utc)
            msg = await db.message_logs.find_one_and_update(
                {"_id": ObjectId(message_log_id), "status": "queued"},
                {
                    "$set": {
                        "status": "sending",
                        "locked_until": now + timedelta(seconds=60),
                        "updated_at": now,
                    }
                },
                return_document=True,
            )
            if not msg:
                logger.info("message_already_claimed", id=message_log_id)
                return

            campaign = await db.campaign_jobs.find_one(
                {"_id": msg["job_id"]}, {"status": 1}
            )
            # If the campaign is paused, revert this message to "queued" (not
            # "cancelled") so that resuming the campaign re-dispatches it. Only a
            # genuinely cancelled/missing campaign should cancel the message.
            if campaign and campaign.get("status") == "paused":
                await db.message_logs.update_one(
                    {"_id": ObjectId(message_log_id)},
                    {
                        "$set": {
                            "status": "queued",
                            "locked_until": None,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                return
            if not campaign or campaign.get("status") == "cancelled":
                await db.message_logs.update_one(
                    {"_id": ObjectId(message_log_id)},
                    {
                        "$set": {
                            "status": "cancelled",
                            "locked_until": None,
                            "updated_at": datetime.now(timezone.utc),
                        },
                        _PUSH: {
                            "status_history": {
                                "status": "cancelled",
                                "timestamp": datetime.now(timezone.utc),
                                "meta": {
                                    "campaign_status": (
                                        campaign.get("status")
                                        if campaign
                                        else "missing"
                                    )
                                },
                            }
                        },
                    },
                )
                return

            # Suppression check
            if await is_suppressed(db, msg["recipient_phone"]):
                await _fail_message(
                    db, message_log_id, "suppressed", "Number is suppressed"
                )
                await db.campaign_jobs.update_one(
                    {"_id": msg["job_id"]},
                    {"$inc": {"failed_count": 1}},
                )
                await _auto_complete_job(db, msg["job_id"])
                return

            # Rate limit
            allowed = await acquire_token(redis)
            if not allowed:
                await db.message_logs.update_one(
                    {"_id": ObjectId(message_log_id)},
                    {"$set": {"status": "queued", "locked_until": None}},
                )
                task.retry(countdown=1)
                return

            # Send via Meta API
            await _do_send(task, db, redis, msg, message_log_id)

    finally:
        try:
            await redis.aclose()
        finally:
            db.client.close()


async def _do_send(
    task: Task,
    db,
    redis,
    msg: dict,
    message_log_id: str,
) -> None:
    """Resolve language, call Meta API, record the result, and auto-complete the job."""
    restaurant_id = msg.get("restaurant_id")
    language = msg.get("language")
    if not language:
        template_id = msg.get("template_id")
        if template_id:
            tpl = await db.templates.find_one({"_id": ObjectId(template_id)}, {"language": 1})
            language = (tpl or {}).get("language")
            
        if not language:
            language = msg.get("template_language")
            
        if not language:
            tpl_query: dict = {"name": msg.get("template_name", "")}
            if restaurant_id:
                tpl_query["restaurant_id"] = restaurant_id
            tpl = await db.templates.find_one(tpl_query, {"language": 1})
            language = (tpl or {}).get("language") or "en_US"

    # Credentials were stamped onto the message_log at campaign creation time.
    wa_phone_id: str | None = msg.get("wa_phone_id") or None
    wa_access_token: str | None = None
    env_key: str = msg.get("wa_access_token_env_key") or ""
    if env_key:
        from app.config import settings as _cfg
        wa_access_token = _cfg.resolve_waba_token(env_key)

    if restaurant_id and (not wa_phone_id or not wa_access_token):
        await _handle_meta_error(
            task, db, msg, message_log_id,
            MetaAPIError("config_error", "Missing or invalid restaurant WABA credentials (wa_phone_id / access_token_env_key). Cannot use global fallback for restaurant messages.")
        )
        return

    try:
        wa_id, endpoint = await send_template_message(
            to=msg["recipient_phone"],
            template_name=msg.get("template_name", ""),
            variables=msg.get("template_variables", {}),
            media_url=msg.get("media_url"),
            language=language,
            phone_id=wa_phone_id,
            access_token=wa_access_token,
            media_type=msg.get("media_type"),
        )
    except MetaAPIError as e:
        await _handle_meta_error(task, db, msg, message_log_id, e)
        return

    await mark_seen(redis, wa_id)
    sent_now = datetime.now(timezone.utc)
    await db.message_logs.update_one(
        {"_id": ObjectId(message_log_id)},
        {
            "$set": {
                "status": "sent",
                "wa_message_id": wa_id,
                "endpoint_used": endpoint,
                "fallback_used": endpoint == "fallback",
                "locked_until": None,
                # Real send time (may be much later than created_at for a campaign
                # that sat queued). Reply-window matching keys off this, not
                # created_at, so replies to a long-delayed send still count.
                "sent_at": sent_now,
                "updated_at": sent_now,
            },
            _PUSH: {
                "status_history": {
                    "status": "sent",
                    "timestamp": sent_now,
                    "meta": {"endpoint": endpoint},
                }
            },
        },
    )
    await db.campaign_jobs.update_one(
        {"_id": msg["job_id"]},
        {"$inc": {"sent_count": 1}},
    )
    await _auto_complete_job(db, msg["job_id"])
    logger.info("message_sent", id=message_log_id, wa_id=wa_id)


async def _handle_meta_error(
    task: Task, db, msg: dict, message_log_id: str, e: MetaAPIError
) -> None:
    """Retry transient Meta API errors; permanently fail after max retries."""
    retry_count = msg.get("retry_count", 0)
    if retry_count < 3:
        countdown = 30 * (4**retry_count)
        await db.message_logs.update_one(
            {"_id": ObjectId(message_log_id)},
            {
                "$set": {"status": "queued", "locked_until": None},
                "$inc": {"retry_count": 1},
            },
        )
        task.retry(countdown=countdown, exc=e)
    else:
        await _fail_message(db, message_log_id, e.code, e.message)
        await db.campaign_jobs.update_one(
            {"_id": msg["job_id"]},
            {"$inc": {"failed_count": 1}},
        )
        await _auto_complete_job(db, msg["job_id"])


async def _auto_complete_job(db, job_id) -> None:
    """Transition job to completed once no messages remain to send.

    Completion is based on the DISTINCT count of message_logs still pending
    (queued/sending), NOT sent_count + failed_count. Those two counters overlap:
    a message counts as 'sent' when Meta accepts it, then counts again as
    'failed' when a delivery webhook reports failure (e.g. error 131049). Their
    sum can therefore exceed total_count and complete the job prematurely,
    abandoning still-queued recipients (which smart retries never pick up, since
    it only retries failures). Counting pending message_logs is exact and can't
    overshoot.
    """
    pending = await db.message_logs.count_documents(
        {"job_id": job_id, "status": {"$in": ["queued", "sending"]}}
    )
    if pending == 0:
        await db.campaign_jobs.update_one(
            {"_id": job_id, "status": "running"},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )


async def _fail_message(db, message_log_id: str, code: str, message: str) -> None:
    now = datetime.now(timezone.utc)
    await db.message_logs.update_one(
        {"_id": ObjectId(message_log_id)},
        {
            "$set": {
                "status": "failed",
                "error_code": code,
                "error_message": message,
                "locked_until": None,
                "updated_at": now,
            },
            _PUSH: {
                "status_history": {
                    "status": "failed",
                    "timestamp": now,
                    "meta": {"code": code},
                }
            },
        },
    )
