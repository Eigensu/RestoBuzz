import json
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.database import get_db
from app.dependencies import require_role
from app.models.contact import PreflightResult, ColumnMapping
from app.services.contact_parser import parse_contacts
from app.services.suppression import is_suppressed

router = APIRouter(prefix="/contacts", tags=["contacts"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", response_model=PreflightResult)
async def upload_contacts(
    file: UploadFile = File(...),
    phone_column: str = "phone",
    name_column: str = "name",
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    if not file.filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(400, "Only .xlsx, .xls, .csv files are supported")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File exceeds 50MB limit")

    mapping = ColumnMapping(phone_column=phone_column, name_column=name_column)

    # Load suppressed phones for dedup check
    suppressed = set()
    async for doc in db.suppression_list.find({}, {"phone": 1}):
        suppressed.add(doc["phone"])

    result = await parse_contacts(content, file.filename, mapping, suppressed)

    # Cache valid rows in Redis for campaign creation
    from redis.asyncio import from_url
    from app.config import settings
    redis = from_url(settings.redis_url, decode_responses=True)
    await redis.set(
        f"file_ref:{result.file_ref}",
        json.dumps([r.model_dump() for r in result.valid_rows]),
        ex=3600,  # 1 hour TTL
    )
    await redis.aclose()

    return result
