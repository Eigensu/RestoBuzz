from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.database import get_db
from app.dependencies import get_active_restaurant, require_role
from app.models.inbox import (
    ConversationListResponse,
    ConversationResponse,
    InboundMessageResponse,
    LocationData,
    ReplyRequest,
)
from app.services.message_types import normalize_message_type
from app.services.meta_api import send_text_message

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
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    db: Annotated[Any, Depends(get_db)],
):
    """Return unread message count for the active restaurant."""
    count = await db.inbound_messages.count_documents(
        {
            "restaurant_id": restaurant["id"],
            "is_read": False,
            "is_resolved": {_MONGO_NE: True},
        }
    )
    return {"count": count}


@router.get("/conversations")
async def list_conversations(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    db: Annotated[Any, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 30,
) -> ConversationListResponse:
    """List conversations for the active restaurant only."""
    skip = (page - 1) * page_size
    since = datetime.now(timezone.utc) - timedelta(days=30)
    pipeline = [
        {
            _MONGO_MATCH: {
                "restaurant_id": restaurant["id"],
                "received_at": {_MONGO_GTE: since},
                "is_resolved": {_MONGO_NE: True},
            }
        },
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


@router.get("/conversations/{phone}")
async def get_conversation(
    phone: str,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    db: Annotated[Any, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[InboundMessageResponse]:
    """Return the full message thread for a phone number, scoped to the active restaurant.

    Outbound messages are matched by restaurant_id when present (new rows stamped
    after the per-restaurant migration) OR by the absence of restaurant_id (legacy
    rows created before scoping was introduced). This prevents historical replies
    from silently disappearing from the thread view during the migration window.
    Once a backfill script has stamped all legacy outbound rows, the $exists
    fallback can be removed.
    """
    skip = (page - 1) * page_size
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rid = restaurant["id"]

    wa_phones = restaurant.get("wa_phones", [])
    phone_ids = [p["phone_id"] for p in wa_phones if p.get("phone_id")]

    legacy_fallback: dict = {"restaurant_id": {"$exists": False}}
    if phone_ids:
        legacy_fallback["wa_phone_id"] = {"$in": phone_ids}

    # Outbound filter: scoped rows OR legacy unscoped rows (migration fallback)
    outbound_restaurant_filter = {
        "$or": [
            {"restaurant_id": rid},
            legacy_fallback,
        ]
    }

    pipeline = [
        {
            _MONGO_MATCH: {
                "from_phone": phone,
                "restaurant_id": rid,
                "received_at": {_MONGO_GTE: since},
            }
        },
        {_MONGO_ADD_FIELDS: {"direction": "inbound"}},
        {
            _MONGO_UNION: {
                "coll": "outbound_messages",
                "pipeline": [
                    {
                        _MONGO_MATCH: {
                            "to_phone": phone,
                            "sent_at": {_MONGO_GTE: since},
                            **outbound_restaurant_filter,
                        }
                    },
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

    items = []
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
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    db: Annotated[Any, Depends(get_db)],
):
    """Mark all messages from a phone number as read for the active restaurant."""
    await db.inbound_messages.update_many(
        {"from_phone": phone, "restaurant_id": restaurant["id"], "is_read": False},
        {_MONGO_SET: {"is_read": True}},
    )
    return {"status": "ok"}


@router.post("/conversations/{phone}/resolve")
async def resolve_conversation(
    phone: str,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    db: Annotated[Any, Depends(get_db)],
):
    """Resolve a conversation for the active restaurant."""
    await db.inbound_messages.update_many(
        {"from_phone": phone, "restaurant_id": restaurant["id"]},
        {_MONGO_SET: {"is_resolved": True}},
    )
    return {"status": "ok"}


@router.post("/conversations/{phone}/reply")
async def reply(
    phone: str,
    body: ReplyRequest,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
):
    """Send a reply to a phone number using the restaurant's own WABA credentials."""
    # Resolve restaurant-specific WABA credentials, fall back to global
    phone_id = settings.meta_primary_phone_id
    token = settings.meta_primary_access_token

    wa_phones = restaurant.get("wa_phones", [])
    if wa_phones:
        primary = wa_phones[0]
        rp = primary.get("phone_id") or ""
        env_key = primary.get("access_token_env_key") or ""
        if rp and env_key:
            rt = settings.resolve_waba_token(env_key) or ""
            if rt:
                phone_id = rp
                token = rt

    wa_id = await send_text_message(
        to=phone,
        body=body.body,
        phone_id=phone_id,
        token=token,
    )

    await db.outbound_messages.insert_one(
        {
            "wa_message_id": wa_id,
            "to_phone": phone,
            "body": body.body,
            "message_type": "text",
            "sent_by": str(current_user["_id"]),
            "sent_at": datetime.now(timezone.utc),
            "status": "sent",
            "restaurant_id": restaurant["id"],
            "wa_phone_id": phone_id,
        }
    )
    return {"wa_message_id": wa_id}
