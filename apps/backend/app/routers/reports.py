"""
Reports Router — Phase 1

Campaign Performance, Member Growth, Delivery Logs.

Design principles:
- All endpoints use get_active_restaurant for tenant isolation (no user-supplied restaurant_id)
- Config-driven date range limits (90d default, 365d for super_admin)
- Redis caching on summary endpoints (5-minute TTL)
- Cursor-based pagination for logs (not offset)
- Both CSV and XLSX exports with audit logging
"""

import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

import openpyxl
from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.database import get_db
from app.dependencies import get_active_restaurant, get_current_user, require_role

router = APIRouter(prefix="/reports", tags=["reports"])
logger = get_logger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
_DEFAULT_MAX_DAYS = 90
_SUPER_ADMIN_MAX_DAYS = 365
_SUMMARY_CACHE_TTL = 300  # 5 minutes

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── Date helpers ───────────────────────────────────────────────────────────────

def _resolve_dates(
    from_date: date | None,
    to_date: date | None,
    current_user: dict,
) -> tuple[datetime, datetime]:
    max_days = (
        _SUPER_ADMIN_MAX_DAYS
        if current_user.get("role") == "super_admin"
        else _DEFAULT_MAX_DAYS
    )
    today = date.today()
    to_date = to_date or today
    from_date = from_date or (today - timedelta(days=30))

    if (to_date - from_date).days > max_days:
        raise ValidationError(
            f"Date range cannot exceed {max_days} days. "
            f"Use a narrower range or contact support for extended access."
        )

    from_dt = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    to_dt = datetime.combine(to_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    return from_dt, to_dt


def _date_hash(from_dt: datetime, to_dt: datetime) -> str:
    key = f"{from_dt.date()}:{to_dt.date()}"
    return hashlib.md5(key.encode()).hexdigest()[:8]  # noqa: S324 (non-crypto use)


# ── Redis cache helpers ────────────────────────────────────────────────────────

def _get_redis():
    try:
        from redis.asyncio import from_url
        from app.config import settings
        return from_url(settings.redis_url, decode_responses=True)
    except Exception:
        return None


async def _cache_get(key: str) -> dict | None:
    redis = _get_redis()
    if not redis:
        return None
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass


async def _cache_set(key: str, value: dict, ttl: int = _SUMMARY_CACHE_TTL) -> None:
    redis = _get_redis()
    if not redis:
        return
    try:
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass


# ── Audit logging ──────────────────────────────────────────────────────────────

async def _audit_export(
    db: AsyncIOMotorDatabase,
    user: dict,
    restaurant_id: str,
    report_type: str,
    export_format: str,
    filters: dict,
) -> None:
    try:
        await db.audit_logs.insert_one({
            "user_id": str(user["_id"]),
            "user_email": user.get("email", ""),
            "resource_type": "report_export",
            "action": f"export_{report_type}",
            "restaurant_id": restaurant_id,
            "metadata": {"format": export_format, "filters": filters},
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.warning("audit_log_failed", error=str(e))


# ── Export response helpers ────────────────────────────────────────────────────

def _xlsx_response(rows: list, headers: list[str], filename: str) -> StreamingResponse:
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title="Report")
    ws.append(headers)
    for row in rows:
        ws.append([str(v) if v is not None else "" for v in row])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
    )


def _csv_response(rows: list, headers: list[str], filename: str) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows([[str(v) if v is not None else "" for v in row] for row in rows])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
    )


def _export_response(rows: list, headers: list[str], filename: str, fmt: str) -> StreamingResponse:
    if fmt == "csv":
        return _csv_response(rows, headers, filename)
    return _xlsx_response(rows, headers, filename)


# ── Campaign Reports ───────────────────────────────────────────────────────────

def _compute_rates(sent: int, delivered: int, read_opened: int, failed: int) -> dict:
    total = sent + failed
    return {
        "delivery_rate": round(delivered / sent * 100, 1) if sent else 0,
        "read_rate": round(read_opened / sent * 100, 1) if sent else 0,
        "failure_rate": round(failed / total * 100, 1) if total else 0,
    }


