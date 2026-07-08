"""Repair counters + reply matching for campaigns sent long after they were created.

Fixes three data artifacts on one campaign (safe, idempotent, dry-run by default):

  1. sent_at — older sent messages predate the sent_at field. Backfill it from the
     'sent' status_history entry (falling back to updated_at) so reply-window
     matching has a real send time to key off.

  2. sent_count — Meta accepting then dropping a message (e.g. 131049) counted it
     as BOTH sent and failed, inflating sent_count. Recompute it as the number of
     messages actually in a successful state (sent/delivered/read).

  3. replies_count — replies to a long-queued campaign were missed because the old
     matcher used created_at (unrelated to real send time), so most plain-text
     replies fell outside the 48h window. Re-match recent inbound messages to this
     campaign's sent messages (same logic as the fixed webhook path) and rebuild
     replies_count from the per-message `replied` flags.

Usage:
    python scripts/backfill_campaign_repair.py <campaign_id>                 # dry run
    python scripts/backfill_campaign_repair.py <campaign_id> --apply
    python scripts/backfill_campaign_repair.py <campaign_id> --apply --reply-days 14
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bson import ObjectId

from app.database import get_fresh_db
from app.utils.phone import normalize_phone

SUCCESS_STATUSES = ["sent", "delivered", "read"]
DEFAULT_REPLY_DAYS = 14


async def _backfill_sent_at(db, jid, apply: bool) -> int:
    """Stamp sent_at on sent messages that predate the field."""
    flt = {
        "job_id": jid,
        "wa_message_id": {"$ne": None},
        "sent_at": {"$exists": False},
    }
    n = await db.message_logs.count_documents(flt)
    if apply and n:
        # Derive from the earliest 'sent' status_history entry, else updated_at.
        await db.message_logs.update_many(
            flt,
            [
                {
                    "$set": {
                        "sent_at": {
                            "$let": {
                                "vars": {
                                    "sent_ts": {
                                        "$min": {
                                            "$map": {
                                                "input": {
                                                    "$filter": {
                                                        "input": {
                                                            "$ifNull": [
                                                                "$status_history",
                                                                [],
                                                            ]
                                                        },
                                                        "as": "h",
                                                        "cond": {
                                                            "$eq": [
                                                                "$$h.status",
                                                                "sent",
                                                            ]
                                                        },
                                                    }
                                                },
                                                "as": "h",
                                                "in": "$$h.timestamp",
                                            }
                                        }
                                    }
                                },
                                "in": {"$ifNull": ["$$sent_ts", "$updated_at"]},
                            }
                        }
                    }
                }
            ],
        )
    return n


async def _recompute_sent_count(db, jid, apply: bool) -> int:
    """sent_count = messages currently in a successful (non-failed) state."""
    real_sent = await db.message_logs.count_documents(
        {"job_id": jid, "status": {"$in": SUCCESS_STATUSES}}
    )
    if apply:
        await db.campaign_jobs.update_one(
            {"_id": jid}, {"$set": {"sent_count": real_sent}}
        )
    return real_sent


def _phone_fallback_filter(jid, inbound: dict) -> dict:
    """Match this job's most recent message actually SENT within 48h of the inbound.

    Uses the real send time — sent_at when present, otherwise the 'sent'
    status_history timestamp — so it works whether or not sent_at has been
    backfilled yet (making dry-run and apply agree)."""
    received_at = inbound.get("received_at")
    from_phone = inbound.get("from_phone") or ""
    variants = list(
        {p for p in [normalize_phone(from_phone), from_phone, f"+{from_phone}"] if p}
    )
    window = received_at - timedelta(hours=48)
    return {
        "job_id": jid,
        "recipient_phone": {"$in": variants},
        "status": {"$in": SUCCESS_STATUSES},
        "replied": {"$ne": True},
        "$or": [
            {"sent_at": {"$gte": window, "$lt": received_at}},
            {
                "status_history": {
                    "$elemMatch": {
                        "status": "sent",
                        "timestamp": {"$gte": window, "$lt": received_at},
                    }
                }
            },
        ],
    }


async def _match_reply(db, jid, inbound: dict) -> bool:
    """Mark this campaign's message as replied for one inbound. Mirrors the fixed
    webhook matcher, scoped to this job. Returns True if a message was newly marked."""
    ctx_id = (inbound.get("raw_payload") or {}).get("context", {}).get("id")
    if ctx_id:
        res = await db.message_logs.find_one_and_update(
            {"job_id": jid, "wa_message_id": ctx_id, "replied": {"$ne": True}},
            {"$set": {"replied": True}},
        )
        if res:
            return True
    res = await db.message_logs.find_one_and_update(
        _phone_fallback_filter(jid, inbound),
        {"$set": {"replied": True}},
        sort=[("sent_at", -1), ("created_at", -1)],
    )
    return res is not None


async def _rematch_replies(db, jid, restaurant_id, reply_days: int, apply: bool) -> int:
    """Re-match recent inbound from this campaign's recipients; returns newly matched."""
    since = datetime.now(timezone.utc) - timedelta(days=reply_days)
    recipients = {
        m["recipient_phone"]
        async for m in db.message_logs.find({"job_id": jid}, {"recipient_phone": 1})
    }
    newly = 0
    q = {"received_at": {"$gte": since}}
    if restaurant_id:
        q["restaurant_id"] = restaurant_id
    async for inbound in db.inbound_messages.find(q).sort("received_at", 1):
        fp = inbound.get("from_phone") or ""
        if not ({normalize_phone(fp), fp, f"+{fp}"} & recipients):
            continue
        if apply:
            if await _match_reply(db, jid, inbound):
                newly += 1
        else:
            # Dry run: count inbound that map to an as-yet-unreplied sent message
            # (context quote-reply, or the phone/send-time fallback).
            ctx_id = (inbound.get("raw_payload") or {}).get("context", {}).get("id")
            hit = None
            if ctx_id:
                hit = await db.message_logs.find_one(
                    {"job_id": jid, "wa_message_id": ctx_id, "replied": {"$ne": True}},
                    {"_id": 1},
                )
            if not hit:
                hit = await db.message_logs.find_one(
                    _phone_fallback_filter(jid, inbound), {"_id": 1}
                )
            if hit:
                newly += 1
    return newly


