"""Pydantic schemas for the ARV engine API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ARVRequest(BaseModel):
    """Optional subject-property overrides for on-demand ARV calculation."""
    sqft: Optional[float] = Field(None, gt=0, description="Living area in sq ft")
    beds: Optional[int]   = Field(None, ge=0, description="Bedroom count")
    baths: Optional[float] = Field(None, ge=0, description="Bathroom count")


class ARVResponse(BaseModel):
    property_id: UUID
    arv: Optional[float] = Field(None, description="After-Repair Value in USD; null when no comps")
    arv_confidence: float = Field(description="Confidence score 0–100")
    comp_count: int       = Field(description="Number of filtered comps used")
    method: str           = Field(description="Calculation method identifier")
    arv_version: str
    calculated_at: datetime


class ARVHistoryItem(BaseModel):
    id: UUID
    arv: Optional[float]
    arv_confidence: Optional[float]
    comp_count: Optional[int]
    method: Optional[str]
    calculated_at: datetime


class ARVHistoryResponse(BaseModel):
    property_id: UUID
    history: list[ARVHistoryItem]
