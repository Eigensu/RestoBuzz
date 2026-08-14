import asyncio
from datetime import datetime, timezone, timedelta

import kombu.exceptions
from bson import ObjectId
from app.workers.celery_app import celery_app
from app.constants.meta_errors import RETRYABLE_FAILED_MATCH
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.services.campaign_service import create_child_retry_campaign
from app.workers.send_task import dispatch_campaign_task

logger = get_logger(__name__)

# Reused Mongo operator literals — named to avoid duplicated-literal warnings.
_EXISTS = "$exists"
_UNSET = "$unset"

# Statuses that mean "this child has not finished yet".
_PENDING_STATUSES = ["queued", "dispatching", "running"]

# How often a root may spawn a retry. Shared by the eligibility predicate and by
# the staleness bound below, so the two can never drift apart.
ROOT_RETRY_GATE_MINUTES = 120

# How long a pending child may sit before we stop believing it is in flight.
#
# A pending child blocks its root from spawning another retry, which is what
# prevents duplicate sends. But nothing else recovers a child stuck in 'running':
# dispatch flips the child to 'running' and only the *last* send marks it
# completed, so a send task lost to a worker restart leaves it running forever —
# and scheduled_poller deliberately never touches 'running'. Without an age bound
# that child wedges its whole retry chain permanently.
#
# Must sit STRICTLY above both the root gate and the longest a child can
# legitimately stay 'running'. A child stays running until its last message
# settles, and a message can take ~10 min on its own (max_retries=3 at a 30·4ⁿ
# backoff) on top of however long RATE_LIMIT_MPS takes to work through the
# recipient list — so a large campaign can legitimately run for hours. Reaping at
# the gate itself would collide with exactly that case.
#
# Reaping is still made safe rather than merely unlikely: _reap_stale_children
# marks the child 'cancelled', which is the one status the send path honours as
# "stop" (see _send in send_task.py). Even a misjudged reap therefore cannot
# double-send.
PENDING_CHILD_STALE_MINUTES = 360


def _child_age_clauses(now: datetime, still_fresh: bool) -> list[dict]:
    """Age predicate for a pending child, as $or branches.

    Age is measured from ``started_at`` (set when dispatch flips the child to
    'running'), falling back to ``created_at`` for a child that never got that
    far. ``still_fresh`` selects the comparison direction so the in-flight and
    stale filters stay exact complements of each other and cannot drift.
    """
    cutoff = now - timedelta(minutes=PENDING_CHILD_STALE_MINUTES)
    op = "$gt" if still_fresh else "$lte"
    return [
        {"started_at": {op: cutoff}},
        {"started_at": None, "created_at": {op: cutoff}},
        {"started_at": {_EXISTS: False}, "created_at": {op: cutoff}},
    ]


def _pending_child_filter(
    root_id: str, now: datetime, after: datetime | None
) -> dict:
    """Children still young enough to count as genuinely in flight.

    Only these block a new retry. ``after`` restricts the check to children newer
    than the latest finished one, matching the original duplicate-send guard.
    """
    flt: dict = {
        "parent_campaign_id": root_id,
        "status": {"$in": _PENDING_STATUSES},
        "$or": _child_age_clauses(now, still_fresh=True),
    }
    if after is not None:
        flt["created_at"] = {"$gt": after}
    return flt


def _stale_child_filter(root_id: str, now: datetime) -> dict:
    """Pending children old enough to be treated as dead rather than in flight.

    Exact complement of _pending_child_filter's age predicate. Not restricted by
    ``after``: any abandoned child in the chain should be reaped, not just ones
    newer than the latest finished child.
    """
    return {
        "parent_campaign_id": root_id,
        "status": {"$in": _PENDING_STATUSES},
        "$or": _child_age_clauses(now, still_fresh=False),
    }


