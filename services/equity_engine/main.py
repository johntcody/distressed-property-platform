"""Equity Engine Service — estimates owner equity and persists results."""

from __future__ import annotations

from services.config import get_db_url
from api.deps import require_auth
from api.middleware import add_rate_limiting

import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Depends

from .calculator import EquityCalculator, EquityInputs
from .models import (
    EquityHistoryItem,
    EquityHistoryResponse,
    EquityRequest,
    EquityResponse,
)

_DEFAULT_ANNUAL_RATE = 0.07
_DEFAULT_TERM_MONTHS = 360

_calculator = EquityCalculator()
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


app = FastAPI(title="Equity Engine", version="1.0.0", lifespan=lifespan, dependencies=[Depends(require_auth)
add_rate_limiting(app)])


# ── helpers ────────────────────────────────────────────────────────────────────

async def _fetch_equity_inputs(
    pool: asyncpg.Pool, property_id: UUID
) -> tuple[EquityInputs, bool]:
    """Build EquityInputs from DB signals.

    Returns (inputs, property_exists). Callers must check the bool and raise
    404 if False — this avoids a second round-trip to the properties table.
    """

    # AVM stub: CAD assessed value (land + improvement).
    # Also serves as the existence + soft-delete check.
    prop = await pool.fetchrow(
        """
        SELECT land_value, improvement_value
        FROM   properties
        WHERE  id = $1 AND deleted_at IS NULL
        """,
        property_id,
    )
    if prop is None:
        return EquityInputs(avm=0.0), False

    # AVM: prefer the most recent Estated valuation; fall back to CAD assessed value
    # when no valuation exists yet (new ingestions, Estated not yet called).
    valuation_row = await pool.fetchrow(
        """
        SELECT avm
        FROM   valuations
        WHERE  property_id = $1
          AND  avm IS NOT NULL
        ORDER  BY valuation_date DESC NULLS LAST, calculated_at DESC
        LIMIT  1
        """,
        property_id,
    )
    if valuation_row and valuation_row["avm"]:
        avm = float(valuation_row["avm"])
    else:
        land = float(prop["land_value"] or 0)
        improvement = float(prop["improvement_value"] or 0)
        avm = land + improvement

    # Most-recent loan amount from any distress event
    loan_row = await pool.fetchrow(
        """
        SELECT loan_amount, filing_date
        FROM   events
        WHERE  property_id = $1
          AND  loan_amount IS NOT NULL
          AND  loan_amount > 0
        ORDER  BY filing_date DESC NULLS LAST
        LIMIT  1
        """,
        property_id,
    )
    original_loan_amount: Optional[float] = None
    months_elapsed: int = 0
    if loan_row and loan_row["loan_amount"]:
        original_loan_amount = float(loan_row["loan_amount"])
        if loan_row["filing_date"]:
            fd = loan_row["filing_date"]
            filing = fd if isinstance(fd, date) else fd.date()
            delta = date.today() - filing
            months_elapsed = max(int(delta.days / 30.44), 0)

    # Total outstanding tax owed.
    # Deduplicate on dedup_key to avoid double-counting re-ingested events;
    # fall back to the raw amount for rows where dedup_key is NULL.
    tax_row = await pool.fetchrow(
        """
        SELECT COALESCE(SUM(tax_amount_owed), 0) AS tax_owed
        FROM (
            SELECT DISTINCT ON (COALESCE(dedup_key, id::text)) tax_amount_owed
            FROM   events
            WHERE  property_id = $1
              AND  event_type = 'tax_delinquency'
              AND  tax_amount_owed IS NOT NULL
            ORDER  BY COALESCE(dedup_key, id::text), filing_date DESC NULLS LAST
        ) deduped
        """,
        property_id,
    )
    tax_owed = float(tax_row["tax_owed"])

    return EquityInputs(
        avm=avm,
        original_loan_amount=original_loan_amount,
        annual_rate=_DEFAULT_ANNUAL_RATE,
        term_months=_DEFAULT_TERM_MONTHS,
        months_elapsed=months_elapsed,
        tax_owed=tax_owed,
    ), True


