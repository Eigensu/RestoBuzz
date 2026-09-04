"""Campaign management routes: CRUD, lifecycle control, analytics, and message logs."""

import csv
import io
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import from_url as redis_from_url
from redis.exceptions import RedisError as RedisClientError

from app.config import settings
from app.constants.meta_errors import RETRYABLE_FAILED_MATCH
from app.database import get_db
from app.dependencies import (
    require_role,
    validate_restaurant_access,
    get_active_restaurant,
)
from app.core.utils import to_object_id
from app.core.logging import get_logger
from app.core.errors import (
    CampaignNotFoundError,
    ContactFileExpiredError,
    ServerError,
    ValidationError,
)
from app.models.campaign import (
    CampaignCreate,
    CampaignResponse,
    CampaignListResponse,
    VariableSource,
)
from app.models.campaign import (
    CampaignTestMessageRequest,
    CampaignTestMessageResponse,
)
from app.models.message import (
    MessageLogListResponse,
    MessageLogResponse,
    StatusHistoryEntry,
)
from app.services.meta_api import send_template_message, MetaAPIError
from app.services.ecard_service import build_card_url
from app.workers.send_task import dispatch_campaign_task
from app.workers.smart_retries_poller import ROOT_RETRY_GATE_MINUTES
from app.services.campaign_service import (
    resolve_waba_credentials,
    create_child_retry_campaign,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
logger = get_logger(__name__)

# ── MongoDB aggregation stage key constants ───────────────────────────────────
_MATCH = "$match"
_GROUP = "$group"
_SORT = "$sort"
_CREATED_AT = "$created_at"
_EXISTS = "$exists"
# Matches both parameter formats: {{1}} on templates created before named
# support, {{customer_name}} on the ones created since.
_BODY_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

# Restaurant fields a variable may be sourced from, mapped to the key on the
# restaurant document. Deliberately a small allowlist — a free-form field path
# would let a campaign body read anything stored on the restaurant.
_RESTAURANT_FIELDS = {"name": "name", "location": "location"}

# Matches only root campaigns. Retry children carry a parent_campaign_id (stored
# as the string form of the root's ObjectId — see create_child_retry_campaign).
_ROOT_ONLY_FILTER = {
    "$or": [
        {"parent_campaign_id": {_EXISTS: False}},
        {"parent_campaign_id": None},
    ]
}


def _retry_chain_filter(root_oid) -> dict:
    """Match a root campaign plus every retry in its chain.

    The two halves need different types for the same id: `_id` is an ObjectId,
    while `parent_campaign_id` is persisted as a string. Mixing them up makes
    the query silently match nothing, so both call sites share this helper.
    """
    return {
        "$or": [
            {"_id": to_object_id(root_oid)},
            {"parent_campaign_id": str(root_oid)},
        ]
    }

# Returned when the Celery broker can't accept a dispatch (HTTP 503).
_QUEUE_UNAVAILABLE_DETAIL = "Campaign queue unavailable, please try again shortly"
# Documents the 503 raised by dispatch endpoints (satisfies HTTPException docs).
_QUEUE_UNAVAILABLE_RESPONSE = {503: {"description": _QUEUE_UNAVAILABLE_DETAIL}}


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


def _template_header_media_type(template_doc: dict | None) -> str | None:
    """Return 'image' | 'video' | 'document' for the template's header, or None.

    Mirrors the WhatsApp template HEADER `format` so the send payload uses the
    matching media parameter type — Meta rejects a send whose header parameter
    type doesn't match the declared header format.
    """
    if not template_doc:
        return None
    for component in template_doc.get("components") or []:
        if str(component.get("type") or "").upper() != "HEADER":
            continue
        fmt = str(component.get("format") or "").upper()
        if fmt == "VIDEO":
            return "video"
        if fmt == "DOCUMENT":
            return "document"
        if fmt == "IMAGE":
            return "image"
    return None


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


def _campaign_wide_variables(
    sources: dict[str, VariableSource], restaurant: dict
) -> dict[str, str]:
    """Values that are the same for every recipient, resolved once.

    A restaurant-sourced variable is read from the sending restaurant rather
    than typed, so a campaign cannot go out carrying the wrong venue's name.
    """
    resolved: dict[str, str] = {}
    for key, source in sources.items():
        if source.kind == "fixed":
            value = str(source.value or "").strip()
        elif source.kind == "restaurant":
            field = _RESTAURANT_FIELDS.get(str(source.field or "").strip())
            if not field:
                raise ValidationError(
                    f"Variable '{key}' asks for an unknown restaurant field "
                    f"'{source.field}'. Available: {', '.join(sorted(_RESTAURANT_FIELDS))}."
                )
            value = str(restaurant.get(field) or "").strip()
        else:
            continue
        if value:
            resolved[key] = value
    return resolved


def _require_variable_coverage(
    allowed_keys: set[str],
    sources: dict[str, VariableSource],
    campaign_variables: dict,
) -> None:
    """Refuse a campaign that would send a message with a hole in it.

    Every variable needs either a value that holds for all recipients or a
    fallback for the rows where its column is blank. Without this the send
    reaches Meta one parameter short and every affected message fails with
    error 132000 — after the campaign has already started.
    """
    missing = sorted(
        key
        for key in allowed_keys
        if not str(campaign_variables.get(key) or "").strip()
        and not str((sources.get(key).fallback if sources.get(key) else "") or "").strip()
    )
    if missing:
        listed = ", ".join(f"{{{{{k}}}}}" for k in missing)
        raise ValidationError(
            f"These variables have no value for every recipient: {listed}. "
            "Give each one a fallback, or a fixed value."
        )


def _resolve_recipient_variables(
    contact: dict,
    *,
    sources: dict[str, VariableSource],
    campaign_variables: dict,
    allowed_keys: set[str],
) -> dict[str, str]:
    """The variable values for one recipient.

    Precedence is most-specific-first: this recipient's own cell, then the
    value that holds campaign-wide, then the fallback.
    """
    row = contact.get("row") or {}
    legacy = contact.get("variables") or {}
    resolved: dict[str, str] = {}

    for key in allowed_keys:
        source = sources.get(key)

        if source:
            # An explicit mapping is the operator's decision; a value cached by
            # an older upload-time mapping must not quietly outrank it.
            if source.kind == "column":
                value = str(row.get(str(source.column or "")) or "").strip()
            elif source.kind == "contact":
                value = str(contact.get("name") or "").strip()
            else:
                # fixed and restaurant are the same for everyone, so they were
                # already resolved into campaign_variables.
                value = str(campaign_variables.get(key) or "").strip()
            if not value:
                value = str(source.fallback or "").strip()
        else:
            # No mapping for this variable: fall back to whatever the upload
            # step recorded, then to the campaign-wide value.
            value = str(legacy.get(key) or "").strip() or str(
                campaign_variables.get(key) or ""
            ).strip()

        if value:
            resolved[key] = value

    return resolved


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
        has_been_retried=doc.get("has_been_retried", False),
        smart_retries=doc.get("smart_retries", False),
        retry_until=doc.get("retry_until"),
        pause_reason=doc.get("pause_reason"),
    )