async def _reap_stale_children(db, root_id: str, now: datetime) -> int:
    """Terminate pending children whose dispatch was lost. Returns how many.

    Marks them 'cancelled' rather than 'failed' deliberately. 'cancelled' is the
    only campaign status the send path treats as "stop": _send in send_task.py
    re-reads the parent's status *after* atomically claiming a message log, so a
    send task still alive for this child aborts instead of delivering. That makes
    reaping safe rather than merely unlikely to collide — even a misjudged reap
    cannot double-send. 'failed' would not do this; _send ignores it and delivers.

    Outstanding message logs are cancelled too, so rows stranded by a fan-out that
    died partway through don't sit 'queued' forever waiting on a worker that is
    never coming.
    """
    stale = await db.campaign_jobs.find(
        _stale_child_filter(root_id, now), {"_id": 1}
    ).to_list(length=None)
    if not stale:
        return 0

    stale_ids = [doc["_id"] for doc in stale]
    await db.campaign_jobs.update_many(
        {"_id": {"$in": stale_ids}},
        {"$set": {"status": "cancelled", "completed_at": now}},
    )
    # message_logs reference their campaign via job_id, not campaign_id.
    await db.message_logs.update_many(
        {"job_id": {"$in": stale_ids}, "status": {"$in": ["queued", "sending"]}},
        {"$set": {"status": "cancelled", "locked_until": None, "updated_at": now}},
    )
    logger.warning(
        "smart_retry_reaped_stale_children",
        root_id=root_id,
        child_ids=[str(cid) for cid in stale_ids],
        count=len(stale_ids),
        stale_after_minutes=PENDING_CHILD_STALE_MINUTES,
    )
    return len(stale_ids)


def _root_retry_eligibility(now: datetime, two_hours_ago: datetime) -> dict:
    """Full eligibility predicate for claiming a ROOT campaign's retry slot.

    Single source of truth shared by the polling prefilter (find) and the atomic
    claim (find_one_and_update) so the two can never drift and break the claim
    guarantee. Matches only root campaigns (no parent_campaign_id) that are
    finished, still within retry_until, and past the 2-hour last_auto_retry_at
    gate. Mirrors the reporting logic in _compute_retry_eligibility.
    """
    return {
        "smart_retries": True,
        "status": {"$in": ["completed", "failed"]},
        "retry_until": {"$gt": now},
        "$and": [
            # Only root campaigns — children have a parent_campaign_id set
            {
                "$or": [
                    {"parent_campaign_id": {_EXISTS: False}},
                    {"parent_campaign_id": None},
                ]
            },
            # 2-hour gate on the root
            {
                "$or": [
                    {"last_auto_retry_at": {_EXISTS: False}},
                    {"last_auto_retry_at": {"$lte": two_hours_ago}},
                ]
            },
        ],
    }


async def _rollback_child_campaign(db, new_job_id_str: str | None) -> None:
    """Delete a child retry campaign (and its message_logs) that was created by
    create_child_retry_campaign but never dispatched, so it isn't stranded in
    'queued' forever. No-op if no child was created."""
    if not new_job_id_str:
        return
    try:
        child_oid = ObjectId(new_job_id_str)
    except Exception:
        logger.exception(
            "smart_retry_rollback_invalid_child_id", child_id=new_job_id_str
        )
        return
    try:
        # message_logs reference the child via their job_id field (see
        # create_child_retry_campaign), not campaign_id/campaign_job_id.
        await db.message_logs.delete_many({"job_id": child_oid})
        await db.campaign_jobs.delete_one({"_id": child_oid})
    except Exception:
        logger.exception(
            "smart_retry_rollback_delete_failed", child_id=new_job_id_str
        )


@celery_app.task(name="app.workers.smart_retries_poller.poll_smart_retries")
def poll_smart_retries() -> None:
    asyncio.run(_poll())


