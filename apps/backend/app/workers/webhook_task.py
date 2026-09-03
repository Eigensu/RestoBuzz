"""Authoritative Celery task for processing incoming WhatsApp webhook payloads.

All Meta webhook processing logic lives here. The FastAPI router
(routers/webhooks.py) is a thin receiver that enqueues this task and returns
200 immediately. This task handles:

  - Status updates  → message_logs, outbound_messages, campaign_jobs counters,
                       billing events, error details
  - Inbound messages → inbound_messages upsert, reply tracking, STOP suppression,
                       benefits auto-reply, unread threshold alert
  - Dead letter      → on_failure persists raw payload to failed_webhooks
"""

import asyncio
from datetime import datetime, timezone, timedelta

from bson.objectid import ObjectId
from redis.asyncio import from_url as redis_from_url

from app.config import settings
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.services.deduplication import is_duplicate, mark_seen
from app.services import member_stats_service
from app.services.suppression import add_suppression
from app.services.message_types import normalize_message_type
from app.services.meta_api import send_text_message
from app.utils.phone import normalize_phone

logger = get_logger(__name__)

STOP_KEYWORDS = {"stop", "unsubscribe", "opt out", "optout", "cancel"}

# Reused Mongo operator literal — named to avoid duplicated-literal warnings.
_SET_ON_INSERT = "$setOnInsert"

# Positive-intent replies that flag a campaign respondent as an "interested"
# member. Matched case-insensitively against the trimmed message body.
INTERESTED_KEYWORDS = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "interested",
    "sure",
    "ok",
    "okay",
    "👍",
}


# ── Celery task ───────────────────────────────────────────────────────────────


from celery import Task


# ── Celery task ───────────────────────────────────────────────────────────────


class _WebhookTask(Task):
    """Custom Task base that persists failed payloads to failed_webhooks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Dead letter handler — persists the raw payload to failed_webhooks so it
        can be replayed after a bug fix. Called by Celery after max_retries is
        exhausted.
        """
        raw_payload = args[0] if args else {}
        db = None
        loop = None
        try:
            db = get_fresh_db()
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                db.failed_webhooks.insert_one(
                    {
                        "task_id": task_id,
                        "payload": raw_payload,
                        "error": str(exc),
                        "traceback": str(einfo),
                        "failed_at": datetime.now(timezone.utc),
                    }
                )
            )
            logger.error(
                "webhook_dead_lettered",
                task_id=task_id,
                error=str(exc),
            )
        except Exception as persist_exc:
            logger.error(
                "webhook_dead_letter_persist_failed",
                task_id=task_id,
                original_error=str(exc),
                persist_error=str(persist_exc),
            )
        finally:
            # Both were leaked when insert_one raised: loop.close() sat on the
            # success path only, and the client was never closed at all.
            if loop is not None:
                loop.close()
            if db is not None:
                db.client.close()


@celery_app.task(
    bind=True,
    base=_WebhookTask,
    name="app.workers.webhook_task.process_webhook_task",
    max_retries=3,
    default_retry_delay=30,
)
def process_webhook_task(self, payload: dict) -> None:
    """Entry point for the Celery webhook processing task."""
    try:
        asyncio.run(_process(payload))
    except Exception as exc:
        logger.error(
            "webhook_task_failed",
            task_id=self.request.id,
            error=str(exc),
            retries=self.request.retries,
        )
        raise self.retry(exc=exc)


# ── Core async processor ──────────────────────────────────────────────────────


async def _process(payload: dict) -> None:
    redis = _get_async_redis()
    db = get_fresh_db()
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Skip template status updates — handled inline by the router.
                if value.get("event") == "message_template_status_update":
                    continue

                restaurant_id, phone_number_id = await _resolve_restaurant(db, value)

                await _handle_statuses(
                    db, redis, value.get("statuses", []), restaurant_id
                )
                await _handle_messages(db, redis, value, restaurant_id, phone_number_id)
    finally:
        try:
            await redis.aclose()
        finally:
            db.client.close()


# ── Restaurant resolution ─────────────────────────────────────────────────────


