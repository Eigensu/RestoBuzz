"""Router for member management endpoints."""

import io
import re
import uuid
import heapq

import openpyxl
from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from redis.asyncio import from_url
from typing import Annotated, Any
from datetime import datetime, timezone

from app.config import settings
from app.database import get_db
from app.core.logging import get_logger
from app.core.utils import to_object_id
from pymongo.errors import DuplicateKeyError
from app.core.errors import (
    NotFoundError,
    ConflictError,
    ValidationError,
    InvalidFileFormatError,
)
from app.dependencies import (
    require_role,
    validate_restaurant_access,
    get_active_restaurant,
)
from app.models.member import (
    MemberCreate,
    MemberUpdate,
    MemberResponse,
    MemberListResponse,
)
from app.models.contact import PreflightResult, ContactRow, InvalidRow
from app.services.dormancy_service import dormancy_service, normalize_phone_for_match
from app.services.fielia_members_service import fielia_service, FieliaDatabaseError
from app.utils.phone import normalize_phone

router = APIRouter(prefix="/members", tags=["members"])
logger = get_logger(__name__)

# Constants for MongoDB operators to avoid duplication
REGEX = "$regex"
OPTIONS = "$options"


def _serialize(doc: dict, activity: tuple | None = None) -> MemberResponse:
    """Serialize a raw MongoDB member document to a MemberResponse."""
    last_visit = doc.get("last_visit")
    if last_visit and isinstance(last_visit, str):
        last_visit = datetime.fromisoformat(last_visit)

    last_visit_date, source = None, None
    if activity:
        last_visit_date, source = activity

    status, fallback_source = dormancy_service.compute_status(
        last_visit_date, last_visit
    )

    return MemberResponse(
        id=str(doc["_id"]),
        restaurant_id=doc["restaurant_id"],
        type=doc["type"],
        name=doc["name"],
        phone=doc["phone"],
        email=doc.get("email"),
        card_uid=doc.get("card_uid"),
        ecard_code=doc.get("ecard_code"),
        tags=doc.get("tags", []),
        notes=doc.get("notes"),
        visit_count=doc.get("visit_count", 0),
        last_visit=last_visit_date or last_visit,
        is_active=doc.get("is_active", True),
        activity_status=status,
        activity_source=source or fallback_source,
        joined_at=doc["joined_at"],
    )


async def _bulk_serialize(
    docs: list[dict], restaurant_id: str, db: Any
) -> list[MemberResponse]:
    """Serialize a batch of member docs with bulk activity lookup."""
    phones = [d.get("phone") for d in docs]
    uuids = [d.get("card_uid") for d in docs]
    activity_map = await dormancy_service.get_bulk_activity(
        db, restaurant_id, phones, uuids
    )
    items = []
    for doc in docs:
        norm_phone = normalize_phone_for_match(doc.get("phone"))
        uuid_val = doc.get("card_uid")
        activity = activity_map.get(uuid_val) or activity_map.get(norm_phone)
        items.append(_serialize(doc, activity))
    return items


@router.get("")
async def list_members(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    member_type: Annotated[str | None, Query(alias="type")] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Annotated[Any, Depends(get_db)] = None,
) -> MemberListResponse:
    """List members for the active restaurant, with optional type filter and search."""
    skip = (page - 1) * page_size

    if restaurant["id"] == "r2":
        return await _list_members_r2(db, member_type, search, page, page_size)

    # Standard model for all other restaurants
    query: dict = {"restaurant_id": restaurant["id"]}
    if member_type and member_type != "all":
        query["type"] = {REGEX: f"^{member_type}$", OPTIONS: "i"}
    if search:
        safe_search = re.escape(search)
        query["$or"] = [
            {"name": {REGEX: safe_search, OPTIONS: "i"}},
            {"phone": {REGEX: safe_search, OPTIONS: "i"}},
            {"email": {REGEX: safe_search, OPTIONS: "i"}},
        ]

    total = await db.members.count_documents(query)
    docs = await (
        db.members.find(query)
        .sort("joined_at", -1)
        .skip(skip)
        .limit(page_size)
        .to_list(length=page_size)
    )
    items = await _bulk_serialize(docs, restaurant["id"], db)
    return MemberListResponse(items=items, total=total, page=page, page_size=page_size)


