import hashlib
import hmac
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, Query
from app.config import settings
from app.database import get_db
from app.core.logging import get_logger
from app.core.errors import WebhookSignatureError
from app.services.message_types import normalize_message_type
from app.services.meta_api import send_text_message, MetaAPIError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


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


@router.get("/meta")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if (
        hub_mode == "subscribe"
        and hub_verify_token == settings.meta_webhook_verify_token
    ):
        return Response(content=hub_challenge, media_type="text/plain")
    raise WebhookSignatureError("Webhook verification failed")


@router.post("/meta", status_code=200)
async def receive_webhook(request: Request, db=Depends(get_db)):
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(body, sig):
        logger.warning("webhook_invalid_signature")
        raise WebhookSignatureError("Invalid webhook signature")

    try:
        payload = json.loads(body)
    except Exception as e:
        logger.error("webhook_json_parse_error", error=str(e))
        await db.webhook_errors.insert_one(
            {
                "raw_body": body.decode("utf-8", errors="replace"),
                "headers": dict(request.headers),
                "error": str(e),
                "received_at": datetime.now(timezone.utc),
            }
        )
        return {"status": "ok"}

    logger.info("webhook_received", entry_count=len(payload.get("entry", [])))

    try:
        await _process_payload(db, payload)
    except Exception as e:
        logger.error("webhook_process_error", error=str(e))
        await db.webhook_errors.insert_one(
            {
                "raw_body": body.decode("utf-8", errors="replace"),
                "payload": payload,
                "error": str(e),
                "received_at": datetime.now(timezone.utc),
            }
        )

    try:
        from app.workers.webhook_task import process_webhook_task

        process_webhook_task.delay(payload)
    except Exception as e:
        logger.exception(
            "webhook_dispatch_error",
            error=str(e),
            task="process_webhook_task",
        )

    return {"status": "ok"}


STOP_KEYWORDS = {"stop", "unsubscribe", "opt out", "optout", "cancel"}


async def _send_benefits_reply(db, to: str, restaurant_id: str = None, phone_id: str = None) -> None:
    """Send the benefits link as a text reply and persist it to outbound_messages."""
    link = settings.benefits_link
    if not link:
        logger.warning("benefits_link_not_configured", to=to)
        return

    # Use provided phone_id (the recipient_id/bot id) or fallback to primary
    phone_id = phone_id or settings.meta_primary_phone_id
    token = settings.meta_primary_access_token
    if not phone_id or not token:
        logger.error("meta_primary_credentials_missing", to=to)
        return

    try:
        body = f"Here's your link: {link}"
        wa_id = await send_text_message(
            to=to,
            body=body,
            phone_id=phone_id,
            token=token,
        )
        # Persist to database so it shows up in the chat thread
        outbound_doc = {
            "wa_message_id": wa_id,
            "to_phone": to,
            "body": body,
            "status": "sent",
            "sent_at": datetime.now(timezone.utc),
            "restaurant_id": restaurant_id,
            "wa_phone_id": phone_id,
            "sender_name": "System (Auto-Response)",
            "channel": "whatsapp"
        }
        await db.outbound_messages.insert_one(outbound_doc)
        logger.info("benefits_reply_sent", to=to, wa_id=wa_id)
    except Exception as e:
        logger.error("benefits_reply_failed", to=to, error=str(e))


