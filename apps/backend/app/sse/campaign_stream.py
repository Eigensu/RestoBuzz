import asyncio
import json
from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.database import get_db
from app.dependencies import require_role

router = APIRouter(tags=["sse"])

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@router.get("/campaigns/{campaign_id}/stream")
async def campaign_stream(
    campaign_id: str,
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    async def event_generator():
        while True:
            doc = await db.campaign_jobs.find_one(
                {"_id": ObjectId(campaign_id)},
                {"status": 1, "sent_count": 1, "delivered_count": 1, "read_count": 1,
                 "failed_count": 1, "total_count": 1},
            )
            if not doc:
                break

            data = {
                "status": doc["status"],
                "sent": doc.get("sent_count", 0),
                "delivered": doc.get("delivered_count", 0),
                "read": doc.get("read_count", 0),
                "failed": doc.get("failed_count", 0),
                "total": doc.get("total_count", 0),
            }
            yield f"data: {json.dumps(data)}\n\n"

            if doc["status"] in TERMINAL_STATUSES:
                break

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/inbox/stream")
async def inbox_stream(
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    """SSE stream for new inbound messages."""
    from datetime import datetime, timezone

    last_check = datetime.now(timezone.utc)

    async def event_generator():
        nonlocal last_check
        while True:
            cursor = db.inbound_messages.find(
                {"received_at": {"$gt": last_check}},
                {"from_phone": 1, "sender_name": 1, "body": 1, "message_type": 1, "received_at": 1},
            ).sort("received_at", 1)

            async for doc in cursor:
                data = {
                    "from_phone": doc["from_phone"],
                    "sender_name": doc.get("sender_name"),
                    "body": doc.get("body"),
                    "message_type": doc.get("message_type"),
                    "received_at": doc["received_at"].isoformat(),
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_check = doc["received_at"]

            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
