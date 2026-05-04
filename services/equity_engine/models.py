"""Pydantic schemas for the equity-engine service API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EquityRequest(BaseModel):
    """Optional overrides for on-demand recalculation without a full DB fetch."""

    avm: Optional[float] = Field(None, ge=0, description="Automated valuation model override")
    original_loan_amount: Optional[float] = Field(None, ge=0)
    annual_rate: Optional[float] = Field(None, ge=0, le=1, description="Annual interest rate as decimal (e.g. 0.07)")
    term_months: Optional[int] = Field(None, gt=0, le=600)
    months_elapsed: Optional[int] = Field(None, ge=0)
    tax_owed: Optional[float] = Field(None, ge=0)


class EquityResponse(BaseModel):
    property_id: UUID
    avm: float
    estimated_loan_balance: float
    tax_owed: float
    equity_amount: float
    equity_pct: Optional[float] = Field(None, description="Equity % of AVM; null when AVM is zero")
    calculator_version: str
    calculated_at: datetime


class EquityHistoryItem(BaseModel):
    id: UUID
    avm: Optional[float] = None
    estimated_loan_balance: Optional[float] = None
    tax_owed: Optional[float] = None
    equity_amount: Optional[float] = None
    equity_pct: Optional[float] = None
    calculator_version: str
    calculated_at: datetime


class EquityHistoryResponse(BaseModel):
    property_id: UUID
    history: list[EquityHistoryItem]
