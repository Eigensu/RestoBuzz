import csv
import io
import json
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
    RedisError,
    ServerError,
    ValidationError,
)
from app.models.campaign import CampaignCreate, CampaignResponse, CampaignListResponse
from app.models.message import (
    MessageLogListResponse,
    MessageLogResponse,
    StatusHistoryEntry,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
logger = get_logger(__name__)


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
        scheduled_at=doc.get("scheduled_at"),
        started_at=doc.get("started_at"),
        completed_at=doc.get("completed_at"),
        created_by=str(doc["created_by"]),
        include_unsubscribe=doc.get("include_unsubscribe", True),
        created_at=doc["created_at"],
    )


@router.get(
    "",
    response_model=CampaignListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
@router.get(
    "/",
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
@router.post("/", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # Validate access manually since it's in the body
    await validate_restaurant_access(current_user, body.restaurant_id, db)
    from redis.asyncio import from_url
    from app.config import settings

    try:
        redis = from_url(settings.redis_url, decode_responses=True)
        raw = await redis.get(f"file_ref:{body.contact_file_ref}")
        await redis.aclose()
    except Exception as e:
        logger.error("campaign_create_cache_error", error=str(e))
        raise RedisError("Cache unavailable") from e

    if not raw:
        raise ContactFileExpiredError(
            "Contact file reference expired or not found. Please re-upload your contacts."
        )

    contacts = json.loads(raw)
    now = datetime.now(timezone.utc)

    job_doc = {
        "restaurant_id": body.restaurant_id,
        "name": body.name,
        "template_id": body.template_id,
        "template_name": body.template_name,
        "template_variables": body.template_variables,
        "media_url": body.media_url,
        "priority": body.priority,
        "status": "draft",
        "total_count": len(contacts),
        "sent_count": 0,
        "delivered_count": 0,
        "read_count": 0,
        "failed_count": 0,
        "scheduled_at": body.scheduled_at,
        "started_at": None,
        "completed_at": None,
        "created_by": current_user["_id"],
        "include_unsubscribe": body.include_unsubscribe,
        "created_at": now,
    }
    result = await db.campaign_jobs.insert_one(job_doc)
    job_id = result.inserted_id

    message_docs = [
        {
            "job_id": job_id,
            "recipient_phone": c["phone"],
            "recipient_name": c.get("name", ""),
            "template_name": body.template_name,
            "template_variables": {**body.template_variables, **c.get("variables", {})},
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
        for c in contacts
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

    job_doc["_id"] = job_id
    return _serialize_campaign(job_doc)


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
        {"$set": {"status": "cancelled"}},
        return_document=True,
    )
    if not doc:
        raise ValidationError("Campaign cannot be cancelled in its current state")
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
            {"$match": {"job_id": to_object_id(campaign_id), "status": "failed"}},
            {"$group": {"_id": "$error_message", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
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
        "scheduled_at": None,
        "started_at": None,
        "completed_at": None,
        "created_by": current_user["_id"],
        "include_unsubscribe": original.get("include_unsubscribe", False),
        "media_url": original.get("media_url"),
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
