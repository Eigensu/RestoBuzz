from pydantic import BaseModel
from typing import Literal
from datetime import datetime


SuppressionReason = Literal["opt_out", "blocked", "bounce"]


class SuppressionCreate(BaseModel):
    phone: str
    reason: SuppressionReason = "blocked"


class SuppressionResponse(BaseModel):
    id: str
    phone: str
    reason: SuppressionReason
    added_by: str | None
    added_at: datetime
