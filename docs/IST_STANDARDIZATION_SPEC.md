# Tech Spec: IST (Asia/Kolkata) Time Standardization

**Status:** Implemented
**Author:** Engineering
**Date:** September 2026
**Branch:** `fix/ist-standardization`

---

## 1. Background & Problem Statement

RestoBuzz serves Indian restaurants exclusively. Every restaurant staff member
reading the dashboard, every export a restaurant downloads, and every date a
user picks in a filter is reasoned about in **Indian Standard Time (UTC+05:30)**.
MongoDB, however, stores every date as naive UTC (the BSON `Date` convention),
and the backend previously mixed conventions:

- Some endpoints called `datetime.utcnow()` / raw `.strftime()` and displayed
  UTC clock values unlabeled, which are wrong by 5.5 hours for an IST reader.
- Some MongoDB aggregations grouped by day/month/hour using the **server's**
  implicit UTC calendar day, so a booking made at 11:30 PM IST (still "today"
  in India) could be bucketed into "yesterday" in a trend chart.
- The frontend independently re-implemented UTC→IST conversion in several
  components with subtly different (and sometimes wrong) logic.

### Why this is a problem

A restaurant's daily revenue trend, "new members this month" count, hourly
send-performance chart, and every CSV/XLSX export are all silently off by
up to a full calendar day for any activity that happens in the UTC 18:30–23:59
window (which is most of the Indian evening). This corrupts numbers restaurant
owners use to make same-day operational decisions and undermines trust in the
product's reporting.

---

## 2. Goals

- Establish a **single source of truth** for all UTC ↔ IST conversion:
  `app/core/time.py` on the backend, `apps/frontend/lib/date.ts` on the
  frontend. No component should hand-roll `Intl.DateTimeFormat` /
  `datetime.astimezone` logic itself.
- **DB writes stay UTC.** Never change what's persisted — only how it's
  displayed, exported, and grouped.
- **API output, exports, and calendar grouping (day/month/hour buckets) use
  IST.** A "today" in the dashboard must match the restaurant staff's actual
  calendar day in India.
- Make the migration incremental and low-risk: where an export already had a
  UTC column depended on by anyone, add the IST column alongside it rather
  than silently replacing values underneath existing consumers.

---

## 3. Design Contract (`app/core/time.py`)

```
DB writes    → always UTC        (use now_utc())
API output   → always IST        (use to_ist() / ist_isoformat() / format_ist())
DB queries   → IST date boundaries converted to UTC  (use date_range_to_utc())
Aggregations → MongoDB timezone="Asia/Kolkata"        (use mongo_hour_ist() / mongo_date_parts_ist())
```

Never call `datetime.now()` bare anywhere in the codebase — use `now_utc()`.

### Core helpers

| Helper | Purpose |
| --- | --- |
| `now_utc()` | Current moment, UTC-aware. All DB writes. |
| `now_ist()` | Current moment, IST-aware. |
| `to_ist(dt)` / `to_utc(dt)` | Convert a `datetime`, ISO string, or `None` between UTC and IST. Naive input is assumed UTC (the MongoDB convention). |
| `to_ist_hour(dt)` / `to_ist_date(dt)` | Extract just the hour or calendar date, in IST. |
| `format_ist(dt, fmt)` | Format a timestamp in IST for exports/UI. |
| `ist_isoformat(dt)` | IST ISO-8601 string, e.g. `2026-09-08T18:35:00+05:30`. |
| `date_range_to_utc(from_date, to_date)` | Convert a user-picked IST calendar range into UTC bounds for a Mongo `$gte`/`$lte` query. |
| `ist_month_start_utc()` | Start of the current IST month, as UTC, for "this month" queries. |
| `mongo_hour_ist(date_field, fallback_field=None)` | Build a `$hour` aggregation expression bucketed by Asia/Kolkata. |
| `mongo_date_parts_ist(date_field, include_day=True)` | Build `{year, month[, day]}` aggregation expressions bucketed by Asia/Kolkata. Pass `include_day=False` for month-level grouping. |

**Every** MongoDB aggregation stage that buckets by calendar day, month, or
hour goes through `mongo_hour_ist()` / `mongo_date_parts_ist()` — never an
inline `{"$year": {"date": ..., "timezone": "Asia/Kolkata"}}` dict. This keeps
the timezone identifier and the `$ifNull` fallback pattern in one place, so a
future correction only needs to happen once. Call sites: `campaigns.py`
(hourly performance), `reports.py` (member growth trend, billing daily
trend), `reservego.py` (monthly revenue trend), `fielia_members_service.py`
(Fielia growth trend).

### Frontend equivalent (`apps/frontend/lib/date.ts`)