async def _resolve_restaurant(db, value: dict) -> tuple[str | None, str | None]:
    """Return (restaurant_id, phone_number_id) from the change value's metadata."""
    metadata = value.get("metadata", {})
    phone_number_id = str(metadata.get("phone_number_id", "")) or None
    if not phone_number_id:
        return None, None
    rest = await db.restaurants.find_one({"wa_phone_ids": phone_number_id})
    if not rest:
        return None, phone_number_id
    return rest.get("id") or str(rest["_id"]), phone_number_id


# ── Status processing ─────────────────────────────────────────────────────────


async def _handle_statuses(
    db, redis, statuses: list, restaurant_id: str | None
) -> None:
    for s in statuses:
        wa_id = s.get("id")
        status = s.get("status")
        if not wa_id or not status:
            continue

        # Dedup key includes restaurant_id + wa_id + status so that each status
        # transition (sent → delivered → read) is independently deduplicated.
        # Without status in the key, the 'delivered' event would block 'read'.
        rid = restaurant_id or "global"
        dedup_key = f"{rid}:{wa_id}:{status}"
        if await is_duplicate(redis, dedup_key):
            logger.debug("webhook_status_duplicate_skipped", wa_id=wa_id, status=status)
            continue
        await mark_seen(redis, dedup_key)

        now = datetime.now(timezone.utc)

        # Update outbound_messages (auto-reply / system messages)
        await db.outbound_messages.update_one(
            {"wa_message_id": wa_id},
            {"$set": {"status": status, "updated_at": now}},
        )

        # Fetch the BEFORE image so we know the message's prior status — needed to
        # keep campaign counters consistent when a status regresses (e.g. an
        # accepted message that Meta later drops as 'failed').
        prev = await db.message_logs.find_one_and_update(
            {"wa_message_id": wa_id},
            {
                "$set": {"status": status, "updated_at": now},
                "$push": {
                    "status_history": {"status": status, "timestamp": now, "meta": s}
                },
            },
            return_document=False,
        )

        if prev:
            logger.info("campaign_message_status_updated", wa_id=wa_id, status=status)
            await _store_error_details(db, wa_id, status, s)
            await _apply_status_counters(db, prev["job_id"], prev.get("status"), status)
            # Lifetime per-member received/read rollup. Driven by the BEFORE
            # image so a redelivered 'delivered' webhook can't double-count.
            # restaurant_id isn't denormalized onto every message_log (older
            # rows predate it) — fall back to the webhook's own resolution.
            await member_stats_service.record_status_change(
                db,
                prev.get("restaurant_id") or restaurant_id,
                prev.get("recipient_phone"),
                prev.get("status"),
                status,
                now,
            )
            await _record_billing_event(db, wa_id, s, prev, now)


async def _apply_status_counters(
    db, job_id, prev_status: str | None, new_status: str
) -> None:
    """Move campaign_jobs counters in step with a message's status transition.

    delivered/read bump their own funnel counters. Crucially, a 'failed' delivery
    webhook for a message we already counted as sent must also back out that
    sent_count increment (made in send_task when Meta accepted the message) —
    otherwise a message Meta accepts and then drops (e.g. error 131049) is counted
    as BOTH sent and failed, inflating sent_count above the true success count.
    """
    inc: dict[str, int] = {}
    if new_status == "delivered":
        inc["delivered_count"] = 1
    elif new_status == "read":
        inc["read_count"] = 1
    elif new_status == "failed":
        inc["failed_count"] = 1
        if prev_status in ("sent", "delivered", "read"):
            inc["sent_count"] = -1
    if inc:
        await db.campaign_jobs.update_one({"_id": job_id}, {"$inc": inc})


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


