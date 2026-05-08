"""Pydantic schemas for the Property Detail API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PropertyDetail(BaseModel):
    property_id:        UUID
    apn:                Optional[str]
    address_raw:        str
    address_norm:       Optional[str]
    city:               str
    county:             str
    state:              str
    zip_code:           str
    legal_description:  Optional[str]
    owner_name:         Optional[str]
    sqft:               Optional[int]
    bedrooms:           Optional[int]
    bathrooms:          Optional[float]
    year_built:         Optional[int]
    land_value:         Optional[float]
    improvement_value:  Optional[float]
    total_cad_value:    Optional[float]
    created_at:         datetime
    updated_at:         datetime
    # latest scores
    distress_score:     Optional[float]
    equity_pct:         Optional[float]
    equity_amount:      Optional[float]
    avm:                Optional[float]
    market_score:       Optional[float]
    estimated_liens:    Optional[float]
    tax_owed:           Optional[float]
    score_calculated_at: Optional[datetime]


class EventItem(BaseModel):
    event_id:            UUID
    event_type:          str
    county:              str
    filing_date:         Optional[date]
    auction_date:        Optional[date]
    foreclosure_stage:   Optional[str]
    borrower_name:       Optional[str]
    lender_name:         Optional[str]
    trustee_name:        Optional[str]
    loan_amount:         Optional[float]
    tax_amount_owed:     Optional[float]
    years_delinquent:    Optional[int]
    case_number:         Optional[str]
    source_url:          Optional[str]
    created_at:          datetime


class EventsResponse(BaseModel):
    property_id: UUID
    total:       int
    items:       list[EventItem]


class AnalysisItem(BaseModel):
    analysis_id:    UUID
    record_type:    str           # 'rehab' | 'mao'
    rehab_level:    Optional[str]
    rehab_cost:     Optional[float]
    rehab_cost_sqft: Optional[float]
    arv_used:       Optional[float]
    discount_pct:   Optional[float]
    holding_costs:  Optional[float]
    closing_costs:  Optional[float]
    mao:            Optional[float]
    mao_version:    Optional[str]
    notes:          Optional[str]
    calculated_at:  datetime
    # joined from valuations
    valuation_arv:  Optional[float]
    arv_confidence: Optional[float]
    comp_count:     Optional[int]
    method:         Optional[str]
    provider:       Optional[str]


class AnalysisResponse(BaseModel):
    property_id: UUID
    items:       list[AnalysisItem]


class ValuationItem(BaseModel):
    valuation_id:     UUID
    avm:              Optional[float]
    arv:              Optional[float]
    arv_confidence:   Optional[float]
    comp_count:       Optional[int]
    method:           Optional[str]
    provider:         Optional[str]
    confidence_score: Optional[float]
    valuation_date:   Optional[date]
    arv_version:      str
    calculated_at:    datetime


class ValuationsResponse(BaseModel):
    property_id:    UUID
    equity_pct:     Optional[float]
    equity_amount:  Optional[float]
    estimated_liens: Optional[float]
    tax_owed:       Optional[float]
    items:          list[ValuationItem]