async def _list_members_r2(
    db: Any,
    member_type: str | None,
    search: str | None,
    page: int,
    page_size: int,
) -> MemberListResponse:
    """Hybrid member listing for restaurant r2 (Fielia + internal DB).
    Correctly paginates by merging and sorting the two sources.
    Uses heapq.merge for O(N) streaming merge and adaptive buffering for dups.
    """
    # 1. Fetch relevant docs from both sources
    # Use a larger buffer (page_size * 3) to handle high duplication rates
    fetch_limit = page * page_size + (page_size * 3)
    
    fielia_items = []
    if not member_type or member_type in ("all", "nfc"):
        fielia_res = await fielia_service.list_members(
            limit=fetch_limit,
            offset=0,
            search=search,
            member_type="nfc" if member_type == "all" else member_type,
        )
        fielia_items = [MemberResponse(**item) for item in fielia_res["items"]]
        fielia_total = fielia_res["total"]
    else:
        fielia_total = 0

    internal_query: dict = {"restaurant_id": "r2"}
    if member_type and member_type != "all":
        internal_query["type"] = {REGEX: f"^{re.escape(member_type)}$", OPTIONS: "i"}
    
    if search:
        safe_search = re.escape(search)
        internal_query["$or"] = [
            {"name": {REGEX: safe_search, OPTIONS: "i"}},
            {"phone": {REGEX: f"^{safe_search}", OPTIONS: "i"}}, 
            {"email": {REGEX: safe_search, OPTIONS: "i"}},
        ]

    internal_total = await db.members.count_documents(internal_query)
    internal_docs = await (
        db.members.find(internal_query)
        .sort("joined_at", -1)
        .limit(fetch_limit)
        .to_list(length=fetch_limit)
    )
    internal_items = await _bulk_serialize(internal_docs, "r2", db)

    # 2. Merge Streams using heapq for efficiency
    # Since both streams are sorted by joined_at descending, we can merge them in O(N).
    # We use a key-extractor to handle the sort order.
    def sort_key(x):
        return x.joined_at or datetime.min.replace(tzinfo=timezone.utc)

    # heapq.merge produces an iterator over the merged stream
    # Note: reverse=True because joined_at is descending
    merged_stream = heapq.merge(internal_items, fielia_items, key=sort_key, reverse=True)

    # 3. Deduplicate and Paginate
    # Pattern: internal items overwrite fielia items in the seen map
    seen_phones = set()
    results = []
    skip_count = (page - 1) * page_size
    
    for item in merged_stream:
        phone = normalize_phone_for_match(item.phone) or f"no_phone_{item.id}"
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        
        if skip_count > 0:
            skip_count -= 1
            continue
            
        results.append(item)
        if len(results) >= page_size:
            break

    # Estimate total (this is tricky with deduplication across pages)
    total = fielia_total + internal_total 
    
    return MemberListResponse(
        items=results,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=201)
