from fastapi import APIRouter, Depends, Query, HTTPException
from bson import ObjectId
from app.database import get_db
from app.dependencies import require_role
from app.models.inbox import (
    ConversationListResponse, ConversationResponse,
    InboundMessageResponse, LocationData, ReplyRequest,
)
from app.services.meta_api import send_text_message
from app.config import settings

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    skip = (page - 1) * page_size
    pipeline = [
        {"$sort": {"received_at": -1}},
        {"$group": {
            "_id": "$from_phone",
            "sender_name": {"$first": "$sender_name"},
            "last_message": {"$first": "$body"},
            "last_message_type": {"$first": "$message_type"},
            "last_received_at": {"$first": "$received_at"},
            "unread_count": {"$sum": {"$cond": [{"$eq": ["$is_read", False]}, 1, 0]}},
        }},
        {"$sort": {"last_received_at": -1}},
        {"$facet": {
            "data": [{"$skip": skip}, {"$limit": page_size}],
            "total": [{"$count": "count"}],
        }},
    ]
    result = await db.inbound_messages.aggregate(pipeline).to_list(1)
    data = result[0]["data"] if result else []
    total = result[0]["total"][0]["count"] if result and result[0]["total"] else 0

    items = [
        ConversationResponse(
            from_phone=d["_id"],
            sender_name=d.get("sender_name"),
            last_message=d.get("last_message"),
            last_message_type=d.get("last_message_type", "text"),
            unread_count=d.get("unread_count", 0),
            last_received_at=d["last_received_at"],
        )
        for d in data
    ]
    return ConversationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/conversations/{phone}", response_model=list[InboundMessageResponse])
async def get_conversation(
    phone: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    skip = (page - 1) * page_size
    cursor = (
        db.inbound_messages.find({"from_phone": phone})
        .sort("received_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    items = []
    async for doc in cursor:
        loc = doc.get("location")
        items.append(InboundMessageResponse(
            id=str(doc["_id"]),
            wa_message_id=doc["wa_message_id"],
            from_phone=doc["from_phone"],
            sender_name=doc.get("sender_name"),
            message_type=doc.get("message_type", "unknown"),
            body=doc.get("body"),
            media_url=doc.get("media_url"),
            media_mime_type=doc.get("media_mime_type"),
            location=LocationData(**loc) if loc else None,
            is_read=doc.get("is_read", False),
            received_at=doc["received_at"],
        ))
    return items


@router.post("/conversations/{phone}/read")
async def mark_read(
    phone: str,
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    await db.inbound_messages.update_many(
        {"from_phone": phone, "is_read": False},
        {"$set": {"is_read": True}},
    )
    return {"status": "ok"}


@router.post("/conversations/{phone}/reply")
async def reply(
    phone: str,
    body: ReplyRequest,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    wa_id = await send_text_message(
        to=phone,
        body=body.body,
        phone_id=settings.meta_primary_phone_id,
        token=settings.meta_primary_access_token,
    )
    return {"wa_message_id": wa_id}
