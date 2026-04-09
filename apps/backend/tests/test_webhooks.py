import pytest
from app.database import get_db

@pytest.mark.asyncio
async def test_webhook_error_collection_exists():
    async for db in get_db():
        errors = await db.webhook_errors.find().to_list(10)
        assert isinstance(errors, list)
        
        messages = await db.outbound_messages.find().to_list(10)
        assert isinstance(messages, list)
