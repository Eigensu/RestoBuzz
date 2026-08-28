"""Tests for the member acquisition report.

Covers the bucketing that decides whether a new member is credited to
marketing — the number a business decision would be made on, so the boundary
between "we caused this" and "we were merely nearby" has to hold.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from bson import ObjectId

import app.routers.reports as reports

NOW = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
CAMPAIGN = ObjectId()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d

        return gen()


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, *a, **k):
        return _Cursor(self.docs)

    async def find_one(self, *a, **k):
        return self.docs[0] if self.docs else None


class _DB:
    def __init__(self, members, touches=None):
        self.members = _Coll(members)
        self.campaign_jobs = _Coll([{"_id": CAMPAIGN, "name": "Diwali Blast"}])
        self.stats = _Coll(touches or [])

    def __getitem__(self, name):
        return self.stats


def _member(phone, *, source, joined_at=NOW, campaign=None):
    return {
        "phone": phone,
        "name": "Member",
        "joined_at": joined_at,
        "source": source,
        "interested_campaign_id": campaign,
        "interested_campaign_name": "Diwali Blast" if campaign else None,
    }


def _touch_doc(phone_key, days_before):
    return {
        "phone_key": phone_key,
        "touches": [{"campaign_id": CAMPAIGN, "at": NOW - timedelta(days=days_before)}],
    }


async def _run(db):
    return await reports.member_acquisition(
        restaurant={"id": "r1", "_id": ObjectId()},
        current_user={"role": "admin"},
        db=db,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 29),
    )


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    async def _none(*a, **k):
        return None

    monkeypatch.setattr(reports, "_cache_get", _none)
    monkeypatch.setattr(reports, "_cache_set", _none)


@pytest.mark.asyncio
async def test_buckets_direct_assisted_and_organic():
    db = _DB(
        members=[
            _member("+919000000001", source="campaign_reply", campaign=CAMPAIGN),
            _member("+919000000002", source="excel"),
            _member("+919000000003", source="nfc"),
        ],
        touches=[_touch_doc("9000000002", days_before=2)],
    )
    result = await _run(db)
    s = result["summary"]

    assert s["new_members"] == 3
    assert s["direct"] == 1  # replied to the campaign
    assert s["assisted"] == 1  # messaged 2 days before joining
    assert s["organic"] == 1  # never messaged
    assert s["from_marketing"] == 2
    assert s["marketing_share"] == 66.7


@pytest.mark.asyncio
async def test_touch_outside_window_is_organic_not_assisted():
    # Messaged long before joining — crediting marketing here would be a lie.
    db = _DB(
        members=[_member("+919000000002", source="excel")],
        touches=[_touch_doc("9000000002", days_before=45)],
    )
    result = await _run(db)
    assert result["summary"]["assisted"] == 0
    assert result["summary"]["organic"] == 1


@pytest.mark.asyncio
async def test_reply_driven_member_is_direct_even_without_touch_history():
    # source='campaign_reply' is stamped at reply time and is causal on its own;
    # it must not depend on the touch rollup existing.
    db = _DB(
        members=[_member("+919000000001", source="campaign_reply", campaign=CAMPAIGN)],
        touches=[],
    )
    result = await _run(db)
    assert result["summary"]["direct"] == 1
    assert result["by_campaign"][0]["campaign_name"] == "Diwali Blast"


@pytest.mark.asyncio
async def test_campaign_breakdown_merges_both_bucket_types():
    db = _DB(
        members=[
            _member("+919000000001", source="campaign_reply", campaign=CAMPAIGN),
            _member("+919000000002", source="excel"),
        ],
        touches=[_touch_doc("9000000002", days_before=2)],
    )
    result = await _run(db)
    row = result["by_campaign"][0]
    assert (row["direct"], row["assisted"], row["total"]) == (1, 1, 2)


@pytest.mark.asyncio
async def test_no_new_members_does_not_divide_by_zero():
    result = await _run(_DB(members=[]))
    assert result["summary"] == {
        "new_members": 0,
        "from_marketing": 0,
        "direct": 0,
        "assisted": 0,
        "organic": 0,
        "marketing_share": 0,
    }


@pytest.mark.asyncio
async def test_response_carries_tracking_coverage_metadata():
    # The UI needs both to avoid presenting a coverage gap as a marketing result.
    result = await _run(_DB(members=[]))
    assert result["attribution_window_days"] == 7
    assert "tracking_started_at" in result
