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
    get_active_restaurant,
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


from datetime import timedelta

def _serialize(doc: dict, activity: tuple | None = None) -> MemberResponse:
    from app.services.dormancy_service import dormancy_service
    
    last_visit = doc.get("last_visit")
    if last_visit and isinstance(last_visit, str):
        last_visit = datetime.fromisoformat(last_visit)

    # Behavioral activity from ReserveGo
    last_visit_date, source = None, None
    if activity:
        last_visit_date, source = activity

    # Compute status using hierarchy
    status, fallback_source = dormancy_service.compute_status(last_visit_date, last_visit)

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


from app.services.fielia_members_service import fielia_service

@router.get("", response_model=MemberListResponse)
async def list_members(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    member_type: Annotated[str | None, Query(alias="type")] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Annotated[Any, Depends(get_db)] = None,
):
    skip = (page - 1) * page_size
    
    # --- HYBRID MODEL FOR R2 (FIELIA) ---
    if restaurant["id"] == "r2":
        fielia_res = {"items": [], "total": 0}
        
        # 1. Fetch from Fielia if applicable
        if not member_type or member_type == "all" or member_type.lower() == "nfc":
            fielia_res = await fielia_service.list_members(
                limit=page_size, 
                offset=skip, 
                search=search, 
                member_type="nfc" if member_type == "all" else member_type
            )
            
        # 2. Fetch from Internal DB (for custom categories or all)
        internal_query: dict = {"restaurant_id": "r2"}
        if member_type and member_type != "all":
            # Strict Case-insensitive match for type (full string match only)
            internal_query["type"] = {"$regex": f"^{member_type}$", "$options": "i"}
        
        if search:
            internal_query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
            ]
            
        internal_total = await db.members.count_documents(internal_query)
        internal_cursor = db.members.find(internal_query).sort("joined_at", -1).skip(skip).limit(page_size)
        internal_docs = await internal_cursor.to_list(length=page_size)
        
        # Bulk dormancy for internal docs
        from app.services.dormancy_service import dormancy_service, normalize_phone_for_match
        internal_phones = [d.get("phone") for d in internal_docs]
        internal_uuids = [d.get("card_uid") for d in internal_docs]
        activity_map = await dormancy_service.get_bulk_activity(db, "r2", internal_phones, internal_uuids)
        
        internal_items = []
        for d in internal_docs:
            norm_phone = normalize_phone_for_match(d.get("phone"))
            uuid = d.get("card_uid")
            activity = activity_map.get(uuid) or activity_map.get(norm_phone)
            internal_items.append(_serialize(d, activity))
            
        # 3. Combine results
        # If a specific non-nfc type is requested, only return internal
        if member_type and member_type != "all" and member_type.lower() != "nfc":
            return MemberListResponse(items=internal_items, total=internal_total, page=page, page_size=page_size)
            
        # If nfc is requested, we mainly show Fielia but append any internal ones
        if member_type and member_type.lower() == "nfc":
            return MemberListResponse(
                items=fielia_res["items"] + internal_items, 
                total=fielia_res["total"] + internal_total,
                page=page,
                page_size=page_size
            )
            
        # If "all" is requested, merge both
        return MemberListResponse(
            items=fielia_res["items"] + internal_items, 
            total=fielia_res["total"] + internal_total,
            page=page,
            page_size=page_size
        )

    # --- STANDARD MODEL FOR OTHER RESTAURANTS ---
    query: dict = {"restaurant_id": restaurant["id"]}
    if member_type and member_type != "all":
        query["type"] = {"$regex": f"^{member_type}$", "$options": "i"}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    total = await db.members.count_documents(query)
    cursor = db.members.find(query).sort("joined_at", -1).skip(skip).limit(page_size)
    docs = await cursor.to_list(length=page_size)

    from app.services.dormancy_service import dormancy_service, normalize_phone_for_match
    
    phones = [d.get("phone") for d in docs]
    uuids = [d.get("card_uid") for d in docs]
    activity_map = await dormancy_service.get_bulk_activity(db, restaurant["id"], phones, uuids)

    items = []
    for d in docs:
        norm_phone = normalize_phone_for_match(d.get("phone"))
        uuid = d.get("card_uid")
        activity = activity_map.get(uuid) or activity_map.get(norm_phone)
        items.append(_serialize(d, activity))

    return MemberListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=MemberResponse, status_code=201)
