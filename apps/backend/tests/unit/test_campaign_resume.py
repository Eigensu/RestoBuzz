"""Resuming a campaign must not strand or leak its Meta block reason.

`pause_reason` is unset before the dispatch is enqueued, which leaves two ways
to get it wrong: a failed dispatch rolls the status back but not the reason
(campaign sits 'paused' with no banner and no explanation — the exact mystery
state auto-pause exists to prevent), and the success path serialises the
pre-update document, pairing status 'queued' with a block that no longer
applies.
"""

import pytest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from fastapi import HTTPException

from app.routers.campaigns import start_campaign


CAMPAIGN_ID = str(ObjectId())

PAUSE_REASON = {
    "code": "132015",
    "summary": "Template paused by Meta for low quality",
    "message": "(#132015) Template is temporarily unavailable to use because it was paused due to low quality.",
    "template_name": "togather_b",
    "auto": True,
}


def _make_doc(**overrides):
    doc = {
        "_id": ObjectId(CAMPAIGN_ID),
        "restaurant_id": "r2",
        "name": "To",
        "template_id": "togather_b",
        "template_name": "togather_b",
        "priority": "MARKETING",
        "status": "paused",
        "created_by": "someone",
        "created_at": "2026-09-03T17:00:42",
        "pause_reason": dict(PAUSE_REASON),
    }
    doc.update(overrides)
    return doc


def _make_db(doc):
    db = AsyncMock()
    db.campaign_jobs = AsyncMock()
    db.campaign_jobs.find_one = AsyncMock(return_value=doc)
    db.campaign_jobs.update_one = AsyncMock()
    db.message_logs = AsyncMock()
    db.message_logs.update_many = AsyncMock()
    return db


def _sets(db):
    """Every $set payload written to campaign_jobs, in call order."""
    return [c.args[1]["$set"] for c in db.campaign_jobs.update_one.call_args_list]


@pytest.mark.asyncio
async def test_successful_resume_does_not_return_a_stale_block():
    doc = _make_doc()
    db = _make_db(doc)

    with patch("app.routers.campaigns.validate_restaurant_access", AsyncMock()), patch(
        "app.routers.campaigns.run_in_threadpool", AsyncMock()
    ):
        resp = await start_campaign(CAMPAIGN_ID, {"role": "admin"}, db)

    assert resp.status == "queued"
    # The dashboard keys the blocked banner off this field; a resumed campaign
    # must not still carry one.
    assert resp.pause_reason is None


@pytest.mark.asyncio
async def test_failed_dispatch_restores_the_block_reason():
    doc = _make_doc()
    db = _make_db(doc)

    with patch("app.routers.campaigns.validate_restaurant_access", AsyncMock()), patch(
        "app.routers.campaigns.run_in_threadpool",
        AsyncMock(side_effect=RuntimeError("broker down")),
    ):
        with pytest.raises(HTTPException) as exc:
            await start_campaign(CAMPAIGN_ID, {"role": "admin"}, db)

    assert exc.value.status_code == 503
    rollback = _sets(db)[-1]
    assert rollback["status"] == "paused"
    # Without this the campaign reads as paused for no stated reason.
    assert rollback["pause_reason"] == PAUSE_REASON


@pytest.mark.asyncio
async def test_failed_dispatch_on_a_draft_adds_no_phantom_reason():
    # A draft was never blocked, so rollback must not invent a pause_reason.
    doc = _make_doc(status="draft")
    doc.pop("pause_reason")
    db = _make_db(doc)

    with patch("app.routers.campaigns.validate_restaurant_access", AsyncMock()), patch(
        "app.routers.campaigns.run_in_threadpool",
        AsyncMock(side_effect=RuntimeError("broker down")),
    ):
        with pytest.raises(HTTPException):
            await start_campaign(CAMPAIGN_ID, {"role": "admin"}, db)

    rollback = _sets(db)[-1]
    assert rollback == {"status": "draft"}


@pytest.mark.asyncio
async def test_auto_pause_resume_hands_back_the_retry_budget():
    doc = _make_doc()
    db = _make_db(doc)

    with patch("app.routers.campaigns.validate_restaurant_access", AsyncMock()), patch(
        "app.routers.campaigns.run_in_threadpool", AsyncMock()
    ):
        await start_campaign(CAMPAIGN_ID, {"role": "admin"}, db)

    args, _ = db.message_logs.update_many.call_args
    assert args[0]["status"] == "queued"
    assert args[1] == {"$set": {"retry_count": 0}}


@pytest.mark.asyncio
async def test_manual_pause_resume_leaves_retry_counts_alone():
    # A human paused this one; the retries it spent were real per-recipient
    # failures and must not be forgiven.
    doc = _make_doc(pause_reason=None)
    db = _make_db(doc)

    with patch("app.routers.campaigns.validate_restaurant_access", AsyncMock()), patch(
        "app.routers.campaigns.run_in_threadpool", AsyncMock()
    ):
        await start_campaign(CAMPAIGN_ID, {"role": "admin"}, db)

    db.message_logs.update_many.assert_not_called()
