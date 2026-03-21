"""
Integration test: two concurrent workers claiming the same message.
Requires a running MongoDB + Redis (use docker compose).
Set INTEGRATION=1 to run.
"""
import os
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION") != "1",
    reason="Set INTEGRATION=1 to run integration tests",
)


@pytest.mark.asyncio
async def test_only_one_worker_claims_message():
    from app.database import get_db
    db = get_db()

    # Insert a queued message
    msg_id = (await db.message_logs.insert_one({
        "job_id": ObjectId(),
        "recipient_phone": "+12125550001",
        "recipient_name": "Test",
        "template_name": "hello_world",
        "template_variables": {},
        "wa_message_id": None,
        "status": "queued",
        "status_history": [],
        "retry_count": 0,
        "locked_until": None,
        "endpoint_used": None,
        "fallback_used": False,
        "error_code": None,
        "error_message": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })).inserted_id

    async def try_claim():
        now = datetime.now(timezone.utc)
        result = await db.message_logs.find_one_and_update(
            {"_id": msg_id, "status": "queued"},
            {"$set": {"status": "sending", "locked_until": now + timedelta(seconds=60)}},
            return_document=True,
        )
        return result is not None

    # Run two concurrent claims
    results = await asyncio.gather(try_claim(), try_claim())
    assert sum(results) == 1, "Exactly one worker should claim the message"

    # Cleanup
    await db.message_logs.delete_one({"_id": msg_id})
