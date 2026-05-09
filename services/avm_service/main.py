"""AVM Service — fetches and caches Automated Valuation Model data from Estated."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends

from services.config import get_db_url
from api.deps import require_auth
from api.middleware import add_rate_limiting
from .client import get_avm
from .models import AvmRequest, AvmResponse

_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    dsn = get_db_url()
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10, command_timeout=30)
    app.state.pool = _pool
    yield
    await _pool.close()
    _pool = None


app = FastAPI(title="AVM Service", version="1.0.0", lifespan=lifespan, dependencies=[Depends(require_auth)
add_rate_limiting(app)])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "avm-service"}


@app.post("/api/v1/avm/{property_id}", response_model=AvmResponse)
async def fetch_avm(property_id: UUID, body: AvmRequest):
    """Fetch or refresh an AVM for a property.

    Returns a cached valuation when one exists and is younger than
    AVM_MAX_AGE_DAYS (default 60).  Set force_refresh=true to bypass.
    """
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    try:
        result = await get_avm(
            pool=pool,
            property_id=property_id,
            address=body.address,
            city=body.city,
            state=body.state,
            zip_code=body.zip_code,
            force_refresh=body.force_refresh,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AVM provider error: {exc.response.status_code}",
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"AVM provider unreachable: {exc}")

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="No AVM provider configured. Set AVM_PROVIDER=attom and ATTOM_API_KEY.",
        )

    return AvmResponse(
        property_id=property_id,
        avm=result.avm,
        confidence_score=result.confidence_score,
        valuation_date=result.valuation_date,
        provider=result.provider,
        from_cache=result.from_cache,
        calculated_at=datetime.now(tz=timezone.utc),
    )


@app.get("/api/v1/avm/{property_id}/latest", response_model=AvmResponse)
async def get_latest_avm(property_id: UUID):
    """Return the most recent stored valuation for a property (no API call)."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    row = await pool.fetchrow(
        """
        SELECT avm, confidence_score, valuation_date, provider, calculated_at
        FROM   valuations
        WHERE  property_id = $1
          AND  avm IS NOT NULL
        ORDER  BY valuation_date DESC NULLS LAST, calculated_at DESC
        LIMIT  1
        """,
        property_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No AVM valuation found for this property")

    return AvmResponse(
        property_id=property_id,
        avm=float(row["avm"]),
        confidence_score=float(row["confidence_score"]) if row["confidence_score"] is not None else None,
        valuation_date=row["valuation_date"],
        provider=row["provider"] or "estated",
        from_cache=True,
        calculated_at=row["calculated_at"],
    )
