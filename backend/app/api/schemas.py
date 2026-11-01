
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RecoveryEvaluateRequest(BaseModel):
    cart_id: str = Field(min_length=1)
    channel: Literal["EMAIL", "SMS"]
    evaluated_at: datetime | None = None


class CampaignScheduleRequest(BaseModel):
    cart_id: str = Field(min_length=1)
    channel: Literal["EMAIL", "SMS"]
    send_id: str = Field(min_length=1)
    evaluated_at: datetime | None = None


class AttributionRequest(BaseModel):
    order_id: str = Field(min_length=1)
    attribution_id: str = Field(min_length=1)