async def main(campaign_id: str, apply: bool, reply_days: int) -> None:
    db = get_fresh_db()
    mode = "APPLY" if apply else "DRY RUN"
    try:
        jid = ObjectId(campaign_id)
    except Exception:
        print(f"Invalid campaign id: {campaign_id!r}")
        return

    job = await db.campaign_jobs.find_one({"_id": jid})
    if not job:
        print(f"Campaign {campaign_id} not found in {db.name}")
        return

    print(f"[{mode}] repairing '{job.get('name')}' ({campaign_id}) in {db.name}\n")

    missing_sent_at = await _backfill_sent_at(db, jid, apply)
    print(f"  sent_at backfilled on : {missing_sent_at} messages")

    old_sent = job.get("sent_count", 0)
    new_sent = await _recompute_sent_count(db, jid, apply)
    print(f"  sent_count            : {old_sent} -> {new_sent}")

    newly_matched = await _rematch_replies(
        db, jid, job.get("restaurant_id"), reply_days, apply
    )
    # After (re)matching, replies_count = messages flagged replied for this job.
    replied_now = await db.message_logs.count_documents(
        {"job_id": jid, "replied": True}
    )
    old_replies = job.get("replies_count", 0)
    if apply:
        # Rebuild from the source-of-truth flags (also self-heals prior drift).
        await db.campaign_jobs.update_one(
            {"_id": jid}, {"$set": {"replies_count": replied_now}}
        )
    projected = replied_now if apply else replied_now + newly_matched
    print(
        f"  replies (last {reply_days}d)  : +{newly_matched} newly matched | "
        f"replies_count {old_replies} -> {projected}"
    )

    if not apply:
        print("\nDRY RUN — nothing changed. Re-run with --apply to commit.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Usage: python scripts/backfill_campaign_repair.py <campaign_id> [--apply] [--reply-days N]")
        sys.exit(1)
    days = (
        int(sys.argv[sys.argv.index("--reply-days") + 1])
        if "--reply-days" in sys.argv
        else DEFAULT_REPLY_DAYS
    )
    asyncio.run(main(args[0], apply="--apply" in sys.argv, reply_days=days))
