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

        cursor = db.campaign_jobs.find(
            {
                "smart_retries": True,
                "has_been_retried": {"$ne": True},
                "status": {"$in": ["completed", "failed"]},
                "failed_count": {"$gt": 0},
                "completed_at": {"$lte": two_hours_ago},
                "retry_until": {"$gt": now},
            }
        )
        async for job in cursor:
            job_id_obj = job["_id"]
            
            # Atomically claim the retry slot
            claimed = await db.campaign_jobs.find_one_and_update(
                {"_id": job_id_obj, "has_been_retried": {"$ne": True}},
                {"$set": {"has_been_retried": True, "retry_claimed_at": now}},
                return_document=False,
            )
            
            if claimed is not None:
                # We claimed it, let's spawn the child retry campaign
                try:
                    new_job_id_str = await create_child_retry_campaign(
                        job, job.get("failed_count", 0), db, job.get("created_by", "system")
                    )
                    
                    dispatch_campaign_task.delay(new_job_id_str)
                    logger.info("smart_retry_dispatched", parent_job_id=str(job_id_obj), child_job_id=new_job_id_str)
                except kombu.exceptions.KombuError:
                    logger.exception(
                        "smart_retry_dispatch_broker_failed", parent_job_id=str(job_id_obj)
                    )
                except Exception:
                    logger.exception(
                        "smart_retry_dispatch_failed", parent_job_id=str(job_id_obj)
                    )
    finally:
        db.client.close()
