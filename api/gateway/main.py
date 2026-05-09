"""API Gateway / BFF — unified entry point for all platform services."""

from fastapi import Depends, FastAPI

from api.deps import require_auth
from api.middleware import add_rate_limiting
from .routes.properties import router as properties_router
from .routes.opportunities import router as opportunities_router
from .routes.alerts import router as alerts_router

app = FastAPI(
    title="Distressed Property Platform API Gateway",
    version="0.1.0",
    dependencies=[Depends(require_auth)],
)
add_rate_limiting(app)

app.include_router(properties_router, prefix="/api/v1")
app.include_router(opportunities_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}
