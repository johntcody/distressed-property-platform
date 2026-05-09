"""Rehab Engine — estimates and persists property rehab costs."""

from __future__ import annotations

from services.config import get_db_url

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Query

from .estimator import RehabEstimator, RehabInputs, RehabResult
from .models import RehabHistoryItem, RehabHistoryResponse, RehabRequest, RehabResponse

_estimator = RehabEstimator()
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


app = FastAPI(title="Rehab Engine", version="1.0.0", lifespan=lifespan)


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fetch_inputs(
    pool: asyncpg.Pool, property_id: UUID, overrides: RehabRequest
) -> tuple[RehabInputs, bool]:
    """Build RehabInputs from DB + caller overrides.

    Returns (inputs, property_exists).
    """
    row = await pool.fetchrow(
        "SELECT sqft FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if row is None:
        return RehabInputs(sqft=0), False

    sqft = float(overrides.sqft if overrides.sqft is not None else (row["sqft"] or 0))
    rehab_level = overrides.rehab_level if overrides.rehab_level is not None else "medium"
    item_overrides = overrides.overrides or {}

    return RehabInputs(sqft=sqft, rehab_level=rehab_level, overrides=item_overrides), True


async def _persist_rehab(
    pool: asyncpg.Pool,
    property_id: UUID,
    result: RehabResult,
    calculated_at: datetime,
) -> None:
    await pool.execute(
        """
        INSERT INTO analysis
            (property_id, record_type, rehab_level, rehab_cost, rehab_cost_sqft,
             notes, calculated_at)
        VALUES ($1, 'rehab', $2, $3, $4, $5, $6)
        """,
        property_id,
        result.rehab_level,
        result.total_cost,
        result.cost_per_sqft,
        json.dumps({
            "sqft": result.sqft,
            "line_items": result.line_items,
            "rehab_version": result.rehab_version,
        }),
        calculated_at,
    )


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "rehab-engine"}


@app.post("/api/v1/rehab/{property_id}", response_model=RehabResponse)
async def calculate_rehab(
    property_id: UUID,
    body: Optional[RehabRequest] = None,
):
    """Compute a rehab cost estimate for a property and persist it."""
    pool = app.state.pool

    inputs, exists = await _fetch_inputs(pool, property_id, body or RehabRequest())
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    if inputs.sqft == 0:
        raise HTTPException(
            status_code=422,
            detail="Property has no sqft on record; supply sqft in the request body",
        )

    try:
        result = _estimator.estimate(inputs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_rehab(pool, property_id, result, calculated_at)

    return RehabResponse(
        property_id=property_id,
        rehab_level=result.rehab_level,
        sqft=result.sqft,
        total_cost=result.total_cost,
        cost_per_sqft=result.cost_per_sqft,
        line_items=result.line_items,
        rehab_version=result.rehab_version,
        calculated_at=calculated_at,
    )


@app.get("/api/v1/rehab/{property_id}", response_model=RehabResponse)
async def get_latest_rehab(property_id: UUID):
    """Return the most recent rehab estimate for a property."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    row = await pool.fetchrow(
        """
        SELECT id, rehab_level, rehab_cost, rehab_cost_sqft, notes, calculated_at
        FROM   analysis
        WHERE  property_id = $1
          AND  record_type  = 'rehab'
          AND  rehab_cost  IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(
            status_code=404, detail="Property exists but has not been rehab-estimated yet"
        )

    try:
        notes = json.loads(row["notes"]) if row["notes"] else {}
    except json.JSONDecodeError:
        notes = {}

    return RehabResponse(
        property_id=property_id,
        rehab_level=row["rehab_level"] or "medium",
        sqft=float(notes.get("sqft", 0.0)),
        total_cost=float(row["rehab_cost"]),
        cost_per_sqft=float(row["rehab_cost_sqft"]) if row["rehab_cost_sqft"] else 0.0,
        line_items=notes.get("line_items", {}),
        rehab_version=notes.get("rehab_version", "1.0"),
        calculated_at=row["calculated_at"],
    )


@app.get(
    "/api/v1/rehab/{property_id}/history",
    response_model=RehabHistoryResponse,
)
async def get_rehab_history(
    property_id: UUID,
    limit: int = Query(50, ge=1, le=500),
):
    """Return rehab estimate history for a property (newest first)."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    rows = await pool.fetch(
        """
        SELECT id, rehab_level, rehab_cost, rehab_cost_sqft, calculated_at
        FROM   analysis
        WHERE  property_id = $1
          AND  record_type  = 'rehab'
          AND  rehab_cost  IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  $2
        """,
        property_id,
        limit,
    )

    items = [
        RehabHistoryItem(
            id=row["id"],
            rehab_level=row["rehab_level"],
            total_cost=float(row["rehab_cost"]) if row["rehab_cost"] is not None else None,
            cost_per_sqft=float(row["rehab_cost_sqft"]) if row["rehab_cost_sqft"] is not None else None,
            calculated_at=row["calculated_at"],
        )
        for row in rows
    ]

    return RehabHistoryResponse(property_id=property_id, history=items)
