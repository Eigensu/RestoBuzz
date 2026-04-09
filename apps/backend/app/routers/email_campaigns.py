"""
Email Campaigns Router — full campaign lifecycle.

Mirrors the WhatsApp campaigns architecture but uses Resend as the send layer.
Templates are stored locally, rendered via Jinja2, and sent as compiled HTML.
"""
import csv
import io
import json
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

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
    TemplateNotFoundError,
    ValidationError,
)
from app.models.email_campaign import (
    EmailCampaignCreate,
    EmailCampaignResponse,
    EmailCampaignListResponse,
)
from app.models.email_log import (
    EmailLogListResponse,
    EmailLogResponse,
    EmailStatusHistoryEntry,
)
from app.config import settings

router = APIRouter(prefix="/email-campaigns", tags=["email-campaigns"])
logger = get_logger(__name__)

# ── MongoDB aggregation stage key constants ───────────────────────────────────
_MATCH = "$match"
_GROUP = "$group"
_SORT = "$sort"
_COND = "$cond"


def _serialize_campaign(doc: dict) -> EmailCampaignResponse:
    return EmailCampaignResponse(
        id=str(doc["_id"]),
        restaurant_id=doc.get("restaurant_id", ""),
        name=doc["name"],
        template_id=str(doc["template_id"]),
        subject=doc["subject"],
        from_email=doc.get("from_email", settings.resend_from_email),
        status=doc["status"],
        total_count=doc.get("total_count", 0),
        sent_count=doc.get("sent_count", 0),
        delivered_count=doc.get("delivered_count", 0),
        opened_count=doc.get("opened_count", 0),
        clicked_count=doc.get("clicked_count", 0),
        bounced_count=doc.get("bounced_count", 0),
        failed_count=doc.get("failed_count", 0),
        complained_count=doc.get("complained_count", 0),
        scheduled_at=doc.get("scheduled_at"),
        started_at=doc.get("started_at"),
        completed_at=doc.get("completed_at"),
        created_by=str(doc["created_by"]),
        created_at=doc["created_at"],
    )


# ── List Campaigns ────────────────────────────────────────────────────────────

