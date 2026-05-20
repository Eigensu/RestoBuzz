"""Meta & Resend webhook receivers.

Meta handler: thin receiver — verify HMAC, parse JSON, enqueue Celery task,
return 200. All processing logic lives in app/workers/webhook_task.py.

Resend handler: unchanged — already well-structured and low-volume.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Query, BackgroundTasks
from starlette.requests import ClientDisconnect
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.database import get_db
from app.core.logging import get_logger
from app.core.errors import WebhookSignatureError
from app.services.alert_service import alert_service
from app.services.email_suppression import add_email_suppression
from app.workers.webhook_task import process_webhook_task

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


# ── Signature verification ────────────────────────────────────────────────────


def _verify_signature(body: bytes, signature: str) -> bool:
    if not settings.meta_webhook_secret:
        return True  # Skip if app secret not configured
    expected = (
        "sha256="
        + hmac.new(
            settings.meta_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


# ── Meta webhook — GET (verification challenge) ───────────────────────────────


@router.get("/meta")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """Handle the Meta webhook verification challenge."""
    if (
        hub_mode == "subscribe"
        and hub_verify_token == settings.meta_webhook_verify_token
    ):
        return Response(content=hub_challenge, media_type="text/plain")
    raise WebhookSignatureError("Webhook verification failed")


# ── Meta webhook — POST (event receiver) ─────────────────────────────────────


@router.post("/meta", status_code=200)
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """Receive and process incoming Meta webhooks."""
    try:
        body = await request.body()
    except ClientDisconnect:
        logger.info("webhook_client_disconnect")
        return {"status": "client_disconnect"}
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(body, sig):
        logger.warning("webhook_invalid_signature")
        raise WebhookSignatureError("Invalid webhook signature")

    try:
        payload = json.loads(body)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("webhook_json_parse_error", error=str(e))
        # Persist parse errors for debugging — still return 200 so Meta doesn't retry.
        background_tasks.add_task(
            _store_parse_error, db, body, dict(request.headers), str(e)
        )
        return {"status": "ok"}

    logger.info("webhook_received", entry_count=len(payload.get("entry", [])))

    # Template status updates are low-volume and fire email alerts.
    # They don't need dedup and are not on the hot path — handle inline.
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("event") == "message_template_status_update":
                background_tasks.add_task(
                    _handle_template_status, db, value, background_tasks
                )

    # Enqueue everything else to the Celery webhooks worker.
    # If Redis is unavailable, apply_async raises — fall back to BackgroundTasks
    # so the data is never lost and Meta still receives a 200. Processing will be
    # slower and without dedup, but correct. Alert on-call if this fires.
    from fastapi.concurrency import run_in_threadpool
    try:
        await run_in_threadpool(
            process_webhook_task.apply_async, args=[payload], queue="webhooks"
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(
            "webhook_enqueue_failed_falling_back_to_background",
            error=str(e),
        )
        background_tasks.add_task(_process_webhook_sync, db, payload)

    return {"status": "ok"}


# ── Fallback processor (Redis-down path) ─────────────────────────────────────


async def _process_webhook_sync(db, payload: dict) -> None:
    """Emergency fallback: process the webhook inline when Celery/Redis is down.

    Mirrors the Celery task logic but runs inside a FastAPI BackgroundTask.
    No deduplication is applied (Redis is unavailable). This path should never
    fire in normal operation — the log event is the alert signal.
    """
    try:
        # Reuse the same async core from webhook_task, but pass the FastAPI db
        # instead of get_fresh_db() since we're already in an async context.
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("event") == "message_template_status_update":
                    continue
                from app.workers.webhook_task import (  # pylint: disable=import-outside-toplevel
                    _resolve_restaurant,
                    _handle_statuses,
                    _handle_messages,
                )

                restaurant_id, phone_number_id = await _resolve_restaurant(db, value)
                # Pass None for redis — _handle_statuses / _handle_messages guard
                # against None redis by skipping dedup (no-op is safe here).
                await _handle_statuses(
                    db, None, value.get("statuses", []), restaurant_id
                )
                await _handle_messages(db, None, value, restaurant_id, phone_number_id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("webhook_sync_fallback_failed", error=str(e))


# ── Template status handler (inline, low-volume) ──────────────────────────────


async def _handle_template_status(
    db, value: dict, background_tasks: BackgroundTasks
) -> None:
    template_name = value.get("message_template_name")
    actual_status = value.get("status", "").upper()

    cursor = db.restaurants.find(
        {}, {"_id": 1, "name": 1, "email": 1, "notification_emails": 1}
    )
    async for rest in cursor:
        if actual_status == "APPROVED":
            background_tasks.add_task(
                alert_service.send_template_approved_alert, db, rest, template_name
            )
        elif actual_status == "REJECTED":
            rejection_reason = value.get("reason", "No reason provided.")
            background_tasks.add_task(
                alert_service.send_template_rejected_alert,
                db,
                rest,
                template_name,
                rejection_reason,
            )


# ── Parse error persistence ───────────────────────────────────────────────────


async def _store_parse_error(db, body: bytes, headers: dict, error: str) -> None:
    await db.webhook_errors.insert_one(
        {
            "raw_body": body.decode("utf-8", errors="replace"),
            "headers": headers,
            "error": error,
            "received_at": datetime.now(timezone.utc),
        }
    )


# ── Resend Webhooks (unchanged) ───────────────────────────────────────────────

# Map Resend event types to our internal status names
_RESEND_EVENT_MAP = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.opened": "opened",
    "email.clicked": "clicked",
    "email.bounced": "bounced",
    "email.failed": "failed",
    "email.complained": "complained",
    "email.delivery_delayed": None,  # logged but no status change
    "email.suppressed": "suppressed",
}

# Map event types to the counter fields on email_campaign_jobs
_RESEND_COUNTER_MAP = {
    "delivered": "delivered_count",
    "opened": "opened_count",
    "clicked": "clicked_count",
    "bounced": "bounced_count",
    "failed": "failed_count",
    "complained": "complained_count",
}


@router.post("/resend", status_code=200)
async def receive_resend_webhook(request: Request, db=Depends(get_db)):
    """Handle Resend webhook events with svix signature verification and idempotency."""
    try:
        body = await request.body()
    except ClientDisconnect:
        logger.info("resend_webhook_client_disconnect")
        return {"status": "client_disconnect"}
    payload_str = body.decode("utf-8")

    # 1. Verify webhook signature
    try:
        from app.services.resend_client import verify_webhook as verify_resend_webhook  # pylint: disable=import-outside-toplevel

        event = verify_resend_webhook(
            payload_str,
            {
                "svix-id": request.headers.get("svix-id", ""),
                "svix-timestamp": request.headers.get("svix-timestamp", ""),
                "svix-signature": request.headers.get("svix-signature", ""),
            },
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("resend_webhook_invalid_signature", error=str(e))
        raise WebhookSignatureError("Invalid Resend webhook signature") from e

    # 2. Idempotency: deduplicate by svix-id
    svix_id = request.headers.get("svix-id", "")
    if svix_id:
        try:
            await db.resend_webhook_events.insert_one(
                {
                    "svix_id": svix_id,
                    "received_at": datetime.now(timezone.utc),
                    "event_type": event.get("type"),
                }
            )
        except Exception:  # pylint: disable=broad-exception-caught
            # Duplicate key → already processed
            logger.info("resend_webhook_duplicate", svix_id=svix_id)
            return {"status": "ok"}

    event_type = event.get("type", "")
    data = event.get("data", {})
    email_id = data.get("email_id")
    new_status = _RESEND_EVENT_MAP.get(event_type)

    logger.info(
        "resend_webhook_received",
        type=event_type,
        email_id=email_id,
    )

    if not email_id or new_status is None:
        return {"status": "ok"}

    await _process_resend_status_update(
        db, email_id, new_status, event_type, svix_id, data
    )
    return {"status": "ok"}


async def _process_resend_status_update(
    db, email_id, new_status, event_type, svix_id, data
):
    now = datetime.now(timezone.utc)
    status_order = ["queued", "sending", "sent", "delivered", "opened", "clicked"]
    terminal_statuses = {"bounced", "failed", "complained", "suppressed"}

    status_query = {
        "resend_email_id": email_id,
        "status": {"$nin": list(terminal_statuses)},
    }

    if new_status in status_order:
        status_query["status"]["$in"] = status_order[: status_order.index(new_status)]

    result = await db.email_logs.find_one_and_update(
        status_query,
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {
                "status_history": {
                    "status": new_status,
                    "timestamp": now,
                    "meta": {"event_type": event_type, "svix_id": svix_id},
                }
            },
        },
        return_document=True,
    )

    if result:
        await _update_campaign_counters(db, result, new_status)
        await _handle_error_reporting(db, result, new_status, data)
        await _handle_auto_suppression(db, result, new_status, data)


async def _update_campaign_counters(db, log, new_status):
    counter_field = _RESEND_COUNTER_MAP.get(new_status)
    if counter_field:
        await db.email_campaign_jobs.update_one(
            {"_id": log["campaign_id"]},
            {"$inc": {counter_field: 1}},
        )


async def _handle_error_reporting(db, log, new_status, data):
    if new_status in ("bounced", "failed"):
        bounce_info = data.get("bounce", {})
        error_reason = (
            bounce_info.get("message")
            or data.get("error", {}).get("message")
            or f"Email {new_status}"
        )
        await db.email_logs.update_one(
            {"_id": log["_id"]},
            {"$set": {"error_reason": error_reason}},
        )


async def _handle_auto_suppression(db, log, new_status, data):
    if new_status in ("bounced", "complained"):
        bounce_type = data.get("bounce", {}).get("type", "")
        reason = (
            "complaint"
            if new_status == "complained"
            else ("soft_bounce" if bounce_type == "Transient" else "hard_bounce")
        )
        await add_email_suppression(db, log["recipient_email"], reason=reason)
        logger.info(
            "email_auto_suppressed",
            email=log["recipient_email"],
            reason=reason,
        )
