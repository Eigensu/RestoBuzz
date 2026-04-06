"""Pydantic models for individual Email Log entries."""

from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


EmailLogStatus = Literal[
    "queued",
    "sending",
    "sent",
    "delivered",
    "opened",
    "clicked",
    "bounced",
    "failed",
    "complained",
    "suppressed",
]


class EmailStatusHistoryEntry(BaseModel):
    status: EmailLogStatus
    timestamp: datetime
    meta: dict = Field(default_factory=dict)


class EmailLogResponse(BaseModel):
    id: str
    campaign_id: str
    recipient_email: str
    recipient_name: str
    resend_email_id: str | None
    status: EmailLogStatus
    status_history: list[EmailStatusHistoryEntry]
    retry_count: int
    error_reason: str | None
    created_at: datetime
    updated_at: datetime


class EmailLogListResponse(BaseModel):
    items: list[EmailLogResponse]
    total: int
    page: int
    page_size: int
