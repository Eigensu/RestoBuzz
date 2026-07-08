"""Show the true message_logs status partition for a campaign vs its counters.

Answers "did this campaign really send everyone, or did it complete early?" by
comparing the DISTINCT per-recipient statuses in message_logs against the
overlapping sent_count/failed_count counters on campaign_jobs.

Usage:
    python scripts/campaign_status_breakdown.py <job_id>
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from bson import ObjectId

from app.config import settings


def _resolve_db_name(mongo_url: str, default: str = "restobuzz") -> str:
    name = (settings.mongodb_db_name or "").strip()
    if name:
        return name
    try:
        path = urlparse(mongo_url).path.strip("/").split("?")[0].split("/")[0]
        return path or default
    except Exception:
        return default


async def main(job_id: str) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = settings.mongodb_url
    db = AsyncIOMotorClient(mongo_url).get_database(_resolve_db_name(mongo_url))
    host = urlparse(mongo_url).hostname or "?"
    if host in ("localhost", "127.0.0.1"):
        print("⚠️  Connected to LOCALHOST — use `railway run` to hit production.\n")

    oid = ObjectId(job_id)
    job = await db.campaign_jobs.find_one({"_id": oid})
    if not job:
        print(f"No campaign_jobs doc with _id={job_id}")
        return

    print(f"Campaign: {job.get('name')!r}  status={job.get('status')}")
    print("job_jobs counters (overlapping funnel — a msg can be in several):")
    print(f"  total_count     : {job.get('total_count', 0)}")
    print(f"  sent_count      : {job.get('sent_count', 0)}")
    print(f"  delivered_count : {job.get('delivered_count', 0)}")
    print(f"  read_count      : {job.get('read_count', 0)}")
    print(f"  failed_count    : {job.get('failed_count', 0)}")
    print(f"  sent+failed     : {job.get('sent_count', 0) + job.get('failed_count', 0)}"
          f"   (completion uses this vs total_count)")
    print()

    # DISTINCT partition — each message_log has exactly one status.
    pipeline = [
        {"$match": {"job_id": oid}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]
    rows = await db.message_logs.aggregate(pipeline).to_list(None)
    total = sum(r["n"] for r in rows)
    print(f"message_logs partition (distinct — sums to real total {total}):")
    pending = 0
    for r in rows:
        print(f"  {r['_id'] or '(none)':<12} {r['n']:>6}")
        if r["_id"] in ("queued", "sending"):
            pending += r["n"]
    print()

    if pending:
        print(f"⚠️  {pending} recipients are still QUEUED/SENDING but the job is "
              f"'{job.get('status')}' — these were ABANDONED (never sent, and smart "
              f"retries won't touch them). This is the premature-completion bug.")
    else:
        print("✅ No recipients left queued/sending — everyone reached a terminal "
              "state. The gap vs 'sent' is genuine send/delivery failures, not "
              "abandonment.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/campaign_status_breakdown.py <job_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
