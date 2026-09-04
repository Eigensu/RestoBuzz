"""A Meta block on the template must park the campaign, not burn its queue.

Regression cover for the 2026-09-04 production incident: Meta paused a template
for low quality (error 132015) mid-campaign. Because 132015 went down the
generic transient-retry path, every still-queued recipient was being charged
retries it could never win — 14,840 of them were minutes away from being marked
permanently failed for a condition that was temporary and fixable.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from bson import ObjectId

from app.services.meta_api import MetaAPIError
from app.workers.send_task import _handle_meta_error


JOB_ID = ObjectId()
MSG_ID = str(ObjectId())

# Meta's verbatim wording for a low-quality pause.
META_132015 = (
    "(#132015) Template is temporarily unavailable to use because it was "
    "paused due to low quality."
)


def _make_db(pause_won: bool = True):
    db = AsyncMock()
    db.message_logs = AsyncMock()
    db.message_logs.update_one = AsyncMock()
    db.campaign_jobs = AsyncMock()
    # find_one_and_update(return_document=False) yields the pre-image, or None
    # when another worker already flipped the campaign out of a live status.
    db.campaign_jobs.find_one_and_update = AsyncMock(
        return_value={"_id": JOB_ID} if pause_won else None
    )
    db.campaign_jobs.update_one = AsyncMock()
    db.templates = AsyncMock()
    db.templates.update_one = AsyncMock()
    return db


def _make_msg(retry_count: int = 1):
    return {
        "job_id": JOB_ID,
        "template_name": "togather_b",
        "restaurant_id": "r2",
        "retry_count": retry_count,
    }


def _job_update(db):
    """(filter, update) passed to campaign_jobs.find_one_and_update."""
    args, _ = db.campaign_jobs.find_one_and_update.call_args
    return args[0], args[1]


def _msg_update(db):
    args, _ = db.message_logs.update_one.call_args
    return args[1]


@pytest.mark.asyncio
async def test_template_pause_pauses_the_campaign():
    db = _make_db()
    task = MagicMock()

    await _handle_meta_error(
        task, db, _make_msg(), MSG_ID, MetaAPIError("132015", META_132015)
    )

    filt, update = _job_update(db)
    assert update["$set"]["status"] == "paused"
    # Guarded: a campaign a human already paused or cancelled must not be
    # dragged back into an auto-paused state.
    assert filt["status"] == {"$in": ["running", "queued", "dispatching"]}


@pytest.mark.asyncio
async def test_template_pause_does_not_consume_a_retry():
    # The whole point: this send failed for a campaign-wide reason, so charging
    # the recipient a retry walks a recoverable message toward permanent death.
    db = _make_db()

    await _handle_meta_error(
        MagicMock(), db, _make_msg(), MSG_ID, MetaAPIError("132015", META_132015)
    )

    update = _msg_update(db)
    assert update["$set"]["status"] == "queued"
    assert "$inc" not in update


@pytest.mark.asyncio
async def test_template_pause_never_calls_task_retry():
    db = _make_db()
    task = MagicMock()

    await _handle_meta_error(
        task, db, _make_msg(), MSG_ID, MetaAPIError("132015", META_132015)
    )

    task.retry.assert_not_called()


@pytest.mark.asyncio
async def test_pause_reason_carries_metas_verbatim_message():
    # The dashboard shows this string directly, so it must survive untouched.
    db = _make_db()

    await _handle_meta_error(
        MagicMock(), db, _make_msg(), MSG_ID, MetaAPIError("132015", META_132015)
    )

    _, update = _job_update(db)
    reason = update["$set"]["pause_reason"]
    assert reason["message"] == META_132015
    assert reason["code"] == "132015"
    assert reason["template_name"] == "togather_b"
    assert reason["auto"] is True


@pytest.mark.asyncio
async def test_template_row_marked_paused_so_picker_stops_offering_it():
    db = _make_db()

    await _handle_meta_error(
        MagicMock(), db, _make_msg(), MSG_ID, MetaAPIError("132015", META_132015)
    )

    args, _ = db.templates.update_one.call_args
    assert args[0] == {"name": "togather_b", "restaurant_id": "r2"}
    assert args[1]["$set"]["status"] == "PAUSED"


@pytest.mark.asyncio
async def test_account_level_block_does_not_touch_the_template_row():
    # 131048 is an account-wide spam limit — the template itself is fine.
    db = _make_db()

    await _handle_meta_error(
        MagicMock(), db, _make_msg(), MSG_ID, MetaAPIError("131048", "Spam rate limit hit")
    )

    db.templates.update_one.assert_not_called()
    _, update = _job_update(db)
    assert update["$set"]["status"] == "paused"


@pytest.mark.asyncio
async def test_losing_the_pause_race_skips_the_template_write():
    # Another worker already paused the campaign; only the winner does the
    # follow-up writes so we don't stampede the templates collection.
    db = _make_db(pause_won=False)

    await _handle_meta_error(
        MagicMock(), db, _make_msg(), MSG_ID, MetaAPIError("132015", META_132015)
    )

    db.templates.update_one.assert_not_called()
    # The message is still returned to the queue by every worker that sees it.
    assert _msg_update(db)["$set"]["status"] == "queued"


@pytest.mark.asyncio
async def test_ordinary_transient_error_still_retries():
    # Regression guard: the blocking-code branch must not swallow the normal
    # retry path that every other transient failure depends on.
    db = _make_db()
    task = MagicMock()

    await _handle_meta_error(
        task, db, _make_msg(retry_count=1), MSG_ID, MetaAPIError("500", "Server error")
    )

    db.campaign_jobs.find_one_and_update.assert_not_called()
    update = _msg_update(db)
    assert update["$inc"] == {"retry_count": 1}
    task.retry.assert_called_once()


@pytest.mark.asyncio
async def test_exhausted_ordinary_error_still_fails_permanently():
    db = _make_db()
    task = MagicMock()

    await _handle_meta_error(
        task, db, _make_msg(retry_count=3), MSG_ID, MetaAPIError("500", "Server error")
    )

    assert _msg_update(db)["$set"]["status"] == "failed"
    task.retry.assert_not_called()
