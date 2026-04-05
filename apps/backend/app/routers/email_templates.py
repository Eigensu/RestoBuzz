"""
Email Templates Router — CRUD for locally-managed templates.

Templates are stored in MongoDB (source of truth).
Jinja2 is used at send-time for variable rendering.
"""
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import (
    require_role,
    require_restaurant_access,
    validate_restaurant_access,
)
from app.core.utils import to_object_id
from app.core.logging import get_logger
from app.core.errors import TemplateNotFoundError, ValidationError
from app.models.email_template import (
    EmailTemplateCreate,
    EmailTemplateUpdate,
    EmailTemplateResponse,
    TemplateVariable,
)
from app.services.resend_client import render_template

router = APIRouter(prefix="/email-templates", tags=["email-templates"])
logger = get_logger(__name__)


def _serialize(doc: dict) -> EmailTemplateResponse:
    return EmailTemplateResponse(
        id=str(doc["_id"]),
        restaurant_id=doc["restaurant_id"],
        name=doc["name"],
        subject=doc["subject"],
        html=doc["html"],
        text=doc.get("text"),
        variables=[TemplateVariable(**v) for v in doc.get("variables", [])],
        version=doc.get("version", 1),
        is_active=doc.get("is_active", True),
        created_by=str(doc["created_by"]),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.get("")
async def list_email_templates(
    validated_rid: Annotated[str, Depends(require_restaurant_access())],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    skip = (page - 1) * page_size
    query = {"restaurant_id": validated_rid}
    total = await db.email_templates.count_documents(query)
    cursor = (
        db.email_templates.find(query)
        .sort("updated_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    items = [_serialize(doc) async for doc in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_email_template(
    body: EmailTemplateCreate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    restaurant_id: Annotated[str, Depends(require_restaurant_access())],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # Validate Jinja2 syntax by doing a dry render
    try:
        test_vars = {v.key: v.fallback_value or "" for v in body.variables}
        render_template(body.html, test_vars)
    except Exception as e:
        raise ValidationError(f"Template HTML has invalid Jinja2 syntax: {e}") from e

    now = datetime.now(timezone.utc)
    doc = {
        "restaurant_id": restaurant_id,
        "name": body.name,
        "subject": body.subject,
        "html": body.html,
        "text": body.text,
        "variables": [v.model_dump() for v in body.variables],
        "version": 1,
        "is_active": True,
        "created_by": current_user["_id"],
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = await db.email_templates.insert_one(doc)
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise ValidationError(
                f"A template named '{body.name}' already exists for this restaurant"
            ) from e
        raise

    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.get("/{template_id}")
async def get_email_template(
    template_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.email_templates.find_one({"_id": to_object_id(template_id)})
    if not doc:
        raise TemplateNotFoundError(f"Email template '{template_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    return _serialize(doc)


@router.put("/{template_id}")
async def update_email_template(
    template_id: str,
    body: EmailTemplateUpdate,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.email_templates.find_one({"_id": to_object_id(template_id)})
    if not doc:
        raise TemplateNotFoundError(f"Email template '{template_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.name is not None:
        updates["name"] = body.name
    if body.subject is not None:
        updates["subject"] = body.subject
    if body.html is not None:
        # Validate syntax
        test_vars = {
            v.key: v.fallback_value or ""
            for v in (body.variables or [TemplateVariable(**v) for v in doc.get("variables", [])])
        }
        try:
            render_template(body.html, test_vars)
        except Exception as e:
            raise ValidationError(f"Template HTML has invalid Jinja2 syntax: {e}") from e
        updates["html"] = body.html
    if body.text is not None:
        updates["text"] = body.text
    if body.variables is not None:
        updates["variables"] = [v.model_dump() for v in body.variables]

    # Bump version
    updates["version"] = doc.get("version", 1) + 1

    result = await db.email_templates.find_one_and_update(
        {"_id": to_object_id(template_id)},
        {"$set": updates},
        return_document=True,
    )
    return _serialize(result)


@router.delete("/{template_id}", status_code=204)
async def delete_email_template(
    template_id: str,
    current_user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    doc = await db.email_templates.find_one({"_id": to_object_id(template_id)})
    if not doc:
        raise TemplateNotFoundError(f"Email template '{template_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)
    await db.email_templates.delete_one({"_id": to_object_id(template_id)})


@router.post("/{template_id}/preview")
async def preview_email_template(
    template_id: str,
    current_user: Annotated[dict, Depends(require_role("viewer"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    sample_data: dict | None = None,
):
    """Render a template with sample or fallback data and return the HTML."""
    doc = await db.email_templates.find_one({"_id": to_object_id(template_id)})
    if not doc:
        raise TemplateNotFoundError(f"Email template '{template_id}' not found")
    await validate_restaurant_access(current_user, doc["restaurant_id"], db)

    variables = {}
    for v in doc.get("variables", []):
        key = v["key"]
        if sample_data and key in sample_data:
            variables[key] = sample_data[key]
        elif v.get("fallback_value") is not None:
            variables[key] = v["fallback_value"]
        else:
            variables[key] = f"[{key}]"

    rendered_html = render_template(doc["html"], variables)
    return {
        "subject": doc["subject"],
        "html": rendered_html,
    }
