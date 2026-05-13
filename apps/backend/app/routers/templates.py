from fastapi import APIRouter, Depends, BackgroundTasks
from datetime import datetime, timezone
from typing import Annotated, Literal
import re
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.dependencies import require_role, get_active_restaurant
from app.services.meta_api import (
    fetch_templates,
    create_template,
    edit_template,
    MetaAPIError,
    create_media_handle_from_url,
)
from app.services.alert_service import alert_service
from app.core.errors import NotFoundError, ValidationError
from app.config import settings
from app.core.logging import get_logger

router = APIRouter(prefix="/templates", tags=["templates"])
logger = get_logger(__name__)


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

            if handle_value:
                data["example"] = {"header_handle": [handle_value]}

        # Remove media_url from the final payload to Meta
        if "media_url" in data.get("example", {}):
            data["example"] = {
                k: v for k, v in data["example"].items() if k != "media_url"
            }
            if not data["example"]:
                data.pop("example", None)

    # Avoid sending empty text values for media header components.
    text = data.get("text")
    is_media_header = (
        component_type == "HEADER" and (component.format or "").upper() != "TEXT"
    )
    if is_media_header and isinstance(text, str) and not text.strip():
        data.pop("text", None)

    # Meta requires variable examples when placeholders are used.
    if component_type in {"BODY", "HEADER"} and isinstance(data.get("text"), str):
        text_val = data["text"]
        matches = [int(m.group(1)) for m in VAR_PATTERN.finditer(text_val)]
        if matches:
            var_count = max(matches)
            if component_type == "BODY":
                if not (
                    isinstance(data.get("example"), dict)
                    and data["example"].get("body_text")
                ):
                    data.setdefault("example", {})["body_text"] = [
                        [f"value_{i}" for i in range(1, var_count + 1)]
                    ]
            elif (
                component_type == "HEADER"
                and (component.format or "").upper() == "TEXT"
            ):
                if not (
                    isinstance(data.get("example"), dict)
                    and data["example"].get("header_text")
                ):
                    data.setdefault("example", {})["header_text"] = [
                        f"value_{i}" for i in range(1, var_count + 1)
                    ]

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