async def _record_billing_event(
    db, wa_id: str, s: dict, message_log: dict, now: datetime
) -> None:
    """Record a billable conversation event from the webhook status payload.

    Captures the pricing category (marketing / utility / authentication) which
    is required for billing reconciliation against Meta's invoices.
    """
    pricing = s.get("pricing")
    if not pricing or not pricing.get("billable"):
        return

    restaurant_id = message_log.get("restaurant_id")
    job_id = message_log.get("job_id")

    if not restaurant_id and job_id:
        try:
            job_oid = ObjectId(job_id) if isinstance(job_id, str) else job_id
            job = await db.campaign_jobs.find_one({"_id": job_oid})
            if job:
                restaurant_id = job.get("restaurant_id")
        except (ValueError, TypeError) as exc:
            logger.error(
                "billing_restaurant_id_lookup_failed",
                job_id=str(job_id),
                error=str(exc),
            )

    await db.meta_billing_events.update_one(
        {"wa_message_id": wa_id},
        {
            _SET_ON_INSERT: {
                "wa_message_id": wa_id,
                "restaurant_id": restaurant_id,
                "job_id": job_id,
                "billable": True,
                "category": (pricing.get("category") or "").lower(),
                "pricing_model": pricing.get("pricing_model") or "CBP",
                "recorded_at": now,
            }
        },
        upsert=True,
    )


# ── Inbound message processing ────────────────────────────────────────────────


async def _handle_messages(
    db,
    redis,
    value: dict,
    restaurant_id: str | None,
    phone_number_id: str | None,
) -> None:
    messages = value.get("messages", [])
    contacts = {
        c["wa_id"]: c.get("profile", {}).get("name") for c in value.get("contacts", [])
    }

    messages_saved = 0

    for msg in messages:
        saved = await _process_inbound_message(
            db, redis, msg, contacts, restaurant_id, phone_number_id
        )
        if saved:
            messages_saved += 1

    # Unread threshold alert — fire once per change block, not per message
    if restaurant_id and messages_saved > 0:
        from app.services.alert_service import alert_service

        await alert_service.check_unread_threshold_alert(db, restaurant_id)


async def _process_inbound_message(
    db,
    redis,
    msg: dict,
    contacts: dict,
    restaurant_id: str | None,
    phone_number_id: str | None,
) -> bool:
    """Process a single inbound message. Returns True if newly saved, False otherwise."""
    wa_id = msg.get("id")
    if not wa_id:
        return False

    if await is_duplicate(redis, wa_id):
        logger.debug("webhook_inbound_duplicate_skipped", wa_id=wa_id)
        return False
    await mark_seen(redis, wa_id)

    from_phone = msg.get("from")
    sender_name = contacts.get(from_phone)
    msg_type = normalize_message_type(msg.get("type"))
    body, media_url, media_mime, media_id, location = _parse_message_content(
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
        "media_id": media_id,  # required for later Media API fetch
        "location": location,
        "is_read": False,
        "received_at": datetime.now(timezone.utc),
        "raw_payload": msg,
        "restaurant_id": restaurant_id,
        "wa_phone_id": phone_number_id,
    }

    result = await db.inbound_messages.update_one(
        {"wa_message_id": wa_id},
        {_SET_ON_INSERT: doc},
        upsert=True,
    )

    if not result.upserted_id:
        return False

    logger.info(
        "inbound_message_saved",
        from_phone=from_phone,
        type=msg_type,
        wa_id=wa_id,
        restaurant_id=restaurant_id,
    )

    orig_msg = await _handle_reply_tracking(db, msg, from_phone, doc["received_at"])

    if body and body.strip().lower() in STOP_KEYWORDS:
        await add_suppression(db, from_phone, reason="opt_out")
        logger.info("auto_suppressed", phone=from_phone)
    else:
        # A positive reply to a campaign message flags the respondent as an
        # "interested" member (skipped above for STOP keywords on purpose).
        await _handle_interested_reply(db, orig_msg, body, from_phone, sender_name)

    await _handle_auto_replies(
        db, msg, msg_type, from_phone, restaurant_id, phone_number_id
    )

    return True


async def _handle_reply_tracking(
    db, msg: dict, from_phone: str, received_at: datetime
) -> dict | None:
    """Mark the original outbound message as replied and increment replies_count.

    Returns the matched outbound message_log (or None) so callers can use the
    campaign + recipient context — e.g. flagging the sender as interested.
    """
    replied_to_wa_id = msg.get("context", {}).get("id")
    orig_msg = await _find_and_mark_replied(
        db, replied_to_wa_id, from_phone, received_at
    )
    if orig_msg and orig_msg.get("job_id"):
        await db.campaign_jobs.update_one(
            {"_id": orig_msg["job_id"]},
            {"$inc": {"replies_count": 1}},
        )
    return orig_msg


