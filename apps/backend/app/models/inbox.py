from pydantic import BaseModel
from typing import Literal
from datetime import datetime


MessageType = Literal[
    "text",
    "image",
    "document",
    "location",
    "sticker",
    "interactive",
    "button",
    "audio",
    "video",
    "unknown",
]
Direction = Literal["inbound", "outbound"]


class LocationData(BaseModel):
    lat: float
    lng: float
    name: str | None = None


class InboundMessageResponse(BaseModel):
    id: str
    wa_message_id: str
    from_phone: str
    sender_name: str | None
    message_type: MessageType
    body: str | None
    media_url: str | None
    media_mime_type: str | None
    location: LocationData | None
    is_read: bool
    received_at: datetime
    direction: Direction = "inbound"
    status: Literal["sent", "delivered", "read", "failed"] | None = None


class ConversationResponse(BaseModel):
    from_phone: str
    sender_name: str | None
    last_message: str | None
    last_message_type: MessageType
    unread_count: int
    last_received_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class ReplyRequest(BaseModel):
    body: str
