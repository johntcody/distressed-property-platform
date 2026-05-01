"""Property event schema — represents distress events from ingestion pipelines."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PropertyEvent(BaseModel):
    event_id: str
    property_id: str
    event_type: str  # foreclosure | tax_delinquency | probate | preforeclosure
    source: str
    county: str
    raw_data: dict
    occurred_at: datetime
    ingested_at: datetime
    # TODO: add event-specific fields per distress type
