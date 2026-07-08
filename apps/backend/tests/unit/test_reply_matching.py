import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.workers.webhook_task import _find_and_mark_replied


@pytest.mark.asyncio
async def test_quote_reply_matches_by_wa_message_id():
    db = AsyncMock()
    db.message_logs = AsyncMock()
    db.message_logs.find_one_and_update = AsyncMock(return_value={"job_id": "j"})

    await _find_and_mark_replied(
        db, "wamid.ABC", "919999999999", datetime.now(timezone.utc)
    )

    flt = db.message_logs.find_one_and_update.call_args[0][0]
    assert flt["wa_message_id"] == "wamid.ABC"


@pytest.mark.asyncio
async def test_plain_reply_window_keys_off_sent_at_not_created_at():
    # The bug this guards: a campaign that sat queued for days has an old
    # created_at, so the reply window must key off the real send time (sent_at),
    # with created_at only as a legacy fallback.
    db = AsyncMock()
    db.message_logs = AsyncMock()
    db.message_logs.find_one_and_update = AsyncMock(return_value=None)

    now = datetime.now(timezone.utc)
    await _find_and_mark_replied(db, None, "919999999999", now)

    call = db.message_logs.find_one_and_update.call_args
    flt = call[0][0]
    # only messages actually sent can be replied to
    assert flt["status"] == {"$in": ["sent", "delivered", "read"]}
    branches = flt["$or"]
    assert any("sent_at" in b and "created_at" not in b for b in branches)
    assert any("sent_at" in b and "created_at" in b for b in branches)  # legacy fallback
    # newest send first
    assert call.kwargs["sort"] == [("sent_at", -1), ("created_at", -1)]
