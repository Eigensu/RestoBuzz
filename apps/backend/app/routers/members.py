import io
import openpyxl

from typing import Annotated, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, UploadFile, File
from app.database import get_db
from app.core.logging import get_logger
from app.dependencies import (
    require_role,
    require_restaurant_access,
    validate_restaurant_access,
)
from app.core.utils import to_object_id
from app.core.errors import (
    NotFoundError,
    ConflictError,
    ValidationError,
    InvalidFileFormatError,
)
from app.models.member import (
    MemberCreate,
    MemberUpdate,
    MemberResponse,
    MemberListResponse,
)
from app.models.contact import PreflightResult, ContactRow, InvalidRow
from app.utils.phone import normalize_phone

router = APIRouter(prefix="/members", tags=["members"])
logger = get_logger(__name__)


def _serialize(doc: dict) -> MemberResponse:
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
        last_visit=doc.get("last_visit"),
        is_active=doc.get("is_active", True),
        joined_at=doc["joined_at"],
    )


@router.get("", response_model=MemberListResponse)
async def list_members(
    restaurant_id: Annotated[str, Query()],
    type: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    current_user: Annotated[dict, Depends(require_role("viewer"))] = None,
    validated_rid: Annotated[str, Depends(require_restaurant_access())] = None,
    db: Annotated[Any, Depends(get_db)] = None,
):
    query: dict = {"restaurant_id": validated_rid}
    if type and type != "all":
        query["type"] = type
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    skip = (page - 1) * page_size
    total = await db.members.count_documents(query)
    cursor = db.members.find(query).sort("joined_at", -1).skip(skip).limit(page_size)
    items = [_serialize(doc) async for doc in cursor]
    return MemberListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=MemberResponse, status_code=201)
