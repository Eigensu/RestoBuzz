import asyncio
from datetime import datetime, timezone, timedelta
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.services.deduplication import is_duplicate, mark_seen
from app.services.suppression import add_suppression
from app.services.message_types import normalize_message_type
from app.utils.phone import normalize_phone

logger = get_logger(__name__)

STOP_KEYWORDS = {"stop", "unsubscribe", "opt out", "optout", "cancel"}


@celery_app.task(name="app.workers.webhook_task.process_webhook_task")
def process_webhook_task(payload: dict) -> None:
    asyncio.run(_process(payload))


async def _process(payload: dict) -> None:
    redis = _get_async_redis()
    db = get_fresh_db()
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                await _handle_statuses(db, redis, value.get("statuses", []))
                await _handle_messages(db, redis, value)
    finally:
        await redis.aclose()


async def _handle_statuses(db, redis, statuses: list) -> None:
    for s in statuses:
        wa_id = s.get("id")
        status = s.get("status")
        if not wa_id or not status:
            continue

        dedup_key = f"status:{wa_id}:{status}"
        if await is_duplicate(redis, dedup_key):
            continue
        await mark_seen(redis, dedup_key)

        now = datetime.now(timezone.utc)
        result = await db.message_logs.find_one_and_update(
            {"wa_message_id": wa_id},
            {
                "$set": {"status": status, "updated_at": now},
                "$push": {
                    "status_history": {"status": status, "timestamp": now, "meta": s}
                },
            },
            return_document=True,
        )
        if result:
            await _store_error_details(db, wa_id, status, s)
            await _increment_campaign_counter(db, result, status)
            await _record_billing_event(db, wa_id, s, result, now)


async def _record_billing_event(
    db, wa_id: str, s: dict, message_log: dict, now: datetime
) -> None:
    """Record a billable conversation event from the webhook status payload.

    Meta only sends billable=true/false + category — no price.
    Price calculation (₹0.95/conversation) happens in reports.py at query time.
    """
    pricing = s.get("pricing")
    if not pricing or not pricing.get("billable"):
        return

    restaurant_id = message_log.get("restaurant_id")
    job_id = message_log.get("job_id")
    
    if not restaurant_id and job_id:
        # Resolve restaurant_id from campaign_jobs
        from bson.objectid import ObjectId
        try:
            job_oid = ObjectId(job_id) if isinstance(job_id, str) else job_id
            job = await db.campaign_jobs.find_one({"_id": job_oid})
            if job:
                restaurant_id = job.get("restaurant_id")
        except Exception:
            pass

    await db.meta_billing_events.update_one(
        {"wa_message_id": wa_id},
        {
            "$setOnInsert": {
                "wa_message_id": wa_id,
                "restaurant_id": restaurant_id,
                "job_id": job_id,
                "category": (pricing.get("category") or "").lower(),
                "pricing_model": pricing.get("pricing_model", "CBP"),
                "recorded_at": now,
            }
        },
        upsert=True,
    )


async def _store_error_details(db, wa_id: str, status: str, s: dict) -> None:
    if status != "failed":
        return
    errors = s.get("errors", [])
    if not errors:
        return
    err = errors[0]
    await db.message_logs.update_one(
        {"wa_message_id": wa_id},
        {
            "$set": {
                "error_code": str(err.get("code", "")),
                "error_message": err.get("title") or err.get("message", "Unknown"),
            }
        },
    )


async def _increment_campaign_counter(db, result: dict, status: str) -> None:
    field = f"{status}_count"
    if field in ("delivered_count", "read_count", "failed_count"):
        await db.campaign_jobs.update_one(
            {"_id": result["job_id"]},
            {"$inc": {field: 1}},
        )


async def _parse_message_content(
    msg: dict, msg_type: str
) -> tuple[str | None, str | None, str | None, dict | None]:
    """Extract body, media_url, media_mime, and location from a message dict."""
    body = None
    media_url = None
    media_mime = None
    location = None

    if msg_type == "text":
        body = msg.get("text", {}).get("body", "")
    elif msg_type in ("image", "document", "sticker"):
        media_obj = msg.get(msg_type, {})
        media_url = media_obj.get("url") or media_obj.get("link")
        media_mime = media_obj.get("mime_type")
        body = media_obj.get("caption") or media_obj.get("filename")
    elif msg_type == "location":
        loc = msg.get("location", {})
        location = {
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
            "name": loc.get("name"),
        }

    return body, media_url, media_mime, location


async def _handle_messages(db, redis, value: dict) -> None:
    messages = value.get("messages", [])
    contacts = {
        c["wa_id"]: c.get("profile", {}).get("name") for c in value.get("contacts", [])
    }

    for msg in messages:
        wa_id = msg.get("id")
        if not wa_id:
            continue
        if await is_duplicate(redis, wa_id):
            continue
        await mark_seen(redis, wa_id)

        from_phone = msg.get("from")
        sender_name = contacts.get(from_phone)
        msg_type = normalize_message_type(msg.get("type"))
        body, media_url, media_mime, location = await _parse_message_content(
            msg, msg_type
        )

        doc = {
            "wa_message_id": wa_id,
            "from_phone": from_phone,
            "sender_name": sender_name,
            "message_type": msg_type,
            "body": body,
            "media_url": media_url,
            "media_mime_type": media_mime,
            "location": location,
            "is_read": False,
            "received_at": datetime.now(timezone.utc),
            "raw_payload": msg,
        }
        await db.inbound_messages.update_one(
            {"wa_message_id": wa_id},
            {"$setOnInsert": doc},
            upsert=True,
        )

        context = msg.get("context", {})
        replied_to_wa_id = context.get("id")
        orig_msg = await _find_and_mark_replied(
            db, replied_to_wa_id, from_phone, doc["received_at"]
        )

        if orig_msg and orig_msg.get("job_id"):
            await db.campaign_jobs.update_one(
                {"_id": orig_msg["job_id"]}, {"$inc": {"replies_count": 1}}
            )

        # STOP keyword → suppression
        if body and body.strip().lower() in STOP_KEYWORDS:
            await add_suppression(db, from_phone, reason="opt_out")
            logger.info("auto_suppressed", phone=from_phone)


async def _find_and_mark_replied(
    db, replied_to_wa_id: str | None, from_phone: str, received_at: datetime
) -> dict | None:
    """Find the original outbound message this inbound is replying to and mark it replied."""
    if replied_to_wa_id:
        return await db.message_logs.find_one_and_update(
            {"wa_message_id": replied_to_wa_id, "replied": {"$ne": True}},
            {"$set": {"replied": True}},
        )

    forty_eight_hours_ago = received_at - timedelta(hours=48)
    normalized = normalize_phone(from_phone)
    phone_variants = list({p for p in [normalized, from_phone, f"+{from_phone}"] if p})
    return await db.message_logs.find_one_and_update(
        {
            "recipient_phone": {"$in": phone_variants},
            "created_at": {"$gte": forty_eight_hours_ago, "$lt": received_at},
            "replied": {"$ne": True},
        },
        {"$set": {"replied": True}},
        sort=[("created_at", -1)],
    )


def _get_async_redis():
    from redis.asyncio import from_url
    from app.config import settings

    return from_url(settings.redis_url, decode_responses=True)