@router.get(
    "",
    dependencies=[Depends(require_role("viewer"))],
)
async def list_campaigns(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    roots_only: Annotated[bool, Query()] = False,
) -> CampaignListResponse:
    """Return a paginated list of campaigns for the active restaurant.

    By default every campaign document is paginated, retry children included.
    Because smart retries create a new child document every couple of hours,
    that makes a page of N documents collapse to far fewer real campaigns in the
    UI.

    With ``roots_only=true`` the pagination window applies to ROOT campaigns
    only, and each returned root is accompanied by its full retry chain. So
    ``total``/``page``/``page_size`` describe roots, while ``items`` holds those
    roots plus their children — meaning ``len(items)`` may exceed ``page_size``.
    Callers that group children under their parent (the campaigns table) then
    render exactly ``page_size`` rows per page with no chain split across pages.
    """
    skip = (page - 1) * page_size
    query: dict = {"restaurant_id": restaurant["id"]}
    if roots_only:
        query.update(_ROOT_ONLY_FILTER)

    total = await db.campaign_jobs.count_documents(query)
    cursor = (
        db.campaign_jobs.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    )
    docs = [doc async for doc in cursor]

    if roots_only and docs:
        # Pull the retry children for this page of roots in a single round trip
        # so the table can still show expanders and effective-reach totals.
        child_cursor = db.campaign_jobs.find(
            {
                "restaurant_id": restaurant["id"],
                "parent_campaign_id": {"$in": [str(d["_id"]) for d in docs]},
            }
        ).sort("created_at", -1)
        docs.extend([child async for child in child_cursor])

    items = [_serialize_campaign(doc) for doc in docs]
    return CampaignListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def _resolve_campaign_contacts(db, file_ref: str) -> list[dict]:
    """Load a campaign's uploaded contacts: Redis cache first, MongoDB fallback
    if the cache is down or the entry has expired."""
    raw = None
    redis = None
    try:
        redis = redis_from_url(settings.redis_url, decode_responses=True)
        raw = await redis.get(f"file_ref:{file_ref}")
    except (RedisClientError, OSError) as e:
        logger.warning(
            "campaign_create_cache_unavailable",
            error=str(e),
            file_ref=file_ref,
        )
        # Proceed to fallback
    finally:
        if redis is not None:
            await redis.aclose()

    if raw:
        return json.loads(raw)

    # FALLBACK: check MongoDB directly if Redis is down or the cache expired.
    doc = await db.contact_files.find_one({"result.file_ref": file_ref})
    if not doc:
        raise ContactFileExpiredError(
            "Contact file reference expired or not found. Please re-upload your contacts."
        )
    return doc["result"]["valid_rows"]


