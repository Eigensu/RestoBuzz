"""Recover campaigns stranded in 'queued' (dispatch task lost, e.g. worker restart).

A 'Send Immediately' campaign sets status='queued' and fires dispatch_campaign_task
WITHOUT a claimed_at field. If that task is lost (worker redeploy/crash), the beat
poller cannot recover it (its self-heal branch requires claimed_at <= 5min-stale),
and Resume rejects a 'queued' job. Such jobs sit frozen forever.

Recovery strategy: rather than publish dispatch_campaign_task ourselves (which needs
a reachable Redis broker — impossible from a laptop, since Railway's Redis is on a
private network), we simply stamp an OLD claimed_at on the stuck job. Within ~60s the
scheduled_poller — running inside Railway where Redis resolves — matches its heal
branch (queued + stale claimed_at + no started_at), claims it, and dispatches it.

This is safe: dispatch_campaign_task only fans out message_logs still at status
'queued', and send_message_task atomically claims each — so already-sent messages are
never re-sent. Because we only need a Mongo write, this runs fine via `railway run`.

Usage:
    python scripts/redispatch_stuck_campaigns.py                 # list stuck jobs (dry run)
    python scripts/redispatch_stuck_campaigns.py --apply         # nudge all stuck jobs
    python scripts/redispatch_stuck_campaigns.py --apply --id <job_id>   # one specific job
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from bson import ObjectId

from app.config import settings

# Only treat as "stuck" if it's been queued for at least this long (avoid racing a
# dispatch that's legitimately in progress).
STUCK_MINUTES = 5


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


async def main(apply: bool, only_id: str | None) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = settings.mongodb_url
    db = AsyncIOMotorClient(mongo_url).get_database(_resolve_db_name(mongo_url))
    host = urlparse(mongo_url).hostname or "?"
    if host in ("localhost", "127.0.0.1"):
        print("⚠️  Connected to LOCALHOST — use `railway run` to hit production.\n")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=STUCK_MINUTES)
    # Stamp a claimed_at well past the poller's 5-min stale threshold so its
    # heal branch matches on the very next run (~60s).
    stale_claimed_at = now - timedelta(minutes=10)
    # No started_at filter: a job that began dispatching then stalled (started_at
    # set, status still queued/dispatching) is exactly the kind we want to nudge —
    # the scheduled_poller now recovers those too.
    query: dict = {"status": {"$in": ["queued", "dispatching"]}}
    if only_id:
        query = {"_id": ObjectId(only_id)}

    print(f"[{'APPLY' if apply else 'DRY RUN'}] scanning for stuck campaigns...\n")
    found = nudged = 0
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
            # Pure Mongo write — no broker needed. The in-Railway scheduled_poller
            # will claim + dispatch this within ~60s.
            await db.campaign_jobs.update_one(
                {"_id": job["_id"]}, {"$set": {"claimed_at": stale_claimed_at}}
            )
            nudged += 1

    print(f"\nStuck campaigns: {found}")
    if apply:
        print(f"Nudged: {nudged} — the scheduled_poller will dispatch within ~60s.")
        print("Watch the worker logs for 'scheduled_wa_campaign_dispatched'.")
    else:
        print("DRY RUN — nothing changed. Re-run with --apply (and --id to target one).")


if __name__ == "__main__":
    args = sys.argv[1:]
    only_id = args[args.index("--id") + 1] if "--id" in args else None
    asyncio.run(main(apply="--apply" in args, only_id=only_id))
