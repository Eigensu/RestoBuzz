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

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        from app.config import settings

        _redis_client = sync_redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _get_async_redis():
    from redis.asyncio import from_url
    from app.config import settings

    return from_url(settings.redis_url, decode_responses=True)


@celery_app.task(bind=True, name="app.workers.send_task.dispatch_campaign_task")
def dispatch_campaign_task(self: Task, job_id: str) -> None:
    asyncio.run(_dispatch(job_id))


async def _dispatch(job_id: str) -> None:
    db = get_fresh_db()
    job = await db.campaign_jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        logger.error("dispatch_job_not_found", job_id=job_id)
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

            # Suppression check
            if await is_suppressed(db, msg["recipient_phone"]):
                await _fail_message(
                    db, message_log_id, "suppressed", "Number is suppressed"
                )
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
            try:
                wa_id, endpoint = await send_template_message(
                    to=msg["recipient_phone"],
                    template_name=msg.get("template_name", ""),
                    variables=msg.get("template_variables", {}),
                    media_url=msg.get("media_url"),
                )
                await mark_seen(redis, wa_id)
                await db.message_logs.update_one(
                    {"_id": ObjectId(message_log_id)},
                    {
                        "$set": {
                            "status": "sent",
                            "wa_message_id": wa_id,
                            "endpoint_used": endpoint,
                            "fallback_used": endpoint == "fallback",
                            "locked_until": None,
                            "updated_at": datetime.now(timezone.utc),
                        },
                        "$push": {
                            "status_history": {
                                "status": "sent",
                                "timestamp": datetime.now(timezone.utc),
                                "meta": {"endpoint": endpoint},
                            }
                        },
                    },
                )
                await db.campaign_jobs.update_one(
                    {"_id": msg["job_id"]},
                    {"$inc": {"sent_count": 1}},
                )
                # Auto-complete if all messages are done
                updated_job = await db.campaign_jobs.find_one({"_id": msg["job_id"]})
                if updated_job and (
                    updated_job.get("sent_count", 0)
                    + updated_job.get("failed_count", 0)
                ) >= updated_job.get("total_count", 0):
                    await db.campaign_jobs.update_one(
                        {"_id": msg["job_id"], "status": "running"},
                        {
                            "$set": {
                                "status": "completed",
                                "completed_at": datetime.now(timezone.utc),
                            }
                        },
                    )
                logger.info("message_sent", id=message_log_id, wa_id=wa_id)

            except MetaAPIError as e:
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
    finally:
        await redis.aclose()


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
            "$push": {
                "status_history": {
                    "status": "failed",
                    "timestamp": now,
                    "meta": {"code": code},
                }
            },
        },
    )
