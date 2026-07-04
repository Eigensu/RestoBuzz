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

# A queued/dispatching job is considered stuck (dispatch task lost) once it has
# been idle this long. Also the grace period before an unclaimed immediate-send
# job is treated as stuck.
STALE_MINUTES = 5


def _recoverable_jobs_filter(now: datetime) -> dict:
    """Jobs the poller should (re)dispatch.

    Two cases, single source of truth for both the scan (find) and the atomic
    claim (find_one_and_update) so they can't drift:

    1. Due scheduled drafts.
    2. queued/dispatching jobs that have gone stale — their dispatch task was lost
       to a worker restart. Staleness is measured by ``claimed_at``, falling back
       to ``created_at`` for a "Send Immediately" job that was never claimed (that
       path sets no claimed_at). ``started_at`` is intentionally NOT required to be
       empty: a job that began dispatching but stalled (status still
       queued/dispatching) must remain recoverable — a genuinely in-flight dispatch
       is status 'running', which this filter never matches. Re-dispatch is safe
       either way: dispatch only fans out message_logs still at 'queued', and each
       send atomically claims its row, so nothing is ever sent twice.
    """
    stale = now - timedelta(minutes=STALE_MINUTES)
    return {
        "$or": [
            {"status": "draft", "scheduled_at": {"$lte": now, "$ne": None}},
            {
                "status": {"$in": ["queued", "dispatching"]},
                "$or": [
                    {"claimed_at": {"$lte": stale}},
                    {"claimed_at": None, "created_at": {"$lte": stale}},
                    {"claimed_at": {"$exists": False}, "created_at": {"$lte": stale}},
                ],
            },
        ]
    }


@celery_app.task(name="app.workers.scheduled_poller.poll_scheduled_campaigns")
def poll_scheduled_campaigns() -> None:
    asyncio.run(_poll())


async def _poll() -> None:
    db = get_fresh_db()
    try:
        now = datetime.now(timezone.utc)

        # ── WhatsApp campaigns ────────────────────────────────────────────────────
        wa_cursor = db.campaign_jobs.find(_recoverable_jobs_filter(now))
        async for job in wa_cursor:
            job_id = str(job["_id"])
            # Optimistic lock: re-assert the full recoverable predicate so only one
            # worker claims the job (and only while it still qualifies).
            claimed = await db.campaign_jobs.find_one_and_update(
                {"_id": job["_id"], **_recoverable_jobs_filter(now)},
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
        email_cursor = db.email_campaign_jobs.find(_recoverable_jobs_filter(now))
        async for job in email_cursor:
            job_id = str(job["_id"])
            claimed = await db.email_campaign_jobs.find_one_and_update(
                {"_id": job["_id"], **_recoverable_jobs_filter(now)},
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
