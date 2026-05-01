"""Rehab Engine — estimates repair and renovation costs."""

from fastapi import FastAPI, APIRouter, HTTPException
from .estimator import RehabEstimator

app = FastAPI(title="Rehab Engine", version="0.1.0")
router = APIRouter()
estimator = RehabEstimator()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rehab-engine"}


@router.post("/rehab/{property_id}")
async def estimate_rehab(property_id: str):
    # TODO: accept condition flags, compute line-item rehab estimate
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(router, prefix="/api/v1")
