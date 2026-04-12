import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import (
    require_role,
    require_restaurant_access,
    validate_restaurant_access,
)
from app.core.utils import to_object_id
from app.core.logging import get_logger
from app.core.errors import (
    CampaignNotFoundError,
    ContactFileExpiredError,
    ServerError,
    ValidationError,
)
from app.models.campaign import CampaignCreate, CampaignResponse, CampaignListResponse
from app.models.campaign import (
    CampaignTestMessageRequest,
    CampaignTestMessageResponse,
)
from app.models.message import (
    MessageLogListResponse,
    MessageLogResponse,
    StatusHistoryEntry,
)
from app.services.meta_api import send_template_message

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
logger = get_logger(__name__)

# ── MongoDB aggregation stage key constants ───────────────────────────────────
_MATCH = "$match"
_GROUP = "$group"
_SORT = "$sort"
_CREATED_AT = "$created_at"
_BODY_VAR_RE = re.compile(r"\{\{(\d+)\}\}")


def _template_body_var_keys(template_doc: dict | None) -> set[str]:
    if not template_doc:
        return set()

    components = template_doc.get("components") or []
    keys: set[str] = set()
    for component in components:
        if component.get("type") != "BODY":
            continue
        text = str(component.get("text") or "")
        keys.update(_BODY_VAR_RE.findall(text))
    return keys


def _sanitize_template_variables(
    variables: dict | None, allowed_keys: set[str]
) -> dict:
    if not variables or not allowed_keys:
        return {}

    cleaned: dict[str, str] = {}
    for key, value in variables.items():
        normalized_key = str(key).strip()
        if normalized_key not in allowed_keys:
            continue
        normalized_value = str(value).strip()
        if not normalized_value:
            continue
        cleaned[normalized_key] = normalized_value
    return cleaned


def _serialize_campaign(doc: dict) -> CampaignResponse:
    return CampaignResponse(
        id=str(doc["_id"]),
        restaurant_id=doc.get("restaurant_id", ""),
        name=doc["name"],
        template_id=doc["template_id"],
        template_name=doc["template_name"],
        priority=doc["priority"],
        status=doc["status"],
        total_count=doc.get("total_count", 0),
        sent_count=doc.get("sent_count", 0),
        delivered_count=doc.get("delivered_count", 0),
        read_count=doc.get("read_count", 0),
        failed_count=doc.get("failed_count", 0),
        replies_count=doc.get("replies_count", 0),
        scheduled_at=doc.get("scheduled_at"),
        started_at=doc.get("started_at"),
        completed_at=doc.get("completed_at"),
        created_by=str(doc["created_by"]),
        include_unsubscribe=doc.get("include_unsubscribe", True),
        created_at=doc["created_at"],
        parent_campaign_id=(
            str(doc["parent_campaign_id"]) if doc.get("parent_campaign_id") else None
        ),
    )


