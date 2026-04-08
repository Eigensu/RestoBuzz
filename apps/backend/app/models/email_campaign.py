"""Pydantic models for Email Campaigns (Resend channel)."""
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


EmailCampaignStatus = Literal[
    "draft",
    "queued",
    "sending",
    "completed",
    "partial_failure",
    "failed",
    "cancelled",
    "quota_exceeded",
]


class EmailCampaignCreate(BaseModel):
    restaurant_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    template_id: str = Field(min_length=1)  # Internal MongoDB template _id
    subject: str = Field(min_length=1, max_length=998)
    from_email: str | None = None  # Override default sender
    reply_to: str | None = None
    scheduled_at: datetime | None = None
    contact_file_ref: str = Field(min_length=1)


class EmailCampaignResponse(BaseModel):
    id: str
    restaurant_id: str
    name: str
    template_id: str
    subject: str
    from_email: str
    status: EmailCampaignStatus
    total_count: int
    sent_count: int
    delivered_count: int
    opened_count: int
    clicked_count: int
    bounced_count: int
    failed_count: int
    complained_count: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: str
    created_at: datetime


class EmailCampaignListResponse(BaseModel):
    items: list[EmailCampaignResponse]
    total: int
    page: int
    page_size: int
