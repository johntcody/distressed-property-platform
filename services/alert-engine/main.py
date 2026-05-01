"""Alert Engine — sends notifications when high-score properties are detected."""

from fastapi import FastAPI, APIRouter, HTTPException
from .notifier import AlertNotifier

app = FastAPI(title="Alert Engine", version="0.1.0")
router = APIRouter()
notifier = AlertNotifier()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "alert-engine"}


@router.post("/alerts/trigger")
async def trigger_alert(property_id: str, score: float):
    # TODO: evaluate alert rules, dispatch to configured channels
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/alerts")
async def list_alerts():
    # TODO: return recent alert history
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(router, prefix="/api/v1")
