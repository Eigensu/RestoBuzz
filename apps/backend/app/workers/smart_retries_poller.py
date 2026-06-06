import asyncio
from datetime import datetime, timezone, timedelta

import kombu.exceptions
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.services.campaign_service import create_child_retry_campaign
from app.workers.send_task import dispatch_campaign_task

logger = get_logger(__name__)


@celery_app.task(name="app.workers.smart_retries_poller.poll_smart_retries")
def poll_smart_retries() -> None:
    asyncio.run(_poll())


async def _poll() -> None:
    db = get_fresh_db()
    try:
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)

        # Find campaigns that need auto-retry:
        # - smart_retries enabled
        # - status completed/failed (finished initial run)
        # - have failed messages
        # - retry_until is still in the future
        # - last_auto_retry_at is missing OR older than 2 hours
        cursor = db.campaign_jobs.find(
            {
                "smart_retries": True,
                "status": {"$in": ["completed", "failed"]},
                "failed_count": {"$gt": 0},
                "retry_until": {"$gt": now},
                "$or": [
                    {"last_auto_retry_at": {"$exists": False}},
                    {"last_auto_retry_at": {"$lte": two_hours_ago}},
                ],
            }
        )
        async for job in cursor:
            job_id_obj = job["_id"]

            # Atomically claim the retry slot for this 2-hour window
            # Use last_auto_retry_at to prevent duplicate retries in the same window
            claimed = await db.campaign_jobs.find_one_and_update(
                {
                    "_id": job_id_obj,
                    "$or": [
                        {"last_auto_retry_at": {"$exists": False}},
                        {"last_auto_retry_at": {"$lte": two_hours_ago}},
                    ],
                },
                {"$set": {"last_auto_retry_at": now}},
                return_document=False,
            )

            if claimed is not None:
                # Check actual failed count (might be less than failed_count if manually retried)
                actual_failed = await db.message_logs.count_documents(
                    {"job_id": job_id_obj, "status": "failed"}
                )

                if actual_failed == 0:
                    logger.info(
                        "smart_retry_skipped_no_failures", job_id=str(job_id_obj)
                    )
                    continue

                # We claimed it, let's spawn the child retry campaign
                try:
                    new_job_id_str = await create_child_retry_campaign(
                        job, actual_failed, db, job.get("created_by", "system")
                    )

                    dispatch_campaign_task.delay(new_job_id_str)
                    logger.info(
                        "smart_retry_dispatched",
                        parent_job_id=str(job_id_obj),
                        child_job_id=new_job_id_str,
                        failed_count=actual_failed,
                    )
                except kombu.exceptions.KombuError:
                    logger.exception(
                        "smart_retry_dispatch_broker_failed",
                        parent_job_id=str(job_id_obj),
                    )
                    # Roll back the claim so it can retry in the next poll
                    await db.campaign_jobs.update_one(
                        {"_id": job_id_obj}, {"$unset": {"last_auto_retry_at": ""}}
                    )
                except Exception:
                    logger.exception(
                        "smart_retry_dispatch_failed", parent_job_id=str(job_id_obj)
                    )
                    # Roll back the claim so it can retry in the next poll
                    await db.campaign_jobs.update_one(
                        {"_id": job_id_obj}, {"$unset": {"last_auto_retry_at": ""}}
                    )
    finally:
        db.client.close()
