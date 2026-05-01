"""Distress Score Service — computes composite distress scores for properties."""

from fastapi import FastAPI
from fastapi import APIRouter, HTTPException
from .scorer import DistressScorer

app = FastAPI(title="Distress Score Service", version="0.1.0")
router = APIRouter()
scorer = DistressScorer()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "distress-score"}


@router.post("/score/{property_id}")
async def score_property(property_id: str):
    # TODO: fetch property data and compute distress score
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(router, prefix="/api/v1")