async def _build_campaign_data(
    restaurant_id: str,
    from_dt: datetime,
    to_dt: datetime,
    channel: str | None,
    db: AsyncIOMotorDatabase,
) -> dict:
    rid_slug = restaurant_id
    # We find the restaurant to get its potential ObjectId _id
    rest_doc = await db.restaurants.find_one({
        "$or": [{"id": restaurant_id}, {"_id": (ObjectId(restaurant_id) if ObjectId.is_valid(restaurant_id) else None)}]
    })
    rid_oid = str(rest_doc["_id"]) if rest_doc else None
    
    # Supported IDs for matching
    rids = list({rid_slug, rid_oid} - {None})

    wa_campaigns = []
    if channel in (None, "whatsapp"):
        async for doc in db.campaign_jobs.find(
            {"restaurant_id": {"$in": rids}, "created_at": {"$gte": from_dt, "$lte": to_dt}},
            sort=[("created_at", -1)],
        ):
            sent = doc.get("sent_count", 0)
            delivered = doc.get("delivered_count", 0)
            read = doc.get("read_count", 0)
            failed = doc.get("failed_count", 0)
            rates = _compute_rates(sent, delivered, read, failed)
            wa_campaigns.append({
                "id": str(doc["_id"]),
                "channel": "whatsapp",
                "name": doc.get("name", "Unnamed"),
                "status": doc.get("status", "unknown"),
                "created_at": doc["created_at"].isoformat(),
                "audience": sent + failed,
                "sent": sent, "delivered": delivered,
                "read_or_opened": read, "failed": failed,
                **rates,
            })

    email_campaigns = []
    if channel in (None, "email"):
        async for doc in db.email_campaign_jobs.find(
            {"restaurant_id": {"$in": rids}, "created_at": {"$gte": from_dt, "$lte": to_dt}},
            sort=[("created_at", -1)],
        ):
            sent = doc.get("sent_count", 0)
            delivered = doc.get("delivered_count", 0)
            opened = doc.get("opened_count", 0)
            failed = doc.get("failed_count", 0) + doc.get("bounced_count", 0)
            rates = _compute_rates(sent, delivered, opened, failed)
            email_campaigns.append({
                "id": str(doc["_id"]),
                "channel": "email",
                "name": doc.get("name", "Unnamed"),
                "status": doc.get("status", "unknown"),
                "created_at": doc["created_at"].isoformat(),
                "audience": doc.get("total_count", 0),
                "sent": sent, "delivered": delivered,
                "read_or_opened": opened, "failed": failed,
                **rates,
            })

    all_campaigns = wa_campaigns + email_campaigns
    all_campaigns.sort(key=lambda x: x["created_at"], reverse=True)

    total_sent = sum(c["sent"] for c in all_campaigns)
    total_delivered = sum(c["delivered"] for c in all_campaigns)
    total_read = sum(c["read_or_opened"] for c in all_campaigns)
    total_failed = sum(c["failed"] for c in all_campaigns)
    rates = _compute_rates(total_sent, total_delivered, total_read, total_failed)

    best = max(all_campaigns, key=lambda x: x["read_rate"], default=None)
    worst = max(all_campaigns, key=lambda x: x["failure_rate"], default=None)

    weekly: dict = defaultdict(lambda: {"sent": 0, "delivered": 0, "read": 0})
    for c in all_campaigns:
        dt = datetime.fromisoformat(c["created_at"])
        week_key = dt.strftime("W%W %Y")
        weekly[week_key]["sent"] += c["sent"]
        weekly[week_key]["delivered"] += c["delivered"]
        weekly[week_key]["read"] += c["read_or_opened"]
    weekly_trend = [{"week": k, **v} for k, v in sorted(weekly.items())]

    return {
        "summary": {
            "total_campaigns": len(all_campaigns),
            "total_sent": total_sent,
            "total_delivered": total_delivered,
            "total_read": total_read,
            "total_failed": total_failed,
            **rates,
            "best_campaign": best,
            "worst_campaign": worst,
        },
        "campaigns": all_campaigns,
        "weekly_trend": weekly_trend,
    }


