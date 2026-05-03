"""Pydantic schemas for the distress-score service API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ingestion.shared.models import ForeclosureStage


class ScoreRequest(BaseModel):
    """Optional overrides for on-demand rescoring without a full DB fetch."""

    foreclosure_stage: Optional[ForeclosureStage] = None
    years_delinquent: Optional[int] = Field(None, ge=0)
    has_active_probate: bool = False
    lp_filing_date: Optional[date] = None
    as_of: Optional[date] = Field(None, description="Override reference date (defaults to today)")


class ScoreResponse(BaseModel):
    property_id: UUID
    score: float = Field(description="Composite distress score 0–100")
    foreclosure_component: float
    tax_component: float
    preforeclosure_component: float
    probate_component: float
    score_version: str
    calculated_at: datetime


class ScoreHistoryItem(BaseModel):
    id: UUID
    score: float
    foreclosure_component: Optional[float] = None
    tax_component: Optional[float] = None
    preforeclosure_component: Optional[float] = None
    probate_component: Optional[float] = None
    score_version: str
    calculated_at: datetime


class ScoreHistoryResponse(BaseModel):
    property_id: UUID
    history: list[ScoreHistoryItem]
