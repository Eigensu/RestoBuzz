"""One-off recovery: resume a campaign whose unsent messages were wrongly cancelled by a pause.

Background
----------
Before the pause/resume fix, pausing a running campaign did NOT requeue its
in-flight messages. The send tasks were already enqueued in the broker; as they
drained, each one saw the campaign was "paused" and marked its message_log as
"cancelled" (permanently). Resuming then found zero "queued" messages and
immediately marked the campaign "completed" without sending anything.

This script repairs such a campaign: it flips the pause-cancelled messages back
to "queued" and re-dispatches the campaign, so sending continues where it left
off. It ONLY touches messages cancelled by a pause (status_history entry with
meta.campaign_status == "paused"), never messages cancelled by an explicit
campaign cancel (meta.reason == "campaign_cancelled").

Usage:
    python scripts/resume_paused_campaign.py <campaign_id>            # dry run (no writes)
    python scripts/resume_paused_campaign.py <campaign_id> --apply    # repair + dispatch
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bson import ObjectId

# Resolve the DB exactly like the app/workers do (reads the root .env, honours
# MONGODB_URL_PROD / MONGODB_DB_NAME) so this always targets the same database.
from app.database import get_fresh_db

# Only messages cancelled *because of a pause* carry this marker in their
# status_history; user-cancelled messages carry meta.reason instead.
PAUSE_CANCELLED_FILTER = {
    "status": "cancelled",
    "status_history": {
        "$elemMatch": {"status": "cancelled", "meta.campaign_status": "paused"}
    },
}


async def resume(campaign_id: str, apply: bool) -> None:
    db = get_fresh_db()
    client = db.client

    mode = "APPLY" if apply else "DRY RUN"
    try:
        campaign_oid = ObjectId(campaign_id)
    except Exception:
        print(f"Invalid campaign id: {campaign_id!r}")
        client.close()
        return

    job = await db.campaign_jobs.find_one({"_id": campaign_oid})
    if not job:
        print(f"Campaign {campaign_id} not found in DB {db.name}")
        client.close()
        return

    print(f"[{mode}] Resume recovery on DB: {db.name}")
    print(f"  campaign : {job.get('name')} ({campaign_id})")
    print(f"  status   : {job.get('status')}")

    base = {"job_id": campaign_oid}
    queued = await db.message_logs.count_documents({**base, "status": "queued"})
    sent = await db.message_logs.count_documents({**base, "status": "sent"})
    failed = await db.message_logs.count_documents({**base, "status": "failed"})
    to_restore = await db.message_logs.count_documents(
        {**base, **PAUSE_CANCELLED_FILTER}
    )
    print(
        f"  messages : queued={queued} sent={sent} failed={failed} "
        f"pause_cancelled(restorable)={to_restore}"
    )

    if to_restore == 0 and queued == 0:
        print("\nNothing to resume — no pause-cancelled or queued messages found.")
        client.close()
        return

    if not apply:
        print(
            f"\n  DRY RUN — would restore {to_restore} message(s) to 'queued', set "
            "campaign to 'queued', and dispatch. Re-run with --apply to commit."
        )
        client.close()
        return

    now = datetime.now(timezone.utc)
    res = await db.message_logs.update_many(
        {**base, **PAUSE_CANCELLED_FILTER},
        {
            "$set": {"status": "queued", "locked_until": None, "updated_at": now},
            "$push": {
                "status_history": {
                    "status": "queued",
                    "timestamp": now,
                    "meta": {"reason": "resume_recovery"},
                }
            },
        },
    )
    print(f"  restored {res.modified_count} message(s) to 'queued'")

    await db.campaign_jobs.update_one(
        {"_id": campaign_oid}, {"$set": {"status": "queued"}}
    )
    print("  campaign status -> 'queued'")

    # Dispatch the same way the /campaigns/{id}/start endpoint does.
    from app.workers.send_task import dispatch_campaign_task

    dispatch_campaign_task.delay(campaign_id)
    print("  dispatched campaign task — sending will resume shortly.")
    client.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Usage: python scripts/resume_paused_campaign.py <campaign_id> [--apply]")
        sys.exit(1)
    asyncio.run(resume(args[0], apply="--apply" in sys.argv))