async def _poll() -> None:
    db = get_fresh_db()
    try:
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(minutes=ROOT_RETRY_GATE_MINUTES)

        # Only poll ROOT campaigns that have actually finished running.
        # Children are never polled directly — the root tracks last_auto_retry_at
        # and we look up the latest completed child to source failures from.
        cursor = db.campaign_jobs.find(_root_retry_eligibility(now, two_hours_ago))
        async for root_job in cursor:
            root_id_obj = root_job["_id"]

            # Atomically claim the retry slot on the ROOT campaign. The filter
            # re-asserts the FULL eligibility predicate from the find() prefilter
            # (not just last_auto_retry_at) so a campaign that was cancelled, had
            # smart_retries toggled off, or aged past retry_until between the read
            # and the claim cannot be claimed.
            claimed = await db.campaign_jobs.find_one_and_update(
                {"_id": root_id_obj, **_root_retry_eligibility(now, two_hours_ago)},
                {"$set": {"last_auto_retry_at": now}},
                return_document=False,
            )

            if claimed is None:
                # Another worker beat us to it
                continue

            # Find the most recent completed/failed child in this chain.
            latest_child = await db.campaign_jobs.find_one(
                {
                    "parent_campaign_id": str(root_id_obj),
                    "status": {"$in": ["completed", "failed"]},
                },
                sort=[("created_at", -1)],
            )

            # Reap children whose dispatch was lost. Without this a child stuck in
            # 'running' blocks the pending guard below forever and the root can
            # never retry again.
            reaped_count = await _reap_stale_children(db, str(root_id_obj), now)
            if reaped_count:
                # latest_child was read before the reap, so it may now be stale.
                # Release the claim and let the next cycle re-read clean state.
                await db.campaign_jobs.update_one(
                    {"_id": root_id_obj}, {_UNSET: {"last_auto_retry_at": ""}}
                )
                continue

            # Guard against duplicate sends: if ANY child is still in flight
            # (queued/dispatching/running), roll back and wait for it to finish
            # before creating another one.  This covers two cases:
            #   a) latest_child is None — a child was dispatched but never completed
            #   b) latest_child exists — but a NEWER child is still running
            pending_child = await db.campaign_jobs.find_one(
                _pending_child_filter(
                    str(root_id_obj),
                    now,
                    latest_child["created_at"] if latest_child is not None else None,
                )
            )
            if pending_child is not None:
                logger.info(
                    "smart_retry_skipped_child_still_running",
                    root_id=str(root_id_obj),
                    child_id=str(pending_child["_id"]),
                    child_status=pending_child["status"],
                )
                await db.campaign_jobs.update_one(
                    {"_id": root_id_obj}, {_UNSET: {"last_auto_retry_at": ""}}
                )
                continue

            source_job = latest_child if latest_child else root_job

            source_id_obj = source_job["_id"]

            # Count actual failures in the source campaign. Must use the same
            # filter as the copy in create_child_retry_campaign, or we spawn a
            # child sized for failures it then declines to carry over.
            actual_failed = await db.message_logs.count_documents(
                {"job_id": source_id_obj, **RETRYABLE_FAILED_MATCH}
            )

            if actual_failed == 0:
                logger.info(
                    "smart_retry_skipped_no_failures",
                    root_id=str(root_id_obj),
                    source_id=str(source_id_obj),
                )
                continue

            # Spawn the child retry campaign
            new_job_id_str: str | None = None
            try:
                new_job_id_str = await create_child_retry_campaign(
                    source_job, actual_failed, db, root_job.get("created_by", "system")
                )

                dispatch_campaign_task.delay(new_job_id_str)
                logger.info(
                    "smart_retry_dispatched",
                    root_id=str(root_id_obj),
                    source_id=str(source_id_obj),
                    child_job_id=new_job_id_str,
                    failed_count=actual_failed,
                )
            except kombu.exceptions.KombuError:
                logger.exception(
                    "smart_retry_dispatch_broker_failed",
                    root_id=str(root_id_obj),
                )
                # Delete the orphaned (never-dispatched) child, then roll back the
                # claim so it retries on the next poll cycle.
                await _rollback_child_campaign(db, new_job_id_str)
                await db.campaign_jobs.update_one(
                    {"_id": root_id_obj}, {_UNSET: {"last_auto_retry_at": ""}}
                )
            except Exception:
                logger.exception(
                    "smart_retry_dispatch_failed", root_id=str(root_id_obj)
                )
                # Delete the orphaned (never-dispatched) child, then roll back the
                # claim so it retries on the next poll cycle.
                await _rollback_child_campaign(db, new_job_id_str)
                await db.campaign_jobs.update_one(
                    {"_id": root_id_obj}, {_UNSET: {"last_auto_retry_at": ""}}
                )
    finally:
        db.client.close()
