import pytest
from unittest.mock import AsyncMock

from app.workers.webhook_task import _apply_status_counters


def _make_db():
    db = AsyncMock()
    db.campaign_jobs = AsyncMock()
    db.campaign_jobs.update_one = AsyncMock()
    return db


def _inc(db):
    """Return the $inc dict passed to campaign_jobs.update_one."""
    args, _ = db.campaign_jobs.update_one.call_args
    return args[1]["$inc"]


@pytest.mark.asyncio
async def test_sent_then_failed_backs_out_sent_count():
    # A message Meta accepted (counted as sent in send_task) then dropped via a
    # failed delivery webhook must not be counted as BOTH sent and failed.
    db = _make_db()
    await _apply_status_counters(db, "job1", "sent", "failed")
    assert _inc(db) == {"failed_count": 1, "sent_count": -1}


@pytest.mark.asyncio
async def test_delivered_then_failed_still_backs_out_sent_count():
    db = _make_db()
    await _apply_status_counters(db, "job1", "delivered", "failed")
    assert _inc(db) == {"failed_count": 1, "sent_count": -1}


@pytest.mark.asyncio
async def test_failed_without_prior_send_does_not_touch_sent_count():
    # No prior successful send (e.g. a bad transition or missing prior status) —
    # only bump failed_count, never decrement sent below reality.
    db = _make_db()
    await _apply_status_counters(db, "job1", None, "failed")
    assert _inc(db) == {"failed_count": 1}


@pytest.mark.asyncio
async def test_delivered_increments_only_delivered():
    db = _make_db()
    await _apply_status_counters(db, "job1", "sent", "delivered")
    assert _inc(db) == {"delivered_count": 1}


@pytest.mark.asyncio
async def test_read_increments_only_read():
    db = _make_db()
    await _apply_status_counters(db, "job1", "delivered", "read")
    assert _inc(db) == {"read_count": 1}


@pytest.mark.asyncio
async def test_sent_webhook_is_noop_for_counters():
    # sent_count is owned by send_task; a 'sent' status webhook must not double it.
    db = _make_db()
    await _apply_status_counters(db, "job1", "sent", "sent")
    db.campaign_jobs.update_one.assert_not_awaited()
