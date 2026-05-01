"""Gateway routes — Properties."""

from fastapi import APIRouter, HTTPException
import httpx

router = APIRouter()

PROPERTY_SERVICE_URL = "http://property-service:8001"


@router.get("/properties")
async def list_properties(county: str = None, distress_type: str = None, limit: int = 20):
    # TODO: proxy to property-service with query params
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/properties/{property_id}")
async def get_property(property_id: str):
    # TODO: proxy to property-service and enrich with scores
    raise HTTPException(status_code=501, detail="Not implemented")
