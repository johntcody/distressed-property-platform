"""Market Score Service — computes and persists neighborhood market scores."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Query

from .models import (
    MarketScoreHistoryItem,
    MarketScoreHistoryResponse,
    MarketScoreRequest,
    MarketScoreResponse,
)
from .scorer import MarketInputs, MarketScorer

_scorer = MarketScorer()
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


app = FastAPI(title="Market Score Service", version="1.0.0", lifespan=lifespan)


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fetch_market_inputs(
    pool: asyncpg.Pool, property_id: UUID
) -> tuple[MarketInputs, bool]:
    """Build MarketInputs from DB signals.

    Returns (inputs, property_exists).  Callers must check the bool and raise
    404 if False.

    Signal sources
    --------------
    zip_code          — properties.zip_code
    appreciation_rate — stub: no live source yet; returns None (neutral sub-score)
    avg_days_on_market — stub: no live source yet; returns None (neutral sub-score)
    rent_to_price_ratio — stub: no live source yet; returns None (neutral sub-score)

    When a market data provider is integrated, replace the stubs here.
    """
    prop = await pool.fetchrow(
        "SELECT zip_code FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if prop is None:
        return MarketInputs(), False

    return MarketInputs(zip_code=prop["zip_code"] or ""), True


async def _persist_market_score(
    pool: asyncpg.Pool,
    property_id: UUID,
    result,
    calculated_at: datetime,
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO property_scores
            (property_id, market_score, score_version, calculated_at, raw_data)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        property_id,
        result.market_score,
        result.score_version,
        calculated_at,
        json.dumps(result.inputs_used),
    )
    return row["id"]


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "market-score"}


@app.post("/api/v1/market-score/{property_id}", response_model=MarketScoreResponse)
async def calculate_market_score(
    property_id: UUID,
    body: MarketScoreRequest = MarketScoreRequest(),
):
    """Compute a market score for a property and persist it."""
    pool = app.state.pool

    inputs, exists = await _fetch_market_inputs(pool, property_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    # Apply caller overrides
    if body.appreciation_rate is not None:
        inputs.appreciation_rate = body.appreciation_rate
    if body.avg_days_on_market is not None:
        inputs.avg_days_on_market = body.avg_days_on_market
    if body.rent_to_price_ratio is not None:
        inputs.rent_to_price_ratio = body.rent_to_price_ratio

    result = _scorer.score(inputs)
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_market_score(pool, property_id, result, calculated_at)

    return MarketScoreResponse(
        property_id=property_id,
        zip_code=result.zip_code,
        market_score=result.market_score,
        appreciation_score=result.appreciation_score,
        liquidity_score=result.liquidity_score,
        yield_score=result.yield_score,
        score_version=result.score_version,
        calculated_at=calculated_at,
    )


@app.get("/api/v1/market-score/{property_id}", response_model=MarketScoreResponse)
async def get_latest_market_score(property_id: UUID):
    """Return the most recent market score for a property."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    row = await pool.fetchrow(
        """
        SELECT id, market_score, score_version, calculated_at, raw_data
        FROM   property_scores
        WHERE  property_id = $1
          AND  market_score IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(
            status_code=404, detail="Property exists but has not been market-scored yet"
        )

    raw = json.loads(row["raw_data"]) if row["raw_data"] else {}

    return MarketScoreResponse(
        property_id=property_id,
        zip_code="",
        market_score=float(row["market_score"]),
        appreciation_score=0.0,
        liquidity_score=0.0,
        yield_score=0.0,
        score_version=row["score_version"],
        calculated_at=row["calculated_at"],
    )


@app.get(
    "/api/v1/market-score/{property_id}/history",
    response_model=MarketScoreHistoryResponse,
)
async def get_market_score_history(
    property_id: UUID,
    limit: int = Query(50, ge=1, le=500),
):
    """Return market score history for a property (newest first)."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL",
        property_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    rows = await pool.fetch(
        """
        SELECT id, market_score, score_version, calculated_at
        FROM   property_scores
        WHERE  property_id = $1
          AND  market_score IS NOT NULL
        ORDER  BY calculated_at DESC
        LIMIT  $2
        """,
        property_id,
        limit,
    )

    items = [
        MarketScoreHistoryItem(
            id=row["id"],
            market_score=float(row["market_score"]) if row["market_score"] is not None else None,
            score_version=row["score_version"],
            calculated_at=row["calculated_at"],
        )
        for row in rows
    ]

    return MarketScoreHistoryResponse(property_id=property_id, history=items)