@router.get("", response_model=EmailCampaignListResponse)
async def list_email_campaigns(
    validated_rid: Annotated[str, Depends(require_restaurant_access())],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    skip = (page - 1) * page_size
    query = {"restaurant_id": validated_rid}
    total = await db.email_campaign_jobs.count_documents(query)
    cursor = (
        db.email_campaign_jobs.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    items = [_serialize_campaign(doc) async for doc in cursor]
    return EmailCampaignListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def _resolve_email_template(db: AsyncIOMotorDatabase, template_id: str):
    template = await db.email_templates.find_one({"_id": to_object_id(template_id)})
    if not template:
        raise TemplateNotFoundError(f"Email template '{template_id}' not found")
    return template


async def _resolve_contacts(body_contact_file_ref: str, db: AsyncIOMotorDatabase):
    from redis.asyncio import from_url

    raw = None
    try:
        redis = from_url(settings.redis_url, decode_responses=True)
        raw = await redis.get(f"file_ref:{body_contact_file_ref}")
        await redis.aclose()
    except Exception as e:
        logger.warning(
            "email_campaign_create_cache_unavailable",
            error=str(e),
            file_ref=body_contact_file_ref,
        )

    if not raw:
        doc = await db.contact_files.find_one(
            {"result.file_ref": body_contact_file_ref}
        )
        if not doc:
            raise ContactFileExpiredError(
                "Contact file reference expired or not found. Please re-upload."
            )
        return doc["result"]["valid_rows"]
    return json.loads(raw)


def _prepare_and_validate_contacts(contacts, template):
    if not contacts:
        raise ValidationError("No contacts found in the uploaded file")

    initial_count = len(contacts)
    seen_emails = set()
    deduped_contacts = []
    for c in contacts:
        email = c.get("email", "").strip().lower()
        if email and email not in seen_emails:
            seen_emails.add(email)
            deduped_contacts.append(c)

    if not deduped_contacts:
        raise ValidationError(
            f"None of the {initial_count} uploaded contacts have a valid or unique email address."
        )

    required_vars = [
        v["key"]
        for v in template.get("variables", [])
        if v.get("fallback_value") is None
    ]
    if required_vars:
        sample = deduped_contacts[0]
        available_keys = set(sample.get("variables", {}).keys())
        missing = [k for k in required_vars if k not in available_keys]
        if missing:
            raise ValidationError(
                f"Contacts are missing required template variables: {', '.join(missing)}"
            )
    return deduped_contacts


@router.post("", response_model=EmailCampaignResponse, status_code=201)
async def create_email_campaign(
    body: EmailCampaignCreate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    await validate_restaurant_access(current_user, body.restaurant_id, db)

    template = await _resolve_email_template(db, body.template_id)
    contacts = await _resolve_contacts(body.contact_file_ref, db)
    contacts = _prepare_and_validate_contacts(contacts, template)

    now = datetime.now(timezone.utc)

    # Create the campaign job (Manual start)
    job_doc = {
        "restaurant_id": body.restaurant_id,
        "name": body.name,
        "template_id": to_object_id(body.template_id),
        "template_snapshot": template,
        "subject": body.subject or template.get("subject", ""),
        "from_email": body.from_email or settings.resend_from_email,
        "reply_to": body.reply_to,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "completed_at": None,
        "total_count": len(contacts),
        "sent_count": 0,
        "delivered_count": 0,
        "opened_count": 0,
        "clicked_count": 0,
        "bounced_count": 0,
        "failed_count": 0,
        "complained_count": 0,
        "metadata": getattr(body, "metadata", {}),
        "created_by": current_user["_id"],
    }

    result = await db.email_campaign_jobs.insert_one(job_doc)
    campaign_id = result.inserted_id

    # Create initial logs
    email_logs = []
    for c in contacts:
        email_logs.append(
            {
                "campaign_id": campaign_id,
                "recipient_email": c["email"].strip().lower(),
                "recipient_name": c.get("name", ""),
                "template_variables": c.get("variables", {}),
                "resend_email_id": None,
                "status": "queued",
                "status_history": [],
                "retry_count": 0,
                "error_reason": None,
                "created_at": now,
                "updated_at": now,
            }
        )

    if email_logs:
        try:
            await db.email_logs.insert_many(email_logs, ordered=False)
        except Exception as e:
            if "duplicate key" not in str(e).lower():
                await db.email_campaign_jobs.delete_one({"_id": campaign_id})
                logger.error(
                    "email_campaign_create_logs_error",
                    campaign_id=str(campaign_id),
                    error=str(e),
                )
                raise ServerError("Failed to create email logs") from e

    job_doc["_id"] = campaign_id
    return _serialize_campaign(job_doc)


# ── Get Campaign ──────────────────────────────────────────────────────────────

@router.get("/analytics")
async def get_email_analytics(
    validated_rid: Annotated[str, Depends(require_restaurant_access())],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """Aggregated email analytics for the dashboard Email tab."""
    campaign_ids = [
        doc["_id"]
        async for doc in db.email_campaign_jobs.find(
            {"restaurant_id": validated_rid}, {"_id": 1}
        )
    ]

    if not campaign_ids:
        return {
            "totals": {
                "sent": 0,
                "delivered": 0,
                "opened": 0,
                "unique_opened": 0,
                "clicked": 0,
                "bounced": 0,
                "failed": 0,
                "complained": 0,
            },
            "delivery_rate": 0,
            "open_rate": 0,
            "click_rate": 0,
            "bounce_rate": 0,
            "failure_breakdown": [],
        }

    base_match = {"campaign_id": {"$in": campaign_ids}}

    # Aggregate totals
    totals_cursor = db.email_logs.aggregate(
        [
            {_MATCH: base_match},
            {
                _GROUP: {
                    "_id": None,
                    "total": {"$sum": 1},
                    "sent": {
                        "$sum": {
                            _COND: [
                                {"$in": ["$status", ["sent", "delivered", "opened", "clicked"]]},
                                1,
                                0,
                            ]
                        }
                    },
                    "delivered": {
                        "$sum": {
                            _COND: [
                                {"$in": ["$status", ["delivered", "opened", "clicked"]]},
                                1,
                                0,
                            ]
                        }
                    },
                    "opened": {
                        "$sum": {
                            _COND: [
                                {"$in": ["$status", ["opened", "clicked"]]},
                                1,
                                0,
                            ]
                        }
                    },
                    "clicked": {
                        "$sum": {_COND: [{"$eq": ["$status", "clicked"]}, 1, 0]}
                    },
                    "bounced": {
                        "$sum": {_COND: [{"$eq": ["$status", "bounced"]}, 1, 0]}
                    },
                    "failed": {
                        "$sum": {_COND: [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "complained": {
                        "$sum": {
                            _COND: [{"$eq": ["$status", "complained"]}, 1, 0]
                        }
                    },
                }
            },
        ]
    )

    totals_list = await totals_cursor.to_list(1)
    t = totals_list[0] if totals_list else {}

    sent = t.get("sent", 0)
    delivered = t.get("delivered", 0)
    opened = t.get("opened", 0)
    clicked = t.get("clicked", 0)
    bounced = t.get("bounced", 0)
    failed = t.get("failed", 0)
    complained = t.get("complained", 0)

    denominator = sent - failed if sent > failed else sent or 1

    # Failure breakdown
    failure_cursor = db.email_logs.aggregate(
        [
            {_MATCH: {**base_match, "status": {"$in": ["failed", "bounced"]}}},
            {_GROUP: {"_id": "$error_reason", "count": {"$sum": 1}}},
            {_SORT: {"count": -1}},
            {"$limit": 10},
        ]
    )
    failure_results = [
        {"reason": r["_id"] or "Unknown", "count": r["count"]}
        async for r in failure_cursor
    ]

    return {
        "totals": {
            "sent": sent,
            "delivered": delivered,
            "opened": opened,
            "unique_opened": opened,  # Each log = unique recipient
            "clicked": clicked,
            "bounced": bounced,
            "failed": failed,
            "complained": complained,
        },
        "delivery_rate": round(delivered / denominator * 100, 2) if denominator else 0,
        "open_rate": round(opened / denominator * 100, 2) if denominator else 0,
        "click_rate": round(clicked / denominator * 100, 2) if denominator else 0,
        "bounce_rate": round(bounced / denominator * 100, 2) if denominator else 0,
        "failure_breakdown": failure_results,
    }


@router.get("/{campaign_id}", response_model=EmailCampaignResponse)
async def get_email_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.email_campaign_jobs.find_one(
        {"_id": to_object_id(campaign_id)}
    )
    if not doc:
        raise CampaignNotFoundError(f"Email campaign '{campaign_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    return _serialize_campaign(doc)


# ── Start Campaign ────────────────────────────────────────────────────────────

@router.post("/{campaign_id}/start", response_model=EmailCampaignResponse)
async def start_email_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.email_campaign_jobs.find_one(
        {"_id": to_object_id(campaign_id)}
    )
    if not doc:
        raise CampaignNotFoundError(f"Email campaign '{campaign_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    if doc["status"] not in ("draft",):
        raise ValidationError(
            f"Cannot start a campaign with status '{doc['status']}'"
        )

    await db.email_campaign_jobs.update_one(
        {"_id": to_object_id(campaign_id)}, {"$set": {"status": "queued"}}
    )

    from app.workers.send_email_task import dispatch_email_campaign_task

    dispatch_email_campaign_task.delay(campaign_id)

    doc["status"] = "queued"
    return _serialize_campaign(doc)


# ── Cancel Campaign ──────────────────────────────────────────────────────────

@router.post("/{campaign_id}/cancel", response_model=EmailCampaignResponse)
async def cancel_email_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.email_campaign_jobs.find_one(
        {"_id": to_object_id(campaign_id)}
    )
    if not doc:
        raise CampaignNotFoundError(f"Email campaign '{campaign_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    doc = await db.email_campaign_jobs.find_one_and_update(
        {
            "_id": to_object_id(campaign_id),
            "status": {"$in": ["draft", "queued", "sending"]},
        },
        {"$set": {"status": "cancelled"}},
        return_document=True,
    )
    if not doc:
        raise ValidationError(
            "Campaign cannot be cancelled in its current state"
        )
    return _serialize_campaign(doc)


# ── List Messages ─────────────────────────────────────────────────────────────

@router.get("/{campaign_id}/messages", response_model=EmailLogListResponse)
async def list_email_messages(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[str | None, Query()] = None,
):
    job = await db.email_campaign_jobs.find_one(
        {"_id": to_object_id(campaign_id)}
    )
    if not job:
        raise CampaignNotFoundError(f"Email campaign '{campaign_id}' not found")
    await validate_restaurant_access(current_user, job["restaurant_id"], db)

    query: dict = {"campaign_id": to_object_id(campaign_id)}
    if status:
        query["status"] = status

    skip = (page - 1) * page_size
    total = await db.email_logs.count_documents(query)
    cursor = (
        db.email_logs.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
    )

    items = []
    async for doc in cursor:
        items.append(
            EmailLogResponse(
                id=str(doc["_id"]),
                campaign_id=str(doc["campaign_id"]),
                recipient_email=doc["recipient_email"],
                recipient_name=doc.get("recipient_name", ""),
                resend_email_id=doc.get("resend_email_id"),
                status=doc["status"],
                status_history=[
                    EmailStatusHistoryEntry(**h)
                    for h in doc.get("status_history", [])
                ],
                retry_count=doc.get("retry_count", 0),
                error_reason=doc.get("error_reason"),
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )
        )

    return EmailLogListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


# ── Delete Campaign ──────────────────────────────────────────────────────────

@router.delete("/{campaign_id}", status_code=204)
async def delete_email_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.email_campaign_jobs.find_one(
        {"_id": to_object_id(campaign_id)}
    )
    if not doc:
        raise CampaignNotFoundError(f"Email campaign '{campaign_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    if doc["status"] == "sending":
        raise ValidationError(
            "Cannot delete a running campaign — cancel it first"
        )
    await db.email_logs.delete_many({"campaign_id": to_object_id(campaign_id)})
    await db.email_campaign_jobs.delete_one(
        {"_id": to_object_id(campaign_id)}
    )


# ── Export Failed ─────────────────────────────────────────────────────────────

@router.get("/{campaign_id}/export-failed")
async def export_failed_emails(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    job = await db.email_campaign_jobs.find_one(
        {"_id": to_object_id(campaign_id)}
    )
    if not job:
        raise CampaignNotFoundError(f"Email campaign '{campaign_id}' not found")
    await validate_restaurant_access(current_user, job["restaurant_id"], db)

    cursor = db.email_logs.find(
        {
            "campaign_id": to_object_id(campaign_id),
            "status": {"$in": ["failed", "bounced"]},
        }
    )

    async def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["email", "name", "status", "error_reason", "retry_count"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        async for doc in cursor:
            writer.writerow(
                [
                    doc["recipient_email"],
                    doc.get("recipient_name", ""),
                    doc["status"],
                    doc.get("error_reason", ""),
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
            "Content-Disposition": f"attachment; filename=email_failed_{campaign_id}.csv"
        },
    )
