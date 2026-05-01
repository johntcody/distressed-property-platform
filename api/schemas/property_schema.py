"""Shared property schema for API layer."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class DistressType(str, Enum):
    foreclosure = "foreclosure"
    tax_delinquency = "tax_delinquency"
    probate = "probate"
    preforeclosure = "preforeclosure"


class PropertyResponse(BaseModel):
    id: str
    address: str
    city: str
    county: str
    state: str
    zip_code: str
    distress_type: DistressType
    distress_score: Optional[float] = None
    arv: Optional[float] = None
    mao: Optional[float] = None
    created_at: datetime
