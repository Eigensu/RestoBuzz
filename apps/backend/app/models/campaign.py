from pydantic import BaseModel, Field, validator, root_validator
from typing import Literal
from datetime import datetime, timezone, timedelta


CampaignStatus = Literal[
    "draft", "queued", "running", "paused", "completed", "failed", "cancelled"
]
Priority = Literal["MARKETING", "UTILITY"]


class CampaignPersonalization(BaseModel):
    """Per-recipient image personalization for a campaign's template header.

    When present, the send path renders each recipient's name onto a single
    base card (uploaded once) via a Cloudinary text-overlay URL, and uses that
    as the message's image header instead of a static `media_url`.
    """

    type: Literal["ecard_name_overlay"] = "ecard_name_overlay"
    base_public_id: str = Field(min_length=1)  # Cloudinary public_id of the blank card
    overlay: dict = Field(default_factory=dict)  # overrides ecard_service defaults


class VariableSource(BaseModel):
    """Where one template variable gets its value for a given recipient.

    kind:
      column     — a header from the uploaded sheet, read per recipient
      restaurant — a field of the sending restaurant, resolved once at creation
                   so a campaign for Fielia Soraia can never carry another
                   restaurant's name
      contact    — the recipient's detected name, independent of the sheet's
                   column naming
      fixed      — one value typed once, identical for everyone

    `fallback` fills in when the resolved value is blank. Meta counts
    parameters, so a missing one fails the whole send with error 132000 rather
    than sending a gappy message.
    """

    kind: Literal["column", "restaurant", "contact", "fixed"]
    column: str | None = None
    field: str | None = None
    value: str | None = None
    fallback: str | None = None


class CampaignCreate(BaseModel):
    restaurant_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    template_id: str = Field(min_length=1)
    template_name: str = Field(min_length=1)
    template_variables: dict = Field(default_factory=dict)
    # Per-variable sources. Supersedes template_variables where both name the
    # same variable; template_variables alone is still accepted so an older
    # client keeps working.
    variable_sources: dict[str, VariableSource] = Field(default_factory=dict)
    media_url: str | None = None
    # Header media kind ("image"/"video"/"document"), derived server-side from
    # the template's HEADER format so the Meta send uses the matching parameter.
    media_type: str | None = None
    personalization: CampaignPersonalization | None = None
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
                raise ValueError(
                    "retry_until cannot be more than 30 days in the future"
                )
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
    contact_file_ref: str | None = None  # Override parent — optional for retries

    @validator("retry_until")
    @classmethod
    def validate_retry_until(cls, v):
        # Override parent's strict-future check for auto-generated campaigns
        # near the deadline. We use the exact same method name to trigger override.
        if v is not None:
            now = datetime.now(timezone.utc)
            cmp_v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if cmp_v > now + timedelta(days=30):
                raise ValueError(
                    "retry_until cannot be more than 30 days in the future"
                )
        return v


class CampaignPauseReason(BaseModel):
    """Why a campaign was parked, when the send path did it rather than a human.

    `message` is Meta's own wording, passed through untouched so the dashboard
    can show the operator exactly what WhatsApp Manager shows.
    """

    code: str
    summary: str
    message: str
    template_name: str | None = None
    paused_at: datetime | None = None
    auto: bool = True


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
    pause_reason: CampaignPauseReason | None = None


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
