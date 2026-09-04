"""WhatsApp user identity: phone numbers and business-scoped user IDs (BSUID).

Meta began including BSUIDs in webhooks in April 2026 and started rolling out
usernames in June 2026. When a user who has adopted a username messages a
business that has not interacted with them in the last 30 days, the webhook
carries ``user_id`` / ``from_user_id`` (their BSUID) and a ``username`` on the
profile, and OMITS ``wa_id`` / ``from`` entirely. Phone number can therefore no
longer be assumed present on an inbound message.

A BSUID is scoped to a single business portfolio — the same person has a
different BSUID for every business they talk to — so it is only ever meaningful
inside this system. Format is an ISO 3166 alpha-2 country code, a period, then
digits, e.g. ``IN.13491208655302741918``.

Phone stays the canonical key wherever we have one: every existing member,
campaign recipient, and suppression entry is keyed on phone, and a phone is
stable across businesses where a BSUID is not. ``wa_identities`` records the
BSUID→phone link as soon as a webhook shows us both, so a conversation that
started as BSUID-only stays continuous once the phone becomes known.
"""

import re
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging import get_logger

logger = get_logger(__name__)

# ISO 3166 alpha-2 country code, a period, then the numeric portion. Anchored so
# a phone number (digits, optionally "+"-prefixed) can never match.
_BSUID_RE = re.compile(r"^[A-Za-z]{2}\.[A-Za-z0-9]{1,128}$")


def is_bsuid(value: str | None) -> bool:
    """True if `value` looks like a BSUID rather than a phone number."""
    return bool(value) and bool(_BSUID_RE.match(value))


def build_contact_index(contacts: list[dict]) -> dict[str, dict]:
    """Index a webhook `contacts` array by every identifier it exposes.

    Both ``wa_id`` and ``user_id`` point at the same contact entry, so a message
    can be resolved by whichever of the two it carries. Uses ``.get()`` on every
    field: for a username user with no prior interaction Meta omits ``wa_id``
    entirely, and subscripting it would raise KeyError and poison the whole
    webhook batch — including messages from ordinary phone-number users in the
    same change block.
    """
    index: dict[str, dict] = {}
    for c in contacts or []:
        profile = c.get("profile") or {}
        entry = {
            "name": profile.get("name"),
            "username": profile.get("username"),
            "phone": c.get("wa_id"),
            "bsuid": c.get("user_id"),
        }
        for key in (entry["phone"], entry["bsuid"]):
            if key:
                index[key] = entry
    return index


def message_identifiers(msg: dict) -> tuple[str | None, str | None]:
    """Return (phone, bsuid) for an inbound message. Either may be None."""
    return msg.get("from"), msg.get("from_user_id")


async def link_identity(
    db: AsyncIOMotorDatabase,
    phone: str | None,
    bsuid: str | None,
    username: str | None = None,
    restaurant_id: str | None = None,
) -> None:
    """Record what we now know about a BSUID.

    Only writes when there is a BSUID to key on. Fields are merged rather than
    replaced so a later phone-less webhook cannot erase a phone we already
    learned.
    """
    if not bsuid:
        return

    now = datetime.now(timezone.utc)
    updates = {"updated_at": now}
    if phone:
        updates["phone"] = phone
    if username:
        updates["username"] = username
    if restaurant_id:
        updates["restaurant_id"] = restaurant_id

    await db.wa_identities.update_one(
        {"bsuid": bsuid},
        {"$set": updates, "$setOnInsert": {"bsuid": bsuid, "first_seen_at": now}},
        upsert=True,
    )


async def resolve_contact_key(
    db: AsyncIOMotorDatabase,
    phone: str | None,
    bsuid: str | None,
) -> str | None:
    """Canonical key for a WhatsApp user: their phone when we know it, else BSUID.

    A BSUID-only message resolves to the phone if some earlier webhook linked
    them, which keeps one person in one conversation thread rather than
    splitting them the moment Meta stops sending the phone number.
    """
    if phone:
        return phone
    if not bsuid:
        return None

    doc = await db.wa_identities.find_one({"bsuid": bsuid}, {"phone": 1})
    return (doc or {}).get("phone") or bsuid


async def phone_for_bsuid(db: AsyncIOMotorDatabase, bsuid: str) -> str | None:
    """Known phone number for a BSUID, if one has ever been linked."""
    doc = await db.wa_identities.find_one({"bsuid": bsuid}, {"phone": 1})
    return (doc or {}).get("phone")


async def bsuid_for_contact_key(
    db: AsyncIOMotorDatabase, contact_key: str
) -> str | None:
    """Reverse lookup: the BSUID we can address `contact_key` by, if any.

    Used on the send path when a conversation has no usable phone number.
    """
    if is_bsuid(contact_key):
        return contact_key
    doc = await db.wa_identities.find_one({"phone": contact_key}, {"bsuid": 1})
    return (doc or {}).get("bsuid")
