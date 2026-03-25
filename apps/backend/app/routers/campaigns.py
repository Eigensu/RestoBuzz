import csv
import io
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from bson import ObjectId
from app.database import get_db
from app.dependencies import require_role, get_current_user
from app.models.campaign import CampaignCreate, CampaignResponse, CampaignListResponse
from app.models.message import (
    MessageLogListResponse,
    MessageLogResponse,
    StatusHistoryEntry,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _serialize_campaign(doc: dict) -> CampaignResponse:
    return CampaignResponse(
        id=str(doc["_id"]),
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


@router.get("/", response_model=CampaignListResponse)
async def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    skip = (page - 1) * page_size
    total = await db.campaign_jobs.count_documents({})
    cursor = (
        db.campaign_jobs.find({}).sort("created_at", -1).skip(skip).limit(page_size)
    )
    items = [_serialize_campaign(doc) async for doc in cursor]
    return CampaignListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post("/", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    # Load contacts from Redis cache
    from redis.asyncio import from_url
    from app.config import settings

    redis = from_url(settings.redis_url, decode_responses=True)
    raw = await redis.get(f"file_ref:{body.contact_file_ref}")
    await redis.aclose()

    if not raw:
        raise HTTPException(
            400, "Contact file reference expired or not found. Re-upload contacts."
        )

    contacts = json.loads(raw)
    now = datetime.now(timezone.utc)

    job_doc = {
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
        "created_by": ObjectId(current_user["id"]),
        "include_unsubscribe": body.include_unsubscribe,
        "created_at": now,
    }
    result = await db.campaign_jobs.insert_one(job_doc)
    job_id = result.inserted_id

    # Bulk insert message logs
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
        await db.message_logs.insert_many(message_docs)

    job_doc["_id"] = job_id
    return _serialize_campaign(job_doc)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    doc = await db.campaign_jobs.find_one({"_id": ObjectId(campaign_id)})
    if not doc:
        raise HTTPException(404, "Campaign not found")
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/start", response_model=CampaignResponse)
async def start_campaign(
    campaign_id: str,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    doc = await db.campaign_jobs.find_one({"_id": ObjectId(campaign_id)})
    if not doc:
        raise HTTPException(404, "Campaign not found")
    if doc["status"] not in ("draft", "paused"):
        raise HTTPException(400, f"Cannot start campaign in '{doc['status']}' status")

    await db.campaign_jobs.update_one(
        {"_id": ObjectId(campaign_id)},
        {"$set": {"status": "queued"}},
    )

    from app.workers.send_task import dispatch_campaign_task

    dispatch_campaign_task.delay(campaign_id)

    doc["status"] = "queued"
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: str,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    doc = await db.campaign_jobs.find_one_and_update(
        {"_id": ObjectId(campaign_id), "status": "running"},
        {"$set": {"status": "paused"}},
        return_document=True,
    )
    if not doc:
        raise HTTPException(400, "Campaign is not running")
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
async def cancel_campaign(
    campaign_id: str,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    doc = await db.campaign_jobs.find_one_and_update(
        {
            "_id": ObjectId(campaign_id),
            "status": {"$in": ["draft", "queued", "running", "paused"]},
        },
        {"$set": {"status": "cancelled"}},
        return_document=True,
    )
    if not doc:
        raise HTTPException(400, "Campaign cannot be cancelled")
    return _serialize_campaign(doc)


@router.get("/{campaign_id}/messages", response_model=MessageLogListResponse)
async def list_messages(
    campaign_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = None,
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    query: dict = {"job_id": ObjectId(campaign_id)}
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
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    cursor = db.message_logs.aggregate(
        [
            {"$match": {"job_id": ObjectId(campaign_id), "status": "failed"}},
            {"$group": {"_id": "$error_message", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
    )
    results = await cursor.to_list(10)
    return [{"reason": r["_id"] or "Unknown", "count": r["count"]} for r in results]


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: str,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    doc = await db.campaign_jobs.find_one({"_id": ObjectId(campaign_id)})
    if not doc:
        raise HTTPException(404, "Campaign not found")
    if doc["status"] == "running":
        raise HTTPException(400, "Cannot delete a running campaign. Cancel it first.")
    await db.message_logs.delete_many({"job_id": ObjectId(campaign_id)})
    await db.campaign_jobs.delete_one({"_id": ObjectId(campaign_id)})


@router.get("/{campaign_id}/export-failed")
async def export_failed(
    campaign_id: str,
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    cursor = db.message_logs.find({"job_id": ObjectId(campaign_id), "status": "failed"})

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