async def create_member(
    body: MemberCreate,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
):
    valid_categories = restaurant.get("member_categories") or ["nfc", "ecard"]
    if body.type not in valid_categories:
        raise ValidationError(f"Invalid member type '{body.type}'. Valid types: {', '.join(valid_categories)}")

    if body.type == "nfc" and not body.card_uid:
        raise ValidationError("card_uid is required for NFC members")
    if body.type == "ecard" and not body.ecard_code:
        raise ValidationError("ecard_code is required for e-card members")

    # Conflict Check: Check internal DB
    existing = await db.members.find_one(
        {"restaurant_id": restaurant["id"], "phone": body.phone}
    )
    if existing:
        raise ConflictError(
            "A member with this phone number already exists in our internal database"
        )
        
    # Conflict Check: Check Fielia if r2
    if restaurant["id"] == "r2":
        from app.services.fielia_members_service import fielia_service
        client = fielia_service.get_client()
        if client:
            f_db = client[fielia_service._db_name]
            f_coll = f_db[fielia_service._collection_name]
            f_existing = await f_coll.find_one({"phone": body.phone})
            if f_existing:
                raise ConflictError(
                    "A member with this phone number already exists in the Fielia database"
                )

    now = datetime.now(timezone.utc)
    doc = {
        "restaurant_id": restaurant["id"],
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
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)] = None,
    member_type: Annotated[str | None, Query(alias="type")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
):
    """Convert members into a PreflightResult so they can be used as campaign contacts."""
    import uuid, json
    from redis.asyncio import from_url
    from app.config import settings

    if member_type == "reservego":
        q1 = db.reservego_uploads.find(
            {"restaurant_id": restaurant["id"]},
            {"guest_name": 1, "phone": 1}
        ).sort("_id", -1)
        q2 = db.reservego_bill_data.find(
            {"restaurant_id": restaurant["id"]},
            {"guest_name": 1, "guest_number": 1}
        ).sort("_id", -1)
        
        async def combined_cursor():
            async for doc in q1:
                yield doc
            async for doc in q2:
                yield {"guest_name": doc.get("guest_name"), "phone": doc.get("guest_number")}
                
        cursor = combined_cursor()
    else:
        query: dict = {"restaurant_id": restaurant["id"], "is_active": True}
        if type in ("nfc", "ecard"):
            query["type"] = type
        cursor = db.members.find(query, {"name": 1, "phone": 1}).sort("_id", -1)

    suppressed = set()
    async for doc in db.suppression_list.find({}, {"phone": 1}):
        suppressed.add(doc["phone"])

    valid_rows = []
    invalid_rows = []
    seen_phones = set()
    duplicate_count = 0
    suppressed_count = 0
    
    row_num = 1
    async for doc in cursor:
        row_num += 1
        phone_value = doc.get("phone")
        raw_phone = str(phone_value).strip() if phone_value else ""
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
            ContactRow(name=doc.get("name", doc.get("guest_name", "")), phone=normalized, variables={})
        )
        if limit and len(valid_rows) >= limit:
            break

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
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    file: Annotated[UploadFile, File()],
    _user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[Any, Depends(get_db)],
    member_type: Annotated[str, Query(alias="type")] = "ecard",
):
    filename = file.filename or ""
    content_type = file.content_type or ""
    # More permissive Excel content type check
    allowed_content_types = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/vnd.ms-excel",
    }
    if not (content_type in allowed_content_types or filename.lower().endswith(".xlsx")):
        logger.error(f"Invalid file format: {content_type}, {filename}")
        raise InvalidFileFormatError("Only .xlsx Excel files are supported for import")

    contents = await file.read()
    if not contents:
        raise InvalidFileFormatError("Uploaded Excel file is empty")

    # Hardening: Prevent massive files from blowing up memory (e.g. > 10MB)
    if len(contents) > 10 * 1024 * 1024:
        raise ValidationError("Excel file is too large (max 10MB)")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True)
    except Exception as exc:
        raise InvalidFileFormatError("Unable to read Excel file") from exc
    ws = wb.active

    # Hardening: Check row count before processing
    if ws.max_row and ws.max_row > 5001:
         raise ValidationError("Excel file has too many rows (max 5000)")

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
    card_uid_idx = find_col(["card_uid", "card id", "uid", "card number", "card nfc id"])
    ecard_code_idx = find_col(["ecard_code", "ecard code", "e-card code", "code"])

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
    deleteAll: Annotated[bool, Query()] = False,
    db: Annotated[Any, Depends(get_db)] = None,
):
    """Bulk delete members for a restaurant. 
    Can delete all members or filter by source (e.g. 'excel')."""
    logger.info(f"Bulk Delete Request - RID: {restaurant['id']}, Source: {source}, DeleteAll: {deleteAll}")

    query = {"restaurant_id": restaurant["id"]}
    
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
