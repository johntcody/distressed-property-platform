"""Market Score Service — evaluates neighborhood and market conditions."""

from fastapi import FastAPI, APIRouter, HTTPException
from .scorer import MarketScorer

app = FastAPI(title="Market Score Service", version="0.1.0")
router = APIRouter()
scorer = MarketScorer()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "market-score"}


@router.post("/market-score/{property_id}")
async def score_market(property_id: str):
    # TODO: fetch comparable sales, days-on-market, price trends
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(router, prefix="/api/v1")