async def create_member(
    body: MemberCreate,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
) -> MemberResponse:
    """Create a new member for the active restaurant."""
    valid_categories = restaurant.get("member_categories") or ["nfc", "ecard"]
    if body.type not in valid_categories:
        raise ValidationError(
            f"Invalid member type '{body.type}'. "
            f"Valid types: {', '.join(valid_categories)}"
        )

    if body.type == "nfc" and not body.card_uid:
        raise ValidationError("card_uid is required for NFC members")
    if body.type == "ecard" and not body.ecard_code:
        raise ValidationError("ecard_code is required for e-card members")

    # Only check uniqueness when a real phone is provided
    if body.phone:
        existing = await db.members.find_one(
            {"restaurant_id": restaurant["id"], "phone": body.phone}
        )
        if existing:
            raise ConflictError(
                "A member with this phone number already exists in our internal database"
            )

        if restaurant["id"] == "r2":
            try:
                if await fielia_service.check_phone_exists(body.phone):
                    raise ConflictError(
                        "A member with this phone number already exists in the Fielia database"
                    )
            except FieliaDatabaseError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="External member service unavailable. Please try again later.",
                    headers={"Retry-After": "10"}
                ) from exc

    now = datetime.now(timezone.utc)
    doc = {
        "restaurant_id": restaurant["id"],
        "type": body.type,
        "name": body.name,
        "phone": body.phone or None,
        "email": body.email,
        "card_uid": body.card_uid,
        "ecard_code": body.ecard_code,
        "tags": body.tags,
        "notes": body.notes,
        "visit_count": 0,
        "last_visit": None,
        "is_active": True,
        "joined_at": now,
    }
    try:
        result = await db.members.insert_one(doc)
    except DuplicateKeyError:
        raise ConflictError("A member with this phone number already exists (concurrent write detected)")

    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.get("/{member_id}")
