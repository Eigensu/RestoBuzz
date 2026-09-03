"""Tests for the durable per-member messaging rollup.

The whole point of this rollup is that it survives the message_logs TTL, so it
can never be recomputed from source. That makes double-counting permanent —
these tests pin the transition rules that prevent it.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import member_stats_service as stats

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _make_db():
    db = MagicMock()
    coll = AsyncMock()
    db.__getitem__ = MagicMock(return_value=coll)
    return db, coll


def _update(coll):
    """Return the update document passed to update_one."""
    args, _ = coll.update_one.call_args
    return args[1]


# ── received / read counters ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delivered_counts_as_received_once():
    db, coll = _make_db()
    await stats.record_status_change(db, "r1", "+919876543210", "sent", "delivered", NOW)
    assert _update(coll)["$inc"] == {"received_count": 1}


@pytest.mark.asyncio
async def test_redelivered_delivered_webhook_does_not_double_count():
    # Meta redelivers status webhooks. The Redis dedup is best-effort (it
    # expires), so the transition rule is the real guard.
    db, coll = _make_db()
    await stats.record_status_change(db, "r1", "+919876543210", "delivered", "delivered", NOW)
    coll.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_read_counts_read_and_received_when_delivered_was_missed():
    # WhatsApp can skip the 'delivered' webhook. A read message necessarily
    # arrived, so it must count toward received too — otherwise read > received.
    db, coll = _make_db()
    await stats.record_status_change(db, "r1", "+919876543210", "sent", "read", NOW)
    assert _update(coll)["$inc"] == {"read_count": 1, "received_count": 1}


@pytest.mark.asyncio
async def test_read_after_delivered_only_counts_read():
    db, coll = _make_db()
    await stats.record_status_change(db, "r1", "+919876543210", "delivered", "read", NOW)
    assert _update(coll)["$inc"] == {"read_count": 1}


@pytest.mark.asyncio
async def test_repeated_read_does_not_double_count():
    db, coll = _make_db()
    await stats.record_status_change(db, "r1", "+919876543210", "read", "read", NOW)
    coll.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_delivered_after_read_does_not_regress_counters():
    # Out-of-order webhooks must not add a second received for the same message.
    db, coll = _make_db()
    await stats.record_status_change(db, "r1", "+919876543210", "read", "delivered", NOW)
    coll.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_failed_status_touches_nothing():
    db, coll = _make_db()
    await stats.record_status_change(db, "r1", "+919876543210", "sent", "failed", NOW)
    coll.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_missing_restaurant_or_phone_is_a_noop():
    db, coll = _make_db()
    await stats.record_status_change(db, None, "+919876543210", "sent", "delivered", NOW)
    await stats.record_status_change(db, "r1", None, "sent", "delivered", NOW)
    await stats.record_status_change(db, "r1", "12345", "sent", "delivered", NOW)  # too short
    coll.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_write_failure_never_propagates():
    # Stats bookkeeping must not be able to break a send or a webhook.
    db, coll = _make_db()
    coll.update_one.side_effect = RuntimeError("mongo down")
    await stats.record_status_change(db, "r1", "+919876543210", "sent", "delivered", NOW)
    await stats.record_sent(db, "r1", "+919876543210", campaign_id="c1", at=NOW)


# ── phone matching ───────────────────────────────────────────────────────────


def test_phone_key_collapses_formatting_differences():
    # A member row, a Fielia card, and a message_log recipient must land on the
    # same key despite different formatting.
    assert (
        stats.phone_key("+91 98765-43210")
        == stats.phone_key("919876543210")
        == stats.phone_key("9876543210")
    )


def test_phone_key_rejects_fragments():
    assert stats.phone_key("98765") is None
    assert stats.phone_key(None) is None


# ── attribution window ───────────────────────────────────────────────────────


def _touch(days_before_join: float, campaign_id="c1"):
    return {"campaign_id": campaign_id, "at": NOW - timedelta(days=days_before_join)}


def test_touch_inside_window_attributes():
    assert stats.find_attributing_touch([_touch(3)], NOW)["campaign_id"] == "c1"


def test_touch_outside_window_does_not_attribute():
    assert stats.find_attributing_touch([_touch(30)], NOW) is None


def test_touch_after_join_does_not_attribute():
    # Messaging someone after they joined didn't cause them to join.
    later = {"campaign_id": "c1", "at": NOW + timedelta(days=1)}
    assert stats.find_attributing_touch([later], NOW) is None


def test_latest_qualifying_touch_wins():
    touches = [_touch(6, "old"), _touch(1, "recent")]
    assert stats.find_attributing_touch(touches, NOW)["campaign_id"] == "recent"


def test_naive_and_aware_datetimes_compare_without_raising():
    # Mongo hands back naive UTC; Fielia join dates arrive tz-aware.
    naive_touch = {"campaign_id": "c1", "at": (NOW - timedelta(days=2)).replace(tzinfo=None)}
    assert stats.find_attributing_touch([naive_touch], NOW)["campaign_id"] == "c1"

    aware_touch = {"campaign_id": "c2", "at": NOW - timedelta(days=2)}
    naive_join = NOW.replace(tzinfo=None)
    assert stats.find_attributing_touch([aware_touch], naive_join)["campaign_id"] == "c2"


def test_no_touches_or_no_join_date_is_unattributed():
    assert stats.find_attributing_touch([], NOW) is None
    assert stats.find_attributing_touch(None, NOW) is None
    assert stats.find_attributing_touch([_touch(1)], None) is None


# ── response merging ─────────────────────────────────────────────────────────


def test_apply_stats_defaults_to_zero_for_never_messaged_member():
    class Target:
        pass

    t = Target()
    stats.apply_stats(t, None)
    assert (t.messages_sent, t.messages_received, t.messages_read) == (0, 0, 0)
    assert t.last_message_at is None
