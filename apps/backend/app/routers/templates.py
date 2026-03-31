from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field
from app.database import get_db
from app.dependencies import require_role
from app.services.meta_api import fetch_templates, create_template, edit_template
from app.core.errors import NotFoundError, ValidationError
from app.config import settings

router = APIRouter(prefix="/templates", tags=["templates"])


# ── Request models ────────────────────────────────────────────────────────────


class TemplateComponent(BaseModel):
    type: str
    text: str | None = None
    format: str | None = None
    example: dict | None = None
    buttons: list[dict] | None = None


class CreateTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=512, pattern=r"^[a-z0-9_]+$")
    category: Literal["MARKETING", "UTILITY", "AUTHENTICATION"]
    language: str = Field(min_length=2, max_length=10)
    components: list[TemplateComponent]


class EditTemplateRequest(BaseModel):
    components: list[TemplateComponent]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_templates(
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    cursor = db.templates.find({}, {"_id": 0}).sort("name", 1)
    return [doc async for doc in cursor]


@router.post("", status_code=201)
async def create_new_template(
    body: CreateTemplateRequest,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    payload = {
        "name": body.name,
        "category": body.category,
        "language": body.language,
        "components": [c.model_dump(exclude_none=True) for c in body.components],
    }
    result = await create_template(
        settings.meta_waba_id,
        settings.meta_primary_access_token,
        payload,
    )
    # Persist locally so it shows up immediately without a sync
    now = datetime.now(timezone.utc)
    doc = {
        "name": body.name,
        "category": body.category,
        "language": body.language,
        "status": result.get("status", "PENDING"),
        "components": payload["components"],
        "meta_id": str(result.get("id", "")),
        "synced_at": now,
    }
    await db.templates.update_one(
        {"name": body.name, "language": body.language},
        {"$set": doc},
        upsert=True,
    )
    return doc


@router.patch("/{template_name}")
async def edit_existing_template(
    template_name: str,
    body: EditTemplateRequest,
    current_user: dict = Depends(require_role("admin")),
    db=Depends(get_db),
):
    doc = await db.templates.find_one({"name": template_name})
    if not doc:
        raise NotFoundError(f"Template '{template_name}' not found")

    meta_id = doc.get("meta_id")
    if not meta_id:
        raise ValidationError(
            "This template has no Meta ID — sync templates first so the ID is stored."
        )

    components = [c.model_dump(exclude_none=True) for c in body.components]
    await edit_template(meta_id, settings.meta_primary_access_token, components)

    # Update local copy
    await db.templates.update_one(
        {"name": template_name},
        {"$set": {"components": components, "synced_at": datetime.now(timezone.utc)}},
    )
    updated = await db.templates.find_one({"name": template_name}, {"_id": 0})
    return updated


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
