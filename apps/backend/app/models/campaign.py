from pydantic import BaseModel, Field, validator, root_validator
from typing import Literal
from datetime import datetime, timezone, timedelta


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
    smart_retries: bool = False
    retry_until: datetime | None = None

    @validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, v):
        if v is not None:
            now = datetime.now(timezone.utc)
            cmp_v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if cmp_v <= now:
                raise ValueError("scheduled_at must be strictly in the future")
        return v

    @validator("retry_until")
    @classmethod
    def validate_retry_until(cls, v):
        if v is not None:
            now = datetime.now(timezone.utc)
            cmp_v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if cmp_v <= now:
                raise ValueError("retry_until must be strictly in the future")
            if cmp_v > now + timedelta(days=30):
                raise ValueError("retry_until cannot be more than 30 days in the future")
        return v

    @root_validator(skip_on_failure=True)
    @classmethod
    def validate_smart_retries(cls, values):
        smart_retries = values.get("smart_retries")
        retry_until = values.get("retry_until")
        if smart_retries and not retry_until:
            raise ValueError("retry_until is required when smart_retries is True")
        return values


class CampaignCreateInternal(CampaignCreate):
    parent_campaign_id: str | None = None
    has_been_retried: bool = False
    completed_at: datetime | None = None

    @validator("retry_until")
    @classmethod
    def validate_retry_until(cls, v):
        # Override parent's strict-future check for auto-generated campaigns
        # near the deadline. We use the exact same method name to trigger override.
        if v is not None:
            now = datetime.now(timezone.utc)
            cmp_v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if cmp_v > now + timedelta(days=30):
                raise ValueError("retry_until cannot be more than 30 days in the future")
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
    has_been_retried: bool = False
    smart_retries: bool = False
    retry_until: datetime | None = None


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
