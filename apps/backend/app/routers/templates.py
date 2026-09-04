from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
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
from app.utils.phone import normalize_phone
from app.config import settings
from app.core.logging import get_logger

router = APIRouter(prefix="/templates", tags=["templates"])
logger = get_logger(__name__)


# ── Request models ────────────────────────────────────────────────────────────


class TemplateButton(BaseModel):
    type: str
    text: str | None = None
    url: str | None = None
    phone_number: str | None = None
    # COPY_CODE carries the coupon here; Meta labels that button itself, so it
    # has no text of its own.
    example: str | None = None


class TemplateComponent(BaseModel):
    type: str
    text: str | None = None
    format: str | None = None
    example: dict | None = None
    buttons: list[TemplateButton] | None = None


class CreateTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=512, pattern=r"^[a-z0-9_]+$")
    category: Literal["MARKETING", "UTILITY", "AUTHENTICATION"]
    language: str = Field(min_length=2, max_length=10)
    components: list[TemplateComponent]


class EditTemplateRequest(BaseModel):
    components: list[TemplateComponent]


VAR_PATTERN = re.compile(r"\{\{(\d+)\}\}")

# Meta's two parameter formats. A template is fixed to one at creation and it
# cannot be changed afterwards, so the format is inferred from the placeholders
# the author actually wrote rather than asked for separately.
#   positional — {{1}}, {{2}}  (every template created before named support)
#   named      — {{customer_name}}
# Lowercase only, matching Meta's rule for named parameters and the frontend's
# own validator — accepting more here just defers the rejection to Meta.
NAMED_VAR_PATTERN = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
ANY_VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
MAX_VAR_NAME = 60

# Meta's template-button rules. Mirrored by lib/templateButtons.ts in the
# frontend, which enforces the same caps before submit — change both together.
MAX_BUTTONS = 10
MAX_BUTTON_TEXT = 25
MAX_BUTTON_URL = 2000
MAX_OFFER_CODE = 15
BUTTON_TYPE_CAPS = {
    "QUICK_REPLY": 10,
    "URL": 2,
    "PHONE_NUMBER": 1,
    "COPY_CODE": 1,
}

# The component order Meta requires of a template payload.
COMPONENT_ORDER = {"HEADER": 0, "BODY": 1, "FOOTER": 2, "BUTTONS": 3}

LANGUAGE_MAP = {
    "en": "en_US",
    "hi": "hi_IN",
    "es": "es_ES",
    "fr": "fr_FR",
    "pt": "pt_BR",
}


def _extract_variables(text: str) -> list[str]:
    """Placeholder names in `text`, in first-appearance order, deduplicated.

    A name repeated in the body is one parameter to Meta, not two.
    """
    seen: list[str] = []
    for match in ANY_VAR_PATTERN.finditer(text or ""):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def _resolve_parameter_format(components: list[TemplateComponent]) -> str:
    """Decide POSITIONAL vs NAMED from the placeholders in the template text.

    Meta rejects a template that mixes the two, and the failure message does not
    say which placeholder is the odd one out, so the mix is caught here instead.
    """
    numbered: list[str] = []
    named: list[str] = []

    for component in components:
        if str(component.type or "").upper() not in {"BODY", "HEADER"}:
            continue
        for name in _extract_variables(component.text or ""):
            (numbered if name.isdigit() else named).append(name)

    if numbered and named:
        raise ValidationError(
            "A template cannot mix numbered and named variables — found "
            f"{{{{{numbered[0]}}}}} and {{{{{named[0]}}}}}. Use one style throughout."
        )

    for name in named:
        if not NAMED_VAR_PATTERN.fullmatch("{{" + name + "}}"):
            raise ValidationError(
                f"Variable name '{name}' is invalid. Use letters, numbers and "
                "underscores, starting with a letter."
            )
        if len(name) > MAX_VAR_NAME:
            raise ValidationError(
                f"Variable name '{name}' exceeds {MAX_VAR_NAME} characters"
            )

    return "NAMED" if named else "POSITIONAL"


