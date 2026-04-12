"""
Celery Beat task: poll for campaigns whose scheduled_at has elapsed
and transition them from draft → queued, then dispatch.

Runs every minute. Uses find_one_and_update as an optimistic lock
so concurrent Beat workers cannot double-dispatch the same campaign.
"""

import asyncio
from datetime import datetime, timezone, timedelta

import kombu.exceptions
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.workers.send_task import dispatch_campaign_task
from app.workers.send_email_task import dispatch_email_campaign_task

logger = get_logger(__name__)


@celery_app.task(name="app.workers.scheduled_poller.poll_scheduled_campaigns")
def poll_scheduled_campaigns() -> None:
    asyncio.run(_poll())


async def _poll() -> None:
    db = get_fresh_db()
    try:
        now = datetime.now(timezone.utc)

        stale_threshold = now - timedelta(minutes=5)

        # ── WhatsApp campaigns ────────────────────────────────────────────────────
        wa_cursor = db.campaign_jobs.find(
            {
                "$or": [
                    {"status": "draft", "scheduled_at": {"$lte": now, "$ne": None}},
                    {"status": {"$in": ["queued", "dispatching"]}, "claimed_at": {"$lte": stale_threshold}, "$or": [{"started_at": {"$exists": False}}, {"started_at": None}]}
                ]
            }
        )
        async for job in wa_cursor:
            job_id = str(job["_id"])
            # Optimistic lock: only wins if status matches exactly our read conditions
            claimed = await db.campaign_jobs.find_one_and_update(
                {
                    "_id": job["_id"],
                    "$or": [
                        {"status": "draft"},
                        {"status": {"$in": ["queued", "dispatching"]}, "claimed_at": {"$lte": stale_threshold}, "$or": [{"started_at": {"$exists": False}}, {"started_at": None}]}
                    ]
                },
                {"$set": {"status": "dispatching", "claimed_at": now}},
                return_document=False,
            )
            if claimed is not None:  # None means another worker won the race


                try:
                    dispatch_campaign_task.delay(job_id)
                    await db.campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "queued", "dispatched_at": now}}
                    )
                    logger.info("scheduled_wa_campaign_dispatched", job_id=job_id)
                except kombu.exceptions.KombuError:
                    logger.exception(
                        "scheduled_wa_dispatch_broker_failed", job_id=job_id
                    )
                    await db.campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "draft"}}
                    )
                except Exception:
                    logger.exception(
                        "scheduled_wa_dispatch_failed", job_id=job_id
                    )
                    await db.campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "draft"}}
                    )

        # ── Email campaigns ───────────────────────────────────────────────────────
        email_cursor = db.email_campaign_jobs.find(
            {
                "$or": [
                    {"status": "draft", "scheduled_at": {"$lte": now, "$ne": None}},
                    {"status": {"$in": ["queued", "dispatching"]}, "claimed_at": {"$lte": stale_threshold}, "$or": [{"started_at": {"$exists": False}}, {"started_at": None}]}
                ]
            }
        )
        async for job in email_cursor:
            job_id = str(job["_id"])
            claimed = await db.email_campaign_jobs.find_one_and_update(
                {
                    "_id": job["_id"],
                    "$or": [
                        {"status": "draft"},
                        {"status": {"$in": ["queued", "dispatching"]}, "claimed_at": {"$lte": stale_threshold}, "$or": [{"started_at": {"$exists": False}}, {"started_at": None}]}
                    ]
                },
                {"$set": {"status": "dispatching", "claimed_at": now}},
                return_document=False,
            )
            if claimed is not None:


                try:
                    dispatch_email_campaign_task.delay(job_id)
                    await db.email_campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "queued", "dispatched_at": now}}
                    )
                    logger.info("scheduled_email_campaign_dispatched", job_id=job_id)
                except kombu.exceptions.KombuError:
                    logger.exception(
                        "scheduled_email_dispatch_broker_failed", job_id=job_id
                    )
                    await db.email_campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "draft"}}
                    )
                except Exception:
                    logger.exception(
                        "scheduled_email_dispatch_failed", job_id=job_id
                    )
                    await db.email_campaign_jobs.update_one(
                        {"_id": job["_id"]}, {"$set": {"status": "draft"}}
                    )
    finally:
        db.client.close()
