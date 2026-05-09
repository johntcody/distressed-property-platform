"""ARV Engine — computes and persists After-Repair Value from comparable sales."""

from __future__ import annotations

from services.config import get_db_url
from api.deps import require_auth
from api.middleware import add_rate_limiting

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Depends

from .arv import ARVCalculator, ARVResult, SubjectProperty
from .models import ARVHistoryItem, ARVHistoryResponse, ARVRequest, ARVResponse

_calculator = ARVCalculator()
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


app = FastAPI(title="ARV Engine", version="1.0.0", lifespan=lifespan, dependencies=[Depends(require_auth)])
add_rate_limiting(app)


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fetch_subject(
    pool: asyncpg.Pool, property_id: UUID, overrides: ARVRequest
) -> tuple[SubjectProperty, bool]:
    """Build SubjectProperty from DB + optional caller overrides.

    Returns (subject, property_exists).
    """
    row = await pool.fetchrow(
        """
        SELECT zip_code, sqft, beds, baths
        FROM   properties
        WHERE  id = $1 AND deleted_at IS NULL
        """,
        property_id,
    )
    if row is None:
        return SubjectProperty(property_id=str(property_id), sqft=0, beds=0, baths=0), False

    # Use is-not-None guards so explicit 0 overrides are honoured
    sqft  = float(overrides.sqft  if overrides.sqft  is not None else (row["sqft"]  or 0))
    beds  = int(  overrides.beds  if overrides.beds  is not None else (row["beds"]  or 0))
    baths = float(overrides.baths if overrides.baths is not None else (row["baths"] or 0))

    return SubjectProperty(
        property_id=str(property_id),
        sqft=sqft,
        beds=beds,
        baths=baths,
        zip_code=row["zip_code"] or "",
    ), True


async def _persist_arv(
    pool: asyncpg.Pool,
    property_id: UUID,
    result: ARVResult,
    calculated_at: datetime,
) -> None:
    await pool.execute(
        """
        INSERT INTO valuations
            (property_id, arv, arv_confidence, comp_count, method, arv_version, calculated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        property_id,
        result.arv,
        result.arv_confidence,
        result.comp_count,
        result.method,
        result.arv_version,
        calculated_at,
    )


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "arv-engine"}


@app.post("/api/v1/arv/{property_id}", response_model=ARVResponse)
async def calculate_arv(
    property_id: UUID,
    body: Optional[ARVRequest] = None,
):
    """Compute ARV for a property and persist it to valuations."""
    pool = app.state.pool

    subject, exists = await _fetch_subject(pool, property_id, body or ARVRequest())
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    if subject.sqft == 0:
        raise HTTPException(
            status_code=422,
            detail="Property has no sqft on record; supply sqft in the request body",
        )

    try:
        result = _calculator.estimate(subject)
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_arv(pool, property_id, result, calculated_at)

    return ARVResponse(
        property_id=property_id,
        arv=result.arv,
        arv_confidence=result.arv_confidence,
        comp_count=result.comp_count,
        method=result.method,
        arv_version=result.arv_version,
        calculated_at=calculated_at,
    )


@app.get("/api/v1/arv/{property_id}", response_model=ARVResponse)
async def get_latest_arv(property_id: UUID):
    """Return the most recent ARV valuation for a property."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    row = await pool.fetchrow(
        """
        SELECT id, arv, arv_confidence, comp_count, method, arv_version, calculated_at
        FROM   valuations
        WHERE  property_id = $1
          AND  arv_confidence IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(
            status_code=404, detail="Property exists but has not been ARV-calculated yet"
        )

    return ARVResponse(
        property_id=property_id,
        arv=float(row["arv"]) if row["arv"] is not None else None,
        arv_confidence=float(row["arv_confidence"]) if row["arv_confidence"] is not None else 0.0,
        comp_count=row["comp_count"] or 0,
        method=row["method"] or "price_per_sqft",
        arv_version=row["arv_version"] or "1.0",
        calculated_at=row["calculated_at"],
    )


@app.get(
    "/api/v1/arv/{property_id}/history",
    response_model=ARVHistoryResponse,
)
async def get_arv_history(
    property_id: UUID,
    limit: int = Query(50, ge=1, le=500),
):
    """Return ARV calculation history for a property (newest first)."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    rows = await pool.fetch(
        """
        SELECT id, arv, arv_confidence, comp_count, method, calculated_at
        FROM   valuations
        WHERE  property_id = $1
          AND  arv_confidence IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  $2
        """,
        property_id,
        limit,
    )

    items = [
        ARVHistoryItem(
            id=row["id"],
            arv=float(row["arv"]) if row["arv"] is not None else None,
            arv_confidence=float(row["arv_confidence"]) if row["arv_confidence"] is not None else None,
            comp_count=row["comp_count"],
            method=row["method"],
            calculated_at=row["calculated_at"],
        )
        for row in rows
    ]

    return ARVHistoryResponse(property_id=property_id, history=items)