async def _resolve_interested_context(
    db, orig_msg: dict
) -> tuple[str | None, str | None, object]:
    """Resolve (restaurant_id, campaign_name, job_id) for an interested reply.

    restaurant_id isn't always denormalized onto message_logs — fall back to the
    campaign job, which always carries it. campaign_name likewise falls back to
    the job's name when the message log doesn't have it.
    """
    restaurant_id = orig_msg.get("restaurant_id")
    job_id = orig_msg.get("job_id")
    campaign_name = orig_msg.get("campaign_name")

    if not restaurant_id and job_id:
        job = await db.campaign_jobs.find_one(
            {"_id": job_id}, {"restaurant_id": 1, "name": 1}
        )
        restaurant_id = (job or {}).get("restaurant_id")
        campaign_name = (job or {}).get("name")
    elif not campaign_name and job_id:
        job = await db.campaign_jobs.find_one({"_id": job_id}, {"name": 1})
        campaign_name = (job or {}).get("name")

    return restaurant_id, campaign_name, job_id


async def _handle_interested_reply(
    db,
    orig_msg: dict | None,
    body: str | None,
    from_phone: str,
    sender_name: str | None,
) -> None:
    """Upsert the campaign respondent as an 'interested' member.

    Only fires when the inbound message was matched to an outbound campaign
    message (orig_msg) AND the body is a positive-intent keyword. Existing
    members are tagged 'interested' (keeping their original type); brand-new
    respondents are created as fresh member docs.
    """
    if not orig_msg or not body:
        return
    if body.strip().lower() not in INTERESTED_KEYWORDS:
        return

    restaurant_id, campaign_name, job_id = await _resolve_interested_context(
        db, orig_msg
    )

    if not restaurant_id:
        logger.warning("interested_reply_no_restaurant", from_phone=from_phone)
        return

    phone = (
        orig_msg.get("recipient_phone")
        or normalize_phone(from_phone)
        or from_phone
    )
    name = orig_msg.get("recipient_name") or sender_name or "Unknown"
    now = datetime.now(timezone.utc)

    await db.members.update_one(
        {"restaurant_id": restaurant_id, "phone": phone},
        {
            "$addToSet": {"tags": "interested"},
            "$set": {
                "interested_at": now,
                "interested_campaign_id": job_id,
                "interested_campaign_name": campaign_name,
                "interested_reply_text": body.strip(),
            },
            _SET_ON_INSERT: {
                "restaurant_id": restaurant_id,
                "type": "interested",
                "name": name,
                "phone": phone,
                "email": None,
                "card_uid": None,
                "ecard_code": None,
                "notes": None,
                "visit_count": 0,
                "last_visit": None,
                "is_active": True,
                "joined_at": now,
                "source": "campaign_reply",
            },
        },
        upsert=True,
    )
    logger.info(
        "interested_member_captured",
        restaurant_id=restaurant_id,
        phone=phone,
        campaign_id=str(job_id) if job_id else None,
    )


def _parse_message_content(
    msg: dict, msg_type: str
) -> tuple[str | None, str | None, str | None, str | None, dict | None]:
    """Extract (body, media_url, media_mime, media_id, location) from a message dict.

    media_id is the WhatsApp media object ID — required to fetch the actual
    media URL later via the Media API. Without it the media is permanently
    inaccessible after the webhook is processed.
    """
    body = None
    media_url = None
    media_mime = None
    media_id = None
    location = None

    if msg_type == "text":
        body = msg.get("text", {}).get("body", "")

    elif msg_type in ("image", "video", "audio", "document", "sticker"):
        media_obj = msg.get(msg_type, {})
        media_id = media_obj.get("id")  # WhatsApp media object ID
        media_url = media_obj.get("url") or media_obj.get("link")
        media_mime = media_obj.get("mime_type")
        body = media_obj.get("caption") or media_obj.get("filename")

    elif msg_type == "button":
        body = msg.get("button", {}).get("text", "")

    elif msg_type == "interactive":
        interactive = msg.get("interactive", {})
        button_reply = interactive.get("button_reply", {})
        body = (
            button_reply.get("title")
            or interactive.get("list_reply", {}).get("title")
            or ""
        )

    elif msg_type == "location":
        loc = msg.get("location", {})
        location = {
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
            "name": loc.get("name"),
        }

    return body, media_url, media_mime, media_id, location


