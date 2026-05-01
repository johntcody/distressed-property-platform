"""Gateway routes — Alerts."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/alerts")
async def list_alerts():
    # TODO: proxy to alert-engine
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/alerts/subscribe")
async def subscribe_alert(county: str, min_score: float, channel: str):
    # TODO: register alert subscription in alert-engine
    raise HTTPException(status_code=501, detail="Not implemented")
