"""
Central time utility — single source of truth for all datetime operations.

Design contract:
  - DB writes  → always UTC  (use now_utc())
  - API output → always IST  (use to_ist() / ist_isoformat() / format_ist())
  - DB queries → IST date boundaries converted to UTC  (use date_range_to_utc())
  - Aggregations → MongoDB timezone="Asia/Kolkata" (use mongo_hour_ist() / mongo_date_parts_ist())

Never call datetime.now() bare anywhere in the codebase. Use now_utc().
"""

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

# Standard IANA identifier for Indian Standard Time (UTC+05:30)
IST_TIMEZONE_NAME = "Asia/Kolkata"
IST = ZoneInfo(IST_TIMEZONE_NAME)
UTC = timezone.utc

__all__ = [
    "IST",
    "IST_TIMEZONE_NAME",
    "UTC",
    "now_utc",
    "now_ist",
    "to_ist",
    "to_utc",
    "to_ist_hour",
    "to_ist_date",
    "format_ist",
    "ist_isoformat",
    "date_range_to_utc",
    "ist_month_start_utc",
    "normalize_external_dt",
    "mongo_hour_ist",
    "mongo_date_parts_ist",
]


# ── DB Write helpers (always UTC) ──────────────────────────────────────────────

def now_utc() -> datetime:
    """Current moment as a timezone-aware UTC datetime. Use for ALL database writes."""
    return datetime.now(timezone.utc)


# ── Display & Conversion helpers (UTC → IST) ───────────────────────────────────

def now_ist() -> datetime:
    """Current moment in Indian Standard Time (Asia/Kolkata)."""
    return datetime.now(timezone.utc).astimezone(IST)


def to_ist(dt: Any) -> datetime | None:
    """Convert any source timestamp to a timezone-aware IST (Asia/Kolkata) datetime.

    Handles:
      - None -> returns None
      - str (ISO 8601 string) -> parses and converts to IST
      - Naive datetime -> safely assumed to be UTC (standard for MongoDB BSON dates)
      - Timezone-aware datetime -> converted to Asia/Kolkata
    """
    if dt is None:
        return None

    if isinstance(dt, str):
        clean_str = dt.strip()
        if clean_str.endswith("Z"):
            clean_str = clean_str[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(clean_str)
        except ValueError:
            try:
                parsed = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
        dt = parsed

    if not isinstance(dt, datetime):
        return None

    if dt.tzinfo is None:
        # Naive datetime from MongoDB represents UTC
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(IST)


def to_utc(dt: Any) -> datetime | None:
    """Convert an IST or naive datetime to a timezone-aware UTC datetime."""
    if dt is None:
        return None

    if isinstance(dt, str):
        clean_str = dt.strip()
        if clean_str.endswith("Z"):
            clean_str = clean_str[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(clean_str)
        except ValueError:
            return None

    if not isinstance(dt, datetime):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def to_ist_hour(dt: Any) -> int | None:
    """Extract the hour of the day (0-23) in Indian Standard Time."""
    ist_dt = to_ist(dt)
    return ist_dt.hour if ist_dt else None


def to_ist_date(dt: Any) -> date | None:
    """Extract the calendar date in Indian Standard Time."""
    ist_dt = to_ist(dt)
    return ist_dt.date() if ist_dt else None


def format_ist(dt: Any, fmt: str = "%Y-%m-%d %H:%M:%S") -> str | None:
    """Format a timestamp in IST for CSV/XLSX exports or user displays."""
    ist_dt = to_ist(dt)
    return ist_dt.strftime(fmt) if ist_dt else None


def ist_isoformat(dt: Any) -> str | None:
    """Return an IST ISO-8601 formatted string (e.g. 2026-09-08T18:35:00+05:30)."""
    ist_dt = to_ist(dt)
    return ist_dt.isoformat() if ist_dt else None


# ── Query helpers (IST day → UTC bounds for MongoDB) ──────────────────────────

def date_range_to_utc(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    """Convert an inclusive IST calendar date range to UTC datetimes for MongoDB queries.

    The user picks dates in IST context (e.g. May 6).
    This converts IST midnight → IST 23:59:59.999999 to UTC so MongoDB $gte/$lte
    correctly covers that calendar day in India, not in UTC.
    """
    start_ist = datetime(
        from_date.year, from_date.month, from_date.day, 0, 0, 0, 0, tzinfo=IST
    )
    end_ist = datetime(
        to_date.year, to_date.month, to_date.day, 23, 59, 59, 999999, tzinfo=IST
    )
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def ist_month_start_utc() -> datetime:
    """Return the first moment of the current IST calendar month as a UTC datetime.
    Use for new members this month style queries.
    """
    now = now_ist()
    start_ist = datetime(now.year, now.month, 1, 0, 0, 0, 0, tzinfo=IST)
    return start_ist.astimezone(timezone.utc)


# ── Normalization helper (external sources: webhooks, Fielia) ──────────────────

def normalize_external_dt(dt: datetime | None) -> datetime | None:
    """Normalize an externally sourced datetime to UTC-aware.
    Naive datetimes are assumed to be UTC (standard for WhatsApp/Meta/Fielia).
    Aware datetimes are converted to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── MongoDB Aggregation Helpers ───────────────────────────────────────────────

def mongo_hour_ist(date_field: str, fallback_field: str | None = None) -> dict:
    """Generate a MongoDB $hour expression that extracts the hour in Asia/Kolkata."""
    clean_field = date_field.lstrip("$")
    field_ref = f"${clean_field}"
    if fallback_field:
        clean_fallback = fallback_field.lstrip("$")
        fallback_ref = f"${clean_fallback}"
        date_expr: Any = {"$ifNull": [field_ref, fallback_ref]}
    else:
        date_expr = field_ref

    return {"$hour": {"date": date_expr, "timezone": IST_TIMEZONE_NAME}}


def mongo_date_parts_ist(date_field: str) -> dict:
    """Generate MongoDB date part expressions (year, month, day) in Asia/Kolkata."""
    clean_field = date_field.lstrip("$")
    field_ref = f"${clean_field}"
    return {
        "year": {"$year": {"date": field_ref, "timezone": IST_TIMEZONE_NAME}},
        "month": {"$month": {"date": field_ref, "timezone": IST_TIMEZONE_NAME}},
        "day": {"$dayOfMonth": {"date": field_ref, "timezone": IST_TIMEZONE_NAME}},
    }


