"""
Central time utility — single source of truth for all datetime operations.

Design contract:
  - DB writes  → always UTC  (use now_utc())
  - API output → always IST  (use to_ist() / ist_isoformat())
  - DB queries → IST date boundaries converted to UTC  (use date_range_to_utc())

Never call datetime.now() bare anywhere in the codebase. Use now_utc().
"""

from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

# India Standard Time — UTC+5:30
IST = ZoneInfo("Asia/Kolkata")


# ── DB Write helpers (always UTC) ──────────────────────────────────────────────

def now_utc() -> datetime:
    """Current moment as a UTC-aware datetime.  Use for ALL database writes."""
    return datetime.now(timezone.utc)


# ── Display helpers (UTC → IST) ────────────────────────────────────────────────

def now_ist() -> datetime:
    """Current moment in IST.  Use for human-readable logs/output only."""
    return now_utc().astimezone(IST)


def to_ist(dt: datetime | None) -> datetime | None:
    """Convert a UTC datetime (from DB) to IST for display.
    Naive datetimes are assumed to be UTC — safe for all MongoDB-sourced values.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)   # treat naive as UTC
    return dt.astimezone(IST)


def ist_isoformat(dt: datetime | None) -> str | None:
    """Return an IST ISO-8601 string ready for API responses.
    e.g. '2025-05-06T17:45:00+05:30'
    """
    converted = to_ist(dt)
    return converted.isoformat() if converted else None


# ── Query helpers (IST day → UTC bounds for MongoDB) ──────────────────────────

def date_range_to_utc(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    """Convert an inclusive IST calendar date range to UTC datetimes for DB queries.

    The user picks dates in IST context (e.g. 'May 6').
    This converts IST midnight → IST 23:59:59 to UTC so MongoDB $gte/$lte
    correctly covers that calendar day in India, not in UTC.

    Args:
        from_date: Start date (IST midnight = start of day).
        to_date:   End date   (IST 23:59:59.999999 = end of day).

    Returns:
        (from_utc, to_utc) — use directly in MongoDB range queries.
    """
    start_ist = datetime(from_date.year, from_date.month, from_date.day,
                         0, 0, 0, 0, tzinfo=IST)
    end_ist = datetime(to_date.year, to_date.month, to_date.day,
                       23, 59, 59, 999999, tzinfo=IST)
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def ist_month_start_utc() -> datetime:
    """Return the first instant of the current IST calendar month, as UTC.
    Use for 'new members this month' style queries.
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
