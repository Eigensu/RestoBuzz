from fastapi import APIRouter, Depends, Query
from typing import Annotated, Any
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.dependencies import require_role, get_active_restaurant
from app.services.message_types import normalize_message_type
from app.models.inbox import (
    ConversationListResponse,
    ConversationResponse,
    InboundMessageResponse,
    LocationData,
    ReplyRequest,
)
from app.services.meta_api import send_text_message
from app.config import settings

# ── SonarCloud Hardening ──────────────────────────────────────────────────────
_MONGO_MATCH = "$match"
_MONGO_GROUP = "$group"
_MONGO_SORT = "$sort"
_MONGO_SUM = "$sum"
_MONGO_FIRST = "$first"
_MONGO_COUNT = "$count"
_MONGO_LIMIT = "$limit"
_MONGO_SKIP = "$skip"
_MONGO_FACET = "$facet"
_MONGO_SET = "$set"
_MONGO_ADD_FIELDS = "$addFields"
_MONGO_LOOKUP = "$lookup"
_MONGO_UNION = "$unionWith"
_MONGO_COND = "$cond"
_MONGO_EQ = "$eq"
_MONGO_NE = "$ne"
_MONGO_GTE = "$gte"

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/unread-count")
async def get_unread_count(
    db: Annotated[Any, Depends(get_db)] = None,
):
    # Global count
    count = await db.inbound_messages.count_documents(
        {"is_read": False, "is_resolved": {_MONGO_NE: True}}
    )
    return {"count": count}


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 30,
    db: Annotated[Any, Depends(get_db)] = None,
):
    skip = (page - 1) * page_size
    since = datetime.now(timezone.utc) - timedelta(days=30)
    pipeline = [
        {_MONGO_MATCH: {
            "received_at": {_MONGO_GTE: since},
            "is_resolved": {_MONGO_NE: True}
        }},
        {_MONGO_SORT: {"from_phone": 1, "received_at": -1}},
        {
            _MONGO_GROUP: {
                "_id": "$from_phone",
                "sender_name": {_MONGO_FIRST: "$sender_name"},
                "last_message": {_MONGO_FIRST: "$body"},
                "last_message_type": {_MONGO_FIRST: "$message_type"},
                "last_received_at": {_MONGO_FIRST: "$received_at"},
                "unread_count": {
                    _MONGO_SUM: {_MONGO_COND: [{_MONGO_EQ: ["$is_read", False]}, 1, 0]}
                },
                "is_resolved": {_MONGO_FIRST: "$is_resolved"},
            }
        },
        {_MONGO_SORT: {"last_received_at": -1}},
        {
            _MONGO_FACET: {
                "data": [{_MONGO_SKIP: skip}, {_MONGO_LIMIT: page_size}],
                "total": [{_MONGO_COUNT: "count"}],
            }
        },
    ]
    result = await db.inbound_messages.aggregate(pipeline).to_list(1)
    data = result[0]["data"] if result else []
    total = result[0]["total"][0]["count"] if result and result[0]["total"] else 0

    items = [
        ConversationResponse(
            from_phone=d["_id"],
            sender_name=d.get("sender_name"),
            last_message=d.get("last_message"),
            last_message_type=normalize_message_type(d.get("last_message_type")),
            unread_count=d.get("unread_count", 0),
            last_received_at=d["last_received_at"],
        )
        for d in data
    ]
    return ConversationListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/conversations/{phone}", response_model=list[InboundMessageResponse])
async def get_conversation(
    phone: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Annotated[Any, Depends(get_db)] = None,
):
    # Global view of conversation (all restaurants)
    skip = (page - 1) * page_size
    items = []

    # Limit to last 30 days
    since = datetime.now(timezone.utc) - timedelta(days=30)

    pipeline = [
        {_MONGO_MATCH: {"from_phone": phone, "received_at": {_MONGO_GTE: since}}},
        {_MONGO_ADD_FIELDS: {"direction": "inbound"}},
        {
            _MONGO_UNION: {
                "coll": "outbound_messages",
                "pipeline": [
                    {_MONGO_MATCH: {"to_phone": phone, "sent_at": {_MONGO_GTE: since}}},
                    {
                        _MONGO_ADD_FIELDS: {
                            "direction": "outbound",
                            "received_at": "$sent_at",
                            "from_phone": phone,
                            "sender_name": "You",
                        }
                    },
                ],
            }
        },
        {_MONGO_SORT: {"received_at": -1}},
        {_MONGO_SKIP: skip},
        {_MONGO_LIMIT: page_size},
    ]

    async for doc in db.inbound_messages.aggregate(pipeline):
        direction = doc.get("direction", "inbound")
        if direction == "inbound":
            loc = doc.get("location")
            items.append(
                InboundMessageResponse(
                    id=str(doc["_id"]),
                    wa_message_id=doc.get("wa_message_id", ""),
                    from_phone=doc["from_phone"],
                    sender_name=doc.get("sender_name"),
                    message_type=normalize_message_type(doc.get("message_type")),
                    body=doc.get("body"),
                    media_url=doc.get("media_url"),
                    media_mime_type=doc.get("media_mime_type"),
                    location=LocationData(**loc) if loc else None,
                    is_read=doc.get("is_read", False),
                    received_at=doc["received_at"],
                    direction="inbound",
                    status=None,
                )
            )
        else:
            items.append(
                InboundMessageResponse(
                    id=str(doc["_id"]),
                    wa_message_id=doc.get("wa_message_id", ""),
                    from_phone=doc["from_phone"],
                    sender_name=doc.get("sender_name", "You"),
                    message_type=normalize_message_type(doc.get("message_type")),
                    body=doc.get("body"),
                    media_url=doc.get("media_url"),
                    media_mime_type=doc.get("media_mime_type"),
                    location=None,
                    is_read=doc.get("status") == "read",
                    received_at=doc["received_at"],
                    direction="outbound",
                    status=doc.get("status", "sent"),
                )
            )

    return items


@router.post("/conversations/{phone}/read")
async def mark_read(
    phone: str,
    db: Annotated[Any, Depends(get_db)] = None,
):
    await db.inbound_messages.update_many(
        {"from_phone": phone, "is_read": False},
        {_MONGO_SET: {"is_read": True}},
    )
    return {"status": "ok"}


@router.post("/conversations/{phone}/resolve")
async def resolve_conversation(
    phone: str,
    db: Annotated[Any, Depends(get_db)] = None,
):
    await db.inbound_messages.update_many(
        {"from_phone": phone},
        {_MONGO_SET: {"is_resolved": True}},
    )
    return {"status": "ok"}


@router.post("/conversations/{phone}/reply")
async def reply(
    phone: str,
    body: ReplyRequest,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)] = None,
):
    wa_id = await send_text_message(
        to=phone,
        body=body.body,
        phone_id=settings.meta_primary_phone_id,
        token=settings.meta_primary_access_token,
    )
    # Save outbound reply without mandatory restaurant_id (global)
    await db.outbound_messages.insert_one(
        {
            "wa_message_id": wa_id,
            "to_phone": phone,
            "body": body.body,
            "message_type": "text",
            "sent_by": str(current_user["_id"]),
            "sent_at": datetime.now(timezone.utc),
            "status": "sent",
        }
    )
    return {"wa_message_id": wa_id}
