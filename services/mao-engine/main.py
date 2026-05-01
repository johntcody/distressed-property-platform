"""MAO Engine — computes Maximum Allowable Offer."""

from fastapi import FastAPI, APIRouter, HTTPException
from .calculator import MAOCalculator

app = FastAPI(title="MAO Engine", version="0.1.0")
router = APIRouter()
calculator = MAOCalculator()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mao-engine"}


@router.post("/mao/{property_id}")
async def calculate_mao(property_id: str):
    # TODO: fetch ARV and rehab estimate, apply MAO formula
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(router, prefix="/api/v1")
