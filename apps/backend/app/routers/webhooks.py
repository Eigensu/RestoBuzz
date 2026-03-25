import hashlib
import hmac
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException, Query
from app.config import settings
from app.database import get_db
from app.core.logging import get_logger

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
    raise HTTPException(403, "Verification failed")


@router.post("/meta", status_code=200)
async def receive_webhook(request: Request, db=Depends(get_db)):
    # Read body once — reuse for both signature check and JSON parse
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(body, sig):
        logger.warning("webhook_invalid_signature")
        raise HTTPException(403, "Invalid signature")

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

    # Process inline — don't rely on Celery being up for inbound messages
    try:
        await _process_payload(db, payload)
    except Exception as e:
        logger.error("webhook_process_error", error=str(e))
        # Still return 200 so Meta doesn't retry endlessly
        await db.webhook_errors.insert_one(
            {
                "raw_body": body.decode("utf-8", errors="replace"),
                "payload": payload,
                "error": str(e),
                "received_at": datetime.now(timezone.utc),
            }
        )

    # Also dispatch to Celery for status updates (delivery receipts)
    try:
        from app.workers.webhook_task import process_webhook_task

        process_webhook_task.delay(payload)
    except Exception:
        pass  # Celery optional — inline processing already handled messages

    return {"status": "ok"}


STOP_KEYWORDS = {"stop", "unsubscribe", "opt out", "optout", "cancel"}


async def _process_payload(db, payload: dict) -> None:
    """Process inbound messages inline without requiring Celery."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
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
                msg_type = msg.get("type", "unknown")
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
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    location = {
                        "lat": loc.get("latitude"),
                        "lng": loc.get("longitude"),
                        "name": loc.get("name"),
                    }
                elif msg_type == "button":
                    body_text = msg.get("button", {}).get("text", "")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    body_text = (
                        interactive.get("button_reply", {}).get("title")
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

                    # Auto-suppress on STOP keywords
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
