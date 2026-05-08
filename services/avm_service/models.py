"""Pydantic schemas for the AVM service API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AvmRequest(BaseModel):
    """Address fields needed to look up an AVM from Estated."""
    address: str = Field(..., description="Street address, e.g. '123 Main St'")
    city: str
    state: str = Field("TX", max_length=2)
    zip_code: str = Field("", description="5-digit ZIP code")
    force_refresh: bool = Field(
        False,
        description="Bypass cache and call Estated even if a fresh valuation exists",
    )


class AvmResponse(BaseModel):
    property_id: UUID
    avm: float
    confidence_score: Optional[float] = Field(
        None, description="Provider confidence 0–100; null when not supplied"
    )
    valuation_date: date
    provider: str
    from_cache: bool
    calculated_at: datetime
