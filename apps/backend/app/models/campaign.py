from pydantic import BaseModel, Field, validator
from typing import Literal
from datetime import datetime, timezone


CampaignStatus = Literal[
    "draft", "queued", "running", "paused", "completed", "failed", "cancelled"
]
Priority = Literal["MARKETING", "UTILITY"]


class CampaignCreate(BaseModel):
    restaurant_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    template_id: str = Field(min_length=1)
    template_name: str = Field(min_length=1)
    template_variables: dict = Field(default_factory=dict)
    media_url: str | None = None
    priority: Priority = Field(default="MARKETING")
    scheduled_at: datetime | None = None
    include_unsubscribe: bool = True
    contact_file_ref: str = Field(min_length=1)  # temp file key from upload step

    @validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, v):
        if v is not None:
            now = datetime.now(timezone.utc)
            cmp_v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if cmp_v <= now:
                raise ValueError("scheduled_at must be strictly in the future")
        return v


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
    replies_count: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: str
    include_unsubscribe: bool
    created_at: datetime
    parent_campaign_id: str | None = None  # set on retry campaigns


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    page: int
    page_size: int


class CampaignTestMessageRequest(BaseModel):
    restaurant_id: str = Field(min_length=1)
    to_phone: str = Field(min_length=7, max_length=20)
    template_name: str = Field(min_length=1)
    template_variables: dict = Field(default_factory=dict)
    media_url: str | None = None


class CampaignTestMessageResponse(BaseModel):
    wa_message_id: str
    endpoint_used: Literal["primary", "fallback"]