@router.get("/campaigns/summary")
async def campaign_summary(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    channel: Annotated[Literal["whatsapp", "email"] | None, Query()] = None,
):
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    rid = restaurant["id"]

    cache_key = f"reports:campaigns:{rid}:{_date_hash(from_dt, to_dt)}:{channel or 'all'}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    result = await _build_campaign_data(rid, from_dt, to_dt, channel, db)
    await _cache_set(cache_key, result)
    return result


@router.get("/campaigns/export")
async def campaign_export(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    channel: Annotated[Literal["whatsapp", "email"] | None, Query()] = None,
    format: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "xlsx",
):
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    rid = restaurant["id"]

    data = await _build_campaign_data(rid, from_dt, to_dt, channel, db)
    campaigns = data["campaigns"]

    headers = ["Channel", "Campaign Name", "Date", "Status", "Audience",
               "Sent", "Delivered", "Delivery %", "Read/Opened", "Read %",
               "Failed", "Failure %"]
    rows = [[
        c["channel"].upper(), c["name"], c["created_at"][:10], c["status"],
        c["audience"], c["sent"], c["delivered"], f"{c['delivery_rate']}%",
        c["read_or_opened"], f"{c['read_rate']}%", c["failed"], f"{c['failure_rate']}%",
    ] for c in campaigns]

    filename = f"campaign_report_{from_dt.date()}_{to_dt.date()}"
    await _audit_export(db, current_user, rid, "campaigns", format, {
        "from": str(from_dt.date()), "to": str(to_dt.date()), "channel": channel,
    })
    return _export_response(rows, headers, filename, format)


# ── Member Reports ─────────────────────────────────────────────────────────────