async def _persist_equity(
    pool: asyncpg.Pool,
    property_id: UUID,
    result,
    calculated_at: datetime,
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO property_scores (
            property_id, avm, estimated_liens, tax_owed,
            equity_amount, equity_pct, score_version, calculated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        property_id,
        result.avm,
        result.estimated_loan_balance,
        result.tax_owed,
        result.equity_amount,
        result.equity_pct,
        result.calculator_version,
        calculated_at,
    )
    return row["id"]


# ── endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "equity-engine"}


@app.post("/api/v1/equity/{property_id}", response_model=EquityResponse)
async def calculate_equity(property_id: UUID, body: EquityRequest = EquityRequest()):
    """Compute equity for a property and persist it."""
    pool = app.state.pool

    inputs, exists = await _fetch_equity_inputs(pool, property_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    # Apply caller overrides
    if body.avm is not None:
        inputs.avm = body.avm
    if body.original_loan_amount is not None:
        inputs.original_loan_amount = body.original_loan_amount
    if body.annual_rate is not None:
        inputs.annual_rate = body.annual_rate
    if body.term_months is not None:
        inputs.term_months = body.term_months
    if body.months_elapsed is not None:
        inputs.months_elapsed = body.months_elapsed
    if body.tax_owed is not None:
        inputs.tax_owed = body.tax_owed

    result = _calculator.calculate(inputs)
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_equity(pool, property_id, result, calculated_at)

    return EquityResponse(
        property_id=property_id,
        avm=result.avm,
        estimated_loan_balance=result.estimated_loan_balance,
        tax_owed=result.tax_owed,
        equity_amount=result.equity_amount,
        equity_pct=result.equity_pct,
        calculator_version=result.calculator_version,
        calculated_at=calculated_at,
    )


@app.get("/api/v1/equity/{property_id}", response_model=EquityResponse)
async def get_latest_equity(property_id: UUID):
    """Return the most-recent equity calculation for a property."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL", property_id
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    # Query property_scores directly so the equity_amount IS NOT NULL filter
    # is applied before ORDER BY, not after DISTINCT ON in the shared view.
    # The shared view picks the latest row overall; if that row is a
    # distress-only score, equity_amount would be NULL and we'd get a false 404.
    row = await pool.fetchrow(
        """
        SELECT id, avm, estimated_liens, tax_owed, equity_amount,
               equity_pct, score_version, calculated_at
        FROM   property_scores
        WHERE  property_id = $1
          AND  equity_amount IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Property exists but has not been scored yet")

    return EquityResponse(
        property_id=property_id,
        avm=float(row["avm"] or 0),
        estimated_loan_balance=float(row["estimated_liens"] or 0),
        tax_owed=float(row["tax_owed"] or 0),
        equity_amount=float(row["equity_amount"] or 0),
        equity_pct=float(row["equity_pct"]) if row["equity_pct"] is not None else None,
        calculator_version=row["score_version"],
        calculated_at=row["calculated_at"],
    )


@app.get("/api/v1/equity/{property_id}/history", response_model=EquityHistoryResponse)
async def get_equity_history(
    property_id: UUID,
    limit: int = Query(50, ge=1, le=500),
):
    """Return equity history for a property (newest first)."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL", property_id
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    rows = await pool.fetch(
        """
        SELECT id, avm, estimated_liens, tax_owed, equity_amount,
               equity_pct, score_version, calculated_at
        FROM   property_scores
        WHERE  property_id = $1
          AND  equity_amount IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  $2
        """,
        property_id,
        limit,
    )

    items = [
        EquityHistoryItem(
            id=row["id"],
            avm=float(row["avm"]) if row["avm"] is not None else None,
            estimated_loan_balance=float(row["estimated_liens"]) if row["estimated_liens"] is not None else None,
            tax_owed=float(row["tax_owed"]) if row["tax_owed"] is not None else None,
            equity_amount=float(row["equity_amount"]) if row["equity_amount"] is not None else None,
            equity_pct=float(row["equity_pct"]) if row["equity_pct"] is not None else None,
            calculator_version=row["score_version"],
            calculated_at=row["calculated_at"],
        )
        for row in rows
    ]

    return EquityHistoryResponse(property_id=property_id, history=items)