@router.get(
    "",
    response_model=CampaignListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_campaigns(
    validated_rid: Annotated[str, Depends(require_restaurant_access())],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    skip = (page - 1) * page_size
    query = {"restaurant_id": validated_rid}
    total = await db.campaign_jobs.count_documents(query)
    cursor = (
        db.campaign_jobs.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    )
    items = [_serialize_campaign(doc) async for doc in cursor]
    return CampaignListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # Validate access manually since it's in the body
    await validate_restaurant_access(current_user, body.restaurant_id, db)
    from redis.asyncio import from_url
    from redis.exceptions import RedisError as RedisClientError
    from app.config import settings

    raw = None
    try:
        redis = from_url(settings.redis_url, decode_responses=True)
        raw = await redis.get(f"file_ref:{body.contact_file_ref}")
        await redis.aclose()
    except (RedisClientError, OSError) as e:
        logger.warning(
            "campaign_create_cache_unavailable",
            error=str(e),
            file_ref=body.contact_file_ref,
        )
        # Proceed to fallback

    if not raw:
        # FALLBACK: Check MongoDB directly if Redis is down or cache expired
        doc = await db.contact_files.find_one(
            {"result.file_ref": body.contact_file_ref}
        )
        if not doc:
            raise ContactFileExpiredError(
                "Contact file reference expired or not found. Please re-upload your contacts."
            )
        contacts = doc["result"]["valid_rows"]
    else:
        contacts = json.loads(raw)

    template_doc = await db.templates.find_one(
        {"name": body.template_name}, {"components": 1}
    )
    allowed_var_keys = _template_body_var_keys(template_doc)
    campaign_template_variables = _sanitize_template_variables(
        body.template_variables, allowed_var_keys
    )

    now = datetime.now(timezone.utc)

    job_doc = {
        "restaurant_id": body.restaurant_id,
        "name": body.name,
        "template_id": body.template_id,
        "template_name": body.template_name,
        "template_variables": campaign_template_variables,
        "media_url": body.media_url,
        "priority": body.priority,
        "status": "draft",
        "total_count": len(contacts),
        "sent_count": 0,
        "delivered_count": 0,
        "read_count": 0,
        "failed_count": 0,
        "replies_count": 0,
        "scheduled_at": body.scheduled_at,
        "started_at": None,
        "completed_at": None,
        "created_by": current_user["_id"],
        "include_unsubscribe": body.include_unsubscribe,
        "created_at": now,
    }
    result = await db.campaign_jobs.insert_one(job_doc)
    job_id = result.inserted_id

    # WhatsApp requires a phone for every message — strip email-only contacts.
    phone_contacts = [c for c in contacts if c.get("phone")]
    if not phone_contacts:
        raise ValidationError(
            "No contacts with a valid phone number found. "
            "WhatsApp campaigns require a phone number for every recipient."
        )

    message_docs = [
        {
            "job_id": job_id,
            "recipient_phone": c["phone"],
            "recipient_name": c.get("name", ""),
            "template_name": body.template_name,
            "template_variables": _sanitize_template_variables(
                {**campaign_template_variables, **c.get("variables", {})},
                allowed_var_keys,
            ),
            "media_url": body.media_url,
            "wa_message_id": None,
            "status": "queued",
            "status_history": [],
            "retry_count": 0,
            "locked_until": None,
            "endpoint_used": None,
            "fallback_used": False,
            "error_code": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        for c in phone_contacts
    ]
    if message_docs:
        try:
            await db.message_logs.insert_many(message_docs)
        except Exception as e:
            await db.campaign_jobs.delete_one({"_id": job_id})
            logger.error(
                "campaign_create_message_logs_error",
                campaign_id=str(job_id),
                error=str(e),
            )
            raise ServerError("Failed to create message logs") from e

    # ── Dispatch or schedule ──────────────────────────────────────────────────
    if body.scheduled_at is None:
        # Send Immediately: transition to queued and fire the Celery task now.
        await db.campaign_jobs.update_one(
            {"_id": job_id}, {"$set": {"status": "queued"}}
        )
        from app.workers.send_task import dispatch_campaign_task

        dispatch_campaign_task.delay(str(job_id))
        job_doc["status"] = "queued"
        logger.info("campaign_dispatched_immediately", campaign_id=str(job_id))
    else:
        # Scheduled: leave as draft — the Beat poller will pick it up.
        logger.info(
            "campaign_scheduled",
            campaign_id=str(job_id),
            scheduled_at=body.scheduled_at.isoformat(),
        )

    job_doc["_id"] = job_id
    return _serialize_campaign(job_doc)


@router.post("/test-message", response_model=CampaignTestMessageResponse)
async def send_test_message(
    body: CampaignTestMessageRequest,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    await validate_restaurant_access(current_user, body.restaurant_id, db)

    # Reuse the template's configured language when available.
    template_doc = await db.templates.find_one(
        {"name": body.template_name}, {"language": 1, "components": 1}
    )
    language = (template_doc or {}).get("language") or "en_US"
    allowed_var_keys = _template_body_var_keys(template_doc)
    request_variables = _sanitize_template_variables(
        body.template_variables, allowed_var_keys
    )

    to_phone = body.to_phone.strip()
    if not to_phone:
        raise ValidationError("Phone number is required")

    wa_message_id, endpoint_used = await send_template_message(
        to=to_phone,
        template_name=body.template_name,
        variables=request_variables,
        media_url=body.media_url,
        language=language,
    )
    resolved_endpoint = "fallback" if endpoint_used == "fallback" else "primary"

    return CampaignTestMessageResponse(
        wa_message_id=wa_message_id,
        endpoint_used=resolved_endpoint,
    )


@router.get("/analytics")
async def get_analytics(
    validated_rid: Annotated[str, Depends(require_restaurant_access())],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """
    Returns real aggregated analytics for the restaurant:
    - failure_breakdown: actual error_message counts from message_logs
    - ttr_distribution: real time-to-read buckets from status_history
    - hourly_performance: actual send-hour distribution from message_logs
    """
    # Get all campaign job IDs for this restaurant
    campaign_ids = [
        doc["_id"]
        async for doc in db.campaign_jobs.find(
            {"restaurant_id": validated_rid}, {"_id": 1}
        )
    ]

    if not campaign_ids:
        return {
            "totals": {"sent": 0, "delivered": 0, "read": 0, "failed": 0},
            "failure_breakdown": [],
            "ttr_distribution": [
                {"range": "0-5 min", "count": 0},
                {"range": "5-30 min", "count": 0},
                {"range": "30-120 min", "count": 0},
                {"range": "2h+", "count": 0},
            ],
            "hourly_performance": [
                {
                    "hour": f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}",
                    "rate": 0,
                    "delivered": 0,
                }
                for h in range(24)
            ],
        }

    base_match = {"job_id": {"$in": campaign_ids}}

    # ── 1. Totals ─────────────────────────────────────────────────────────────
    totals_cursor = db.campaign_jobs.aggregate(
        [
            {_MATCH: {"restaurant_id": validated_rid}},
            {
                _GROUP: {
                    "_id": None,
                    "sent": {"$sum": "$sent_count"},
                    "delivered": {"$sum": "$delivered_count"},
                    "read": {"$sum": "$read_count"},
                    "failed": {"$sum": "$failed_count"},
                    "replies": {"$sum": "$replies_count"},
                    "total_campaigns": {"$sum": 1},
                }
            },
        ]
    )
    totals_list = await totals_cursor.to_list(1)
    totals_dict = totals_list[0] if totals_list else {"sent": 0, "delivered": 0, "read": 0, "failed": 0, "replies": 0, "total_campaigns": 0}
    totals = {
        "sent": totals_dict.get("sent", 0),
        "delivered": totals_dict.get("delivered", 0),
        "read": totals_dict.get("read", 0),
        "failed": totals_dict.get("failed", 0),
        "replies": totals_dict.get("replies", 0),
        "total_campaigns": totals_dict.get("total_campaigns", 0),
    }

    # ── 2. Failure Breakdown ──────────────────────────────────────────────────
    failure_cursor = db.message_logs.aggregate(
        [
            {_MATCH: {**base_match, "status": "failed"}},
            {_GROUP: {"_id": "$error_message", "count": {"$sum": 1}}},
            {_SORT: {"count": -1}},
            {"$limit": 10},
        ]
    )
    failure_results = [
        {"reason": r["_id"] or "Unknown", "count": r["count"]}
        async for r in failure_cursor
    ]

    # ── 3. TTR Distribution ───────────────────────────────────────────────────
    # For each message that reached "read" status, find the timestamp of the
    # first "read" entry in status_history and diff against sent_at.
    ttr_cursor = db.message_logs.aggregate(
        [
            {_MATCH: {**base_match, "status": "read"}},
            {
                "$addFields": {
                    "sent_locs": {
                        "$filter": {
                            "input": "$status_history",
                            "as": "sh",
                            "cond": {"$in": ["$$sh.status", ["sent", "delivered"]]},
                        }
                    }
                }
            },
            {
                "$addFields": {
                    "sent_at": {
                        "$cond": [
                            {"$gt": [{"$size": "$sent_locs"}, 0]},
                            {"$arrayElemAt": ["$sent_locs.timestamp", 0]},
                            _CREATED_AT,
                        ]
                    }
                }
            },
            # Unwind status_history to find the first "read" event
            {"$unwind": "$status_history"},
            {_MATCH: {"status_history.status": "read"}},
            # Keep only the earliest read event per message
            {_SORT: {"status_history.timestamp": 1}},
            {
                _GROUP: {
                    "_id": "$_id",
                    "sent_at": {"$first": "$sent_at"},
                    "read_at": {"$first": "$status_history.timestamp"},
                }
            },
            # Compute diff in minutes
            {
                "$addFields": {
                    "minutes": {
                        "$divide": [
                            {"$subtract": ["$read_at", "$sent_at"]},
                            60000,  # ms -> minutes
                        ]
                    }
                }
            },
            # Bucket into ranges
            {
                "$bucket": {
                    "groupBy": "$minutes",
                    "boundaries": [0, 5, 30, 120],
                    "default": "2h+",
                    "output": {"count": {"$sum": 1}},
                }
            },
        ]
    )

    ttr_raw = {r["_id"]: r["count"] async for r in ttr_cursor}
    ttr_distribution = [
        {"range": "0-5 min", "count": ttr_raw.get(0, 0)},
        {"range": "5-30 min", "count": ttr_raw.get(5, 0)},
        {"range": "30-120 min", "count": ttr_raw.get(30, 0)},
        {"range": "2h+", "count": ttr_raw.get("2h+", 0)},
    ]

    # ── 3. Hourly Performance ─────────────────────────────────────────────────
    # Group message_logs by the hour of their created_at (actual send time),
    # counting delivered and read messages per hour.
    hourly_cursor = db.message_logs.aggregate(
        [
            {_MATCH: {**base_match, "status": {"$in": ["delivered", "read"]}}},
            {"$addFields": {"hour": {"$hour": "$updated_at"}}},
            {
                _GROUP: {
                    "_id": "$hour",
                    "delivered": {"$sum": 1},
                    "read": {"$sum": {"$cond": [{"$eq": ["$status", "read"]}, 1, 0]}},
                }
            },
        ]
    )

    hourly_map: dict[int, dict] = {
        r["_id"]: {"delivered": r["delivered"], "read": r["read"]}
        async for r in hourly_cursor
    }

    hourly_performance = []
    for h in range(24):
        stats = hourly_map.get(h, {"delivered": 0, "read": 0})
        rate = (
            (stats["read"] / stats["delivered"] * 100) if stats["delivered"] > 0 else 0
        )
        period = "AM" if h < 12 else "PM"
        display_hour = h % 12 or 12
        hourly_performance.append(
            {
                "hour": f"{display_hour} {period}",
                "rate": round(rate, 2),
                "delivered": stats["delivered"],
            }
        )

    return {
        "totals": totals,
        "failure_breakdown": failure_results,
        "ttr_distribution": ttr_distribution,
        "hourly_performance": hourly_performance,
    }


@router.get("/{campaign_id}/group")
async def get_campaign_group(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """
    Returns the full retry chain for a campaign plus aggregate effective-reach stats.
    The root campaign is the one with no parent_campaign_id.
    All retries share the same parent_campaign_id pointing to the root.
    """
    campaign_oid = to_object_id(campaign_id)
    doc = await db.campaign_jobs.find_one({"_id": campaign_oid})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    # Resolve root
    root_oid = doc.get("parent_campaign_id") or campaign_oid

    # Fetch root + all retries
    cursor = db.campaign_jobs.find(
        {"$or": [{"_id": root_oid}, {"parent_campaign_id": root_oid}]}
    ).sort("created_at", 1)
    chain = [_serialize_campaign(d) async for d in cursor]

    if not chain:
        chain = [_serialize_campaign(doc)]

    root = chain[0]
    # Effective reach = original total minus the final campaign's remaining failures
    last = chain[-1]
    effective_sent = root.total_count - last.failed_count

    return {
        "root_id": str(root_oid),
        "original_total": root.total_count,
        "effective_sent": max(0, effective_sent),
        "effective_pct": (
            round(max(0, effective_sent) / root.total_count * 100, 1)
            if root.total_count > 0
            else 0
        ),
        "retry_count": len(chain) - 1,
        "campaigns": chain,
    }


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/start", response_model=CampaignResponse)
async def start_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    if doc["status"] not in ("draft", "paused"):
        raise ValidationError(f"Cannot start a campaign with status '{doc['status']}'")

    await db.campaign_jobs.update_one(
        {"_id": to_object_id(campaign_id)}, {"$set": {"status": "queued"}}
    )

    from app.workers.send_task import dispatch_campaign_task

    dispatch_campaign_task.delay(campaign_id)

    doc["status"] = "queued"
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # Fetch first to check ownership/access
    doc = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    doc = await db.campaign_jobs.find_one_and_update(
        {"_id": to_object_id(campaign_id), "status": "running"},
        {"$set": {"status": "paused"}},
        return_document=True,
    )
    if not doc:
        raise ValidationError("Campaign is not currently running")
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
async def cancel_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # Fetch first to check ownership/access
    doc = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    doc = await db.campaign_jobs.find_one_and_update(
        {
            "_id": to_object_id(campaign_id),
            "status": {"$in": ["draft", "queued", "running", "paused"]},
        },
        {
            "$set": {
                "status": "cancelled",
                "completed_at": datetime.now(timezone.utc),
            }
        },
        return_document=True,
    )
    if not doc:
        raise ValidationError("Campaign cannot be cancelled in its current state")

    await db.message_logs.update_many(
        {"job_id": to_object_id(campaign_id), "status": {"$in": ["queued", "sending"]}},
        {
            "$set": {
                "status": "cancelled",
                "locked_until": None,
                "updated_at": datetime.now(timezone.utc),
            },
            "$push": {
                "status_history": {
                    "status": "cancelled",
                    "timestamp": datetime.now(timezone.utc),
                    "meta": {"reason": "campaign_cancelled"},
                }
            },
        },
    )
    return _serialize_campaign(doc)


@router.get("/{campaign_id}/messages", response_model=MessageLogListResponse)
async def list_messages(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[str | None, Query()] = None,
):
    # Fetch job to verify access
    job = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not job:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, job["restaurant_id"], db)

    query: dict = {"job_id": to_object_id(campaign_id)}
    if status:
        query["status"] = status

    skip = (page - 1) * page_size
    total = await db.message_logs.count_documents(query)
    cursor = (
        db.message_logs.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    )

    items = []
    async for doc in cursor:
        items.append(
            MessageLogResponse(
                id=str(doc["_id"]),
                job_id=str(doc["job_id"]),
                recipient_phone=doc["recipient_phone"],
                recipient_name=doc.get("recipient_name", ""),
                wa_message_id=doc.get("wa_message_id"),
                status=doc["status"],
                status_history=[
                    StatusHistoryEntry(**h) for h in doc.get("status_history", [])
                ],
                retry_count=doc.get("retry_count", 0),
                endpoint_used=doc.get("endpoint_used"),
                fallback_used=doc.get("fallback_used", False),
                error_code=doc.get("error_code"),
                error_message=doc.get("error_message"),
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )
        )

    return MessageLogListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/{campaign_id}/failure-breakdown")
async def failure_breakdown(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # Fetch job to verify access
    job = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not job:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, job["restaurant_id"], db)

    cursor = db.message_logs.aggregate(
        [
            {_MATCH: {"job_id": to_object_id(campaign_id), "status": "failed"}},
            {_GROUP: {"_id": "$error_message", "count": {"$sum": 1}}},
            {_SORT: {"count": -1}},
            {"$limit": 10},
        ]
    )
    results = await cursor.to_list(10)
    return [{"reason": r["_id"] or "Unknown", "count": r["count"]} for r in results]


@router.post(
    "/{campaign_id}/retry-failed", response_model=CampaignResponse, status_code=201
)
async def retry_failed(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    campaign_oid = to_object_id(campaign_id)
    original = await db.campaign_jobs.find_one({"_id": campaign_oid})
    if not original:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    retry_restaurant_id = original.get("restaurant_id")
    if not retry_restaurant_id:
        raise ValidationError(
            "Original campaign has no restaurant_id and cannot be retried"
        )

    await validate_restaurant_access(current_user, retry_restaurant_id, db)

    failed_query = {"job_id": campaign_oid, "status": "failed"}
    failed_count = await db.message_logs.count_documents(failed_query)

    if failed_count == 0:
        raise ValidationError("No failed messages to retry")

    now = datetime.now(timezone.utc)

    # Walk up to find the root campaign so all retries share the same root
    root_id = original.get("parent_campaign_id") or campaign_oid

    job_doc = {
        "restaurant_id": retry_restaurant_id,
        "name": f"{original['name']} (retry)",
        "template_id": original.get("template_id", ""),
        "template_name": original["template_name"],
        "priority": original["priority"],
        "status": "queued",
        "total_count": failed_count,
        "sent_count": 0,
        "delivered_count": 0,
        "read_count": 0,
        "failed_count": 0,
        "replies_count": 0,
        "scheduled_at": None,
        "started_at": None,
        "completed_at": None,
        "created_by": current_user["_id"],
        "include_unsubscribe": original.get("include_unsubscribe", False),
        "media_url": original.get("media_url"),
        "parent_campaign_id": root_id,
        "created_at": now,
    }
    result = await db.campaign_jobs.insert_one(job_doc)
    job_id = result.inserted_id

    cursor = db.message_logs.find(failed_query)
    batch_size = 1000
    new_logs_batch = []

    async for log in cursor:
        new_logs_batch.append(
            {
                "job_id": job_id,
                "recipient_phone": log["recipient_phone"],
                "recipient_name": log.get("recipient_name", ""),
                "template_name": log["template_name"],
                "template_variables": log.get("template_variables", {}),
                "media_url": log.get("media_url"),
                "status": "queued",
                "retry_count": 0,
                "endpoint_used": None,
                "fallback_used": False,
                "error_code": None,
                "error_message": None,
                "status_history": [],
                "created_at": now,
                "updated_at": now,
                "locked_until": None,
            }
        )

        if len(new_logs_batch) >= batch_size:
            await db.message_logs.insert_many(new_logs_batch)
            new_logs_batch = []

    if new_logs_batch:
        await db.message_logs.insert_many(new_logs_batch)

    from app.workers.send_task import dispatch_campaign_task

    dispatch_campaign_task.delay(str(job_id))

    job_doc["_id"] = job_id
    return _serialize_campaign(job_doc)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    if doc["status"] == "running":
        raise ValidationError("Cannot delete a running campaign — cancel it first")
    await db.message_logs.delete_many({"job_id": to_object_id(campaign_id)})
    await db.campaign_jobs.delete_one({"_id": to_object_id(campaign_id)})


@router.get("/{campaign_id}/export-failed")
async def export_failed(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # Fetch job to verify access
    job = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not job:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, job["restaurant_id"], db)

    cursor = db.message_logs.find(
        {"job_id": to_object_id(campaign_id), "status": "failed"}
    )

    async def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["phone", "name", "error_code", "error_message", "retry_count"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        async for doc in cursor:
            writer.writerow(
                [
                    doc["recipient_phone"],
                    doc.get("recipient_name", ""),
                    doc.get("error_code", ""),
                    doc.get("error_message", ""),
                    doc.get("retry_count", 0),
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=failed_{campaign_id}.csv"
        },
    )