| Helper | Purpose |
| --- | --- |
| `parse(date)` | Parse a backend timestamp, treating an offset-less string as UTC (the backend serializes naive-UTC datetimes with no `Z`/offset suffix). **Every** component that turns a raw API timestamp into a `Date` must go through this — never `new Date(apiValue)` directly. |
| `relativeIST`, `absoluteIST`, `timeIST`, `inboxShortDateIST` | Display formatters for common UI cases. |
| `toISTDateKey(date)` | `'YYYY-MM-DD'` in IST — the grouping key that must match the backend's `mongo_date_parts_ist` bucketing. |
| `toISTDateLabel(date)` | `'MMM D'`, for chart x-axes. |
| `toISTDateMedium(date)` | `'D MMM YYYY'`, for table cells (campaign tables, acquisition section). |
| `getISTTodayParts()` / `getISTDateOffset(daysAgo, base?)` | Today's IST calendar date, and N days before it. Pass a `getISTTodayParts()` result as `base` when deriving several offsets in a loop, so "now" isn't re-resolved via `Intl.DateTimeFormat` on every iteration. |

---

## 4. Detailed Changes by Area

### 4.1 Exports (`app/routers/reports.py`)

Three CSV/XLSX exports gained an IST-formatted column alongside the existing
UTC one, so nothing consuming the original column silently breaks:

- **Member export** (`/reports/members/export`): `Joined Date (UTC)` /
  `Joined Date (IST)`, `Last Visit (UTC)` / `Last Visit (IST)`.
- **Delivery logs export** (`/reports/logs/export`): `Timestamp (UTC)` /
  `Timestamp (IST)`.
- **Billing export** (`/reports/billing/export`): `Date (UTC)` / `Date (IST)`.

The header list for each export is updated in lockstep with its row-builder —
row length and header length must always match exactly (a mismatch silently
shifts every column label one or more positions to the left with no error at
export time or in the file itself).

### 4.2 ReserveGo exports (`app/routers/reservego.py`)

`_fmt_dt()` (used by both the Guests and Bills XLSX exports) now routes every
`datetime`/`str` value through `format_ist()`. The monthly revenue trend
aggregation groups by `mongo_date_parts_ist("booking_time", include_day=False)`
instead of an inline `$year`/`$month` expression.

### 4.3 Campaign hourly performance (`app/routers/campaigns.py`)

The `$hour` aggregation for the "messages by hour of day" chart uses
`mongo_hour_ist("updated_at", fallback_field="created_at")`, matching the
`$ifNull` fallback that was previously written out by hand.

### 4.4 Fielia growth trend (`app/services/fielia_members_service.py`)

Same treatment as the member growth trend: groups by
`mongo_date_parts_ist("createdAt", include_day=False)`.

### 4.5 Frontend display (`CampaignTable.tsx`, `AcquisitionSection.tsx`)

Backend timestamps (`created_at`, `scheduled_at`, `tracking_started_at`) are
serialized by Pydantic as naive-UTC strings with **no** `Z` or offset suffix.
Passing one straight to `new Date(...)` makes the JS runtime interpret it in
the *browser's local timezone* — for a viewer in India, that means the naive
UTC wall-clock digits get read as if they were already IST, and the
subsequent `timeZone: "Asia/Kolkata"` formatting compounds the error instead
of correcting it. The net effect: the displayed time is off by exactly the
UTC↔IST offset (5.5 hours), which can shift the displayed date by a full day.

Fixed by routing every such timestamp through `parse()` before formatting,
and consolidating the three duplicated `Intl.DateTimeFormat("en-IN", {day,
month, year})` blocks (`CampaignTable.tsx` root row, retry row, and
`AcquisitionSection.tsx`) into the shared `toISTDateMedium()` helper.

### 4.6 Inbox date separator (`app/(dashboard)/inbox/page.tsx`)

`DateSeparator` had its own inline copy of the "does this string already
carry a timezone" check (`endsWith("Z") || includes("+")`), which — like the
original version of `lib/date.ts`'s `parse()` — mishandled a **negative**
UTC offset (`...-05:00`): the check would fail to recognize it as already
timezone-qualified and append a spurious trailing `Z`, corrupting the parsed
instant. `parse()` now uses a proper trailing-offset regex
(`/(Z|[+-]\d{2}:\d{2})$/`) and is exported from `lib/date.ts`; the inbox
component now imports and uses it instead of duplicating the logic.

### 4.7 Dashboard time-series performance (`useDashboardAnalytics.ts`)

The 14-day time-series builder called `getISTDateOffset(i)` once per day,
and each call independently re-resolved "now" via a fresh
`Intl.DateTimeFormat(...).formatToParts(new Date())`. `getISTTodayParts()` is
now called once before the loop and passed in as `getISTDateOffset(i,
todayIST)`, cutting 14 `Intl.DateTimeFormat` construction + formatting passes
down to 1.

---

## 5. Fixes to Pre-Existing Issues in This Branch

