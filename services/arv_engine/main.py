"""ARV Engine — computes and persists After-Repair Value from comparable sales."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Query

from .arv import ARVCalculator, SubjectProperty
from .models import ARVHistoryItem, ARVHistoryResponse, ARVRequest, ARVResponse

_calculator = ARVCalculator()
_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    dsn = os.environ.get("DATABASE_URL")
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10, command_timeout=30)
    app.state.pool = _pool
    yield
    await _pool.close()
    _pool = None


app = FastAPI(title="ARV Engine", version="1.0.0", lifespan=lifespan)


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

    sqft  = float(overrides.sqft  or row["sqft"]  or 0)
    beds  = int(  overrides.beds  or row["beds"]  or 0)
    baths = float(overrides.baths or row["baths"] or 0)

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
    result,
    calculated_at: datetime,
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO valuations
            (property_id, arv, arv_confidence, comp_count, method, calculated_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        property_id,
        result.arv,
        result.arv_confidence,
        result.comp_count,
        result.method,
        calculated_at,
    )
    return row["id"]


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "arv-engine"}


@app.post("/api/v1/arv/{property_id}", response_model=ARVResponse)
async def calculate_arv(
    property_id: UUID,
    body: ARVRequest = ARVRequest(),
):
    """Compute ARV for a property and persist it to valuations."""
    pool = app.state.pool

    subject, exists = await _fetch_subject(pool, property_id, body)
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    if subject.sqft == 0:
        raise HTTPException(
            status_code=422,
            detail="Property has no sqft on record; supply sqft in the request body",
        )

    result = _calculator.estimate(subject)
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
        SELECT id, arv, arv_confidence, comp_count, method, calculated_at
        FROM   valuations
        WHERE  property_id = $1
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
        arv_version="1.0",
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
