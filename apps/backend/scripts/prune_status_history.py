"""Report (and optionally reclaim) space taken by message_logs.status_history.

status_history is an unbounded array of {status, timestamp, meta} sub-documents
appended on every WhatsApp status webhook (sent -> delivered -> read). It is the
single heaviest field on a message_log and is largely redundant with the
top-level `status` + `updated_at`. Removing it keeps the row (final status,
failed-export, reply matching all still work) while freeing most of the space.

Dry run measures exactly what status_history costs — total, and per campaign —
using MongoDB's $bsonSize so the numbers are real bytes, not estimates.

--apply $unsets status_history from TERMINAL, OLD message_logs only
(status in sent/delivered/read/failed/cancelled AND created_at older than
--older-than-days), so nothing in-flight is ever touched.

⚠️ Atlas note: $unset frees logical space but WiredTiger does not return blocks
to the OS until you also run `compact` (Atlas: db.runCommand({compact:
"message_logs"})). The storage-quota number drops after compaction.

Usage:
    python scripts/prune_status_history.py                         # dry run: full report
    python scripts/prune_status_history.py --older-than-days 60     # tune the age window
    python scripts/prune_status_history.py --apply                  # strip history (>=30d, terminal)
    python scripts/prune_status_history.py --apply --older-than-days 90
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo.errors import OperationFailure

from app.config import settings

TERMINAL_STATUSES = ["sent", "delivered", "read", "failed", "cancelled"]
# "read" is deliberately excluded: campaign TTR aggregation (campaigns.py) unwinds
# status_history to find the first "read" event, so stripping it from read logs
# would silently break time-to-read reporting for old campaigns.
PRUNABLE_STATUSES = [s for s in TERMINAL_STATUSES if s != "read"]
DEFAULT_OLDER_THAN_DAYS = 30
TOP_N_CAMPAIGNS = 15
DEFAULT_BATCH_SIZE = 500
_ATLAS_QUOTA_CODE = 8000  # over-space-quota AtlasError


def _prune_query(cutoff: datetime) -> dict:
    """Filter for prunable logs: prunable terminal status, older than cutoff, and
    still carrying a non-empty status_history. Shared by _apply and the dry-run
    count so the two can't drift (e.g. the "read" exclusion stays in one place)."""
    return {
        "status": {"$in": PRUNABLE_STATUSES},
        "created_at": {"$lt": cutoff},
        "status_history": {"$exists": True, "$ne": []},
    }


def _resolve_db_name(mongo_url: str, default: str = "restobuzz") -> str:
    """Same resolution the app uses: MONGODB_DB_NAME, else the URL path."""
    name = (settings.mongodb_db_name or "").strip()
    if name:
        return name
    try:
        path = urlparse(mongo_url).path.strip("/").split("?")[0].split("/")[0]
        return path or default
    except Exception:
        return default


def _human(num_bytes: float) -> str:
    """Bytes -> human-readable (MiB/GiB) string."""
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TiB"


async def _collection_size(db) -> None:
    """Print overall message_logs storage footprint from collStats."""
    try:
        stats = await db.command("collStats", "message_logs")
    except Exception as e:
        print(f"  (collStats unavailable: {e})")
        return
    print("message_logs collection:")
    print(f"  documents      : {stats.get('count', 0):,}")
    print(f"  data size      : {_human(stats.get('size', 0))}   (logical)")
    print(f"  storage size   : {_human(stats.get('storageSize', 0))}   (on disk)")
    print(f"  total indexes  : {_human(stats.get('totalIndexSize', 0))}")
    print()


async def _overall_report(db) -> None:
    """Aggregate exact status_history cost across the whole collection."""
    pipeline = [
        {
            "$group": {
                "_id": None,
                "docs": {"$sum": 1},
                "with_history": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$size": {"$ifNull": ["$status_history", []]}}, 0]},
                            1,
                            0,
                        ]
                    }
                },
                "history_entries": {
                    "$sum": {"$size": {"$ifNull": ["$status_history", []]}}
                },
                # $bsonSize needs a document input, so wrap the array. The tiny
                # per-doc wrapper overhead is negligible against the total.
                "history_bytes": {
                    "$sum": {"$bsonSize": {"h": {"$ifNull": ["$status_history", []]}}}
                },
                "doc_bytes": {"$sum": {"$bsonSize": "$$ROOT"}},
            }
        }
    ]
    rows = await db.message_logs.aggregate(pipeline, allowDiskUse=True).to_list(1)
    if not rows:
        print("No message_logs found.\n")
        return
    r = rows[0]
    doc_bytes = r["doc_bytes"] or 1
    hist_bytes = r["history_bytes"]
    pct = 100.0 * hist_bytes / doc_bytes
    print("status_history cost (whole collection):")
    print(f"  docs with history : {r['with_history']:,} / {r['docs']:,}")
    print(f"  history entries   : {r['history_entries']:,}")
    print(f"  history bytes     : {_human(hist_bytes)}")
    print(f"  all-docs bytes    : {_human(doc_bytes)}")
    print(f"  history is        : {pct:.1f}% of total document bytes")
    print(f"  --> reclaimable by $unset: ~{_human(hist_bytes)} (before compaction)")
    print()


