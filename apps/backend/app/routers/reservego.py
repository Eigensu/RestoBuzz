"""
ReserveGo upload portal.

Auth: simple username/password against env vars RESERVEGO_USER / RESERVEGO_PASSWORD.
Returns a short-lived JWT (role=reservego) used to authenticate the upload endpoint.

Performance: openpyxl parsing (CPU-bound) runs in a thread pool; DB writes use
bulk_write so the entire sheet is one round-trip instead of N awaits.
"""

import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Annotated

import openpyxl
from fastapi import APIRouter, Body, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from pymongo import UpdateOne

from app.config import settings
from app.core.errors import InvalidCredentialsError, InvalidFileFormatError, AppError
from app.core.security import _create_token, decode_token
from app.database import get_db

router = APIRouter(prefix="/reservego", tags=["reservego"])
_bearer = HTTPBearer()
_executor = ThreadPoolExecutor(max_workers=2)

# ── String constants (avoids Sonar duplicate-literal warnings) ────────────────
_COL_GUEST_NAME = "guest name"
_COL_BILL_AMOUNT = "bill amount"
_COL_BILL_NUMBER = "bill number"
_COL_BOOKING_TIME = "booking time"


class _PortalNotConfiguredError(AppError):
    status_code = 503
    error_type = "not_configured"


GUEST_PROFILE_HEADERS = [
    _COL_GUEST_NAME,
    "phone number",
    "email id",
    "total visits",
    "source",
    "mode",
    "last visited date",
    "birthday",
    "anniversary",
]

BILL_HEADERS = [
    "sno",
    "outlet name",
    _COL_BOOKING_TIME,
    "seated time",
    "reserved time",
    "booking type",
    _COL_GUEST_NAME,
    "guest number",
    "guest email",
    "pax",
    "reserved by",
    "section(s)",
    "table(s)",
    "vist count",
    "booking status",
    "deletion type",
    "deleted reason",
    "source of booking",
    "preferences",
    "tags",
    "guest comments",
    "outlet comments",
    _COL_BILL_AMOUNT,
    _COL_BILL_NUMBER,
    "booking amount",
    "booking amount tranx id",
    "booking amount payment status",
    "booking amount payment date",
]

GUEST_PROFILE_SHEETS = {"no of visits", "no visit data", "not visited in 3 months"}
BILL_SHEET = _COL_BILL_AMOUNT


# ── Auth ──────────────────────────────────────────────────────────────────────


def _mint_token() -> str:
    return _create_token(
        {"sub": "reservego", "role": "reservego", "type": "access"},
        timedelta(hours=6),
    )


def _require_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise InvalidCredentialsError("Invalid or expired token") from exc
    if payload.get("role") != "reservego":
        raise InvalidCredentialsError("Not a reservego token")


# ── Schemas ───────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_idx(raw_headers: list, headers: list) -> dict:
    return {h: (raw_headers.index(h) if h in raw_headers else None) for h in headers}


def _cell(row: tuple, idx: dict, h: str):
    i = idx.get(h)
    return row[i] if i is not None and i < len(row) else None


def _parse_date(val) -> datetime | None:
    return val.replace(tzinfo=timezone.utc) if isinstance(val, datetime) else None


def _str_val(row, idx, h):
    v = _cell(row, idx, h)
    s = str(v).strip() if v is not None else None
    return None if not s or s.lower() == "none" else s


def _num_val(row, idx, h):
    v = _cell(row, idx, h)
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _sheet_headers(ws) -> list:
    return [
        str(c).strip().lower() if c is not None else ""
        for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])
    ]


# ── Sync parsers (run in thread) ──────────────────────────────────────────────


def _parse_sheet_rows(ws, parse_fn, idx) -> tuple[list, int]:
    """Generic row iterator — returns (docs, skipped)."""
    docs, skipped = [], 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        doc = parse_fn(row, idx)
        if doc is None:
            skipped += 1
        else:
            docs.append(doc)
    return docs, skipped


