import pytest
from unittest.mock import AsyncMock

from app.workers.webhook_task import _handle_interested_reply


def _make_db(member_categories=None):
    db = AsyncMock()
    db.members = AsyncMock()
    db.members.update_one = AsyncMock()
    db.campaign_jobs = AsyncMock()
    db.campaign_jobs.find_one = AsyncMock(return_value={"name": "Summer Promo"})
    db.restaurants = AsyncMock()
    db.restaurants.find_one = AsyncMock(
        return_value=(
            {"member_categories": member_categories}
            if member_categories is not None
            else None
        )
    )
    return db


@pytest.mark.asyncio
async def test_positive_reply_upserts_interested_member():
    db = _make_db(member_categories=["nfc", "ecard"])
    orig_msg = {
        "restaurant_id": "r1",
        "job_id": "job123",
        "recipient_phone": "+919999999999",
        "recipient_name": "Asha",
    }

    await _handle_interested_reply(db, orig_msg, "Yes", "919999999999", "WA Asha")

    db.members.update_one.assert_awaited_once()
    args, kwargs = db.members.update_one.call_args
    flt, update = args[0], args[1]
    assert flt == {"restaurant_id": "r1", "phone": "+919999999999"}
    assert update["$addToSet"]["tags"] == "interested"
    # "interested" is a segment carried by the tag, never a member type: a new
    # respondent is filed under a real configured category so they still show
    # up on a category tab.
    assert update["$setOnInsert"]["type"] == "nfc"
    assert update["$set"]["interested_campaign_name"] == "Summer Promo"
    assert kwargs.get("upsert") is True


@pytest.mark.asyncio
async def test_non_keyword_reply_does_nothing():
    db = _make_db()
    orig_msg = {"restaurant_id": "r1", "job_id": "job123"}

    await _handle_interested_reply(db, orig_msg, "what time?", "919999999999", None)

    db.members.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_matched_campaign_does_nothing():
    db = _make_db()

    await _handle_interested_reply(db, None, "yes", "919999999999", None)

    db.members.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_respondent_type_falls_back_when_no_categories():
    """A restaurant with no categories configured still gets a usable type."""
    db = _make_db()
    orig_msg = {
        "restaurant_id": "r1",
        "job_id": "job123",
        "recipient_phone": "+919999999999",
    }

    await _handle_interested_reply(db, orig_msg, "yes", "919999999999", None)

    update = db.members.update_one.call_args.args[1]
    assert update["$setOnInsert"]["type"] == "ecard"
    assert update["$addToSet"]["tags"] == "interested"


@pytest.mark.asyncio
async def test_new_respondent_uses_first_configured_category():
    """Custom categories are honoured — nothing hardcodes nfc/ecard."""
    db = _make_db(member_categories=["vip", "regular"])
    orig_msg = {
        "restaurant_id": "r1",
        "job_id": "job123",
        "recipient_phone": "+919999999999",
    }

    await _handle_interested_reply(db, orig_msg, "yes", "919999999999", None)

    update = db.members.update_one.call_args.args[1]
    assert update["$setOnInsert"]["type"] == "vip"


@pytest.mark.asyncio
async def test_restaurant_id_falls_back_to_campaign_job():
    db = _make_db(member_categories=["nfc"])
    db.campaign_jobs.find_one = AsyncMock(
        return_value={"restaurant_id": "r9", "name": "Fallback Promo"}
    )
    orig_msg = {"job_id": "job123", "recipient_phone": "+910000000000"}

    await _handle_interested_reply(db, orig_msg, "interested", "910000000000", None)

    db.members.update_one.assert_awaited_once()
    flt = db.members.update_one.call_args.args[0]
    assert flt["restaurant_id"] == "r9"
