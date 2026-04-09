"""Pydantic models for locally-managed Email Templates."""
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class TemplateVariable(BaseModel):
    key: str = Field(min_length=1)
    type: Literal["string", "number"] = "string"
    fallback_value: str | int | float | None = None


class EmailTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=998)
    html: str = Field(min_length=1)
    text: str | None = None  # plain-text fallback
    variables: list[TemplateVariable] = Field(default_factory=list)


class EmailTemplateUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    html: str | None = None
    text: str | None = None
    variables: list[TemplateVariable] | None = None


class EmailTemplateResponse(BaseModel):
    id: str
    restaurant_id: str
    name: str
    subject: str
    html: str
    text: str | None
    variables: list[TemplateVariable]
    version: int
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