async def _handle_auto_replies(
    db,
    msg: dict,
    msg_type: str,
    from_phone: str,
    restaurant_id: str | None,
    phone_number_id: str | None,
) -> None:
    """Dispatch benefits auto-reply if the message triggers it."""
    is_benefits = False

    if msg_type == "interactive":
        if (
            msg.get("interactive", {}).get("button_reply", {}).get("id")
            == "get_benefits"
        ):
            is_benefits = True
    elif msg_type == "button":
        btn_text = (msg.get("button", {}).get("text") or "").strip().lower()
        btn_payload = (msg.get("button", {}).get("payload") or "").strip().lower()
        if btn_payload == "get_benefits" or btn_text == "get the benefits":
            is_benefits = True

    if is_benefits:
        await _send_benefits_reply(db, from_phone, restaurant_id, phone_number_id)


async def _send_benefits_reply(
    db,
    to: str,
    restaurant_id: str | None,
    phone_id: str | None,
) -> None:
    """Send the benefits link as a text reply and persist it to outbound_messages.

    Running inside a Celery task means this Meta API call no longer blocks the
    HTTP response cycle.
    """
    link = settings.benefits_link
    if not link:
        logger.warning("benefits_link_not_configured", to=to)
        return

    # Prefer the restaurant's own WABA credentials when available.
    # Fall back to the global primary phone if not configured.
    resolved_phone_id = phone_id or settings.meta_primary_phone_id
    resolved_token = settings.meta_primary_access_token

    if restaurant_id:
        rest_doc = await db.restaurants.find_one(
            {"id": restaurant_id}, {"wa_phones": 1}
        )
        wa_phones = (rest_doc or {}).get("wa_phones", [])
        if wa_phones:
            primary = wa_phones[0]
            rp = primary.get("phone_id") or ""
            env_key = primary.get("access_token_env_key") or ""
            rt = settings.resolve_waba_token(env_key) if env_key else ""
            if not rp or not rt:
                logger.error("meta_restaurant_credentials_resolution_failed", restaurant_id=restaurant_id)
                return
            resolved_phone_id = rp
            resolved_token = rt

    if not resolved_phone_id or not resolved_token:
        logger.error("meta_primary_credentials_missing", to=to)
        return

    try:
        body = f"Here's your link: {link}"
        wa_id = await send_text_message(
            to=to,
            body=body,
            phone_id=resolved_phone_id,
            token=resolved_token,
        )
        await db.outbound_messages.insert_one(
            {
                "wa_message_id": wa_id,
                "to_phone": to,
                "body": body,
                "status": "sent",
                "sent_at": datetime.now(timezone.utc),
                "restaurant_id": restaurant_id,
                "wa_phone_id": resolved_phone_id,
                "sender_name": "System (Auto-Response)",
                "channel": "whatsapp",
            }
        )
        logger.info("benefits_reply_sent", to=to, wa_id=wa_id)
    except Exception as e:
        logger.error("benefits_reply_failed", to=to, error=str(e))


async def _find_and_mark_replied(
    db,
    replied_to_wa_id: str | None,
    from_phone: str,
    received_at: datetime,
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
    # Match the recipient's most recent SENT campaign message within 48h of its
    # actual send time. Keying off sent_at (not created_at) is essential: a
    # campaign can sit queued for days, so created_at is unrelated to when the
    # recipient actually received the message and could reply. Fall back to
    # created_at only for legacy messages sent before sent_at was recorded.
    return await db.message_logs.find_one_and_update(
        {
            "recipient_phone": {"$in": phone_variants},
            "status": {"$in": ["sent", "delivered", "read"]},
            "replied": {"$ne": True},
            "$or": [
                {"sent_at": {"$gte": forty_eight_hours_ago, "$lt": received_at}},
                {
                    "sent_at": {"$exists": False},
                    "created_at": {"$gte": forty_eight_hours_ago, "$lt": received_at},
                },
            ],
        },
        {"$set": {"replied": True}},
        sort=[("sent_at", -1), ("created_at", -1)],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_async_redis():
    return redis_from_url(settings.redis_url, decode_responses=True)