async def _process_payload(db, payload: dict) -> None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            # This is the Meta Phone Number ID that received the message
            recipient_id = str(metadata.get("phone_number_id", "")) if metadata.get("phone_number_id") else None

            # 1. Resolve restaurant_id from recipient_id
            restaurant_id = None
            if recipient_id:
                # Store resolved RID in a local cache for this batch if needed, 
                # but a simple DB fetch is safe.
                rest_doc = await db.restaurants.find_one({"wa_phone_ids": recipient_id})
                if rest_doc:
                    restaurant_id = rest_doc.get("id") or str(rest_doc["_id"])

            messages = value.get("messages", [])
            contacts = {
                c["wa_id"]: c.get("profile", {}).get("name")
                for c in value.get("contacts", [])
            }

            for msg in messages:
                wa_id = msg.get("id")
                if not wa_id:
                    continue

                from_phone = msg.get("from")
                sender_name = contacts.get(from_phone)
                msg_type = normalize_message_type(msg.get("type"))
                body_text = None
                media_url = None
                media_mime = None
                location = None

                if msg_type == "text":
                    body_text = msg.get("text", {}).get("body", "")
                elif msg_type in ("image", "document", "sticker", "audio", "video"):
                    media_obj = msg.get(msg_type, {})
                    media_url = media_obj.get("url") or media_obj.get("link")
                    media_mime = media_obj.get("mime_type")
                    body_text = media_obj.get("caption") or media_obj.get("filename")
                elif msg_type == "button":
                    btn = msg.get("button", {})
                    body_text = btn.get("text", "")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    button_reply = interactive.get("button_reply", {})
                    body_text = (
                        button_reply.get("title")
                        or interactive.get("list_reply", {}).get("title")
                        or ""
                    )

                doc = {
                    "wa_message_id": wa_id,
                    "from_phone": from_phone,
                    "sender_name": sender_name,
                    "message_type": msg_type,
                    "body": body_text,
                    "media_url": media_url,
                    "media_mime_type": media_mime,
                    "location": location,
                    "is_read": False,
                    "received_at": datetime.now(timezone.utc),
                    "raw_payload": msg,
                    "restaurant_id": restaurant_id,  # Mandatory for tenant-scoping
                    "wa_phone_id": recipient_id,
                    # If restaurant_id is None, it effectively quarantines the message 
                    # from all tenant-scoped APIs.
                }

                result = await db.inbound_messages.update_one(
                    {"wa_message_id": wa_id},
                    {"$setOnInsert": doc},
                    upsert=True,
                )

                if result.upserted_id:
                    logger.info(
                        "inbound_message_saved",
                        from_phone=from_phone,
                        type=msg_type,
                        wa_id=wa_id,
                    )

                    # Trigger automated benefits response if button id matches
                    # (Checked after idempotency to prevent duplicate replies)
                    if msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        if interactive.get("button_reply", {}).get("id") == "get_benefits":
                            await _send_benefits_reply(db, from_phone, restaurant_id, recipient_id)
                    elif msg_type == "button":
                        btn = msg.get("button", {})
                        btn_payload = (btn.get("payload") or "").strip().lower()
                        btn_text = (btn.get("text") or "").strip().lower()
                        if btn_payload == "get_benefits" or btn_text == "get the benefits":
                            await _send_benefits_reply(db, from_phone, restaurant_id, recipient_id)

                    if body_text and body_text.strip().lower() in STOP_KEYWORDS:
                        await db.suppression_list.update_one(
                            {"phone": from_phone},
                            {
                                "$setOnInsert": {
                                    "phone": from_phone,
                                    "reason": "opt_out",
                                    "added_at": datetime.now(timezone.utc),
                                }
                            },
                            upsert=True,
                        )
                        logger.info("auto_suppressed", phone=from_phone)

            # Handle status updates (delivered, read, failed)
            statuses = value.get("statuses", [])
            for status in statuses:
                wa_id = status.get("id")
                wa_status = status.get("status")
                if not wa_id or not wa_status:
                    continue

                if wa_status not in {
                    "queued",
                    "sending",
                    "sent",
                    "delivered",
                    "read",
                    "failed",
                    "cancelled",
                }:
                    logger.warning(
                        "webhook_invalid_status", wa_id=wa_id, status=wa_status
                    )
                    continue

                # Update outbound_messages (inbox replies) in real time;
                # campaign-related status handling (message_logs, status_history,
                # counters, etc.) is delegated to the Celery worker.
                result = await db.outbound_messages.update_one(
                    {"wa_message_id": wa_id},
                    {
                        "$set": {
                            "status": wa_status,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                if result.modified_count > 0:
                    logger.info(
                        "outbound_status_updated", wa_id=wa_id, status=wa_status
                    )


# ── Resend Webhooks ───────────────────────────────────────────────────────────

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
    body = await request.body()
    payload_str = body.decode("utf-8")

    # 1. Verify webhook signature
    try:
        from app.services.resend_client import verify_webhook

        event = verify_webhook(
            payload_str,
            {
                "svix-id": request.headers.get("svix-id", ""),
                "svix-timestamp": request.headers.get("svix-timestamp", ""),
                "svix-signature": request.headers.get("svix-signature", ""),
            },
        )
    except Exception as e:
        logger.warning("resend_webhook_invalid_signature", error=str(e))
        raise WebhookSignatureError("Invalid Resend webhook signature")

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
        except Exception:
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
        from app.services.email_suppression import add_email_suppression

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