def _reject_header_variables(components: list[TemplateComponent]) -> None:
    """Refuse a TEXT header that contains a placeholder.

    Meta would accept the template, but every send would fail: _build_payload
    emits header parameters only for media headers, and the campaign wizard
    collects variables from the BODY alone. Allowing this would approve a
    template that can never actually be delivered.
    """
    for component in components:
        if str(component.type or "").upper() != "HEADER":
            continue
        if (component.format or "TEXT").upper() != "TEXT":
            continue
        names = _extract_variables(component.text or "")
        if names:
            raise ValidationError(
                f"The header cannot contain variables (found {{{{{names[0]}}}}}). "
                "Move it into the message body."
            )


def _named_examples(names: list[str], supplied: object) -> list[dict[str, str]]:
    """Meta's named-parameter example block, preserving any sample the author
    typed and inventing a readable one for the rest.

    A template with no examples is far likelier to be rejected on review, so a
    missing sample is filled rather than left out.
    """
    provided: dict[str, str] = {}
    if isinstance(supplied, list):
        for item in supplied:
            if isinstance(item, dict):
                param = str(item.get("param_name") or "").strip()
                sample = str(item.get("example") or "").strip()
                if param and sample:
                    provided[param] = sample

    return [
        {
            "param_name": name,
            "example": provided.get(name) or name.replace("_", " ").title(),
        }
        for name in names
    ]


def _normalize_language_code(code: str) -> str:
    normalized = (code or "").strip()
    if not normalized:
        return "en_US"
    return LANGUAGE_MAP.get(normalized, normalized)


def _normalize_buttons(buttons: list[TemplateButton]) -> list[dict]:
    """Validate a BUTTONS component and reduce it to what Meta accepts.

    Meta rejects a malformed button set with a generic "invalid parameter",
    which tells the operator nothing about which of the ten rows was wrong, so
    every rule is checked here and reported against the offending button.

    Call-to-action buttons are emitted before the quick replies: Meta requires
    quick replies in a mixed set to be contiguous, and putting them last is
    always a valid grouping regardless of the order they arrived in.
    """
    if not buttons:
        raise ValidationError(
            "BUTTONS component requires structured buttons; plain text buttons are not supported yet"
        )
    if len(buttons) > MAX_BUTTONS:
        raise ValidationError(f"A template can have at most {MAX_BUTTONS} buttons")

    counts: dict[str, int] = {}
    for button in buttons:
        btn_type = str(button.type or "").upper().strip()
        if btn_type not in BUTTON_TYPE_CAPS:
            supported = ", ".join(sorted(BUTTON_TYPE_CAPS))
            raise ValidationError(
                f"Unsupported button type '{button.type}'. Supported types: {supported}"
            )
        counts[btn_type] = counts.get(btn_type, 0) + 1
        if counts[btn_type] > BUTTON_TYPE_CAPS[btn_type]:
            raise ValidationError(
                f"At most {BUTTON_TYPE_CAPS[btn_type]} {btn_type} button(s) allowed per template"
            )

    cta: list[dict] = []
    quick_replies: list[dict] = []
    labels: set[str] = set()

    for button in buttons:
        btn_type = str(button.type or "").upper().strip()

        if btn_type == "COPY_CODE":
            code = (button.example or "").strip()
            if not code:
                raise ValidationError("Copy offer code button needs an offer code")
            if len(code) > MAX_OFFER_CODE:
                raise ValidationError(
                    f"Offer code must be {MAX_OFFER_CODE} characters or fewer"
                )
            cta.append({"type": "COPY_CODE", "example": code})
            continue

        text = (button.text or "").strip()
        if not text:
            raise ValidationError(f"{btn_type} button needs button text")
        if len(text) > MAX_BUTTON_TEXT:
            raise ValidationError(
                f"Button text '{text}' exceeds {MAX_BUTTON_TEXT} characters"
            )
        if text.lower() in labels:
            raise ValidationError(f"Duplicate button text '{text}' — each must differ")
        labels.add(text.lower())

        if btn_type == "URL":
            url = (button.url or "").strip()
            if not url:
                raise ValidationError(f"Button '{text}' needs a URL")
            if not url.lower().startswith(("http://", "https://")):
                raise ValidationError(f"Button '{text}' URL must start with https://")
            if len(url) > MAX_BUTTON_URL:
                raise ValidationError(f"Button '{text}' URL is too long")
            # A dynamic URL needs a button parameter on every send, which
            # _build_payload does not emit — the placeholder would ship to the
            # customer verbatim.
            if VAR_PATTERN.search(url) or "{{" in url:
                raise ValidationError(
                    f"Button '{text}' uses a variable in its URL, which is not supported yet"
                )
            cta.append({"type": "URL", "text": text, "url": url})

        elif btn_type == "PHONE_NUMBER":
            raw = (button.phone_number or "").strip()
            e164 = normalize_phone(raw) if raw else None
            if not e164:
                raise ValidationError(
                    f"Button '{text}' needs a valid phone number (got '{raw}')"
                )
            cta.append({"type": "PHONE_NUMBER", "text": text, "phone_number": e164})

        else:
            quick_replies.append({"type": "QUICK_REPLY", "text": text})

    return cta + quick_replies


