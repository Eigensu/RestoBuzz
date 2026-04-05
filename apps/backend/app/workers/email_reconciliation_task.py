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


async def _reconcile() -> None:
    db = get_fresh_db()
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    window_cutoff = now - timedelta(hours=RECONCILIATION_WINDOW_HOURS)

    # Find logs that are stuck in non-terminal statuses and are old enough
    query = {
        "status": {"$nin": list(TERMINAL_STATUSES)},
        "resend_email_id": {"$type": "string"},
        "created_at": {"$gte": window_cutoff},
        "updated_at": {"$lt": stale_cutoff},
    }

    cursor = db.email_logs.find(query).limit(200)
    reconciled = 0
    errors = 0

    async for log in cursor:
        resend_id = log["resend_email_id"]
        try:
            email_data = resend.Emails.get(resend_id)
            if not isinstance(email_data, dict):
                continue

            # Map Resend's last_event to our status
            last_event = email_data.get("last_event")
            if not last_event:
                continue

            # Resend returns events like "email.delivered" → extract "delivered"
            new_status = last_event.replace("email.", "")
            if new_status not in (
                "sent",
                "delivered",
                "bounced",
                "failed",
                "opened",
                "clicked",
                "complained",
            ):
                continue

            # Only update if the status has actually progressed
            current_status = log["status"]
            status_order = [
                "queued",
                "sending",
                "sent",
                "delivered",
                "opened",
                "clicked",
            ]
            if (
                new_status in status_order
                and current_status in status_order
                and status_order.index(new_status)
                <= status_order.index(current_status)
            ):
                continue

            await db.email_logs.update_one(
                {"_id": log["_id"]},
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

            # Update campaign counters
            counter_field = f"{new_status}_count"
            if counter_field in (
                "delivered_count",
                "opened_count",
                "clicked_count",
                "bounced_count",
                "failed_count",
                "complained_count",
            ):
                await db.email_campaign_jobs.update_one(
                    {"_id": log["campaign_id"]},
                    {"$inc": {counter_field: 1}},
                )

            reconciled += 1

        except Exception as e:
            logger.warning(
                "email_reconciliation_error",
                resend_id=resend_id,
                error=str(e),
            )
            errors += 1

    logger.info(
        "email_reconciliation_complete",
        reconciled=reconciled,
        errors=errors,
    )
