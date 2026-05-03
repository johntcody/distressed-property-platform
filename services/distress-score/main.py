"""Distress Score Service — computes and persists composite distress scores."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException

from .models import ScoreHistoryItem, ScoreHistoryResponse, ScoreRequest, ScoreResponse
from .scorer import DistressScorer, DistressSignals

_scorer = DistressScorer()
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


app = FastAPI(title="Distress Score Service", version="1.0.0", lifespan=lifespan)


# ── helpers ────────────────────────────────────────────────────────────────────

async def _get_pool(request) -> asyncpg.Pool:
    return request.app.state.pool


async def _fetch_signals(pool: asyncpg.Pool, property_id: UUID) -> DistressSignals:
    """Query the events table and build a DistressSignals object."""
    rows = await pool.fetch(
        """
        SELECT event_type, foreclosure_stage, years_delinquent, filing_date
        FROM   events
        WHERE  property_id = $1
        ORDER  BY filing_date DESC NULLS LAST
        """,
        property_id,
    )

    signals = DistressSignals()

    for row in rows:
        etype = row["event_type"]

        if etype == "foreclosure" and signals.foreclosure_stage is None:
            signals.foreclosure_stage = row["foreclosure_stage"]

        elif etype == "tax_delinquency" and signals.years_delinquent is None:
            signals.years_delinquent = row["years_delinquent"]

        elif etype == "probate":
            signals.has_active_probate = True

        elif etype == "preforeclosure" and signals.lp_filing_date is None:
            fd = row["filing_date"]
            if fd:
                signals.lp_filing_date = fd if isinstance(fd, date) else fd.date()

    return signals


async def _persist_score(
    pool: asyncpg.Pool,
    property_id: UUID,
    result,
    calculated_at: datetime,
) -> UUID:
    """Insert a new row into property_scores and return its id."""
    row = await pool.fetchrow(
        """
        INSERT INTO property_scores (
            property_id, distress_score, score_version, calculated_at,
            raw_data
        ) VALUES ($1, $2, $3, $4, $5::jsonb)
        RETURNING id
        """,
        property_id,
        result.score,
        result.score_version,
        calculated_at,
        f'{{"foreclosure":{result.foreclosure_component},'
        f'"tax":{result.tax_component},'
        f'"preforeclosure":{result.preforeclosure_component},'
        f'"probate":{result.probate_component}}}',
    )
    return row["id"]


# ── endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "distress-score"}


@app.post("/api/v1/score/{property_id}", response_model=ScoreResponse)
async def score_property(property_id: UUID, body: ScoreRequest = ScoreRequest()):
    """Compute the distress score for a property and store it."""
    pool = app.state.pool

    # Verify property exists
    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL", property_id
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    # Build signals: DB events first, then overlay any explicit overrides from body
    signals = await _fetch_signals(pool, property_id)
    if body.foreclosure_stage is not None:
        signals.foreclosure_stage = body.foreclosure_stage
    if body.years_delinquent is not None:
        signals.years_delinquent = body.years_delinquent
    if body.has_active_probate:
        signals.has_active_probate = True
    if body.lp_filing_date is not None:
        signals.lp_filing_date = body.lp_filing_date
    if body.as_of is not None:
        signals.as_of = body.as_of

    result = _scorer.score(signals)
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_score(pool, property_id, result, calculated_at)

    return ScoreResponse(
        property_id=property_id,
        score=result.score,
        foreclosure_component=result.foreclosure_component,
        tax_component=result.tax_component,
        preforeclosure_component=result.preforeclosure_component,
        probate_component=result.probate_component,
        score_version=result.score_version,
        calculated_at=calculated_at,
    )


@app.get("/api/v1/score/{property_id}", response_model=ScoreResponse)
async def get_latest_score(property_id: UUID):
    """Return the most-recent distress score for a property."""
    pool = app.state.pool

    row = await pool.fetchrow(
        """
        SELECT id, distress_score, score_version, calculated_at, raw_data
        FROM   latest_property_scores
        WHERE  property_id = $1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="No score found for this property")

    raw = row["raw_data"] or {}
    return ScoreResponse(
        property_id=property_id,
        score=float(row["distress_score"] or 0),
        foreclosure_component=float(raw.get("foreclosure", 0)),
        tax_component=float(raw.get("tax", 0)),
        preforeclosure_component=float(raw.get("preforeclosure", 0)),
        probate_component=float(raw.get("probate", 0)),
        score_version=row["score_version"],
        calculated_at=row["calculated_at"],
    )


@app.get("/api/v1/score/{property_id}/history", response_model=ScoreHistoryResponse)
async def get_score_history(property_id: UUID, limit: int = 50):
    """Return the full score history for a property (newest first)."""
    pool = app.state.pool

    rows = await pool.fetch(
        """
        SELECT id, distress_score, score_version, calculated_at, raw_data
        FROM   property_scores
        WHERE  property_id = $1
        ORDER  BY calculated_at DESC
        LIMIT  $2
        """,
        property_id,
        limit,
    )

    items = []
    for row in rows:
        raw = row["raw_data"] or {}
        items.append(
            ScoreHistoryItem(
                id=row["id"],
                score=float(row["distress_score"] or 0),
                foreclosure_component=raw.get("foreclosure"),
                tax_component=raw.get("tax"),
                preforeclosure_component=raw.get("preforeclosure"),
                probate_component=raw.get("probate"),
                score_version=row["score_version"],
                calculated_at=row["calculated_at"],
            )
        )

    return ScoreHistoryResponse(property_id=property_id, history=items)
