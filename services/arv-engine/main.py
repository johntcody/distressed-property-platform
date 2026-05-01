"""ARV Engine — estimates After-Repair Value using comparable sales."""

from fastapi import FastAPI, APIRouter, HTTPException
from .arv import ARVCalculator

app = FastAPI(title="ARV Engine", version="0.1.0")
router = APIRouter()
calculator = ARVCalculator()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "arv-engine"}


@router.post("/arv/{property_id}")
async def estimate_arv(property_id: str):
    # TODO: fetch comps and compute ARV
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(router, prefix="/api/v1")
