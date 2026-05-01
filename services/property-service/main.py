"""Property Service — CRUD and lookup for distressed property records."""

from fastapi import FastAPI
from .routes import router

app = FastAPI(title="Property Service", version="0.1.0")
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "property-service"}