async def _per_campaign_report(db) -> None:
    """Top campaigns by status_history bytes, with names."""
    pipeline = [
        {"$match": {"status_history": {"$exists": True, "$ne": []}}},
        {
            "$group": {
                "_id": "$job_id",
                "history_bytes": {"$sum": {"$bsonSize": {"h": "$status_history"}}},
                "docs": {"$sum": 1},
            }
        },
        {"$sort": {"history_bytes": -1}},
        {"$limit": TOP_N_CAMPAIGNS},
    ]
    rows = await db.message_logs.aggregate(pipeline, allowDiskUse=True).to_list(
        TOP_N_CAMPAIGNS
    )
    if not rows:
        return
    job_ids = [r["_id"] for r in rows]
    jobs = {
        j["_id"]: j
        async for j in db.campaign_jobs.find(
            {"_id": {"$in": job_ids}}, {"name": 1, "status": 1}
        )
    }
    print(f"Top {len(rows)} campaigns by status_history size:")
    for r in rows:
        job = jobs.get(r["_id"], {})
        name = job.get("name", "(unknown)")
        status = job.get("status", "?")
        print(
            f"  {_human(r['history_bytes']):>10}  docs={r['docs']:>5}  "
            f"status={status:<10} {name!r}  [{r['_id']}]"
        )
    print()


async def _apply(db, cutoff: datetime, batch_size: int) -> None:
    """$unset status_history on terminal logs older than cutoff, in small batches.

    A single update_many over 100k+ docs is rejected on a near-full Atlas cluster
    ("would put you over your space quota") because WiredTiger writes new versions
    of every doc before reclaiming the old ones. Small batches each fit in the
    thin headroom and net-free space, so headroom grows as we go. On a quota
    error we shrink the batch and wait for a checkpoint; on success we ramp back
    up. The query itself is self-draining: once a doc's status_history is unset it
    no longer matches, so a plain find(...).limit() always returns fresh work.
    """
    query = _prune_query(cutoff)
    to_change = await db.message_logs.count_documents(query)
    print(f"[APPLY] $unset status_history on {to_change:,} terminal logs "
          f"older than {cutoff.date()} (batches up to {batch_size})...")
    if not to_change:
        print("  Nothing matched — nothing to do.\n")
        return

    target = batch_size
    size = batch_size
    modified = 0
    while True:
        ids = [
            d["_id"]
            async for d in db.message_logs.find(query, {"_id": 1}).limit(size)
        ]
        if not ids:
            break
        try:
            res = await db.message_logs.update_many(
                {"_id": {"$in": ids}}, {"$unset": {"status_history": ""}}
            )
        except OperationFailure as e:
            if e.code == _ATLAS_QUOTA_CODE and size > 25:
                size = max(25, size // 2)
                print(f"  quota tight — shrinking batch to {size}, "
                      f"waiting 5s for a checkpoint...")
                await asyncio.sleep(5)
                continue
            raise
        modified += res.modified_count
        print(f"  ...{modified:,}/{to_change:,} stripped")
        size = min(target, int(size * 1.5) + 1)  # ramp back up as space frees
        await asyncio.sleep(0.1)  # let WiredTiger reclaim between batches

    print(f"  done — modified {modified:,} documents.")
    print("  Re-run the dry report to confirm the freed space; then redeploy the "
          "backend to recreate the dropped index + add the TTL cap.")
    print()


async def main(apply: bool, older_than_days: int, batch_size: int) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = settings.mongodb_url
    db = AsyncIOMotorClient(mongo_url).get_database(_resolve_db_name(mongo_url))
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    host = urlparse(mongo_url).hostname or "?"
    if host in ("localhost", "127.0.0.1"):
        print("⚠️  Connected to LOCALHOST — set MONGODB_URL_PROD or use "
              "`railway run` to hit production.\n")
    print(f"[{'APPLY' if apply else 'DRY RUN'}] db={db.name}  host={host}  "
          f"older_than_days={older_than_days}\n")

    await _collection_size(db)
    await _overall_report(db)
    await _per_campaign_report(db)

    if apply:
        await _apply(db, cutoff, batch_size)
    else:
        eligible = await db.message_logs.count_documents(_prune_query(cutoff))
        print(
            f"DRY RUN — nothing changed. {eligible:,} terminal logs older than "
            f"{cutoff.date()} would have status_history stripped by --apply."
        )


if __name__ == "__main__":
    args = sys.argv[1:]
    days = (
        int(args[args.index("--older-than-days") + 1])
        if "--older-than-days" in args
        else DEFAULT_OLDER_THAN_DAYS
    )
    batch = (
        int(args[args.index("--batch-size") + 1])
        if "--batch-size" in args
        else DEFAULT_BATCH_SIZE
    )
    asyncio.run(
        main(apply="--apply" in args, older_than_days=days, batch_size=batch)
    )
