from pydantic import BaseModel
from typing import Literal
from datetime import datetime


MessageStatus = Literal["queued", "sending", "sent", "delivered", "read", "failed"]
EndpointUsed = Literal["primary", "fallback"]


class StatusHistoryEntry(BaseModel):
    status: MessageStatus
    timestamp: datetime
    meta: dict = {}


class MessageLogResponse(BaseModel):
    id: str
    job_id: str
    recipient_phone: str
    recipient_name: str
    wa_message_id: str | None
    status: MessageStatus
    status_history: list[StatusHistoryEntry]
    retry_count: int
    endpoint_used: EndpointUsed | None
    fallback_used: bool
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class MessageLogListResponse(BaseModel):
    items: list[MessageLogResponse]
    total: int
    page: int
    page_size: int
