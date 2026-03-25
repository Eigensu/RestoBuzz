from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from app.database import get_db
from app.dependencies import require_role
from app.services.meta_api import fetch_templates
from app.config import settings

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/")
async def list_templates(
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    cursor = db.templates.find({}, {"_id": 0}).sort("name", 1)
    return [doc async for doc in cursor]


@router.post("/sync", status_code=200)
async def sync_templates(
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    templates = await fetch_templates(
        settings.meta_waba_id,
        settings.meta_primary_access_token,
    )
    for t in templates:
        await db.templates.update_one(
            {"name": t["name"], "language": t.get("language")},
            {"$set": {**t, "synced_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    return {"synced": len(templates)}
