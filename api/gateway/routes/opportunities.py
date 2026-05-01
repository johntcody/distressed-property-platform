"""Gateway routes — Opportunities."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/opportunities")
async def list_opportunities(min_score: float = 70.0, limit: int = 20):
    """Return high-distress-score properties ranked as investment opportunities."""
    # TODO: query distress-score service, join with property data and MAO
    raise HTTPException(status_code=501, detail="Not implemented")
