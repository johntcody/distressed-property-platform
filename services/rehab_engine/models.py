"""Pydantic schemas for the rehab engine API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RehabRequest(BaseModel):
    """Optional overrides for an on-demand rehab estimate."""
    rehab_level: Optional[str] = Field(
        None,
        description="Template to use: light | medium | heavy",
        pattern="^(light|medium|heavy)$",
    )
    sqft: Optional[float] = Field(None, gt=0, description="Living area in sq ft")
    overrides: Optional[dict[str, float]] = Field(
        None,
        description="Per-sqft cost overrides keyed by line-item name",
    )


class RehabResponse(BaseModel):
    property_id: UUID
    rehab_level: str
    sqft: float
    total_cost: float = Field(description="Estimated rehab cost in USD")
    cost_per_sqft: float
    line_items: dict[str, float] = Field(description="Per-item cost breakdown")
    rehab_version: str
    calculated_at: datetime


class RehabHistoryItem(BaseModel):
    id: UUID
    rehab_level: Optional[str]
    total_cost: Optional[float]
    cost_per_sqft: Optional[float]
    calculated_at: datetime


class RehabHistoryResponse(BaseModel):
    property_id: UUID
    history: list[RehabHistoryItem]
