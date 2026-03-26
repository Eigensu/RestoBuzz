from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from bson import ObjectId
from app.database import get_db
from app.dependencies import require_role
from app.core.errors import ValidationError, ConflictError, NotFoundError
from app.models.suppression import SuppressionCreate, SuppressionResponse
import phonenumbers

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/suppression")
async def list_suppression(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    skip = (page - 1) * page_size
    total = await db.suppression_list.count_documents({})
    cursor = (
        db.suppression_list.find({}).sort("added_at", -1).skip(skip).limit(page_size)
    )
    items = []
    async for doc in cursor:
        items.append(
            SuppressionResponse(
                id=str(doc["_id"]),
                phone=doc["phone"],
                reason=doc["reason"],
                added_by=str(doc["added_by"]) if doc.get("added_by") else None,
                added_at=doc["added_at"],
            )
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/suppression", response_model=SuppressionResponse, status_code=201)
async def add_suppression(
    body: SuppressionCreate,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    try:
        parsed = phonenumbers.parse(body.phone, None)
        phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        raise ValidationError(f"'{body.phone}' is not a valid phone number")

    now = datetime.now(timezone.utc)
    doc = {
        "phone": phone,
        "reason": body.reason,
        "added_by": ObjectId(current_user["id"]),
        "added_at": now,
    }
    try:
        result = await db.suppression_list.insert_one(doc)
    except Exception:
        raise ConflictError(
            f"Phone number '{phone}' is already in the suppression list"
        )

    return SuppressionResponse(
        id=str(result.inserted_id),
        **{k: v for k, v in doc.items() if k != "_id"},
        added_by=current_user["id"],
    )


@router.delete("/suppression/{phone}")
async def remove_suppression(
    phone: str,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    result = await db.suppression_list.delete_one({"phone": phone})
    if result.deleted_count == 0:
        raise NotFoundError(f"Phone number '{phone}' not found in suppression list")
    return {"status": "removed"}
