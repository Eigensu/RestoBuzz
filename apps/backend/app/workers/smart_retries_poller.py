import asyncio
from datetime import datetime, timezone, timedelta

import kombu.exceptions
from bson import ObjectId
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger
from app.services.campaign_service import create_child_retry_campaign
from app.workers.send_task import dispatch_campaign_task

logger = get_logger(__name__)

# Reused Mongo operator literals — named to avoid duplicated-literal warnings.
_EXISTS = "$exists"
_UNSET = "$unset"


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
        two_hours_ago = now - timedelta(hours=2)

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

            # Guard against duplicate sends: if ANY child is still in flight
            # (queued/dispatching/running), roll back and wait for it to finish
            # before creating another one.  This covers two cases:
            #   a) latest_child is None — a child was dispatched but never completed
            #   b) latest_child exists — but a NEWER child is still running
            pending_filter: dict = {
                "parent_campaign_id": str(root_id_obj),
                "status": {"$in": ["queued", "dispatching", "running"]},
            }
            if latest_child is not None:
                pending_filter["created_at"] = {"$gt": latest_child["created_at"]}

            pending_child = await db.campaign_jobs.find_one(pending_filter)
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

            # Count actual failures in the source campaign
            actual_failed = await db.message_logs.count_documents(
                {"job_id": source_id_obj, "status": "failed"}
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
