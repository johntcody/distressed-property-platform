"""Pydantic schemas for the Opportunity Dashboard API."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

CaseType  = Literal["foreclosure", "tax_delinquency", "probate", "preforeclosure"]
SortField = Literal["distress_score", "equity_pct", "auction_date", "filing_date", "mao"]
SortDir   = Literal["asc", "desc"]


class OpportunityItem(BaseModel):
    property_id:       UUID
    address:           Optional[str]
    city:              Optional[str]
    county:            str
    zip_code:          str
    sqft:              Optional[int]
    bedrooms:          Optional[int]
    bathrooms:         Optional[float]
    year_built:        Optional[int]
    owner_name:        Optional[str]
    # scores
    distress_score:    Optional[float]
    equity_pct:        Optional[float]
    equity_amount:     Optional[float]
    avm:               Optional[float]
    # deal analysis
    arv:               Optional[float]
    mao:               Optional[float]
    # latest event
    event_type:        Optional[str]
    foreclosure_stage: Optional[str]
    filing_date:       Optional[date]
    auction_date:      Optional[date]


class OpportunitiesResponse(BaseModel):
    total:     int = Field(description="Total rows matching the applied filters")
    page:      int
    page_size: int
    items:     list[OpportunityItem]
