from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from typing import Annotated, Literal
import re
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.dependencies import require_role
from app.services.meta_api import (
    fetch_templates,
    create_template,
    edit_template,
    MetaAPIError,
    create_media_handle_from_url,
)
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


VAR_PATTERN = re.compile(r"\{\{(\d+)\}\}")

LANGUAGE_MAP = {
    "en": "en_US",
    "hi": "hi_IN",
    "es": "es_ES",
    "fr": "fr_FR",
    "pt": "pt_BR",
}


def _normalize_language_code(code: str) -> str:
    normalized = (code or "").strip()
    if not normalized:
        return "en_US"
    return LANGUAGE_MAP.get(normalized, normalized)


def _normalize_component_for_meta(component: TemplateComponent) -> dict:
    """Strip UI-only fields and invalid empty values before sending to Meta API."""
    data = component.model_dump(exclude_none=True)
    component_type = str(component.type or "").upper().strip()
    data["type"] = component_type

    # Prevent sending unsupported text-only buttons payloads.
    if component_type == "BUTTONS" and not data.get("buttons"):
        raise ValidationError(
            "BUTTONS component requires structured buttons; plain text buttons are not supported yet"
        )

    # Frontend uses media_url for local preview/upload flow. Meta expects media
    # example under `header_handle` for media HEADER components.
    example = data.get("example")
    if isinstance(example, dict):
        media_url = example.get("media_url")
        header_handles = example.get("header_handle")
        if component_type == "HEADER" and (component.format or "").upper() in {
            "IMAGE",
            "VIDEO",
            "DOCUMENT",
        }:
            handle_value: str | None = None
            if isinstance(media_url, str) and media_url.strip():
                handle_value = media_url.strip()
            elif (
                isinstance(header_handles, list)
                and header_handles
                and isinstance(header_handles[0], str)
                and header_handles[0].strip()
            ):
                handle_value = header_handles[0].strip()

            example = {"header_handle": [handle_value]} if handle_value else {}

        cleaned_example = {k: v for k, v in example.items() if k != "media_url"}
        if cleaned_example:
            data["example"] = cleaned_example
        else:
            data.pop("example", None)

    # Avoid sending empty text values for media header components.
    text = data.get("text")
    if isinstance(text, str) and not text.strip():
        data.pop("text", None)

    # Meta requires body variable examples when placeholders are used.
    if component_type == "BODY" and isinstance(data.get("text"), str):
        matches = [int(m.group(1)) for m in VAR_PATTERN.finditer(data["text"])]
        if matches and not (
            isinstance(data.get("example"), dict) and data["example"].get("body_text")
        ):
            var_count = max(matches)
            data["example"] = {
                "body_text": [[f"value_{i}" for i in range(1, var_count + 1)]]
            }

    return data


async def _resolve_media_header_handles(components: list[dict]) -> list[dict]:
    resolved: list[dict] = []
    for comp in components:
        item = dict(comp)
        if item.get("type") == "HEADER" and str(item.get("format", "")).upper() in {
            "IMAGE",
            "VIDEO",
            "DOCUMENT",
        }:
            example = item.get("example")
            if isinstance(example, dict):
                handles = example.get("header_handle")
                if (
                    isinstance(handles, list)
                    and handles
                    and isinstance(handles[0], str)
                    and handles[0].strip().startswith("https://")
                ):
                    if not settings.meta_primary_access_token:
                        raise ValidationError(
                            "Meta access token missing; cannot upload template media"
                        )
                    media_id = await create_media_handle_from_url(
                        handles[0].strip(),
                        settings.meta_app_id,
                        settings.meta_primary_access_token,
                    )
                    item["example"] = {"header_handle": [media_id]}
        resolved.append(item)
    return resolved


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_templates(
    _current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    cursor = db.templates.find({}, {"_id": 0}).sort("name", 1)
    return [doc async for doc in cursor]


@router.post("", status_code=201)
async def create_new_template(
    body: CreateTemplateRequest,
    _current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    normalized_components = [_normalize_component_for_meta(c) for c in body.components]
    normalized_components = await _resolve_media_header_handles(normalized_components)
    if not any(c.get("type") == "BODY" for c in normalized_components):
        raise ValidationError("Template must include a BODY component with text")
    payload = {
        "name": body.name,
        "category": body.category,
        "language": _normalize_language_code(body.language),
        "components": [c for c in normalized_components if c],
    }
    try:
        result = await create_template(
            settings.meta_waba_id,
            settings.meta_primary_access_token,
            payload,
        )
    except MetaAPIError as exc:
        raise ValidationError(f"Meta rejected template payload: {exc.message}") from exc

    meta_id = result.get("id")
    if not meta_id:
        raise ValidationError(
            "Meta did not return a template ID — the template may not have been created. "
            "Check your WABA settings and try again."
        )

    # Persist locally so it shows up immediately without a sync
    now = datetime.now(timezone.utc)
    doc = {
        "name": body.name,
        "category": body.category,
        "language": _normalize_language_code(body.language),
        "status": result.get("status", "PENDING"),
        "components": payload["components"],
        "meta_id": str(meta_id),
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
    _current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.templates.find_one({"name": template_name})
    if not doc:
        raise NotFoundError(f"Template '{template_name}' not found")

    meta_id = doc.get("meta_id")
    if not meta_id:
        raise ValidationError(
            "This template has no Meta ID — sync templates first so the ID is stored."
        )

    components = [_normalize_component_for_meta(c) for c in body.components]
    await edit_template(meta_id, settings.meta_primary_access_token, components)

    # Update local copy — use meta_id to target the exact document,
    # avoiding ambiguity when multiple language variants share a name.
    await db.templates.update_one(
        {"meta_id": meta_id},
        {"$set": {"components": components, "synced_at": datetime.now(timezone.utc)}},
    )
    updated = await db.templates.find_one({"meta_id": meta_id}, {"_id": 0})
    return updated


@router.post("/sync", status_code=200)
async def sync_templates(
    _current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    templates = await fetch_templates(
        settings.meta_waba_id,
        settings.meta_primary_access_token,
    )
    keys: list[dict[str, str | None]] = []
    for t in templates:
        key = {"name": t["name"], "language": t.get("language")}
        keys.append(key)
        await db.templates.update_one(
            key,
            {"$set": {**t, "synced_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    # Remove templates that no longer exist in Meta for this workspace.
    if keys:
        await db.templates.delete_many({"$nor": keys})
    else:
        await db.templates.delete_many({})

    return {"synced": len(templates), "pruned": True}
