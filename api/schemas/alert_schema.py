"""Alert schema."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class Alert(BaseModel):
    alert_id: str
    property_id: str
    trigger_score: float
    channel: str
    sent_at: datetime
    acknowledged: bool = False


class AlertSubscription(BaseModel):
    county: str
    min_distress_score: float
    channel: str
    contact: str
    # TODO: add per-user subscription management
