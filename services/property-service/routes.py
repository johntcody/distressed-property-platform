"""Property Service routes."""

from fastapi import APIRouter, HTTPException
from typing import List
from .models import Property, PropertyCreate

router = APIRouter()


@router.get("/properties", response_model=List[Property])
async def list_properties(county: str = None, distress_type: str = None, limit: int = 20):
    # TODO: query database with filters
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/properties/{property_id}", response_model=Property)
async def get_property(property_id: str):
    # TODO: fetch property by ID from database
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/properties", response_model=Property, status_code=201)
async def create_property(payload: PropertyCreate):
    # TODO: persist new property record
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/properties/{property_id}", status_code=204)
async def delete_property(property_id: str):
    # TODO: soft-delete property record
    raise HTTPException(status_code=501, detail="Not implemented")