def _build_campaign_message_docs(
    phone_contacts: list[dict],
    *,
    job_id,
    body: CampaignCreate,
    media_type,
    campaign_template_variables: dict,
    variable_sources: dict[str, VariableSource],
    allowed_var_keys,
    wa_phone_id,
    wa_access_token_env_key,
    now: datetime,
) -> list[dict]:
    """Materialize per-recipient message_logs. Renders a personalized e-card
    media_url per recipient when personalization is enabled, else uses the
    campaign's static media_url. May raise (e.g. build_card_url) — the caller
    rolls back the draft job on failure."""
    return [
        {
            "job_id": job_id,
            "restaurant_id": body.restaurant_id,
            "recipient_phone": c["phone"],
            "recipient_name": c.get("name", ""),
            "template_name": body.template_name,
            "template_variables": _resolve_recipient_variables(
                c,
                sources=variable_sources,
                campaign_variables=campaign_template_variables,
                allowed_keys=allowed_var_keys,
            ),
            "media_url": (
                build_card_url(
                    body.personalization.base_public_id,
                    c.get("name", ""),
                    body.personalization.overlay,
                )
                if body.personalization
                else body.media_url
            ),
            "media_type": media_type,
            "wa_message_id": None,
            "status": "queued",
            "status_history": [],
            "retry_count": 0,
            "locked_until": None,
            "endpoint_used": None,
            "fallback_used": False,
            "error_code": None,
            "error_message": None,
            "wa_phone_id": wa_phone_id,
            "wa_access_token_env_key": wa_access_token_env_key,
            "created_at": now,
            "updated_at": now,
        }
        for c in phone_contacts
    ]