A code review of this branch (see PR discussion) surfaced issues beyond the
IST conversion itself, all addressed in this pass:

| Area | Issue | Fix |
| --- | --- | --- |
| `reservego.py` `_fmt_dt` | The pre-existing `isinstance(val, datetime)` branch ran *before* the new IST-aware branch and always matched first (every caller passes a `datetime`), so the new `format_ist()` path was unreachable dead code — ReserveGo exports stayed in raw UTC. | Removed the dead branch; `format_ist()` is now the only path for `datetime`/`str` input. |
| `app/config.py` | `mongodb_url`'s `AliasChoices` order was flipped to `(MONGODB_URL, MONGODB_URL_PROD)`, unrelated to IST work and contradicting the comment above it — in any environment with both vars set, this silently points the app at the wrong database. | Reverted to `(MONGODB_URL_PROD, MONGODB_URL)`. |
| `reports/page.tsx` | The "All Time" report preset's lower bound was silently narrowed from `2020-01-01` to `2024-01-01`, unrelated to IST work — would silently drop older member/campaign data for any restaurant with pre-2024 history. | Reverted to `2020-01-01`. |
| `reports.py` weekly trend | Any campaign whose `created_at` failed to parse was silently bucketed under `"Unknown"` with no signal that something was wrong (the prior code raised loudly via `datetime.fromisoformat`). | Kept the safe fallback (one bad record shouldn't 500 the whole endpoint for every campaign) but added a `logger.warning("campaign_created_at_unparseable", ...)` so the condition is now visible instead of silent. |
| `time.py` | `mongo_hour_ist()` / `mongo_date_parts_ist()` were introduced as the intended single source of truth but nothing was migrated to call them — five call sites kept hand-rolled, duplicated `$year`/`$month`/`$hour` timezone dicts. | Migrated all five call sites (§4.1–4.4 above). |
| `database.py` | TLS CA-bundle selection (`certifi.where() if "+srv" in url else None`) was duplicated verbatim across `get_client`, `get_fresh_db`, `get_fielia_db`; `import certifi` sat mid-file instead of with the top-level imports, and `certifi` was undeclared in `requirements.txt` (only present transitively via `httpx`). | Extracted a `_ca_cert_for(uri)` helper used by all three; moved the import to the top; added `certifi==2025.7.14` to `requirements.txt`. |
| `reports.py`, `fielia_members_service.py` | Both files had two separate `from app.core.time import (...)` statements (an artifact of a merge/paste), instead of one combined import. | Merged into a single import statement in each file. |

---

## 6. Files Changed

| File | Change type |
| --- | --- |
| `app/core/time.py` | `mongo_date_parts_ist` gains `include_day` parameter |
| `app/config.py` | Revert unrelated `AliasChoices` order flip |
| `app/database.py` | Dedupe TLS CA-cert logic into `_ca_cert_for`; move `certifi` import to top |
| `app/routers/campaigns.py` | Hourly performance aggregation uses `mongo_hour_ist` |
| `app/routers/reports.py` | Fix 3 export header/row mismatches; dedupe import; use `mongo_date_parts_ist`; log unparseable campaign dates |
| `app/routers/reservego.py` | Fix dead `_fmt_dt` branch; use `mongo_date_parts_ist` for monthly revenue |
| `app/services/fielia_members_service.py` | Dedupe import; use `mongo_date_parts_ist` |
| `requirements.txt` | Add explicit `certifi` pin |
| `apps/frontend/lib/date.ts` | Export fixed `parse()`; add `toISTDateMedium`, `getISTTodayParts` |
| `apps/frontend/app/(dashboard)/inbox/page.tsx` | Use shared `parse()` instead of duplicated, buggy offset heuristic |
| `apps/frontend/app/(dashboard)/reports/page.tsx` | Revert unrelated "All Time" lower-bound change |
| `apps/frontend/app/(dashboard)/dashboard/hooks/useDashboardAnalytics.ts` | Compute IST "today" once per render instead of per loop iteration |
| `apps/frontend/components/campaigns/organisms/CampaignTable.tsx` | Fix double-timezone bug via `parse()`; dedupe date formatting via `toISTDateMedium` |
| `apps/frontend/components/reports/molecules/AcquisitionSection.tsx` | Fix double-timezone bug via `toISTDateMedium` |

---

## 7. Verification

- `python3 -m py_compile` on every changed backend file — clean.
- Full backend test suite: **301 passed, 4 skipped**.
- `tsc --noEmit` on the frontend — clean, no type errors.
- Manual trace of each of the three export row/header pairs to confirm
  column counts now match exactly.

## 8. What Is NOT Changing

- No database migration — all persisted values remain naive UTC.
- No API contract changes beyond additive export columns (existing UTC
  columns and their positions are preserved; new IST columns are appended
  immediately after their UTC counterpart).
- No change to how `now_utc()` is used for writes anywhere in the codebase.