async def get_member(
    member_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[Any, Depends(get_db)],
) -> MemberResponse:
    """Fetch a single member by ID."""
    doc = await db.members.find_one({"_id": to_object_id(member_id)})
    if not doc:
        raise NotFoundError(f"Member '{member_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    return _serialize(doc)


@router.patch("/{member_id}")
async def update_member(
    member_id: str,
    body: MemberUpdate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
) -> MemberResponse:
    """Update fields on an existing member."""
    doc = await db.members.find_one({"_id": to_object_id(member_id)})
    if not doc:
        raise NotFoundError(f"Member '{member_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise ValidationError("No fields provided to update")

    doc = await db.members.find_one_and_update(
        {"_id": to_object_id(member_id)},
        {"$set": updates},
        return_document=True,
    )
    return _serialize(doc)


@router.delete("/{member_id}", status_code=204)
async def delete_member(
    member_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
) -> None:
    """Delete a member by ID."""
    doc = await db.members.find_one({"_id": to_object_id(member_id)})
    if not doc:
        raise NotFoundError(f"Member '{member_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    await db.members.delete_one({"_id": to_object_id(member_id)})


@router.post("/{member_id}/visit")
async def record_visit(
    member_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
) -> MemberResponse:
    """Increment visit count and update last_visit timestamp for a member."""
    doc = await db.members.find_one({"_id": to_object_id(member_id)})
    if not doc:
        raise NotFoundError(f"Member '{member_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    now = datetime.now(timezone.utc)
    doc = await db.members.find_one_and_update(
        {"_id": to_object_id(member_id)},
        {"$inc": {"visit_count": 1}, "$set": {"last_visit": now}},
        return_document=True,
    )
    return _serialize(doc)


@router.post("/as-contacts")
async def members_as_contacts(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)] = None,
    member_type: Annotated[str | None, Query(alias="type")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> PreflightResult:
    """
    Convert members into a PreflightResult for use as campaign contacts.

    Sources:
    - reservego: combines reservego_uploads + reservego_bill_data collections
    - r2 (Fielia): streams Fielia NFC members then appends internal DB members
    - all others: queries internal members DB only
    """
    suppressed: set[str] = set()
    async for sup in db.suppression_list.find({}, {"phone": 1}):
        suppressed.add(sup["phone"])

    valid_rows: list[ContactRow] = []
    invalid_rows: list[InvalidRow] = []
    seen_phones: set[str] = set()
    duplicate_count = 0
    suppressed_count = 0
    row_num = 1

    def process_row(name: str, raw_phone_val: Any) -> None:
        nonlocal row_num, duplicate_count, suppressed_count
        raw_phone = str(raw_phone_val).strip() if raw_phone_val else ""
        if not raw_phone:
            invalid_rows.append(
                InvalidRow(row_number=row_num, raw_value="", reason="Empty phone")
            )
            row_num += 1
            return
        normalized = normalize_phone(raw_phone)
        if not normalized:
            invalid_rows.append(
                InvalidRow(
                    row_number=row_num,
                    raw_value=raw_phone,
                    reason="Invalid phone number",
                )
            )
            row_num += 1
            return
        if normalized in seen_phones:
            duplicate_count += 1
            row_num += 1
            return
        seen_phones.add(normalized)
        if normalized in suppressed:
            suppressed_count += 1
            row_num += 1
            return
        valid_rows.append(ContactRow(name=name or "", phone=normalized, variables={}))
        row_num += 1

    if member_type == "reservego":
        await _process_reservego(db, restaurant["id"], limit, process_row, valid_rows)
    else:
        await _process_members(
            db, restaurant, member_type, limit, process_row, valid_rows
        )

    file_ref = str(uuid.uuid4())
    redis = from_url(settings.redis_url, decode_responses=True)
    await redis.set(
        f"file_ref:{file_ref}",
        json.dumps([r.model_dump() for r in valid_rows]),
        ex=3600,
    )
    await redis.aclose()

    return PreflightResult(
        valid_count=len(valid_rows),
        invalid_count=len(invalid_rows),
        duplicate_count=duplicate_count,
        suppressed_count=suppressed_count,
        valid_rows=valid_rows,
        invalid_rows=invalid_rows,
        file_ref=file_ref,
    )


async def _process_reservego(
    db: Any,
    restaurant_id: str,
    limit: int | None,
    process_row: Any,
    valid_rows: list,
) -> None:
    """Stream ReserveGo uploads and bill data into the contact processor."""
    async for doc in db.reservego_uploads.find(
        {"restaurant_id": restaurant_id}, {"guest_name": 1, "phone": 1}
    ).sort("_id", -1):
        if limit and len(valid_rows) >= limit:
            return
        process_row(doc.get("guest_name", ""), doc.get("phone"))

    async for doc in db.reservego_bill_data.find(
        {"restaurant_id": restaurant_id}, {"guest_name": 1, "guest_number": 1}
    ).sort("_id", -1):
        if limit and len(valid_rows) >= limit:
            return
        process_row(doc.get("guest_name", ""), doc.get("guest_number"))


async def _process_members(
    db: Any,
    restaurant: dict,
    member_type: str | None,
    limit: int | None,
    process_row: Any,
    valid_rows: list,
) -> None:
    """Stream Fielia (r2 only) then internal DB members into the contact processor."""
    if restaurant["id"] == "r2" and (not member_type or member_type in ("all", "nfc")):
        async for doc in fielia_service.stream_all_members(member_type=member_type):
            if limit and len(valid_rows) >= limit:
                return
            process_row(doc.get("name", ""), doc.get("phone"))

    internal_query: dict = {"restaurant_id": restaurant["id"], "is_active": True}
    if member_type and member_type != "all":
        internal_query["type"] = {REGEX: f"^{re.escape(member_type)}$", OPTIONS: "i"}

    async for doc in db.members.find(internal_query, {"name": 1, "phone": 1}).sort(
        "_id", -1
    ):
        if limit and len(valid_rows) >= limit:
            return
        process_row(doc.get("name", ""), doc.get("phone"))


@router.post("/import")
async def import_members(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    file: Annotated[UploadFile, File()],
    _user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
    member_type: Annotated[str, Query(alias="type")] = "ecard",
) -> dict:
    """Bulk-import members from an uploaded XLSX file."""
    filename = file.filename or ""
    content_type = file.content_type or ""
    allowed_content_types = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/vnd.ms-excel",
    }
    if not (
        content_type in allowed_content_types or filename.lower().endswith(".xlsx")
    ):
        logger.error(
            "import_invalid_format", content_type=content_type, filename=filename
        )
        raise InvalidFileFormatError("Only .xlsx Excel files are supported for import")

    contents = await file.read()
    if not contents:
        raise InvalidFileFormatError("Uploaded Excel file is empty")
    if len(contents) > 10 * 1024 * 1024:
        raise ValidationError("Excel file is too large (max 10MB)")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True)
    except (ValueError, KeyError) as exc:
        raise InvalidFileFormatError("Unable to read Excel file") from exc

    ws = wb.active
    if ws.max_row and ws.max_row > 5001:
        raise ValidationError("Excel file has too many rows (max 5000)")

    raw_headers = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]

    def find_col(names: list[str]) -> int | None:
        for n in names:
            if n in raw_headers:
                return raw_headers.index(n)
        return None

    name_idx = find_col(["name", "full name", "fullname", "customer name"])
    phone_idx = find_col(
        ["phone", "contact number", "mobile", "phone number", "contact"]
    )
    email_idx = find_col(["email", "email address"])
    card_uid_idx = find_col(
        ["card_uid", "card id", "uid", "card number", "card nfc id"]
    )
    ecard_code_idx = find_col(["ecard_code", "ecard code", "e-card code", "code"])

    if name_idx is None:
        raise InvalidFileFormatError("Excel must have a 'Name' column")

    now = datetime.now(timezone.utc)
    inserted = skipped = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        name = str(row[name_idx]).strip() if row[name_idx] else ""
        if not name:
            skipped += 1
            continue

        raw_phone = (
            str(row[phone_idx]).strip()
            if phone_idx is not None and row[phone_idx]
            else ""
        )
        email = (
            str(row[email_idx]).strip()
            if email_idx is not None and row[email_idx]
            else None
        )
        card_uid = (
            str(row[card_uid_idx]).strip()
            if card_uid_idx is not None and row[card_uid_idx]
            else None
        )
        ecard_code = (
            str(row[ecard_code_idx]).strip()
            if ecard_code_idx is not None and row[ecard_code_idx]
            else None
        )

        if raw_phone and raw_phone != "None":
            phone = normalize_phone(raw_phone)
            if phone is None:
                skipped += 1
                continue
        else:
            phone = None  # store None, not "", to avoid duplicate-empty-phone index collisions

        if phone:
            existing = await db.members.find_one(
                {"restaurant_id": restaurant["id"], "phone": phone}
            )
            if existing:
                skipped += 1
                continue

        await db.members.insert_one(
            {
                "restaurant_id": restaurant["id"],
                "type": member_type,
                "name": name,
                "phone": phone,
                "email": email,
                "card_uid": card_uid,
                "ecard_code": ecard_code,
                "tags": [],
                "notes": None,
                "visit_count": 0,
                "last_visit": None,
                "is_active": True,
                "joined_at": now,
                "source": "excel",
            }
        )
        inserted += 1

    return {"inserted": inserted, "skipped": skipped}


@router.delete("/bulk", status_code=204)
async def bulk_delete_members(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _user: Annotated[dict, Depends(require_role("admin"))],
    source: Annotated[str | None, Query()] = None,
    delete_all: Annotated[bool, Query(alias="deleteAll")] = False,
    db: Annotated[Any, Depends(get_db)] = None,
) -> None:
    """Bulk delete members. Requires either deleteAll=true or a source filter."""
    logger.info(
        "bulk_delete_request",
        restaurant_id=restaurant["id"],
        source=source,
        delete_all=delete_all,
    )

    query: dict = {"restaurant_id": restaurant["id"]}
    if delete_all:
        pass  # no additional filter
    elif source:
        query["source"] = source
    else:
        raise ValidationError(
            "Must specify either 'deleteAll=true' or a 'source' to delete in bulk"
        )

    result = await db.members.delete_many(query)
    logger.info("bulk_delete_result", deleted_count=result.deleted_count)
