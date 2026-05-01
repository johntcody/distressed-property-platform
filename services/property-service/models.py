"""Property data models."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class DistressType(str, Enum):
    foreclosure = "foreclosure"
    tax_delinquency = "tax_delinquency"
    probate = "probate"
    preforeclosure = "preforeclosure"


class Property(BaseModel):
    id: str
    address: str
    city: str
    county: str
    state: str = "TX"
    zip_code: str
    distress_type: DistressType
    owner_name: Optional[str] = None
    parcel_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # TODO: add appraisal value, lot size, year built, sqft


class PropertyCreate(BaseModel):
    address: str
    city: str
    county: str
    zip_code: str
    distress_type: DistressType
    owner_name: Optional[str] = None
    parcel_id: Optional[str] = None
