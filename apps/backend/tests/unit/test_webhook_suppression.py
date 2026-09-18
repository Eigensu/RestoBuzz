import pytest
from unittest.mock import AsyncMock, patch

from app.workers.webhook_task import _process_inbound_message

def _make_db():
    db = AsyncMock()
    # Mock inbound_messages upsert to succeed (not a duplicate)
    db.inbound_messages = AsyncMock()
    upsert_result = AsyncMock()
    upsert_result.upserted_id = "new_msg_id"
    db.inbound_messages.update_one = AsyncMock(return_value=upsert_result)
    
    # Mock identities finding
    db.wa_identities = AsyncMock()
    db.wa_identities.find_one = AsyncMock(return_value=None)
    db.wa_identities.update_one = AsyncMock()
    
    # Mock suppression list
    db.suppression_list = AsyncMock()
    db.suppression_list.update_one = AsyncMock()
    
    # Mock message_logs
    db.message_logs = AsyncMock()
    db.message_logs.find_one_and_update = AsyncMock(return_value=None)
    
    return db

@pytest.mark.asyncio
@patch("app.workers.webhook_task.add_suppression")
async def test_stop_keyword_suppresses_normalized_phone(mock_add_suppression):
    db = _make_db()
    
    msg = {
        "id": "wamid.123",
        "from": "919404814024",
        "type": "text",
        "text": {"body": "STOP"}
    }
    
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    
    contact_index = {
        "919404814024": {"phone": "919404814024", "name": "Tester"}
    }
    
    await _process_inbound_message(db, redis, msg, contact_index, "r1", "phone1")
    
    mock_add_suppression.assert_awaited_once_with(
        db, "+919404814024", reason="opt_out"
    )

@pytest.mark.asyncio
@patch("app.workers.webhook_task.add_suppression")
async def test_bsuid_fallback(mock_add_suppression):
    db = _make_db()
    
    msg = {
        "id": "wamid.456",
        "from_user_id": "IN.123456789",
        "type": "text",
        "text": {"body": "unsubscribe"}
    }
    
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    
    contact_index = {
        "IN.123456789": {"bsuid": "IN.123456789", "name": "Tester"}
    }
    
    await _process_inbound_message(db, redis, msg, contact_index, "r1", "phone1")
    
    mock_add_suppression.assert_awaited_once_with(
        db, "IN.123456789", reason="opt_out"
    )

