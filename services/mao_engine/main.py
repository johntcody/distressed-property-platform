"""MAO Engine — computes and persists Maximum Allowable Offer calculations."""

from __future__ import annotations

from services.config import get_db_url
from api.deps import require_auth
from api.middleware import add_rate_limiting

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Depends

from .calculator import MAOCalculator, MAOInputs, MAOResult
from .models import MAOHistoryItem, MAOHistoryResponse, MAORequest, MAOResponse

_calculator = MAOCalculator()
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


app = FastAPI(title="MAO Engine", version="1.0.0", lifespan=lifespan, dependencies=[Depends(require_auth)
add_rate_limiting(app)])


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fetch_inputs(
    pool: asyncpg.Pool,
    property_id: UUID,
    overrides: MAORequest,
) -> tuple[MAOInputs, bool]:
    """Build MAOInputs from latest DB values + caller overrides.

    ARV: pulled from valuations (latest row with arv_confidence IS NOT NULL).
    Rehab: pulled from analysis (latest row with record_type='rehab').
    Returns (inputs, property_exists).
    """
    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        return MAOInputs(arv=0, rehab_cost=0), False

    # Fetch ARV and rehab concurrently
    arv_row, rehab_row = await asyncio.gather(
        pool.fetchrow(
            """
            SELECT arv FROM valuations
            WHERE  property_id = $1 AND arv_confidence IS NOT NULL
            ORDER  BY calculated_at DESC LIMIT 1
            """,
            property_id,
        ),
        pool.fetchrow(
            """
            SELECT rehab_cost FROM analysis
            WHERE  property_id = $1
              AND  record_type  = 'rehab'
              AND  rehab_cost  IS NOT NULL
            ORDER  BY calculated_at DESC LIMIT 1
            """,
            property_id,
        ),
    )

    arv = float(
        overrides.arv
        if overrides.arv is not None
        else (arv_row["arv"] if arv_row and arv_row["arv"] is not None else 0)
    )
    rehab_cost = float(
        overrides.rehab_cost
        if overrides.rehab_cost is not None
        else (rehab_row["rehab_cost"] if rehab_row and rehab_row["rehab_cost"] is not None else 0)
    )
    discount_pct  = overrides.discount_pct  if overrides.discount_pct  is not None else 70.0
    holding_costs = overrides.holding_costs if overrides.holding_costs is not None else 0.0
    closing_costs = overrides.closing_costs if overrides.closing_costs is not None else 0.0

    return MAOInputs(
        arv=arv,
        rehab_cost=rehab_cost,
        discount_pct=discount_pct,
        holding_costs=holding_costs,
        closing_costs=closing_costs,
    ), True


async def _persist_mao(
    pool: asyncpg.Pool,
    property_id: UUID,
    result: MAOResult,
    calculated_at: datetime,
) -> None:
    await pool.execute(
        """
        INSERT INTO analysis
            (property_id, record_type, rehab_level, arv_used, discount_pct,
             rehab_cost, holding_costs, closing_costs, mao, mao_version, calculated_at)
        VALUES ($1, 'mao', NULL, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        property_id,
        result.arv,
        result.discount_pct,
        result.rehab_cost,
        result.holding_costs,
        result.closing_costs,
        result.mao,
        result.mao_version,
        calculated_at,
    )


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mao-engine"}


@app.post("/api/v1/mao/{property_id}", response_model=MAOResponse)
async def calculate_mao(
    property_id: UUID,
    body: Optional[MAORequest] = None,
):
    """Compute a MAO estimate for a property and persist it."""
    pool = app.state.pool
    req = body or MAORequest()

    inputs, exists = await _fetch_inputs(pool, property_id, req)
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    if inputs.arv == 0:
        raise HTTPException(
            status_code=422,
            detail="No ARV on record for this property; run arv-engine first or supply arv in the request body",
        )
    if inputs.rehab_cost == 0 and req.rehab_cost is None:
        raise HTTPException(
            status_code=422,
            detail="No rehab estimate on record for this property; run rehab-engine first or supply rehab_cost in the request body",
        )

    try:
        result = _calculator.calculate(inputs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_mao(pool, property_id, result, calculated_at)

    return MAOResponse(
        property_id=property_id,
        arv=result.arv,
        discount_pct=result.discount_pct,
        rehab_cost=result.rehab_cost,
        holding_costs=result.holding_costs,
        closing_costs=result.closing_costs,
        mao=result.mao,
        mao_version=result.mao_version,
        calculated_at=calculated_at,
    )


@app.get("/api/v1/mao/{property_id}", response_model=MAOResponse)
async def get_latest_mao(property_id: UUID):
    """Return the most recent MAO calculation for a property."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    row = await pool.fetchrow(
        """
        SELECT arv_used, discount_pct, rehab_cost, holding_costs,
               closing_costs, mao, mao_version, calculated_at
        FROM   analysis
        WHERE  property_id = $1
          AND  record_type  = 'mao'
          AND  mao          IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Property exists but has not been MAO-calculated yet",
        )

    return MAOResponse(
        property_id=property_id,
        arv=float(row["arv_used"]),
        discount_pct=float(row["discount_pct"]),
        rehab_cost=float(row["rehab_cost"]) if row["rehab_cost"] is not None else 0.0,
        holding_costs=float(row["holding_costs"]) if row["holding_costs"] is not None else 0.0,
        closing_costs=float(row["closing_costs"]) if row["closing_costs"] is not None else 0.0,
        mao=float(row["mao"]),
        mao_version=row["mao_version"],
        calculated_at=row["calculated_at"],
    )


@app.get(
    "/api/v1/mao/{property_id}/history",
    response_model=MAOHistoryResponse,
)
async def get_mao_history(
    property_id: UUID,
    limit: int = Query(50, ge=1, le=500),
):
    """Return MAO calculation history for a property (newest first)."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    rows = await pool.fetch(
        """
        SELECT id, arv_used, discount_pct, mao, calculated_at
        FROM   analysis
        WHERE  property_id = $1
          AND  record_type  = 'mao'
          AND  mao          IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  $2
        """,
        property_id,
        limit,
    )

    items = [
        MAOHistoryItem(
            id=row["id"],
            arv_used=float(row["arv_used"])         if row["arv_used"]     is not None else None,
            discount_pct=float(row["discount_pct"]) if row["discount_pct"] is not None else None,
            mao=float(row["mao"])                   if row["mao"]          is not None else None,
            calculated_at=row["calculated_at"],
        )
        for row in rows
    ]

    return MAOHistoryResponse(property_id=property_id, history=items)
