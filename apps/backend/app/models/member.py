from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

MemberType = Literal["nfc", "ecard"]


class MemberCreate(BaseModel):
    restaurant_id: str
    type: MemberType
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=7, max_length=20)
    email: str | None = None
    card_uid: str | None = None  # NFC chip UID
    ecard_code: str | None = None  # E-card code
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class MemberUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    card_uid: str | None = None
    ecard_code: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    is_active: bool | None = None


class MemberResponse(BaseModel):
    id: str
    restaurant_id: str
    type: MemberType
    name: str
    phone: str
    email: str | None
    card_uid: str | None
    ecard_code: str | None
    tags: list[str]
    notes: str | None
    visit_count: int
    last_visit: datetime | None
    is_active: bool
    joined_at: datetime


class MemberListResponse(BaseModel):
    items: list[MemberResponse]
    total: int
    page: int
    page_size: int