def _order_components(components: list[dict]) -> list[dict]:
    """Sort into Meta's required HEADER, BODY, FOOTER, BUTTONS order.

    The sort is stable, so components Meta may add later that this map does not
    know about keep their relative order at the end.
    """
    return sorted(
        components, key=lambda c: COMPONENT_ORDER.get(str(c.get("type", "")), 99)
    )


def _normalize_component_for_meta(
    component: TemplateComponent, parameter_format: str = "POSITIONAL"
) -> dict:
    """Strip UI-only fields and invalid empty values before sending to Meta API."""
    data = component.model_dump(exclude_none=True)
    component_type = str(component.type or "").upper().strip()
    data["type"] = component_type

    if component_type == "BUTTONS":
        return {"type": "BUTTONS", "buttons": _normalize_buttons(component.buttons or [])}

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

    # Meta requires variable examples when placeholders are used, and the shape
    # of that example block differs between the two parameter formats.
    is_text_header = (
        component_type == "HEADER" and (component.format or "").upper() == "TEXT"
    )
    if component_type in {"BODY", "HEADER"} and isinstance(data.get("text"), str):
        text_val = data["text"]

        if parameter_format == "NAMED":
            names = _extract_variables(text_val)
            if names and (component_type == "BODY" or is_text_header):
                key = (
                    "body_text_named_params"
                    if component_type == "BODY"
                    else "header_text_named_params"
                )
                existing = data.get("example")
                supplied = existing.get(key) if isinstance(existing, dict) else None
                data.setdefault("example", {})[key] = _named_examples(
                    names, supplied
                )
        else:
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
                elif is_text_header:
                    if not (
                        isinstance(data.get("example"), dict)
                        and data["example"].get("header_text")
                    ):
                        data.setdefault("example", {})["header_text"] = [
                            f"value_{i}" for i in range(1, var_count + 1)
                        ]

    return data


async def _resolve_media_header_handles(components: list[dict], access_token: str | None = None) -> list[dict]:
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
                    if not access_token:
                        raise ValidationError(
                            "Meta access token missing; cannot upload template media"
                        )
                    media_id = await create_media_handle_from_url(
                        handles[0].strip(),
                        settings.meta_app_id,
                        access_token,
                    )
                    item["example"] = {"header_handle": [media_id]}
        resolved.append(item)
    return resolved


