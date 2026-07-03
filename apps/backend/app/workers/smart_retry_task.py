"""Smart retry worker — automatically retries failed campaign messages every 2 hours."""

import asyncio
from datetime import datetime, timezone, timedelta
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.services.campaign_service import create_child_retry_campaign
from app.workers.send_task import dispatch_campaign_task

logger = get_logger(__name__)


@celery_app.task(name="app.workers.smart_retry_task.auto_retry_failed_messages")
def auto_retry_failed_messages() -> None:
    """Periodic task: find campaigns with smart_retries enabled and retry their failed messages."""
    asyncio.run(_auto_retry())


async def _auto_retry() -> None:
    db = get_fresh_db()
    now = datetime.now(timezone.utc)

    try:
        # Find all campaigns that:
        # 1. Have smart_retries=True
        # 2. retry_until is still in the future
        # 3. Status is completed (has finished its initial run)
        # 4. Have failed messages
        # 5. Were NOT auto-retried in the last 2 hours (prevent duplicate retries)
        two_hours_ago = now - timedelta(hours=2)

        # Use last_auto_retry_at to track when we last created a retry child
        # If missing or older than 2 hours, we can retry again
        query = {
            "smart_retries": True,
            "retry_until": {"$gte": now},
            "status": "completed",
            "failed_count": {"$gt": 0},
            "$or": [
                {"last_auto_retry_at": {"$exists": False}},
                {"last_auto_retry_at": {"$lt": two_hours_ago}},
            ],
        }

        cursor = db.campaign_jobs.find(query)
        retried_count = 0

        async for campaign in cursor:
            campaign_id = campaign["_id"]
            restaurant_id = campaign.get("restaurant_id")

            if not restaurant_id:
                logger.warning(
                    "smart_retry_skipped_no_restaurant",
                    campaign_id=str(campaign_id),
                )
                continue

            # Count actual failed messages (might be less than failed_count if some were manually retried)
            failed_query = {"job_id": campaign_id, "status": "failed"}
            actual_failed = await db.message_logs.count_documents(failed_query)

            if actual_failed == 0:
                logger.info(
                    "smart_retry_skipped_no_failures",
                    campaign_id=str(campaign_id),
                )
                continue

            # Create retry child campaign
            # We don't use has_been_retried flag for smart retries so manual retry stays available
            try:
                # Create a system user ID placeholder for auto-retries
                system_user_id = campaign.get("created_by")

                job_id_str = await create_child_retry_campaign(
                    campaign, actual_failed, db, system_user_id
                )

                # Dispatch the retry campaign
                dispatch_campaign_task.apply_async(args=[job_id_str], queue="celery")

                # Update parent campaign to track when we last auto-retried
                await db.campaign_jobs.update_one(
                    {"_id": campaign_id},
                    {"$set": {"last_auto_retry_at": now}},
                )

                retried_count += 1
                logger.info(
                    "smart_retry_created",
                    campaign_id=str(campaign_id),
                    campaign_name=campaign["name"],
                    retry_campaign_id=job_id_str,
                    failed_count=actual_failed,
                )

            except Exception as exc:
                logger.error(
                    "smart_retry_failed",
                    campaign_id=str(campaign_id),
                    error=str(exc),
                )
                continue

        logger.info("smart_retry_batch_complete", retried_count=retried_count)

    except Exception as e:
        logger.error("smart_retry_task_failed", error=str(e))
