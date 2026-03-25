import asyncio
import json
from bson import ObjectId
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from app.database import get_db
from app.dependencies import get_db as _get_db
from app.core.security import decode_token

router = APIRouter(tags=["sse"])

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


async def _user_from_token(token: str, db) -> dict:
    """Validate a raw JWT string (used for SSE query-param auth)."""
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not an access token"
        )
    from bson import ObjectId

    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User not found"
        )
    return user


@router.get("/campaigns/{campaign_id}/stream")
async def campaign_stream(
    campaign_id: str,
    token: str = Query(...),
    db=Depends(_get_db),
):
    await _user_from_token(token, db)

    async def event_generator():
        while True:
            doc = await db.campaign_jobs.find_one(
                {"_id": ObjectId(campaign_id)},
                {
                    "status": 1,
                    "sent_count": 1,
                    "delivered_count": 1,
                    "read_count": 1,
                    "failed_count": 1,
                    "total_count": 1,
                },
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
    token: str = Query(...),
    db=Depends(_get_db),
):
    """SSE stream for new inbound messages. Auth via ?token= query param (EventSource can't send headers)."""
    await _user_from_token(token, db)

    from datetime import datetime, timezone

    last_check = datetime.now(timezone.utc)

    async def event_generator():
        nonlocal last_check
        while True:
            cursor = db.inbound_messages.find(
                {"received_at": {"$gt": last_check}},
                {
                    "from_phone": 1,
                    "sender_name": 1,
                    "body": 1,
                    "message_type": 1,
                    "received_at": 1,
                },
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
