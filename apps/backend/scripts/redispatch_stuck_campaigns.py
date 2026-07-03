"""Recover campaigns stranded in 'queued' (dispatch task lost, e.g. worker restart).

A 'Send Immediately' campaign sets status='queued' and fires dispatch_campaign_task
WITHOUT a claimed_at field. If that task is lost (worker redeploy/crash), the beat
poller cannot recover it (its heal query requires claimed_at), and Resume rejects a
'queued' job. Such jobs sit frozen forever. This re-enqueues their dispatch task.

Re-dispatch is safe: dispatch_campaign_task only fans out message_logs still at
status 'queued', and send_message_task atomically claims each one — so already-sent
messages are never re-sent.

Requires a live worker consuming the marketing/utility queue (check Railway logs first).

Usage:
    python scripts/redispatch_stuck_campaigns.py                 # list stuck jobs (dry run)
    python scripts/redispatch_stuck_campaigns.py --apply         # re-dispatch all stuck
    python scripts/redispatch_stuck_campaigns.py --apply --id <job_id>   # one specific job
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from bson import ObjectId

# Only treat as "stuck" if it's been queued for at least this long (avoid racing a
# dispatch that's legitimately in progress).
STUCK_MINUTES = 5


def _parse_db_name(mongo_url: str, default: str = "restobuzz") -> str:
    try:
        path = urlparse(mongo_url).path.strip("/").split("?")[0].split("/")[0]
        return path or default
    except Exception:
        return default


async def main(apply: bool, only_id: str | None) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.workers.send_task import dispatch_campaign_task

    mongo_url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017/restobuzz")
    db = AsyncIOMotorClient(mongo_url).get_database(_parse_db_name(mongo_url))

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_MINUTES)
    query: dict = {
        "status": {"$in": ["queued", "dispatching"]},
        "$or": [{"started_at": {"$exists": False}}, {"started_at": None}],
    }
    if only_id:
        query = {"_id": ObjectId(only_id)}

    print(f"[{'APPLY' if apply else 'DRY RUN'}] scanning for stuck campaigns...\n")
    found = redispatched = 0
    async for job in db.campaign_jobs.find(query):
        created = job.get("created_at")
        # Skip very fresh queued jobs unless an explicit id was given.
        if not only_id and created and created.replace(tzinfo=timezone.utc) > cutoff:
            continue
        found += 1
        jid = str(job["_id"])
        queued = await db.message_logs.count_documents(
            {"job_id": job["_id"], "status": "queued"}
        )
        print(
            f"  {jid}  name={job.get('name')!r}  status={job.get('status')}  "
            f"queued_msgs={queued}  total={job.get('total_count')}"
        )
        if apply:
            dispatch_campaign_task.delay(jid)
            redispatched += 1

    print(f"\nStuck campaigns: {found}")
    if apply:
        print(f"Re-dispatched: {redispatched} (watch the worker logs for 'dispatch_complete')")
    else:
        print("DRY RUN — nothing enqueued. Re-run with --apply (and --id to target one).")


if __name__ == "__main__":
    args = sys.argv[1:]
    only_id = args[args.index("--id") + 1] if "--id" in args else None
    asyncio.run(main(apply="--apply" in args, only_id=only_id))
