from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


CampaignStatus = Literal["draft", "queued", "running", "paused", "completed", "failed", "cancelled"]
Priority = Literal["MARKETING", "UTILITY"]


class CampaignCreate(BaseModel):
    restaurant_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    template_id: str
    template_name: str
    template_variables: dict = Field(default_factory=dict)
    media_url: str | None = None
    priority: Priority = "MARKETING"
    scheduled_at: datetime | None = None
    include_unsubscribe: bool = True
    contact_file_ref: str  # temp file key from upload step


class CampaignResponse(BaseModel):
    id: str
    restaurant_id: str
    name: str
    template_id: str
    template_name: str
    priority: Priority
    status: CampaignStatus
    total_count: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: str
    include_unsubscribe: bool
    created_at: datetime


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    page: int
    page_size: int
