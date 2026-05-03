"""Distress Score Service — computes and persists composite distress scores."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException, Query

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
    signals = DistressSignals()

    # Most-recent foreclosure stage (ordered by filing_date)
    fc_row = await pool.fetchrow(
        """
        SELECT foreclosure_stage
        FROM   events
        WHERE  property_id = $1 AND event_type = 'foreclosure'
        ORDER  BY filing_date DESC NULLS LAST
        LIMIT  1
        """,
        property_id,
    )
    if fc_row:
        signals.foreclosure_stage = fc_row["foreclosure_stage"]

    # MAX years_delinquent across all tax records — avoids taking a re-filed
    # lower count when an older record has a higher delinquency value.
    tax_row = await pool.fetchrow(
        """
        SELECT MAX(years_delinquent) AS years_delinquent
        FROM   events
        WHERE  property_id = $1 AND event_type = 'tax_delinquency'
        """,
        property_id,
    )
    if tax_row:
        signals.years_delinquent = tax_row["years_delinquent"]

    # Probate: treat as active only if a probate event was filed within the last 2 years.
    # Older closed/discharged probate cases should not permanently inflate the score.
    signals.has_active_probate = await pool.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM events
            WHERE  property_id = $1
              AND  event_type = 'probate'
              AND  filing_date >= CURRENT_DATE - INTERVAL '2 years'
        )
        """,
        property_id,
    )

    # Most-recent Lis Pendens filing date
    lp_row = await pool.fetchrow(
        """
        SELECT filing_date
        FROM   events
        WHERE  property_id = $1 AND event_type = 'preforeclosure'
        ORDER  BY filing_date DESC NULLS LAST
        LIMIT  1
        """,
        property_id,
    )
    if lp_row and lp_row["filing_date"]:
        fd = lp_row["filing_date"]
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
        json.dumps({
            "foreclosure":    result.foreclosure_component,
            "tax":            result.tax_component,
            "preforeclosure": result.preforeclosure_component,
            "probate":        result.probate_component,
        }),
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
        signals.foreclosure_stage = body.foreclosure_stage.value
    if body.years_delinquent is not None:
        signals.years_delinquent = body.years_delinquent
    # Always apply the probate override so callers can explicitly clear it (False)
    if body.has_active_probate is not None:
        signals.has_active_probate = body.has_active_probate
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

    # Check property existence first so callers can distinguish 404 reasons.
    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL", property_id
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

    row = await pool.fetchrow(
        """
        SELECT id, distress_score, score_version, calculated_at, raw_data
        FROM   latest_property_scores
        WHERE  property_id = $1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Property exists but has not been scored yet")

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
async def get_score_history(
    property_id: UUID,
    limit: int = Query(50, ge=1, le=500),
):
    """Return the full score history for a property (newest first)."""
    pool = app.state.pool

    exists = await pool.fetchval(
        "SELECT 1 FROM properties WHERE id = $1 AND deleted_at IS NULL", property_id
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Property not found")

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
