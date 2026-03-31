import io
import openpyxl

from typing import Annotated, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, UploadFile, File
from app.database import get_db
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

router = APIRouter(prefix="/members", tags=["members"])


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
    if type in ("nfc", "ecard"):
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
    if content_type not in allowed_content_types or not filename.lower().endswith(
        ".xlsx"
    ):
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
        phone = (
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

        if phone and phone != "None":
            phone = phone.replace(" ", "").replace("+", "").replace("-", "")
            if not phone.startswith("91"):
                phone = "91" + phone.lstrip("0")
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
            }
        )
        inserted += 1

    return {"inserted": inserted, "skipped": skipped}
