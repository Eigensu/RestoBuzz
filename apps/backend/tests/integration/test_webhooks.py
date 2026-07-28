"""Integration test: requires a running MongoDB. Set INTEGRATION=1 to run."""
import os

import pytest
from app.database import get_db

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION") != "1",
    reason="Set INTEGRATION=1 to run integration tests",
)


@pytest.mark.asyncio
async def test_webhook_error_collection_exists():
    db = get_db()
    errors = await db.webhook_errors.find().to_list(10)
    assert isinstance(errors, list)
    
    messages = await db.outbound_messages.find().to_list(10)
    assert isinstance(messages, list)
