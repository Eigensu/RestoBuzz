"""One-off backfill: tag historical campaign yes-repliers as 'interested' members.

The live capture (webhook_task._handle_interested_reply) only fires at reply time,
so any positive replies that arrived BEFORE that code was deployed were never
tagged. This script replays the same matching + upsert logic over existing
inbound_messages so those respondents land in the Interested tab too.

Matching mirrors production exactly:
  1. Direct reply  → inbound raw_payload.context.id == message_logs.wa_message_id
  2. Fallback      → latest outbound to the same phone within REPLY_WINDOW_HOURS
                     before the reply (production uses 48h in _find_and_mark_replied)

The actual member upsert is delegated to the production
_handle_interested_reply() so backfilled docs are identical to live ones (and the
$addToSet/$set are idempotent — safe to re-run, and harmless for replies the live
code already captured after deploy).

Usage:
    python scripts/backfill_interested_members.py            # dry run (no writes)
    python scripts/backfill_interested_members.py --apply    # perform the upserts
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.phone import normalize_phone
from app.workers.webhook_task import INTERESTED_KEYWORDS, _handle_interested_reply

# Mirror production's reply-match window (_find_and_mark_replied uses 48h).
REPLY_WINDOW_HOURS = 48


def _parse_db_name(mongo_url: str, default: str = "restobuzz") -> str:
    try:
        path = urlparse(mongo_url).path.strip("/").split("?")[0].split("/")[0]
        return path or default
    except Exception:
        return default


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _build_lookups(db) -> tuple[dict, dict]:
    """Return (wa_message_id → log, normalized_phone → time-sorted logs)."""
    wa_lookup: dict = {}
    recipient_map: dict = {}
    async for log in db.message_logs.find():
        wa_id = log.get("wa_message_id")
        if wa_id:
            wa_lookup[wa_id] = log
        norm = normalize_phone(log.get("recipient_phone"))
        if norm:
            recipient_map.setdefault(norm, []).append(log)
    for logs in recipient_map.values():
        logs.sort(
            key=lambda x: _to_utc(x["created_at"])
            if x.get("created_at")
            else datetime.min.replace(tzinfo=timezone.utc)
        )
    return wa_lookup, recipient_map


def _match_outbound(
    wa_lookup: dict, recipient_map: dict, msg: dict, received_at: datetime
) -> dict | None:
    """Reconstruct the campaign message this reply belongs to (or None)."""
    context_id = msg.get("raw_payload", {}).get("context", {}).get("id")
    if context_id and context_id in wa_lookup:
        return wa_lookup[context_id]

    norm = normalize_phone(msg.get("from_phone"))
    if not norm or norm not in recipient_map:
        return None
    window_start = received_at - timedelta(hours=REPLY_WINDOW_HOURS)
    candidates = [
        log
        for log in recipient_map[norm]
        if log.get("created_at") is not None
        and window_start <= _to_utc(log["created_at"]) < received_at
    ]
    return candidates[-1] if candidates else None


async def backfill(apply: bool) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017/restobuzz")
    db_name = _parse_db_name(mongo_url)
    client = AsyncIOMotorClient(mongo_url)
    db = client.get_database(db_name)

    mode = "APPLY" if apply else "DRY RUN"
    print(f"[{mode}] Interested-member backfill on DB: {db_name}")
    print("Building message_logs lookups...")
    wa_lookup, recipient_map = await _build_lookups(db)

    positive = matched = upserted = 0
    unmatched: list[str] = []

    async for msg in db.inbound_messages.find():
        body = (msg.get("body") or "").strip()
        if body.lower() not in INTERESTED_KEYWORDS:
            continue
        positive += 1

        received_at = msg.get("received_at")
        if not received_at:
            continue
        received_at = _to_utc(received_at)

        orig_msg = _match_outbound(wa_lookup, recipient_map, msg, received_at)
        if orig_msg is None:
            unmatched.append(msg.get("from_phone") or "?")
            continue
        matched += 1

        if apply:
            await _handle_interested_reply(
                db, orig_msg, body, msg.get("from_phone"), msg.get("sender_name")
            )
            upserted += 1
        else:
            print(
                f"  would tag: phone={orig_msg.get('recipient_phone') or msg.get('from_phone')} "
                f"reply={body!r} job_id={orig_msg.get('job_id')}"
            )

    print("\n── Summary ─────────────────────────────")
    print(f"  positive-keyword replies scanned : {positive}")
    print(f"  matched to a campaign message     : {matched}")
    print(f"  unmatched (no campaign found)     : {len(unmatched)}")
    if apply:
        print(f"  members upserted/tagged           : {upserted}")
    else:
        print("\n  DRY RUN — no writes. Re-run with --apply to commit.")
    client.close()


if __name__ == "__main__":
    asyncio.run(backfill(apply="--apply" in sys.argv))