def _preserve_unmanaged_components(
    components: list[dict], stored: dict
) -> list[dict]:
    """Carry over BUTTONS components the editor cannot express.

    Meta's edit endpoint REPLACES the whole component set, and the edit form has
    no buttons UI — it strips BUTTONS on load. Without this, editing the body of
    a template whose buttons were set at creation, or added in Meta Business
    Manager, would silently delete them. Buttons must stay last: Meta requires
    HEADER, BODY, FOOTER, BUTTONS order.
    """
    if any(str(c.get("type", "")).upper() == "BUTTONS" for c in components):
        return components

    stored_buttons = [
        c
        for c in (stored.get("components") or [])
        if isinstance(c, dict)
        and str(c.get("type", "")).upper() == "BUTTONS"
        and c.get("buttons")
    ]
    if not stored_buttons:
        return components

    logger.info(
        "template_edit_preserved_buttons",
        template=stored.get("name"),
        restaurant_id=stored.get("restaurant_id"),
        count=len(stored_buttons),
    )
    return components + stored_buttons


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
    parameter_format = _resolve_parameter_format(body.components)
    _reject_header_variables(body.components)
    normalized_components = [
        _normalize_component_for_meta(c, parameter_format) for c in body.components
    ]
    normalized_components = await _resolve_media_header_handles(normalized_components, token)
    normalized_components = _order_components(normalized_components)
    if not any(c.get("type") == "BODY" for c in normalized_components):
        raise ValidationError("Template must include a BODY component with text")
    payload = {
        "name": body.name,
        "category": body.category,
        "language": _normalize_language_code(body.language),
        "components": [c for c in normalized_components if c],
        "parameter_format": parameter_format,
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
        # Stored so the campaign send path knows which parameter shape this
        # template expects without re-deriving it from the body text.
        "parameter_format": parameter_format,
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
    # An edit cannot change the format Meta fixed at creation, so the stored one
    # wins over whatever this partial component set would imply on its own.
    parameter_format = str(doc.get("parameter_format") or "").upper() or (
        _resolve_parameter_format(body.components)
    )
    components = [
        _normalize_component_for_meta(c, parameter_format) for c in body.components
    ]
    # Same upload step as create: Meta only accepts an uploaded handle in
    # example.header_handle, never a raw https:// URL.
    components = await _resolve_media_header_handles(components, token)
    components = _order_components(components)
    components = _preserve_unmanaged_components(components, doc)
    try:
        await edit_template(meta_id, token, components)
    except MetaAPIError as exc:
        raise ValidationError(f"Meta rejected template edit: {exc.message}") from exc

    update: dict = {
        "components": components,
        "synced_at": datetime.now(timezone.utc),
    }
    # Keep the displayable media URL in sync — components now hold the opaque
    # Meta handle, which the UI cannot render.
    for comp in body.components:
        if (comp.type or "").upper() == "HEADER" and (
            comp.format or ""
        ).upper() in {"IMAGE", "VIDEO", "DOCUMENT"}:
            if isinstance(comp.example, dict):
                media_url = comp.example.get("media_url")
                if isinstance(media_url, str) and media_url.strip():
                    update["media_url"] = media_url.strip()
            break

    await db.templates.update_one(
        {"meta_id": meta_id, "restaurant_id": restaurant["id"]},
        {"$set": update},
    )
    updated = await db.templates.find_one(
        {"meta_id": meta_id, "restaurant_id": restaurant["id"]}, {"_id": 0}
    )
    return updated


@router.post(
    "/sync",
    status_code=200,
    responses={502: {"description": "Meta refused or failed the template fetch"}},
)
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
    except MetaAPIError as exc:
        logger.error(
            "template_sync_failed",
            restaurant_id=rid,
            waba_id=waba_id,
            code=exc.code,
            message=exc.message,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Meta refused the template fetch [{exc.code}]: {exc.message}",
        ) from exc
    except Exception as e:
        logger.exception("template_sync_unexpected_error", restaurant_id=rid)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch templates from Meta: {type(e).__name__}: {e}",
        ) from e

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
    # Meta returns the template id as "id"; store it as "meta_id" — that is the
    # field PATCH /templates/{name} needs to push an edit back to Meta.
    meta_id = update_fields.pop("id", None)
    if meta_id:
        update_fields["meta_id"] = str(meta_id)
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
