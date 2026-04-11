"""
Celery Beat task: poll for campaigns whose scheduled_at has elapsed
and transition them from draft → queued, then dispatch.

Runs every minute. Uses find_one_and_update as an optimistic lock
so concurrent Beat workers cannot double-dispatch the same campaign.
"""

import asyncio
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.scheduled_poller.poll_scheduled_campaigns")
def poll_scheduled_campaigns() -> None:
    asyncio.run(_poll())


async def _poll() -> None:
    db = get_fresh_db()
    try:
        now = datetime.now(timezone.utc)

        # ── WhatsApp campaigns ────────────────────────────────────────────────────
        wa_cursor = db.campaign_jobs.find(
            {"status": "draft", "scheduled_at": {"$lte": now, "$ne": None}}
        )
        async for job in wa_cursor:
            job_id = str(job["_id"])
            # Optimistic lock: only wins if status is still "draft"
            claimed = await db.campaign_jobs.find_one_and_update(
                {"_id": job["_id"], "status": "draft"},
                {"$set": {"status": "queued"}},
                return_document=False,
            )
            if claimed is not None:  # None means another worker won the race
                from app.workers.send_task import dispatch_campaign_task

                try:
                    dispatch_campaign_task.delay(job_id)
                    logger.info("scheduled_wa_campaign_dispatched", job_id=job_id)
                except Exception as exc:
                    logger.error(
                        "scheduled_wa_dispatch_failed", job_id=job_id, error=str(exc)
                    )
                    await db.campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "draft"}}
                    )

        # ── Email campaigns ───────────────────────────────────────────────────────
        email_cursor = db.email_campaign_jobs.find(
            {"status": "draft", "scheduled_at": {"$lte": now, "$ne": None}}
        )
        async for job in email_cursor:
            job_id = str(job["_id"])
            claimed = await db.email_campaign_jobs.find_one_and_update(
                {"_id": job["_id"], "status": "draft"},
                {"$set": {"status": "queued"}},
                return_document=False,
            )
            if claimed is not None:
                from app.workers.send_email_task import dispatch_email_campaign_task

                try:
                    dispatch_email_campaign_task.delay(job_id)
                    logger.info("scheduled_email_campaign_dispatched", job_id=job_id)
                except Exception as exc:
                    logger.error(
                        "scheduled_email_dispatch_failed", job_id=job_id, error=str(exc)
                    )
                    await db.email_campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "draft"}}
                    )
    finally:
        db.client.close()
