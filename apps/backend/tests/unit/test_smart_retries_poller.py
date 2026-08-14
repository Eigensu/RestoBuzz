from datetime import datetime, timezone, timedelta

from app.workers.smart_retries_poller import (
    PENDING_CHILD_STALE_MINUTES,
    _pending_child_filter,
    _stale_child_filter,
    _child_age_clauses,
)


def _now():
    return datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)


def _cutoff():
    return _now() - timedelta(minutes=PENDING_CHILD_STALE_MINUTES)


def test_pending_filter_is_age_bounded():
    # The core fix: a child stuck in 'running' must not block its root forever,
    # so the in-flight filter has to constrain age at all.
    flt = _pending_child_filter("root1", _now(), None)
    assert flt["$or"] == _child_age_clauses(_now(), still_fresh=True)


def test_pending_and_stale_filters_are_exact_complements():
    # If these two ever drift, a child could match neither and silently wedge the
    # chain again, or match both and be reaped while genuinely in flight.
    fresh = _child_age_clauses(_now(), still_fresh=True)
    stale = _child_age_clauses(_now(), still_fresh=False)

    assert [set(c.keys()) for c in fresh] == [set(c.keys()) for c in stale]
    for f, s in zip(fresh, stale):
        field = "started_at" if "$gt" in str(f.get("started_at")) else "created_at"
        assert f[field] == {"$gt": _cutoff()}
        assert s[field] == {"$lte": _cutoff()}


def test_age_measured_by_started_at_with_created_at_fallback():
    # A child that reached 'running' has started_at; one lost before dispatch
    # only has created_at. Both must be reapable.
    clauses = _child_age_clauses(_now(), still_fresh=False)
    assert {"started_at": {"$lte": _cutoff()}} in clauses
    assert {"started_at": None, "created_at": {"$lte": _cutoff()}} in clauses
    assert {"started_at": {"$exists": False}, "created_at": {"$lte": _cutoff()}} in clauses


def test_pending_filter_scopes_to_children_newer_than_latest_finished():
    after = datetime(2026, 8, 14, 9, 0, 0, tzinfo=timezone.utc)
    flt = _pending_child_filter("root1", _now(), after)
    assert flt["created_at"] == {"$gt": after}


def test_pending_filter_without_after_does_not_constrain_created_at_at_top_level():
    flt = _pending_child_filter("root1", _now(), None)
    assert "created_at" not in flt


def test_stale_filter_is_not_scoped_by_after():
    # Any abandoned child in the chain should be reaped, not only ones newer than
    # the latest finished child — otherwise an old orphan survives forever.
    flt = _stale_child_filter("root1", _now())
    assert "created_at" not in flt


def test_both_filters_match_only_unfinished_children_of_the_root():
    for flt in (
        _pending_child_filter("root1", _now(), None),
        _stale_child_filter("root1", _now()),
    ):
        assert flt["parent_campaign_id"] == "root1"
        assert flt["status"] == {"$in": ["queued", "dispatching", "running"]}


def test_stale_threshold_exceeds_root_retry_gate():
    # The root is gated to one retry per 2 hours; reaping sooner than that could
    # kill a child that is still legitimately working.
    assert PENDING_CHILD_STALE_MINUTES >= 120
