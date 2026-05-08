"""Pydantic schemas for the MAO engine API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MAORequest(BaseModel):
    """All fields optional — defaults pulled from DB or calculator defaults."""
    arv:           Optional[float] = Field(None, gt=0,   description="Override ARV in USD")
    rehab_cost:    Optional[float] = Field(None, ge=0,   description="Override rehab cost in USD")
    discount_pct:  Optional[float] = Field(None, gt=0, le=100, description="Discount % of ARV (e.g. 70.0)")
    holding_costs: Optional[float] = Field(None, ge=0,   description="Holding costs in USD")
    closing_costs: Optional[float] = Field(None, ge=0,   description="Closing costs in USD")


class MAOResponse(BaseModel):
    property_id:   UUID
    arv:           float
    discount_pct:  float
    rehab_cost:    float
    holding_costs: float
    closing_costs: float
    mao:           float = Field(description="Maximum allowable offer in USD")
    mao_version:   str
    calculated_at: datetime


class MAOHistoryItem(BaseModel):
    id:            UUID
    arv_used:      Optional[float]
    discount_pct:  Optional[float]
    mao:           Optional[float]
    calculated_at: datetime


class MAOHistoryResponse(BaseModel):
    property_id: UUID
    history:     list[MAOHistoryItem]
