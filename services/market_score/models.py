"""Pydantic schemas for the market score service API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MarketScoreRequest(BaseModel):
    """Optional signal overrides for on-demand recalculation."""
    appreciation_rate: Optional[float] = Field(
        None, ge=-1.0, le=10.0,
        description="YoY price appreciation as decimal (e.g. 0.05 = 5%)",
    )
    avg_days_on_market: Optional[float] = Field(
        None, ge=0,
        description="Average days on market for comparable properties",
    )
    rent_to_price_ratio: Optional[float] = Field(
        None, ge=0, le=10.0,
        description="Gross rent-to-price ratio as decimal (e.g. 0.07 = 7%)",
    )


class MarketScoreResponse(BaseModel):
    property_id: UUID
    zip_code: str
    market_score: float = Field(description="Overall market score 0–100")
    appreciation_score: float
    liquidity_score: float
    yield_score: float
    score_version: str
    calculated_at: datetime


class MarketScoreHistoryItem(BaseModel):
    id: UUID
    zip_code: Optional[str] = None
    market_score: Optional[float] = None
    score_version: str
    calculated_at: datetime


class MarketScoreHistoryResponse(BaseModel):
    property_id: UUID
    history: list[MarketScoreHistoryItem]