async def create_member(
    body: MemberCreate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
):
    await validate_restaurant_access(current_user, body.restaurant_id, db)
    if body.type == "nfc" and not body.card_uid:
        raise ValidationError("card_uid is required for NFC members")
    if body.type == "ecard" and not body.ecard_code:
        raise ValidationError("ecard_code is required for e-card members")

    existing = await db.members.find_one(
        {"restaurant_id": body.restaurant_id, "phone": body.phone}
    )
    if existing:
        raise ConflictError(
            "A member with this phone number already exists in this restaurant"
        )

    now = datetime.now(timezone.utc)
    doc = {
        "restaurant_id": body.restaurant_id,
        "type": body.type,
        "name": body.name,
        "phone": body.phone,
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
    result = await db.members.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.get("/{member_id}", response_model=MemberResponse)
async def get_member(
    member_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[Any, Depends(get_db)],
):
    doc = await db.members.find_one({"_id": to_object_id(member_id)})
    if not doc:
        raise NotFoundError(f"Member '{member_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    return _serialize(doc)


@router.patch("/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: str,
    body: MemberUpdate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
):
    # Fetch first to check ownership/access
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
):
    doc = await db.members.find_one({"_id": to_object_id(member_id)})
    if not doc:
        raise NotFoundError(f"Member '{member_id}' not found")

    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    await db.members.delete_one({"_id": to_object_id(member_id)})


@router.post("/{member_id}/visit", response_model=MemberResponse)
async def record_visit(
    member_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
):
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


@router.post("/as-contacts", response_model=PreflightResult)
async def members_as_contacts(
    restaurant_id: Annotated[str, Query()],
    current_user: Annotated[dict, Depends(require_role("admin"))],
    validated_rid: Annotated[str, Depends(require_restaurant_access())] = None,
    db: Annotated[Any, Depends(get_db)] = None,
    type: Annotated[str | None, Query()] = None,
):
    """Convert members into a PreflightResult so they can be used as campaign contacts."""
    import uuid, json
    from redis.asyncio import from_url
    from app.config import settings

    query: dict = {"restaurant_id": validated_rid, "is_active": True}
    if type in ("nfc", "ecard"):
        query["type"] = type

    suppressed = set()
    async for doc in db.suppression_list.find({}, {"phone": 1}):
        suppressed.add(doc["phone"])

    valid_rows = []
    invalid_rows = []
    seen_phones = set()
    duplicate_count = 0
    suppressed_count = 0
    
    row_num = 1
    async for doc in db.members.find(query, {"name": 1, "phone": 1}):
        row_num += 1
        raw_phone = doc.get("phone", "").strip() if doc.get("phone") else ""
        if not raw_phone:
            invalid_rows.append(InvalidRow(row_number=row_num, raw_value="", reason="Empty phone"))
            continue
        
        normalized = normalize_phone(raw_phone)
        if not normalized:
            invalid_rows.append(InvalidRow(row_number=row_num, raw_value=raw_phone, reason="Invalid phone number"))
            continue

        if normalized in seen_phones:
            duplicate_count += 1
            continue
        seen_phones.add(normalized)

        if normalized in suppressed:
            suppressed_count += 1
            continue

        valid_rows.append(
            ContactRow(name=doc.get("name", ""), phone=normalized, variables={})
        )

    file_ref = str(uuid.uuid4())

    redis = from_url(settings.redis_url, decode_responses=True)
    await redis.set(
        f"file_ref:{file_ref}", 
        json.dumps([r.model_dump() for r in valid_rows]), 
        ex=3600
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


@router.post("/import")
async def import_members(
    restaurant_id: Annotated[str, Query()],
    file: Annotated[UploadFile, File()],
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
    type: Annotated[str, Query()] = "ecard",
):
    await validate_restaurant_access(current_user, restaurant_id, db)

    filename = file.filename or ""
    content_type = file.content_type or ""
    allowed_content_types = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if content_type not in allowed_content_types or not filename.lower().endswith(".xlsx"):
        raise InvalidFileFormatError("Only .xlsx Excel files are supported for import")

    contents = await file.read()
    if not contents:
        raise InvalidFileFormatError("Uploaded Excel file is empty")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents))
    except Exception as exc:
        raise InvalidFileFormatError("Unable to read Excel file") from exc
    ws = wb.active

    raw_headers = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]

    def find_col(names):
        for n in names:
            if n in raw_headers:
                return raw_headers.index(n)
        return None

    name_idx = find_col(["name", "full name", "fullname", "customer name"])
    phone_idx = find_col(
        ["phone", "contact number", "mobile", "phone number", "contact"]
    )
    email_idx = find_col(["email", "email address"])

    if name_idx is None:
        raise InvalidFileFormatError("Excel must have a 'Name' column")

    now = datetime.now(timezone.utc)
    inserted = skipped = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        name = str(row[name_idx]).strip() if row[name_idx] else ""
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

        if not name:
            skipped += 1
            continue

        # Validate and normalise phone via shared parser (E.164 output or None).
        # Members with no phone column are stored with an explicit empty string.
        if raw_phone and raw_phone != "None":
            phone = normalize_phone(raw_phone)
            if phone is None:
                # Parser rejected the value — skip rather than persist garbage.
                skipped += 1
                continue
        else:
            phone = ""

        if phone:
            existing = await db.members.find_one(
                {"restaurant_id": restaurant_id, "phone": phone}
            )
            if existing:
                skipped += 1
                continue

        await db.members.insert_one(
            {
                "restaurant_id": restaurant_id,
                "type": type,
                "name": name,
                "phone": phone,
                "email": email,
                "card_uid": None,
                "ecard_code": None,
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
    restaurant_id: Annotated[str, Query()],
    source: Annotated[str | None, Query()] = None,
    deleteAll: Annotated[bool, Query()] = False,
    current_user: Annotated[dict, Depends(require_role("admin"))] = None,
    db: Annotated[Any, Depends(get_db)] = None,
):
    """Bulk delete members for a restaurant. 
    Can delete all members or filter by source (e.g. 'excel')."""
    await validate_restaurant_access(current_user, restaurant_id, db)

    logger.info(f"Bulk Delete Request - RID: {restaurant_id}, Source: {source}, DeleteAll: {deleteAll}")

    query = {"restaurant_id": restaurant_id}
    
    if deleteAll:
        # No additional filters
        pass
    elif source:
        query["source"] = source
    else:
        raise ValidationError("Must specify either 'deleteAll=true' or a 'source' to delete in bulk")

    result = await db.members.delete_many(query)
    logger.info(f"Bulk Deletion Result: {result.deleted_count} documents removed")
    return None