def _parse_workbook(contents: bytes, filename: str, now: datetime) -> dict:
    """Parse all sheets — runs synchronously, call via run_in_executor."""
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True, read_only=True)
    result = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        key = sheet_name.strip().lower()
        raw_headers = _sheet_headers(ws)

        if key in GUEST_PROFILE_SHEETS:
            idx = _make_idx(raw_headers, GUEST_PROFILE_HEADERS)
            docs, skipped = _parse_sheet_rows(
                ws,
                lambda row, i, sn=sheet_name: _parse_guest_row(
                    row, i, sn, filename, now
                ),
                idx,
            )
            result[sheet_name] = ("guest", docs, skipped)

        elif key == BILL_SHEET:
            idx = _make_idx(raw_headers, BILL_HEADERS)
            docs, skipped = _parse_sheet_rows(
                ws,
                lambda row, i: _parse_bill_row(row, i, filename, now),
                idx,
            )
            result[sheet_name] = ("bill", docs, skipped)

        else:
            result[sheet_name] = ("unknown", [], 0)

    wb.close()
    return result


def _parse_guest_row(row, idx, sheet_name, filename, now) -> dict | None:
    guest_name = str(_cell(row, idx, _COL_GUEST_NAME) or "").strip()
    if not guest_name or guest_name.lower() == "none":
        return None

    raw_phone = _cell(row, idx, "phone number")
    phone = ""
    if raw_phone is not None:
        phone = (
            str(int(raw_phone))
            if isinstance(raw_phone, float)
            else str(raw_phone).strip()
        )
        phone = phone.replace(" ", "").replace("+", "").replace("-", "")

    email_val = _cell(row, idx, "email id")
    email = str(email_val).strip() if email_val else None
    if email and email.lower() == "none":
        email = None

    total_visits_val = _cell(row, idx, "total visits")
    total_visits = int(total_visits_val) if total_visits_val is not None else 0

    return {
        "guest_name": guest_name,
        "phone": phone,
        "email": email,
        "total_visits": total_visits,
        "source": str(_cell(row, idx, "source") or "").strip() or None,
        "mode": str(_cell(row, idx, "mode") or "").strip() or None,
        "last_visited_date": _parse_date(_cell(row, idx, "last visited date")),
        "birthday": _parse_date(_cell(row, idx, "birthday")),
        "anniversary": _parse_date(_cell(row, idx, "anniversary")),
        "sheet": sheet_name,
        "uploaded_at": now,
        "filename": filename,
    }


def _parse_bill_row(row, idx, filename, now) -> dict | None:
    guest_name = str(_cell(row, idx, _COL_GUEST_NAME) or "").strip()
    if not guest_name or guest_name.lower() == "none":
        return None

    return {
        "sno": _num_val(row, idx, "sno"),
        "outlet_name": _str_val(row, idx, "outlet name"),
        "booking_time": _parse_date(_cell(row, idx, _COL_BOOKING_TIME)),
        "seated_time": _parse_date(_cell(row, idx, "seated time")),
        "reserved_time": _parse_date(_cell(row, idx, "reserved time")),
        "booking_type": _str_val(row, idx, "booking type"),
        "guest_name": guest_name,
        "guest_number": _str_val(row, idx, "guest number"),
        "guest_email": _str_val(row, idx, "guest email"),
        "pax": _num_val(row, idx, "pax"),
        "reserved_by": _str_val(row, idx, "reserved by"),
        "sections": _str_val(row, idx, "section(s)"),
        "tables": _str_val(row, idx, "table(s)"),
        "visit_count": _num_val(row, idx, "vist count"),
        "booking_status": _str_val(row, idx, "booking status"),
        "deletion_type": _str_val(row, idx, "deletion type"),
        "deleted_reason": _str_val(row, idx, "deleted reason"),
        "source_of_booking": _str_val(row, idx, "source of booking"),
        "preferences": _str_val(row, idx, "preferences"),
        "tags": _str_val(row, idx, "tags"),
        "guest_comments": _str_val(row, idx, "guest comments"),
        "outlet_comments": _str_val(row, idx, "outlet comments"),
        "bill_amount": _num_val(row, idx, _COL_BILL_AMOUNT),
        "bill_number": _str_val(row, idx, _COL_BILL_NUMBER),
        "booking_amount": _num_val(row, idx, "booking amount"),
        "booking_amount_tranx_id": _str_val(row, idx, "booking amount tranx id"),
        "booking_amount_payment_status": _str_val(
            row, idx, "booking amount payment status"
        ),
        "booking_amount_payment_date": _parse_date(
            _cell(row, idx, "booking amount payment date")
        ),
        "uploaded_at": now,
        "filename": filename,
    }


