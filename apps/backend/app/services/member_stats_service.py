"""Durable per-member messaging counters and marketing attribution.

`message_logs` rows expire after MESSAGE_LOG_TTL_DAYS (see app/database.py), so
they cannot answer "how many messages has this member ever received?". This
service keeps a small, permanent per-phone rollup that is incremented as the
send and webhook paths observe each message, plus a capped history of campaign
touches used to attribute new members to the marketing that reached them.

Keyed by (restaurant_id, phone_key) rather than by member _id on purpose: some
restaurants keep their members in an external database (r2 -> Fielia's
test.cards, see member_match_service), so there is no member document we can own
or write to. A phone-keyed rollup in our own DB works uniformly for both.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from app.core.logging import get_logger
from app.services.dormancy_service import normalize_phone_for_match

logger = get_logger(__name__)

COLLECTION = "member_message_stats"

# How many recent campaign touches to retain per phone. Attribution only ever
# looks a few days back from a member's join date, so a short tail is enough —
# and it keeps the document a fixed, small size no matter how many campaigns a
# phone receives.
TOUCH_HISTORY_LIMIT = 20

# A member who joined within this many days of a campaign reaching them is
# counted as marketing-assisted. Kept well inside MESSAGE_LOG_TTL_DAYS so the
# backfill script can reconstruct recent history from surviving message_logs.
ATTRIBUTION_WINDOW_DAYS = 7

# Statuses that mean the message actually landed on the recipient's device.
_ARRIVED = ("delivered", "read")


def _as_utc(dt: datetime | None) -> datetime | None:
    """Coerce a datetime to UTC-aware; naive values are assumed to be UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def phone_key(phone: str | None) -> str | None:
    """Matching key for a phone number (last 10 digits).

    Reuses the codebase-wide convention from dormancy_service so a member row,
    a Fielia card, and a message_log recipient all collapse to the same key
    regardless of "+91" prefixes or formatting.
    """
    return normalize_phone_for_match(phone)


async def record_sent(
    db: Any,
    restaurant_id: str | None,
    phone: str | None,
    *,
    campaign_id: Any = None,
    at: datetime,
) -> None:
    """Record that a campaign message was accepted by Meta for this phone.

    Called from the send path. Bumps the lifetime sent counter and appends a
    campaign touch used later for acquisition attribution.
    """
    key = phone_key(phone)
    if not key or not restaurant_id:
        return

    touch = {"campaign_id": campaign_id, "at": at}
    try:
        await db[COLLECTION].update_one(
            {"restaurant_id": restaurant_id, "phone_key": key},
            {
                "$inc": {"sent_count": 1},
                "$set": {"last_sent_at": at, "last_campaign_id": campaign_id},
                "$min": {"first_sent_at": at},
                "$push": {"touches": {"$each": [touch], "$slice": -TOUCH_HISTORY_LIMIT}},
                "$setOnInsert": {
                    "restaurant_id": restaurant_id,
                    "phone_key": key,
                    "received_count": 0,
                    "read_count": 0,
                },
            },
            upsert=True,
        )
    except Exception as e:  # never let stats bookkeeping break a send
        logger.warning("member_stats_record_sent_failed", phone_key=key, error=str(e))


