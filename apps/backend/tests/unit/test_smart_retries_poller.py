from datetime import datetime, timezone, timedelta

from app.workers.smart_retries_poller import (
    PENDING_CHILD_STALE_MINUTES,
    ROOT_RETRY_GATE_MINUTES,
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
    for f, s in zip(fresh, stale, strict=True):
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


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return self._docs


class _FakeCollection:
    def __init__(self, docs=None):
        self._docs = docs or []
        self.updates = []

    def find(self, flt, projection=None):
        return _FakeCursor(self._docs)

    async def update_many(self, flt, update):
        self.updates.append((flt, update))


class _FakeDB:
    def __init__(self, children):
        self.campaign_jobs = _FakeCollection(children)
        self.message_logs = _FakeCollection()


async def test_reap_cancels_rather_than_fails_so_live_sends_abort():
    # The load-bearing safety property. _send in send_task.py aborts only on
    # 'cancelled' — it ignores 'failed' and delivers anyway. If this ever
    # regresses to 'failed', a reaped-but-still-live child keeps sending while the
    # next cycle spawns a duplicate for the same recipients.
    from app.workers.smart_retries_poller import _reap_stale_children

    db = _FakeDB([{"_id": "child1"}])
    count = await _reap_stale_children(db, "root1", _now())

    assert count == 1
    _, job_update = db.campaign_jobs.updates[0]
    assert job_update["$set"]["status"] == "cancelled"


async def test_reap_also_cancels_outstanding_message_logs():
    # Rows stranded by a fan-out that died partway through must not sit 'queued'
    # forever waiting on a worker that is never coming.
    from app.workers.smart_retries_poller import _reap_stale_children

    db = _FakeDB([{"_id": "child1"}])
    await _reap_stale_children(db, "root1", _now())

    log_filter, log_update = db.message_logs.updates[0]
    assert log_filter["job_id"] == {"$in": ["child1"]}
    assert log_filter["status"] == {"$in": ["queued", "sending"]}
    assert log_update["$set"]["status"] == "cancelled"


async def test_reap_is_a_noop_when_nothing_is_stale():
    from app.workers.smart_retries_poller import _reap_stale_children

    db = _FakeDB([])
    assert await _reap_stale_children(db, "root1", _now()) == 0
    assert db.campaign_jobs.updates == []
    assert db.message_logs.updates == []


def test_stale_threshold_strictly_exceeds_root_retry_gate():
    # Must be STRICTLY greater, not equal. At equality the reaper fires on exactly
    # the cycle the root becomes eligible again, so a child still legitimately
    # sending gets reaped and the next cycle spawns a duplicate for the same
    # recipients. A child can legitimately run for hours: a single message can
    # take ~10 min alone (max_retries=3 at 30·4ⁿ backoff) on top of RATE_LIMIT_MPS
    # pacing through the recipient list.
    assert PENDING_CHILD_STALE_MINUTES > ROOT_RETRY_GATE_MINUTES