# ── Bulk DB writers ───────────────────────────────────────────────────────────


async def _bulk_upsert_guests(docs: list, db: AsyncIOMotorDatabase) -> None:
    if not docs:
        return
    ops = []
    for doc in docs:
        if doc["phone"]:
            ops.append(UpdateOne({"phone": doc["phone"]}, {"$set": doc}, upsert=True))
        else:
            ops.append(
                UpdateOne(
                    {
                        "guest_name": doc["guest_name"],
                        "email": doc["email"],
                        "sheet": doc["sheet"],
                    },
                    {"$set": doc},
                    upsert=True,
                )
            )
    await db.reservego_uploads.bulk_write(ops, ordered=False)


async def _bulk_upsert_bills(docs: list, db: AsyncIOMotorDatabase) -> None:
    if not docs:
        return
    ops = []
    for doc in docs:
        if doc.get("bill_number"):
            ops.append(
                UpdateOne(
                    {"bill_number": doc["bill_number"]},
                    {"$set": doc},
                    upsert=True,
                )
            )
        else:
            ops.append(
                UpdateOne(
                    {
                        "guest_name": doc["guest_name"],
                        "booking_time": doc["booking_time"],
                    },
                    {"$set": doc},
                    upsert=True,
                )
            )
    await db.reservego_bill_data.bulk_write(ops, ordered=False)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
async def reservego_login(body: Annotated[LoginRequest, Body()]):
    if not settings.reservego_user or not settings.reservego_password:
        raise _PortalNotConfiguredError("ReserveGo portal not configured")
    if (
        body.username != settings.reservego_user
        or body.password != settings.reservego_password
    ):
        raise InvalidCredentialsError("Invalid username or password")
    return LoginResponse(access_token=_mint_token())


@router.post("/upload")
async def reservego_upload(
    file: Annotated[UploadFile, File()],
    _auth: Annotated[None, Depends(_require_token)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise InvalidFileFormatError("Only .xlsx Excel files are supported")

    contents = await file.read()
    if not contents:
        raise InvalidFileFormatError("Uploaded file is empty")

    now = datetime.now(timezone.utc)

    loop = asyncio.get_event_loop()
    try:
        parsed = await loop.run_in_executor(
            _executor, _parse_workbook, contents, filename, now
        )
    except Exception as exc:
        raise InvalidFileFormatError("Unable to read Excel file") from exc

    sheets_summary = {}
    for sheet_name, (kind, docs, skipped) in parsed.items():
        if kind == "guest":
            await _bulk_upsert_guests(docs, db)
            sheets_summary[sheet_name] = {"inserted": len(docs), "skipped": skipped}
        elif kind == "bill":
            await _bulk_upsert_bills(docs, db)
            sheets_summary[sheet_name] = {"inserted": len(docs), "skipped": skipped}
        else:
            sheets_summary[sheet_name] = {
                "inserted": 0,
                "skipped": 0,
                "note": "unrecognised sheet, skipped",
            }

    total_inserted = sum(v["inserted"] for v in sheets_summary.values())
    total_skipped = sum(v["skipped"] for v in sheets_summary.values())

    return {
        "inserted": total_inserted,
        "skipped": total_skipped,
        "filename": filename,
        "uploaded_at": now.isoformat(),
        "sheets": sheets_summary,
    }