@router.get("/members/summary")
async def member_summary(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
):
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    
    # We find all possible identifiers for the restaurant (Slug and OID)
    rid = restaurant["id"]
    rid_oid = str(restaurant.get("_id"))
    rids = list({rid, rid_oid} - {None})

    cache_key = f"reports:members:{rid}:{_date_hash(from_dt, to_dt)}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    dormant_cutoff = now - timedelta(days=30)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # Monthly growth trend
    growth_raw = await db.members.aggregate([
        {"$match": {"restaurant_id": {"$in": rids}, "joined_at": {"$gte": from_dt, "$lte": to_dt}}},
        {"$group": {
            "_id": {"year": {"$year": "$joined_at"}, "month": {"$month": "$joined_at"}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1}},
    ]).to_list(24)
    monthly_growth = [
        {
            "month": f"{_MONTH_NAMES[r['_id']['month'] - 1]} {r['_id']['year']}",
            "new_members": r["count"],
        }
        for r in growth_raw
    ]

    # Category split - scoped to restaurant but NOT the current date filter
    # (Shows the composition of the ENTIRE member base)
    cat_raw = await db.members.aggregate([
        {"$match": {"restaurant_id": {"$in": rids}, "is_active": True}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]).to_list(20)
    category_split = [{"category": r["_id"] or "unknown", "count": r["count"]} for r in cat_raw]

    # --- Scalar counts (parallelised via gather) ---
    import asyncio
    total_all_t = db.members.count_documents({"restaurant_id": {"$in": rids}})
    total_active_t = db.members.count_documents({"restaurant_id": {"$in": rids}, "is_active": True})
    new_month_t = db.members.count_documents({"restaurant_id": {"$in": rids}, "joined_at": {"$gte": month_start}})
    dormant_t = db.members.count_documents({
        "restaurant_id": {"$in": rids}, "is_active": True,
        "$or": [{"last_visit": {"$lt": dormant_cutoff}}, {"last_visit": None}],
    })
    total_all, total_active, new_this_month, dormant = await asyncio.gather(
        total_all_t, total_active_t, new_month_t, dormant_t,
    )

    # Top visitors - scoped to restaurant but NOT the current date filter
    top_visitors = []
    async for doc in db.members.find(
        {"restaurant_id": {"$in": rids}, "is_active": True},
        {"name": 1, "phone": 1, "type": 1, "visit_count": 1, "last_visit": 1},
    ).sort("visit_count", -1).limit(10):
        top_visitors.append({
            "name": doc.get("name", ""),
            "phone": doc.get("phone", ""),
            "type": doc.get("type", ""),
            "visit_count": doc.get("visit_count", 0),
            "last_visit": doc["last_visit"].isoformat() if doc.get("last_visit") else None,
        })

    result = {
        "summary": {
            "total_members": total_all,
            "active_members": total_active,
            "new_this_month": new_this_month,
            "dormant_members": dormant,
            "dormant_rate": round(dormant / total_active * 100, 1) if total_active else 0,
        },
        "monthly_growth": monthly_growth,
        "category_split": category_split,
        "top_visitors": top_visitors,
    }

    await _cache_set(cache_key, result)
    return result


@router.get("/members/export")
async def member_export(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    format: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "xlsx",
):
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    rid = restaurant["id"]
    rid_oid = str(restaurant.get("_id"))
    rids = list({rid, rid_oid} - {None})

    query: dict = {"restaurant_id": {"$in": rids}, "joined_at": {"$gte": from_dt, "$lte": to_dt}}
    if category:
        query["type"] = category

    headers = ["Name", "Phone", "Email", "Type", "Joined Date", "Visit Count",
               "Last Visit", "Is Active", "Card UID", "eCard Code", "Tags", "Notes"]
    rows = []
    async for doc in db.members.find(query).sort("joined_at", -1):
        rows.append([
            doc.get("name", ""),
            doc.get("phone", ""),
            doc.get("email", "") or "",
            doc.get("type", ""),
            doc["joined_at"].strftime("%Y-%m-%d") if doc.get("joined_at") else "",
            doc.get("visit_count", 0),
            doc["last_visit"].strftime("%Y-%m-%d") if doc.get("last_visit") else "",
            "Yes" if doc.get("is_active") else "No",
            doc.get("card_uid", "") or "",
            doc.get("ecard_code", "") or "",
            ", ".join(doc.get("tags", [])),
            doc.get("notes", "") or "",
        ])

    filename = f"member_report_{from_dt.date()}_{to_dt.date()}"
    await _audit_export(db, current_user, rid, "members", format, {
        "from": str(from_dt.date()), "to": str(to_dt.date()), "category": category,
    })
    return _export_response(rows, headers, filename, format)


# ── Delivery Logs ──────────────────────────────────────────────────────────────

@router.get("/logs")
async def delivery_logs(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    channel: Annotated[Literal["whatsapp", "email"] | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    after_id: Annotated[str | None, Query()] = None,  # cursor pagination
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    rid = restaurant["id"]
    rid_oid = str(restaurant.get("_id"))
    rids = list({rid, rid_oid} - {None})

    # Gather tenant-scoped job IDs
    wa_job_ids = (
        [doc["_id"] async for doc in db.campaign_jobs.find({"restaurant_id": {"$in": rids}}, {"_id": 1})]
        if channel in (None, "whatsapp") else []
    )
    email_job_ids = (
        [doc["_id"] async for doc in db.email_campaign_jobs.find({"restaurant_id": {"$in": rids}}, {"_id": 1})]
        if channel in (None, "email") else []
    )

    results: list[dict] = []

    # ------------------------------------------------------------------
    # WhatsApp logs
    # ------------------------------------------------------------------
    if wa_job_ids:
        wa_q: dict = {
            "job_id": {"$in": wa_job_ids},
            "created_at": {"$gte": from_dt, "$lte": to_dt},
        }
        if status:
            wa_q["status"] = status
        if search:
            wa_q["to_phone"] = {"$regex": search, "$options": "i"}
        if after_id:
            try:
                wa_q["_id"] = {"$lt": ObjectId(after_id)}
            except Exception:
                pass

        async for doc in db.message_logs.find(wa_q).sort("_id", -1).limit(page_size):
            results.append({
                "id": str(doc["_id"]),
                "channel": "whatsapp",
                "recipient": doc.get("to_phone", ""),
                "recipient_name": doc.get("name", ""),
                "campaign_id": str(doc.get("job_id", "")),
                "status": doc.get("status", ""),
                "error_reason": doc.get("error_message", ""),
                "retry_count": doc.get("retry_count", 0),
                "created_at": doc["created_at"].isoformat(),
            })

    # ------------------------------------------------------------------
    # Email logs
    # ------------------------------------------------------------------
    if email_job_ids:
        email_q: dict = {
            "campaign_id": {"$in": email_job_ids},
            "created_at": {"$gte": from_dt, "$lte": to_dt},
        }
        if status:
            email_q["status"] = status
        if search:
            email_q["recipient_email"] = {"$regex": search, "$options": "i"}
        if after_id:
            try:
                email_q["_id"] = {"$lt": ObjectId(after_id)}
            except Exception:
                pass

        async for doc in db.email_logs.find(email_q).sort("_id", -1).limit(page_size):
            results.append({
                "id": str(doc["_id"]),
                "channel": "email",
                "recipient": doc.get("recipient_email", ""),
                "recipient_name": doc.get("recipient_name", ""),
                "campaign_id": str(doc.get("campaign_id", "")),
                "status": doc.get("status", ""),
                "error_reason": doc.get("error_reason", ""),
                "retry_count": doc.get("retry_count", 0),
                "created_at": doc["created_at"].isoformat(),
            })

    # Merge-sort and slice
    results.sort(key=lambda x: x["created_at"], reverse=True)
    results = results[:page_size]
    next_cursor = results[-1]["id"] if len(results) == page_size else None

    return {"items": results, "next_cursor": next_cursor, "page_size": page_size}


@router.get("/logs/export")
async def export_logs(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    channel: Annotated[Literal["whatsapp", "email"] | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    format: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "xlsx",
):
    _MAX_EXPORT_ROWS = 5000
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    rid = restaurant["id"]
    rid_oid = str(restaurant.get("_id"))
    rids = list(set([rid, rid_oid]) - {None})

    headers = ["Timestamp", "Channel", "Recipient", "Name",
               "Campaign ID", "Status", "Error Reason", "Retry Count"]
    rows: list[list] = []

    wa_job_ids = [doc["_id"] async for doc in db.campaign_jobs.find({"restaurant_id": {"$in": rids}}, {"_id": 1})]
    if channel in (None, "whatsapp") and wa_job_ids:
        wa_q: dict = {
            "job_id": {"$in": wa_job_ids},
            "created_at": {"$gte": from_dt, "$lte": to_dt},
        }
        if status:
            wa_q["status"] = status
        async for doc in db.message_logs.find(wa_q).sort("created_at", -1).limit(_MAX_EXPORT_ROWS):
            rows.append([
                doc["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "WhatsApp",
                doc.get("to_phone", ""),
                doc.get("name", ""),
                str(doc.get("job_id", "")),
                doc.get("status", ""),
                doc.get("error_message", ""),
                doc.get("retry_count", 0),
            ])

    email_job_ids = [doc["_id"] async for doc in db.email_campaign_jobs.find({"restaurant_id": {"$in": rids}}, {"_id": 1})]
    if channel in (None, "email") and email_job_ids:
        email_q: dict = {
            "campaign_id": {"$in": email_job_ids},
            "created_at": {"$gte": from_dt, "$lte": to_dt},
        }
        if status:
            email_q["status"] = status
        async for doc in db.email_logs.find(email_q).sort("created_at", -1).limit(_MAX_EXPORT_ROWS):
            rows.append([
                doc["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "Email",
                doc.get("recipient_email", ""),
                doc.get("recipient_name", ""),
                str(doc.get("campaign_id", "")),
                doc.get("status", ""),
                doc.get("error_reason", ""),
                doc.get("retry_count", 0),
            ])

    rows.sort(key=lambda x: x[0], reverse=True)

    filename = f"delivery_logs_{from_dt.date()}_{to_dt.date()}"
    await _audit_export(db, current_user, rid, "logs", format, {
        "from": str(from_dt.date()), "to": str(to_dt.date()),
        "channel": channel, "status": status,
    })
    return _export_response(rows, headers, filename, format)

# ── Inbox Engagement Reports ──────────────────────────────────────────────────

async def _build_inbox_data(
    restaurant: dict,
    from_dt: datetime,
    to_dt: datetime,
    db: AsyncIOMotorDatabase,
) -> dict:
    rid = restaurant["id"]

    # Now that we have restaurant_id directly on messages, the query is much faster
    # and includes potential members (anonymous senders).
    # The report is now GLOBAL (irrespective of rid) but includes restaurant attribution
    pipeline = [
        {"$match": {
            "received_at": {"$gte": from_dt, "$lte": to_dt}
        }},
        {"$sort": {"received_at": -1}},
        {
            "$lookup": {
                "from": "members",
                "localField": "from_phone",
                "foreignField": "phone",
                "as": "member_info",
            }
        },
        {
            "$lookup": {
                "from": "restaurants",
                "localField": "restaurant_id",
                "foreignField": "id",
                "as": "restaurant_info",
            }
        },
        {
            "$addFields": {
                "displayName": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$member_info.name", 0]},
                        "$sender_name",
                        "$from_phone",
                    ]
                },
                "restaurantName": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$restaurant_info.name", 0]},
                        "Unassigned"
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$from_phone",
                "name": {"$first": "$displayName"},
                "restaurant_id": {"$first": "$restaurant_id"},
                "restaurant_name": {"$first": "$restaurantName"},
                "message_count": {"$sum": 1},
                "last_message": {"$first": "$body"},
                "last_received_at": {"$max": "$received_at"},
            }
        },
        {"$sort": {"message_count": -1}},
    ]

    engaged_customers = await db.inbound_messages.aggregate(pipeline).to_list(1000)
    
    total_messages = sum(c["message_count"] for c in engaged_customers)
    unique_senders = len(engaged_customers)
    avg_per_sender = round(total_messages / unique_senders, 1) if unique_senders else 0

    return {
        "summary": {
            "total_incoming_messages": total_messages,
            "unique_engaged_senders": unique_senders,
            "avg_messages_per_sender": avg_per_sender,
            "top_engaged_customer": engaged_customers[0] if engaged_customers else None,
        },
        "engaged_customers": [
            {
                "phone": c["_id"],
                "name": c["name"] or "Unknown",
                "restaurant_id": c.get("restaurant_id"),
                "restaurant_name": c.get("restaurant_name") or "Unassigned",
                "message_count": c["message_count"],
                "last_message": c["last_message"] or "(Media/Other)",
                "last_received_at": c["last_received_at"].isoformat(),
            }
            for c in engaged_customers
        ],
    }


@router.get("/inbox/summary")
async def inbox_summary(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
):
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    rid = restaurant["id"]

    cache_key = f"reports:inbox:{rid}:{_date_hash(from_dt, to_dt)}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    result = await _build_inbox_data(restaurant, from_dt, to_dt, db)
    await _cache_set(cache_key, result)
    return result


@router.get("/inbox/export")
async def inbox_export(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    format: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "xlsx",
):
    from_dt, to_dt = _resolve_dates(from_date, to_date, current_user)
    rid = restaurant["id"]

    data = await _build_inbox_data(restaurant, from_dt, to_dt, db)
    customers = data["engaged_customers"]

    headers = ["Customer Name", "Phone", "Incoming Messages", "Latest Message Recv.", "Last Active Date"]
    rows = [[
        c["name"], c["phone"], c["message_count"], c["last_message"], c["last_received_at"][:10],
    ] for c in customers]

    filename = f"inbox_engagement_report_{from_dt.date()}_{to_dt.date()}"
    await _audit_export(db, current_user, rid, "inbox", format, {
        "from": str(from_dt.date()), "to": str(to_dt.date()),
    })
    return _export_response(rows, headers, filename, format)