def _resolve_restaurant_waba(restaurant: dict) -> tuple[str, str]:
    """Return (waba_id, access_token) for the restaurant.

    Convention: wa_phones[0] is always the primary outbound number. This is
    enforced by PUT /restaurants/{id}/phones — the first entry in the array is
    used for all outbound operations. Additional entries (index 1+) are reserved
    for future multi-number support.

    Raises ValidationError (HTTP 422) if:
    - wa_phones is empty (restaurant not yet configured), or
    - waba_id is present but the env var for the token is not set.

    This is intentional for templates — a misconfigured WABA should surface
    immediately rather than silently falling back to another restaurant's WABA.
    For inbox reply, the fallback to global credentials is handled separately.
    """
    name = restaurant.get("name", restaurant.get("id", "unknown"))
    wa_phones = restaurant.get("wa_phones", [])
    if wa_phones:
        primary = wa_phones[0]
        waba_id = primary.get("waba_id") or ""
        env_key = primary.get("access_token_env_key") or ""
        token = settings.resolve_waba_token(env_key) if env_key else ""
        if waba_id and token:
            return waba_id, token
        if waba_id and not token:
            raise ValidationError(
                f"WhatsApp access token for '{name}' is missing. "
                f"Add the '{env_key}' environment variable and restart the server."
            )
    raise ValidationError(
        f"'{name}' has no WhatsApp Business Account configured. "
        "Go to Admin → Restaurants and add a phone number with WABA credentials."
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_templates(
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """Return templates for the active restaurant.

    Scoping rule:
    - Restaurants WITH wa_phones configured → see only their own templates
      (restaurant_id matches).
    - Restaurants WITHOUT wa_phones (not yet migrated) → see legacy global
      templates (no restaurant_id field) via the $exists fallback.

    This boundary prevents cross-restaurant template leakage while allowing
    a zero-downtime migration. Once all restaurants are configured and synced,
    the $exists branch can be removed.
    """
    rid = restaurant["id"]
    has_wa_phones = bool(restaurant.get("wa_phones"))

    if has_wa_phones:
        # Fully configured restaurant — show only its own templates
        query: dict = {"restaurant_id": rid}
    else:
        # Legacy / unconfigured restaurant — show global (unscoped) templates only
        query = {"restaurant_id": {"$exists": False}}

    cursor = db.templates.find(query, {"_id": 0}).sort("name", 1)
    return [doc async for doc in cursor]


@router.post("", status_code=201)
async def create_new_template(
    body: CreateTemplateRequest,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    waba_id, token = _resolve_restaurant_waba(restaurant)
    normalized_components = [_normalize_component_for_meta(c) for c in body.components]
    normalized_components = await _resolve_media_header_handles(normalized_components)
    if not any(c.get("type") == "BODY" for c in normalized_components):
        raise ValidationError("Template must include a BODY component with text")
    payload = {
        "name": body.name,
        "category": body.category,
        "language": _normalize_language_code(body.language),
        "components": [c for c in normalized_components if c],
        "parameter_format": "POSITIONAL",
    }
    try:
        result = await create_template(waba_id, token, payload)
    except MetaAPIError as exc:
        raise ValidationError(f"Meta rejected template payload: {exc.message}") from exc

    meta_id = result.get("id")
    if not meta_id:
        raise ValidationError(
            "Meta did not return a template ID — the template may not have been created. "
            "Check your WABA settings and try again."
        )

    now = datetime.now(timezone.utc)

    original_media_url = None
    for comp in body.components:
        if (comp.type or "").upper() == "HEADER" and (
            comp.format or ""
        ).upper() == "IMAGE":
            if isinstance(comp.example, dict):
                original_media_url = comp.example.get("media_url") or None
            break

    doc = {
        "name": body.name,
        "category": body.category,
        "language": _normalize_language_code(body.language),
        "status": result.get("status", "PENDING"),
        "components": payload["components"],
        "meta_id": str(meta_id),
        "restaurant_id": restaurant["id"],
        "synced_at": now,
    }
    if original_media_url:
        doc["media_url"] = original_media_url

    await db.templates.update_one(
        {
            "name": body.name,
            "language": doc["language"],
            "restaurant_id": restaurant["id"],
        },
        {"$set": doc},
        upsert=True,
    )
    return doc


@router.patch("/{template_name}")
async def edit_existing_template(
    template_name: str,
    body: EditTemplateRequest,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    language: str | None = None,
):
    query: dict = {"name": template_name, "restaurant_id": restaurant["id"]}
    if language:
        query["language"] = language

    doc = await db.templates.find_one(query)
    if not doc:
        raise NotFoundError(f"Template '{template_name}' not found")

    meta_id = doc.get("meta_id")
    if not meta_id:
        raise ValidationError(
            "This template has no Meta ID — sync templates first so the ID is stored."
        )

    _, token = _resolve_restaurant_waba(restaurant)
    components = [_normalize_component_for_meta(c) for c in body.components]
    await edit_template(meta_id, token, components)

    await db.templates.update_one(
        {"meta_id": meta_id},
        {"$set": {"components": components, "synced_at": datetime.now(timezone.utc)}},
    )
    updated = await db.templates.find_one({"meta_id": meta_id}, {"_id": 0})
    return updated


@router.post("/sync", status_code=200)
async def sync_templates(
    background_tasks: BackgroundTasks,
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """Sync templates from the restaurant's own WABA and prune stale local copies."""
    waba_id, token = _resolve_restaurant_waba(restaurant)
    rid = restaurant["id"]

    try:
        templates = await fetch_templates(waba_id, token)
    except Exception as e:
        return {"error": str(e)}

    keys: list[dict] = []
    for t in templates:
        key = await _sync_single_template(db, t, background_tasks, rid)
        keys.append(key)

    # Prune templates that no longer exist in Meta for this restaurant
    if keys:
        await db.templates.delete_many({"restaurant_id": rid, "$nor": keys})
    else:
        await db.templates.delete_many({"restaurant_id": rid})

    return {"synced": len(templates), "pruned": True}


async def _sync_single_template(
    db: AsyncIOMotorDatabase,
    t: dict,
    background_tasks: BackgroundTasks,
    restaurant_id: str,
) -> dict:
    """Upsert one template scoped to a restaurant and fire an approval alert if newly APPROVED."""
    lang = t.get("language")
    key: dict = {"name": t["name"], "restaurant_id": restaurant_id}
    if lang:
        key["language"] = lang

    old_doc = await db.templates.find_one(key)
    was_approved = bool(old_doc and old_doc.get("status") == "APPROVED")
    already_alerted = bool(old_doc and old_doc.get("alert_sent"))
    is_approved = t.get("status") == "APPROVED"

    update_fields = {
        **t,
        "restaurant_id": restaurant_id,
        "synced_at": datetime.now(timezone.utc),
    }
    await db.templates.update_one(key, {"$set": update_fields}, upsert=True)

    if not was_approved and is_approved and not already_alerted:
        rest = await db.restaurants.find_one({"id": restaurant_id})
        if rest:
            background_tasks.add_task(
                alert_service.send_template_approved_alert, db, rest, t["name"]
            )
        await db.templates.update_one(
            key,
            {"$set": {"alert_sent": True, "synced_at": datetime.now(timezone.utc)}},
        )

    return key