async def record_status_change(
    db: Any,
    restaurant_id: str | None,
    phone: str | None,
    prev_status: str | None,
    new_status: str,
    at: datetime,
) -> None:
    """Move the lifetime received/read counters for one status transition.

    Driven by the transition rather than the raw webhook so each message can
    contribute at most 1 to received_count and 1 to read_count, however many
    times Meta redelivers the same status. A message that jumps straight to
    'read' without a 'delivered' webhook still counts as received — 'read'
    implies it arrived.
    """
    key = phone_key(phone)
    if not key or not restaurant_id:
        return

    inc: dict[str, int] = {}
    ts: dict[str, datetime] = {}

    if new_status == "delivered" and prev_status not in _ARRIVED:
        inc["received_count"] = 1
        ts["last_received_at"] = at
    elif new_status == "read":
        if prev_status != "read":
            inc["read_count"] = 1
            ts["last_read_at"] = at
        if prev_status not in _ARRIVED:
            inc["received_count"] = 1
            ts["last_received_at"] = at

    if not inc:
        return

    try:
        await db[COLLECTION].update_one(
            {"restaurant_id": restaurant_id, "phone_key": key},
            {
                "$inc": inc,
                "$set": ts,
                "$setOnInsert": {
                    "restaurant_id": restaurant_id,
                    "phone_key": key,
                    "sent_count": 0,
                },
            },
            upsert=True,
        )
    except Exception as e:  # never let stats bookkeeping break webhook processing
        logger.warning(
            "member_stats_record_status_failed",
            phone_key=key,
            status=new_status,
            error=str(e),
        )


async def get_bulk_stats(
    db: Any, restaurant_id: str, phones: Iterable[str | None]
) -> dict[str, dict]:
    """Fetch messaging rollups for a page of members, keyed by phone_key.

    One query per page — callers must not fetch per member.
    """
    keys = {k for k in (phone_key(p) for p in phones) if k}
    if not keys:
        return {}

    stats: dict[str, dict] = {}
    try:
        cursor = db[COLLECTION].find(
            {"restaurant_id": restaurant_id, "phone_key": {"$in": list(keys)}},
            {
                "phone_key": 1,
                "sent_count": 1,
                "received_count": 1,
                "read_count": 1,
                "last_sent_at": 1,
                "last_received_at": 1,
                "last_read_at": 1,
            },
        )
        async for doc in cursor:
            stats[doc["phone_key"]] = doc
    except Exception as e:
        # A missing rollup degrades to zeroes in the UI; it must never 500 the
        # members list.
        logger.error("member_stats_bulk_fetch_failed", error=str(e))
        return {}

    return stats


def apply_stats(target: Any, stats: dict | None) -> None:
    """Copy a rollup onto a MemberResponse, defaulting to zero when absent."""
    stats = stats or {}
    target.messages_sent = stats.get("sent_count", 0) or 0
    target.messages_received = stats.get("received_count", 0) or 0
    target.messages_read = stats.get("read_count", 0) or 0
    target.last_message_at = stats.get("last_sent_at")


async def get_attribution_touches(
    db: Any, restaurant_id: str, phones: Iterable[str | None]
) -> dict[str, list[dict]]:
    """Fetch campaign touch history for a set of phones, keyed by phone_key."""
    keys = {k for k in (phone_key(p) for p in phones) if k}
    if not keys:
        return {}

    touches: dict[str, list[dict]] = {}
    cursor = db[COLLECTION].find(
        {"restaurant_id": restaurant_id, "phone_key": {"$in": list(keys)}},
        {"phone_key": 1, "touches": 1},
    )
    async for doc in cursor:
        touches[doc["phone_key"]] = doc.get("touches") or []
    return touches


def find_attributing_touch(
    touches: list[dict] | None,
    joined_at: datetime | None,
    window_days: int = ATTRIBUTION_WINDOW_DAYS,
) -> dict | None:
    """Return the campaign touch that plausibly produced this signup.

    A touch qualifies when the campaign reached the phone at most `window_days`
    before the member joined, and not after they joined. The latest qualifying
    touch wins — that is the message they most likely acted on.
    """
    if not touches or not joined_at:
        return None

    # Fielia join dates arrive tz-aware while Mongo hands back naive UTC — pin
    # both sides to UTC so the comparison can't raise.
    joined_at = _as_utc(joined_at)
    window_start = joined_at - timedelta(days=window_days)
    best = None
    for touch in touches:
        at = _as_utc(touch.get("at"))
        if not at:
            continue
        if window_start <= at <= joined_at and (best is None or at > best["at"]):
            best = {"campaign_id": touch.get("campaign_id"), "at": at}
    return best
