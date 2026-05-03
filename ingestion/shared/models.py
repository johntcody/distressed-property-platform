"""Shared Pydantic models for ingestion pipeline events."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DistressEventType(str, Enum):
    foreclosure = "foreclosure"
    tax_delinquency = "tax_delinquency"
    probate = "probate"
    preforeclosure = "preforeclosure"


class ForeclosureStage(str, Enum):
    NOD = "NOD"
    NTS = "NTS"
    auction = "auction"
    REO = "REO"


class NormalizedAddress(BaseModel):
    raw: str
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = "TX"
    zip_code: Optional[str] = None
    normalized: Optional[str] = None   # USPS-formatted canonical form
    confidence: float = 0.0            # 0.0–1.0


class PropertyRecord(BaseModel):
    apn: Optional[str] = None
    address: str
    address_norm: Optional[str] = None
    city: str
    county: str
    state: str = "TX"
    zip_code: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    owner_name: Optional[str] = None
    sqft: Optional[int] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    year_built: Optional[int] = None
    land_value: Optional[float] = None
    improvement_value: Optional[float] = None
    legal_description: Optional[str] = None


class ForeclosureEvent(BaseModel):
    county: str
    event_type: DistressEventType = DistressEventType.foreclosure
    filing_date: Optional[date] = None
    auction_date: Optional[date] = None
    foreclosure_stage: Optional[ForeclosureStage] = None
    borrower_name: Optional[str] = None
    lender_name: Optional[str] = None
    trustee_name: Optional[str] = None
    loan_amount: Optional[float] = None
    legal_description: Optional[str] = None
    address: Optional[str] = None
    source_url: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def dedup_key(self) -> Optional[str]:
        # Require at least filing_date and one identifying field to avoid collisions
        # on records where key source fields are missing.
        if not self.filing_date:
            return None
        borrower = (self.borrower_name or "").lower().strip()
        address = (self.address or "").lower().strip()
        if not borrower and not address:
            return None
        return "|".join([self.county, self.event_type.value, str(self.filing_date), borrower, address])


class TaxDelinquencyEvent(BaseModel):
    county: str
    event_type: DistressEventType = DistressEventType.tax_delinquency
    filing_date: Optional[date] = None
    owner_name: Optional[str] = None
    address: Optional[str] = None
    tax_amount_owed: Optional[float] = None
    years_delinquent: Optional[int] = None
    apn: Optional[str] = None
    source_url: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def dedup_key(self) -> Optional[str]:
        if not self.filing_date:
            return None
        identifier = (self.apn or self.address or "").lower().strip()
        if not identifier:
            return None
        return "|".join([self.county, self.event_type.value, str(self.filing_date), identifier])


class ProbateEvent(BaseModel):
    county: str
    event_type: DistressEventType = DistressEventType.probate
    filing_date: Optional[date] = None
    case_number: Optional[str] = None
    decedent_name: Optional[str] = None
    executor_name: Optional[str] = None
    address: Optional[str] = None
    source_url: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def dedup_key(self) -> Optional[str]:
        if not self.case_number or not self.case_number.strip():
            return None
        return "|".join([self.county, self.event_type.value, self.case_number.strip()])


class PreforeclosureEvent(BaseModel):
    county: str
    event_type: DistressEventType = DistressEventType.preforeclosure
    filing_date: Optional[date] = None
    borrower_name: Optional[str] = None
    lender_name: Optional[str] = None
    address: Optional[str] = None
    lp_instrument_number: Optional[str] = None
    lp_keywords: Optional[List[str]] = None
    legal_description: Optional[str] = None
    source_url: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def dedup_key(self) -> Optional[str]:
        instrument = (self.lp_instrument_number or "").strip()
        if not instrument and not self.filing_date:
            return None
        if not instrument:
            return None
        return "|".join([self.county, self.event_type.value, instrument, str(self.filing_date or "")])
