"""Equity Engine — estimates owner equity position for distressed properties."""

from fastapi import FastAPI, APIRouter, HTTPException
from .calculator import EquityCalculator

app = FastAPI(title="Equity Engine", version="0.1.0")
router = APIRouter()
calculator = EquityCalculator()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "equity-engine"}


@router.post("/equity/{property_id}")
async def calculate_equity(property_id: str):
    # TODO: fetch appraisal value and lien data, compute equity
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(router, prefix="/api/v1")
