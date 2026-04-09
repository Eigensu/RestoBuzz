"""
Email Reconciliation CRON Task.

Runs periodically to catch any emails that are stuck in non-terminal statuses
because webhooks were lost or delayed.

Uses the Resend API to fetch the actual status of stale email logs.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import resend

from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.config import settings

resend.api_key = settings.resend_api_key

logger = get_logger(__name__)

# Terminal statuses that need no reconciliation
TERMINAL_STATUSES = {"delivered", "bounced", "failed", "complained", "suppressed"}

# Only reconcile logs from the last 48 hours
RECONCILIATION_WINDOW_HOURS = 48

# How old a log must be before we consider it stale
STALE_THRESHOLD_MINUTES = 10


@celery_app.task(name="app.workers.email_reconciliation_task.reconcile_email_statuses")
def reconcile_email_statuses() -> None:
    asyncio.run(_reconcile())


STATUS_ORDER = [
    "queued",
    "sending",
    "sent",
    "delivered",
    "opened",
    "clicked",
]

INCREMENTAL_COUNTERS = {
    "delivered",
    "opened",
    "clicked",
    "bounced",
    "failed",
    "complained",
}


async def _reconcile_single_log(db, log: dict) -> bool:
    resend_id = log["resend_email_id"]
    try:
        email_data = await asyncio.to_thread(resend.Emails.get, resend_id)
        if not isinstance(email_data, dict):
            return False

        last_event = email_data.get("last_event")
        if not last_event:
            return False

        new_status = last_event.replace("email.", "")
        if new_status not in (
            "sent", "delivered", "bounced", "failed", "opened", "clicked", "complained"
        ):
            return False

        current_status = log["status"]
        if (
            new_status in STATUS_ORDER
            and current_status in STATUS_ORDER
            and STATUS_ORDER.index(new_status) <= STATUS_ORDER.index(current_status)
        ):
            return False

        # Update log and increment campaign counters
        update_result = await db.email_logs.update_one(
            {"_id": log["_id"], "status": current_status},
            {
                "$set": {
                    "status": new_status,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$push": {
                    "status_history": {
                        "status": new_status,
                        "timestamp": datetime.now(timezone.utc),
                        "meta": {"source": "reconciliation"},
                    }
                },
            },
        )

        if update_result.modified_count > 0:
            if new_status in INCREMENTAL_COUNTERS:
                await db.email_campaign_jobs.update_one(
                    {"_id": log["campaign_id"]},
                    {"$inc": {f"{new_status}_count": 1}},
                )
            return True
        return False

    except Exception as e:
        logger.warning(
            "email_reconciliation_error",
            resend_id=resend_id,
            error=str(e),
        )
        return False


async def _reconcile() -> None:
    db = get_fresh_db()
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    window_cutoff = now - timedelta(hours=RECONCILIATION_WINDOW_HOURS)

    query = {
        "status": {"$nin": list(TERMINAL_STATUSES)},
        "resend_email_id": {"$type": "string"},
        "created_at": {"$gte": window_cutoff},
        "updated_at": {"$lt": stale_cutoff},
    }

    cursor = db.email_logs.find(query).limit(200)
    reconciled = 0

    async for log in cursor:
        success = await _reconcile_single_log(db, log)
        if success:
            reconciled += 1

    logger.info(
        "email_reconciliation_complete",
        reconciled=reconciled,
    )
