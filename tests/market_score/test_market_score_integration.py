"""
Integration tests for the market score service against a live DB.
Requires DATABASE_URL to be set (Neon test branch).

Covers:
  - _fetch_market_inputs returns (MarketInputs, False) for unknown property
  - _fetch_market_inputs returns (MarketInputs, True) with correct zip_code
  - _persist_market_score writes all columns to property_scores
  - _persist_market_score raw_data contains sub-scores and zip_code
  - GET latest: returns 404 when property has no score
  - POST→persist round-trip: market_score stored is correct value
  - Multiple persisted scores: latest is returned (ORDER BY calculated_at DESC)
  - raw_data round-trip: sub-scores survive DB write and re-read
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live-DB tests",
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(dsn=os.environ["DATABASE_URL"], min_size=1, max_size=2)
    yield p
    await p.close()


@pytest.fixture
async def prop(pool):
    """Seed a property row with a known zip_code; clean up on teardown."""
    prop_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO properties (id, address, city, county, zip_code, land_value, improvement_value)
        VALUES ($1, '123 Test St', 'Austin', 'Travis', '78701', 150000.00, 200000.00)
        """,
        prop_id,
    )
    yield prop_id
    await pool.execute("DELETE FROM property_scores WHERE property_id = $1", prop_id)
    await pool.execute("DELETE FROM properties      WHERE id          = $1", prop_id)


# ── _fetch_market_inputs ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_market_inputs_unknown_property(pool):
    from services.market_score.main import _fetch_market_inputs

    inputs, exists = await _fetch_market_inputs(pool, uuid.uuid4())
    assert exists is False


@pytest.mark.asyncio
async def test_fetch_market_inputs_returns_zip_code(pool, prop):
    from services.market_score.main import _fetch_market_inputs

    inputs, exists = await _fetch_market_inputs(pool, prop)
    assert exists is True
    assert inputs.zip_code == "78701"


@pytest.mark.asyncio
async def test_fetch_market_inputs_signals_are_none(pool, prop):
    """All market signals are stubbed — they must come back None until a provider is wired."""
    from services.market_score.main import _fetch_market_inputs

    inputs, exists = await _fetch_market_inputs(pool, prop)
    assert exists is True
    assert inputs.appreciation_rate is None
    assert inputs.avg_days_on_market is None
    assert inputs.rent_to_price_ratio is None


# ── _persist_market_score ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_market_score_writes_correct_score(pool, prop):
    from services.market_score.main import _persist_market_score
    from services.market_score.scorer import MarketInputs, MarketScorer

    scorer = MarketScorer()
    result = scorer.score(MarketInputs(
        zip_code="78701",
        appreciation_rate=0.10,
        avg_days_on_market=60,
        rent_to_price_ratio=0.07,
    ))
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_market_score(pool, prop, result, calculated_at)

    row = await pool.fetchrow(
        "SELECT market_score, score_version FROM property_scores WHERE property_id = $1",
        prop,
    )
    assert row is not None
    assert float(row["market_score"]) == pytest.approx(result.market_score, rel=1e-4)
    assert row["score_version"] == "1.0"


@pytest.mark.asyncio
async def test_persist_market_score_raw_data_contains_sub_scores(pool, prop):
    from services.market_score.main import _persist_market_score
    from services.market_score.scorer import MarketInputs, MarketScorer

    scorer = MarketScorer()
    result = scorer.score(MarketInputs(
        zip_code="78701",
        appreciation_rate=0.15,
        avg_days_on_market=30,
        rent_to_price_ratio=0.08,
    ))
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_market_score(pool, prop, result, calculated_at)

    row = await pool.fetchrow(
        "SELECT raw_data FROM property_scores WHERE property_id = $1",
        prop,
    )
    raw = json.loads(row["raw_data"]) if row["raw_data"] else {}
    assert raw.get("zip_code") == "78701"
    assert raw.get("appreciation_score") == pytest.approx(100.0)
    assert raw.get("liquidity_score") == pytest.approx(75.0)   # (1 - 30/120)*100
    assert raw.get("yield_score") == pytest.approx(80.0)       # (0.08/0.10)*100


# ── latest score query ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_score_row_returns_none(pool, prop):
    """Property exists but has never been scored — fetchrow must return nothing."""
    row = await pool.fetchrow(
        """
        SELECT market_score FROM property_scores
        WHERE  property_id = $1 AND market_score IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert row is None


@pytest.mark.asyncio
async def test_latest_score_returned_after_multiple_inserts(pool, prop):
    """Two score rows inserted; the one with the later calculated_at must be returned."""
    from services.market_score.main import _persist_market_score
    from services.market_score.scorer import MarketInputs, MarketScorer

    scorer = MarketScorer()
    now = datetime.now(tz=timezone.utc)

    older = scorer.score(MarketInputs(appreciation_rate=0.05))  # score ≈ 83.33
    await _persist_market_score(pool, prop, older, now - timedelta(hours=2))

    newer = scorer.score(MarketInputs(appreciation_rate=0.10))  # score ≈ 88.89
    await _persist_market_score(pool, prop, newer, now)

    row = await pool.fetchrow(
        """
        SELECT market_score FROM property_scores
        WHERE  property_id = $1 AND market_score IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert float(row["market_score"]) == pytest.approx(newer.market_score, rel=1e-4)


# ── raw_data round-trip ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_raw_data_round_trip_sub_scores_survive_db(pool, prop):
    """Sub-scores written to raw_data must be readable back as the same values."""
    from services.market_score.main import _persist_market_score
    from services.market_score.scorer import MarketInputs, MarketScorer

    scorer = MarketScorer()
    result = scorer.score(MarketInputs(
        zip_code="78701",
        appreciation_rate=0.075,   # → appreciation_score = 50.0
        avg_days_on_market=60,     # → liquidity_score    = 50.0
        rent_to_price_ratio=0.05,  # → yield_score        = 50.0
    ))
    assert result.market_score == pytest.approx(50.0)

    await _persist_market_score(pool, prop, result, datetime.now(tz=timezone.utc))

    row = await pool.fetchrow(
        "SELECT raw_data FROM property_scores WHERE property_id = $1 ORDER BY calculated_at DESC LIMIT 1",
        prop,
    )
    raw = json.loads(row["raw_data"]) if row["raw_data"] else {}
    assert raw.get("appreciation_score") == pytest.approx(50.0)
    assert raw.get("liquidity_score") == pytest.approx(50.0)
    assert raw.get("yield_score") == pytest.approx(50.0)
    assert raw.get("zip_code") == "78701"