@router.post("", status_code=201, responses=_QUEUE_UNAVAILABLE_RESPONSE)
async def create_campaign(
    body: CampaignCreate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> CampaignResponse:
    """Create a new campaign and immediately queue or schedule it."""
    # Validate access manually since restaurant_id is in the body (not a path/query param)
    await validate_restaurant_access(current_user, body.restaurant_id, db)

    contacts = await _resolve_campaign_contacts(db, body.contact_file_ref)

    template_doc = await db.templates.find_one(
        {"name": body.template_name, "restaurant_id": body.restaurant_id},
        {"components": 1},
    )
    allowed_var_keys = _template_body_var_keys(template_doc)
    media_type = _template_header_media_type(template_doc)
    variable_sources = {
        key: source
        for key, source in body.variable_sources.items()
        if key in allowed_var_keys
    }
    restaurant_doc = await db.restaurants.find_one({"id": body.restaurant_id}) or {}
    campaign_template_variables = _sanitize_template_variables(
        {
            **body.template_variables,
            **_campaign_wide_variables(variable_sources, restaurant_doc),
        },
        allowed_var_keys,
    )
    _require_variable_coverage(
        allowed_var_keys, variable_sources, campaign_template_variables
    )

    now = datetime.now(timezone.utc)

    job_doc = {
        "restaurant_id": body.restaurant_id,
        "name": body.name,
        "template_id": body.template_id,
        "template_name": body.template_name,
        "template_variables": campaign_template_variables,
        # Kept for the campaign detail view and for debugging a bad send: the
        # per-recipient values on message_logs show what went out, this shows
        # where each one was meant to come from.
        "variable_sources": {
            key: source.model_dump(exclude_none=True)
            for key, source in variable_sources.items()
        },
        "media_url": body.media_url,
        "media_type": media_type,
        "personalization": (
            body.personalization.model_dump() if body.personalization else None
        ),
        "priority": body.priority,
        "status": "draft",
        "total_count": len(contacts),
        "sent_count": 0,
        "delivered_count": 0,
        "read_count": 0,
        "failed_count": 0,
        "replies_count": 0,
        "scheduled_at": body.scheduled_at,
        "smart_retries": body.smart_retries,
        "retry_until": body.retry_until,
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

    # Personalized e-cards render the recipient's name onto the card image — a
    # blank name would produce a nameless card, so fail loudly rather than send
    # a broken card. Surface the count so the operator can fix the sheet.
    if body.personalization:
        nameless = sum(1 for c in phone_contacts if not (c.get("name") or "").strip())
        if nameless:
            await db.campaign_jobs.delete_one({"_id": job_id})
            raise ValidationError(
                f"{nameless} of {len(phone_contacts)} contacts have no name. "
                "Personalized e-card campaigns require a name for every recipient — "
                "add the missing names and re-upload."
            )

    # Resolve WABA credentials once for the whole campaign — O(1) per campaign.
    # phone_id and env_key are stamped onto every message_log so _do_send()
    # can resolve the token from env at send time — no raw token ever in DB.
    wa_phone_id, _token, wa_access_token_env_key = await resolve_waba_credentials(
        db, body.restaurant_id
    )

    try:
        message_docs = _build_campaign_message_docs(
            phone_contacts,
            job_id=job_id,
            body=body,
            media_type=media_type,
            campaign_template_variables=campaign_template_variables,
            variable_sources=variable_sources,
            allowed_var_keys=allowed_var_keys,
            wa_phone_id=wa_phone_id,
            wa_access_token_env_key=wa_access_token_env_key,
            now=now,
        )
    except Exception as e:
        # build_card_url (or variable sanitization) can raise while materializing
        # the message docs — don't leave the just-inserted job stranded in draft.
        await db.campaign_jobs.delete_one({"_id": job_id})
        logger.error(
            "campaign_create_media_url_error",
            campaign_id=str(job_id),
            error=str(e),
        )
        raise ValidationError("Failed to build personalized e-card media") from e
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
        try:
            await run_in_threadpool(dispatch_campaign_task.delay, str(job_id))
        except Exception as e:
            logger.error("campaign_dispatch_failed", error=str(e))
            # Broker enqueue failed — remove the just-created job and its message
            # logs so a 503 truly means nothing was created (no orphaned campaign
            # stranded in 'queued' that never dispatches).
            await db.message_logs.delete_many({"job_id": job_id})
            await db.campaign_jobs.delete_one({"_id": job_id})
            raise HTTPException(
                status_code=503,
                detail=_QUEUE_UNAVAILABLE_DETAIL,
            ) from e
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


@router.post("/test-message")
async def send_test_message(
    body: CampaignTestMessageRequest,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> CampaignTestMessageResponse:
    """Send a single test WhatsApp message using the specified template."""
    await validate_restaurant_access(current_user, body.restaurant_id, db)

    # Reuse the template's configured language when available.
    template_doc = await db.templates.find_one(
        {"name": body.template_name, "restaurant_id": body.restaurant_id},
        {"language": 1, "components": 1},
    )
    language = (template_doc or {}).get("language") or "en_US"
    media_type = _template_header_media_type(template_doc)
    allowed_var_keys = _template_body_var_keys(template_doc)
    request_variables = _sanitize_template_variables(
        body.template_variables, allowed_var_keys
    )

    to_phone = body.to_phone.strip()
    if not to_phone:
        raise ValidationError("Phone number is required")

    # Resolve restaurant-specific WABA credentials for the test send
    wa_phone_id, wa_access_token, _ = await resolve_waba_credentials(
        db, body.restaurant_id
    )

    try:
        wa_message_id, endpoint_used = await send_template_message(
            to=to_phone,
            template_name=body.template_name,
            variables=request_variables,
            media_url=body.media_url,
            language=language,
            phone_id=wa_phone_id,
            access_token=wa_access_token,
            media_type=media_type,
        )
    except MetaAPIError as e:
        if e.code in ("network_error", "parse_error", "config_error", "no_endpoint"):
            raise ServerError(str(e)) from e
        raise ValidationError(str(e)) from e

    resolved_endpoint = "fallback" if endpoint_used == "fallback" else "primary"

    return CampaignTestMessageResponse(
        wa_message_id=wa_message_id,
        endpoint_used=resolved_endpoint,
    )


@router.get("/analytics")
async def get_analytics(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
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
            {"restaurant_id": restaurant["id"]}, {"_id": 1}
        )
    ]

    async def _get_rg_count() -> int:
        pipeline = [
            {_MATCH: {"restaurant_id": restaurant["id"]}},
            {
                "$project": {
                    "_id": 0,
                    "phone": {"$trim": {"input": {"$toString": "$phone"}}},
                }
            },
            {_MATCH: {"phone": {"$ne": ""}}},
            {
                "$unionWith": {
                    "coll": "reservego_bill_data",
                    "pipeline": [
                        {_MATCH: {"restaurant_id": restaurant["id"]}},
                        {
                            "$project": {
                                "_id": 0,
                                "phone": {
                                    "$trim": {"input": {"$toString": "$guest_number"}}
                                },
                            }
                        },
                        {_MATCH: {"phone": {"$ne": ""}}},
                    ],
                }
            },
            {"$group": {"_id": "$phone"}},
            {"$count": "count"},
        ]
        result = await db.reservego_uploads.aggregate(pipeline).to_list(length=1)
        return result[0]["count"] if result else 0

    reservego_members_count = await _get_rg_count()

    if not campaign_ids:
        return {
            "totals": {
                "sent": 0,
                "delivered": 0,
                "read": 0,
                "failed": 0,
                "replies": 0,
                "total_campaigns": 0,
                "reservego_members": reservego_members_count,
            },
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
    # sent_count is only taken from root campaigns (no parent_campaign_id) to
    # avoid double-counting recipients who were retried.
    # delivered/read/failed/replies are aggregated across all campaigns in the
    # chain because those reflect real delivery outcomes regardless of which
    # attempt produced them.
    root_totals_cursor = db.campaign_jobs.aggregate(
        [
            {
                _MATCH: {
                    "restaurant_id": restaurant["id"],
                    "parent_campaign_id": {"$exists": False},
                }
            },
            {
                _GROUP: {
                    "_id": None,
                    "sent": {"$sum": "$sent_count"},
                    "total_campaigns": {"$sum": 1},
                }
            },
        ]
    )
    root_totals_list = await root_totals_cursor.to_list(1)
    root_totals_dict = (
        root_totals_list[0] if root_totals_list else {"sent": 0, "total_campaigns": 0}
    )

    delivery_totals_cursor = db.campaign_jobs.aggregate(
        [
            {_MATCH: {"restaurant_id": restaurant["id"]}},
            {
                _GROUP: {
                    "_id": None,
                    "delivered": {"$sum": "$delivered_count"},
                    "read": {"$sum": "$read_count"},
                    "failed": {"$sum": "$failed_count"},
                    "replies": {"$sum": "$replies_count"},
                }
            },
        ]
    )
    delivery_totals_list = await delivery_totals_cursor.to_list(1)
    delivery_totals_dict = (
        delivery_totals_list[0]
        if delivery_totals_list
        else {"delivered": 0, "read": 0, "failed": 0, "replies": 0}
    )

    totals = {
        "sent": root_totals_dict.get("sent", 0),
        "delivered": delivery_totals_dict.get("delivered", 0),
        "read": delivery_totals_dict.get("read", 0),
        "failed": delivery_totals_dict.get("failed", 0),
        "replies": delivery_totals_dict.get("replies", 0),
        "total_campaigns": root_totals_dict.get("total_campaigns", 0),
        "reservego_members": reservego_members_count,
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
                            # Guard against documents where status_history is
                            # missing/null: $filter returns null for a null input,
                            # and $size below then errors (Location17124).
                            "input": {"$ifNull": ["$status_history", []]},
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
    root_oid = to_object_id(doc.get("parent_campaign_id") or campaign_oid)

    # Fetch root + all retries
    cursor = db.campaign_jobs.find(_retry_chain_filter(root_oid)).sort(
        "created_at", 1
    )
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


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> CampaignResponse:
    """Fetch a single campaign by ID."""
    doc = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/start", responses=_QUEUE_UNAVAILABLE_RESPONSE)
async def start_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> CampaignResponse:
    """Transition a draft or paused campaign to queued and dispatch the Celery task."""
    doc = await db.campaign_jobs.find_one({"_id": to_object_id(campaign_id)})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    previous_status = doc["status"]
    if previous_status not in ("draft", "paused"):
        raise ValidationError(
            f"Cannot start a campaign with status '{previous_status}'"
        )

    previous_pause_reason = doc.get("pause_reason")

    await db.campaign_jobs.update_one(
        {"_id": to_object_id(campaign_id)},
        {"$set": {"status": "queued"}, "$unset": {"pause_reason": ""}},
    )

    try:
        await run_in_threadpool(dispatch_campaign_task.delay, campaign_id)
    except Exception as e:
        logger.error("campaign_dispatch_failed", error=str(e))
        # Revert to the prior status so the campaign isn't stranded in 'queued'
        # with no dispatch task enqueued. The block reason has to come back with
        # it: a campaign returned to 'paused' without one shows no banner and
        # reads as a mystery pause, which is the state this whole path exists
        # to avoid.
        #
        # Guarded on the exact status this call wrote, so the revert is a
        # compare-and-swap rather than a blind overwrite. Without the guard a
        # cancel landing while the broker call was timing out (/cancel accepts
        # 'queued') would be undone, resurrecting a cancelled campaign as
        # paused.
        rollback: dict = {"status": previous_status}
        if previous_pause_reason is not None:
            rollback["pause_reason"] = previous_pause_reason
        await db.campaign_jobs.update_one(
            {"_id": to_object_id(campaign_id), "status": "queued"},
            {"$set": rollback},
        )
        raise HTTPException(
            status_code=503,
            detail=_QUEUE_UNAVAILABLE_DETAIL,
        ) from e

    # Resuming from an auto-pause means the operator believes the block is
    # cleared (template edited or unpaused in WhatsApp Manager). Hand back the
    # retries the block consumed before it was recognised as campaign-wide —
    # otherwise messages left at retry_count 1-2 by the old burn get only the
    # remainder of their budget and fail permanently on the next hiccup.
    #
    # Deliberately after the dispatch: a resume that never reached the broker
    # has not happened, and must not leave the retry budget rewritten behind
    # it. The fan-out runs in a worker, so this lands before any send reads a
    # count in all but a pathological interleaving — and there the reset only
    # forgives one extra attempt, which is the intent anyway.
    if (previous_pause_reason or {}).get("auto"):
        await db.message_logs.update_many(
            {"job_id": to_object_id(campaign_id), "status": "queued"},
            {"$set": {"retry_count": 0}},
        )

    # `doc` predates the update, so drop the reason we just unset — otherwise
    # the response pairs status 'queued' with a stale block and the dashboard
    # renders the banner on a campaign that resumed fine.
    doc.pop("pause_reason", None)
    doc["status"] = "queued"
    return _serialize_campaign(doc)


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> CampaignResponse:
    """Pause a currently running campaign."""
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


@router.post("/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> CampaignResponse:
    """Cancel a campaign and mark all queued/sending messages as cancelled."""
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


@router.get("/{campaign_id}/messages")
async def list_messages(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[str | None, Query()] = None,
) -> MessageLogListResponse:
    """Return paginated message logs for a campaign, optionally filtered by status."""
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
    """Return the top-10 failure reasons for a campaign's message logs."""
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
    "/{campaign_id}/retry-failed",
    status_code=201,
    responses=_QUEUE_UNAVAILABLE_RESPONSE,
)
async def retry_failed(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> CampaignResponse:
    """Create a child retry campaign for all failed messages in the given campaign."""
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

    failed_query = {"job_id": campaign_oid, **RETRYABLE_FAILED_MATCH}
    failed_count = await db.message_logs.count_documents(failed_query)

    if failed_count == 0:
        raise ValidationError("No failed messages to retry")

    now = datetime.now(timezone.utc)

    # Atomic compare-and-set: claim the retry slot only if not already taken.
    # Uses update_one so concurrent requests cannot both succeed.
    claim_result = await db.campaign_jobs.update_one(
        {"_id": campaign_oid, "has_been_retried": {"$ne": True}},
        {"$set": {"has_been_retried": True, "retry_claimed_at": now}},
    )
    if claim_result.modified_count == 0:
        raise ValidationError("This campaign has already been retried")

    job_id_str = await create_child_retry_campaign(
        original, failed_count, db, current_user["_id"]
    )

    try:
        await run_in_threadpool(dispatch_campaign_task.delay, job_id_str)
    except Exception as e:
        logger.error("campaign_dispatch_failed", error=str(e))
        # Rollback parent claim and delete created child campaign
        await db.campaign_jobs.update_one(
            {"_id": campaign_oid},
            {"$unset": {"has_been_retried": "", "retry_claimed_at": ""}},
        )
        child_oid = to_object_id(job_id_str)
        await db.campaign_jobs.delete_one({"_id": child_oid})
        await db.message_logs.delete_many({"job_id": child_oid})
        raise HTTPException(
            status_code=503,
            detail=_QUEUE_UNAVAILABLE_DETAIL,
        ) from e

    new_doc = await db.campaign_jobs.find_one({"_id": to_object_id(job_id_str)})
    return _serialize_campaign(new_doc)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """Delete a campaign and all its associated message logs."""
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
    """Stream a CSV of all failed messages for a campaign."""
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


def _as_aware(dt: datetime | None) -> datetime | None:
    """Coerce a possibly naive datetime (as stored in Mongo) to UTC-aware.

    Datetimes written without tzinfo come back from Motor as offset-naive, which
    can't be compared against datetime.now(timezone.utc). Treat them as UTC.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _compute_retry_eligibility(doc: dict, now: datetime) -> tuple:
    """Derive (is_eligible, reason_not_eligible, next_retry_at, next_retry_in_seconds).

    Extracted from get_smart_retry_status to keep that handler's complexity low.
    """
    if not doc.get("smart_retries", False):
        return False, "Smart retries not enabled for this campaign", None, None

    retry_until = _as_aware(doc.get("retry_until"))
    if not retry_until:
        return False, "No retry_until deadline set", None, None
    if retry_until <= now:
        return False, "Retry deadline has passed", None, None
    if doc.get("failed_count", 0) == 0:
        return False, "No failed messages to retry", None, None

    status = doc["status"]
    if status not in ["completed", "failed"]:
        return (
            False,
            f"Campaign status is '{status}' (must be completed or failed)",
            None,
            None,
        )

    # Eligible. Next retry is ROOT_RETRY_GATE_MINUTES after the last auto-retry,
    # or immediately if it has never been retried / that window has elapsed.
    last_auto_retry_at = _as_aware(doc.get("last_auto_retry_at"))
    if last_auto_retry_at:
        next_retry_at = last_auto_retry_at + timedelta(
            minutes=ROOT_RETRY_GATE_MINUTES
        )
        if next_retry_at > now:
            return True, None, next_retry_at, int((next_retry_at - now).total_seconds())
    return True, None, now, 0


@router.get("/{campaign_id}/smart-retry-status")
async def get_smart_retry_status(
    campaign_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """
    Get smart retry status for a campaign including:
    - When the last auto-retry happened
    - When the next auto-retry will happen (if eligible)
    - All child retry campaigns created by smart retries
    - Time until retry_until deadline
    """
    campaign_oid = to_object_id(campaign_id)
    doc = await db.campaign_jobs.find_one({"_id": campaign_oid})
    if not doc:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    now = datetime.now(timezone.utc)

    # Find the root campaign (for tracking all retries in chain)
    root_oid = to_object_id(doc.get("parent_campaign_id") or campaign_oid)

    # Get all campaigns in the retry chain
    cursor = db.campaign_jobs.find(_retry_chain_filter(root_oid)).sort(
        "created_at", 1
    )

    campaigns = []
    raw_chain = []
    async for campaign in cursor:
        raw_chain.append(campaign)
        campaigns.append(
            {
                "id": str(campaign["_id"]),
                "name": campaign["name"],
                "status": campaign["status"],
                "created_at": campaign.get("created_at"),
                "total_count": campaign.get("total_count", 0),
                "sent_count": campaign.get("sent_count", 0),
                "delivered_count": campaign.get("delivered_count", 0),
                "failed_count": campaign.get("failed_count", 0),
                "is_root": campaign["_id"] == root_oid,
            }
        )

    # Eligibility must reflect the retry chain, not just the requested campaign:
    # children are never polled directly, and the root's failed_count never
    # decreases after a successful retry. So key the deadline/gate fields on the
    # ROOT (what the poller actually claims against) but source the failure count
    # from the latest attempt in the chain (root or newest child, sorted asc).
    root_doc = next((c for c in raw_chain if c["_id"] == root_oid), doc)
    latest_attempt = raw_chain[-1] if raw_chain else doc

    smart_retries_enabled = root_doc.get("smart_retries", False)
    retry_until = root_doc.get("retry_until")
    last_auto_retry_at = root_doc.get("last_auto_retry_at")
    failed_count = latest_attempt.get("failed_count", 0)
    status = root_doc["status"]

    # Eligibility + next-retry timing (extracted to keep complexity low).
    (
        is_eligible_for_retry,
        reason_not_eligible,
        next_retry_at,
        next_retry_in_seconds,
    ) = _compute_retry_eligibility({**root_doc, "failed_count": failed_count}, now)

    # Calculate time until deadline
    deadline_in_seconds = None
    if retry_until:
        deadline_in_seconds = max(0, int((_as_aware(retry_until) - now).total_seconds()))

    # Calculate time since last retry
    last_retry_seconds_ago = None
    if last_auto_retry_at:
        last_retry_seconds_ago = int((now - _as_aware(last_auto_retry_at)).total_seconds())

    return {
        "campaign_id": campaign_id,
        "campaign_name": doc["name"],
        "smart_retries_enabled": smart_retries_enabled,
        "status": status,
        "failed_count": failed_count,
        "retry_until": retry_until,
        "last_auto_retry_at": last_auto_retry_at,
        "last_retry_seconds_ago": last_retry_seconds_ago,
        "next_retry_at": next_retry_at,
        "next_retry_in_seconds": next_retry_in_seconds,
        "deadline_in_seconds": deadline_in_seconds,
        "is_eligible_for_retry": is_eligible_for_retry,
        "reason_not_eligible": reason_not_eligible,
        "retry_chain": campaigns,
        "total_retries": len(campaigns) - 1,  # Exclude root
        "poller_frequency": "Every 15 minutes",
        "retry_interval": f"Every {ROOT_RETRY_GATE_MINUTES // 60} hours",
    }
