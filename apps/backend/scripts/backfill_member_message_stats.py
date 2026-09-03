"""One-off backfill: rebuild member_message_stats from surviving message_logs.

The per-member messaging rollup (app/services/member_stats_service.py) is only
written as sends and status webhooks happen, so on the day it ships every member
reads as "0 received, 0 read". This script replays the message_logs that still
exist to seed the counters.

Hard limit worth stating plainly: message_logs carry a TTL of
MESSAGE_LOG_TTL_DAYS (30 at time of writing, see app/database.py), so this can
only recover roughly the last month. Anything older was deleted by MongoDB and
is not recoverable from any source. Counts are exact from here forward.

Each log row contributes at most 1 to sent/received/read, matching the live
transition rules: a row that reached 'read' counts as both received and read,
since a read message necessarily arrived.

Usage:
    python scripts/backfill_member_message_stats.py              # dry run
    python scripts/backfill_member_message_stats.py --apply      # seed new rollups only
    python scripts/backfill_member_message_stats.py --apply --overwrite

--apply only creates rollups that don't exist yet; rollups the live path has
already started are left alone. --overwrite replaces them with a full
recomputation, which is ONLY safe in the first days after deploy while
message_logs still covers everything the counters have seen. Run it later and
you will overwrite months of accumulated lifetime counts with the last 30 days.
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from app.services.member_stats_service import (
    COLLECTION,
    TOUCH_HISTORY_LIMIT,
    phone_key,
)

# Statuses meaning the message landed on the device.
ARRIVED = ("delivered", "read")
# Statuses meaning Meta accepted it for delivery.
ACCEPTED = ("sent", "delivered", "read")


def _parse_db_name(mongo_url: str, default: str = "restobuzz") -> str:
    try:
        path = urlparse(mongo_url).path.strip("/").split("?")[0].split("/")[0]
        return path or default
    except Exception:
        return default


def _to_utc(dt) -> datetime | None:
    if not isinstance(dt, datetime):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


async def _resolve_restaurant_ids(db, logs_missing_rid: set) -> dict:
    """restaurant_id isn't denormalized onto older message_logs — recover it
    from the campaign job, which always carries it."""
    if not logs_missing_rid:
        return {}
    mapping = {}
    async for job in db.campaign_jobs.find(
        {"_id": {"$in": list(logs_missing_rid)}}, {"restaurant_id": 1}
    ):
        mapping[job["_id"]] = job.get("restaurant_id")
    return mapping


def _sent_time(log: dict) -> datetime | None:
    """When the message actually went out. sent_at is the true send time for
    campaigns that sat queued; created_at is the fallback for older rows."""
    return _to_utc(log.get("sent_at")) or _to_utc(log.get("created_at"))


async def main(apply: bool, overwrite: bool) -> None:
    mongo_url = os.environ.get("MONGODB_URL") or os.environ.get("MONGODB_URI")
    if not mongo_url:
        print("MONGODB_URL is not set.")
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get("MONGODB_DB_NAME") or _parse_db_name(mongo_url)]

    logs = []
    missing_rid_jobs = set()
    async for log in db.message_logs.find(
        {},
        {
            "restaurant_id": 1,
            "recipient_phone": 1,
            "status": 1,
            "job_id": 1,
            "sent_at": 1,
            "created_at": 1,
        },
    ):
        if not log.get("restaurant_id") and log.get("job_id"):
            missing_rid_jobs.add(log["job_id"])
        logs.append(log)

    job_rids = await _resolve_restaurant_ids(db, missing_rid_jobs)

    # (restaurant_id, phone_key) -> accumulated rollup
    acc: dict = defaultdict(
        lambda: {
            "sent_count": 0,
            "received_count": 0,
            "read_count": 0,
            "first_sent_at": None,
            "last_sent_at": None,
            "last_received_at": None,
            "last_read_at": None,
            "last_campaign_id": None,
            "touches": [],
        }
    )
    skipped = 0

    for log in logs:
        rid = log.get("restaurant_id") or job_rids.get(log.get("job_id"))
        key = phone_key(log.get("recipient_phone"))
        if not rid or not key:
            skipped += 1
            continue

        status = log.get("status")
        at = _sent_time(log)
        row = acc[(rid, key)]

        if status in ACCEPTED:
            row["sent_count"] += 1
            if at:
                row["touches"].append({"campaign_id": log.get("job_id"), "at": at})
                if row["first_sent_at"] is None or at < row["first_sent_at"]:
                    row["first_sent_at"] = at
                if row["last_sent_at"] is None or at > row["last_sent_at"]:
                    row["last_sent_at"] = at
                    row["last_campaign_id"] = log.get("job_id")
        if status in ARRIVED:
            row["received_count"] += 1
            if at and (row["last_received_at"] is None or at > row["last_received_at"]):
                row["last_received_at"] = at
        if status == "read":
            row["read_count"] += 1
            if at and (row["last_read_at"] is None or at > row["last_read_at"]):
                row["last_read_at"] = at

    print(f"message_logs scanned : {len(logs)}")
    print(f"skipped (no rid/phone): {skipped}")
    print(f"member rollups        : {len(acc)}")
    totals = {
        "sent": sum(r["sent_count"] for r in acc.values()),
        "received": sum(r["received_count"] for r in acc.values()),
        "read": sum(r["read_count"] for r in acc.values()),
    }
    print(f"totals                : {totals}")

    existing = await db[COLLECTION].count_documents({})
    print(f"rollups already present: {existing}")
    if existing and not overwrite:
        print("  -> these are left untouched; pass --overwrite to recompute them")

    if not apply:
        print("\nDRY RUN — no writes. Re-run with --apply to persist.")
        client.close()
        return

    ops = []
    for (rid, key), row in acc.items():
        # Keep only the most recent touches, matching the live cap.
        row["touches"].sort(key=lambda t: t["at"])
        touches = row["touches"][-TOUCH_HISTORY_LIMIT:]
        doc = {
            "sent_count": row["sent_count"],
            "received_count": row["received_count"],
            "read_count": row["read_count"],
            "touches": touches,
        }
        for field in (
            "first_sent_at",
            "last_sent_at",
            "last_received_at",
            "last_read_at",
            "last_campaign_id",
        ):
            if row[field] is not None:
                doc[field] = row[field]

        # A full recomputation, never an $inc — so re-running can't double a
        # count. $setOnInsert by default so an existing rollup (which may hold
        # history that message_logs has since expired) is never clobbered;
        # --overwrite opts into replacing it.
        identity = {"restaurant_id": rid, "phone_key": key}
        update = (
            {"$set": doc, "$setOnInsert": identity}
            if overwrite
            else {"$setOnInsert": {**doc, **identity}}
        )
        ops.append(UpdateOne(identity, update, upsert=True))
        if len(ops) >= 1000:
            await db[COLLECTION].bulk_write(ops, ordered=False)
            ops = []
    if ops:
        await db[COLLECTION].bulk_write(ops, ordered=False)

    mode = "recomputed" if overwrite else "seeded (existing rows untouched)"
    print(f"\n{len(acc)} rollups {mode} in {COLLECTION}.")
    client.close()


if __name__ == "__main__":
    asyncio.run(
        main(apply="--apply" in sys.argv, overwrite="--overwrite" in sys.argv)
    )
