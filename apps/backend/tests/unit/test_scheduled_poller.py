from datetime import datetime, timezone, timedelta

from app.workers.scheduled_poller import _recoverable_jobs_filter, STALE_MINUTES


def _has_key(obj, key: str) -> bool:
    """Recursively check whether `key` appears anywhere in a nested query dict."""
    if isinstance(obj, dict):
        return any(k == key or _has_key(v, key) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_key(v, key) for v in obj)
    return False


def _now():
    return datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_filter_does_not_gate_on_started_at():
    # The core gap 1 fix: a job that began dispatching then stalled (started_at
    # set, status still queued/dispatching) must remain recoverable, so the filter
    # must not constrain started_at at all.
    flt = _recoverable_jobs_filter(_now())
    assert not _has_key(flt, "started_at")


def test_filter_has_draft_and_stale_branches():
    flt = _recoverable_jobs_filter(_now())
    branches = flt["$or"]
    assert {"status": "draft", "scheduled_at": {"$lte": _now(), "$ne": None}} in branches
    stale = next(b for b in branches if b.get("status") == {"$in": ["queued", "dispatching"]})
    # staleness measured by claimed_at, with a created_at fallback for never-claimed
    # (Send Immediately) jobs.
    cutoff = _now() - timedelta(minutes=STALE_MINUTES)
    clauses = stale["$or"]
    assert {"claimed_at": {"$lte": cutoff}} in clauses
    assert {"claimed_at": None, "created_at": {"$lte": cutoff}} in clauses
    assert {"claimed_at": {"$exists": False}, "created_at": {"$lte": cutoff}} in clauses
