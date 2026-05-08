"""
Integration tests for the rehab engine against a live DB.
Requires DATABASE_URL to be set (Neon test branch).

Covers:
  - _fetch_inputs returns (RehabInputs, False) for unknown property
  - _fetch_inputs reads sqft from DB
  - _fetch_inputs caller sqft override takes precedence over DB value
  - _fetch_inputs rehab_level override applied correctly
  - _persist_rehab writes record_type='rehab', rehab_level, rehab_cost, rehab_cost_sqft
  - _persist_rehab stores sqft and line_items in notes JSON
  - GET isolation: analysis row with record_type != 'rehab' not returned
  - POST→persist round-trip: sqft and line_items survive DB write
  - Multiple persisted rows: latest returned (ORDER BY calculated_at DESC)
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
    """Seed a property with known sqft; clean up on teardown."""
    prop_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO properties
            (id, address, city, county, zip_code, sqft,
             land_value, improvement_value)
        VALUES ($1, '123 Rehab Test St', 'Austin', 'Travis', '78701',
                1200, 100000.00, 150000.00)
        """,
        prop_id,
    )
    yield prop_id
    await pool.execute(
        "DELETE FROM analysis   WHERE property_id = $1", prop_id
    )
    await pool.execute(
        "DELETE FROM properties WHERE id          = $1", prop_id
    )


# ── _fetch_inputs ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_inputs_unknown_property(pool):
    from services.rehab_engine.main import _fetch_inputs
    from services.rehab_engine.models import RehabRequest

    _, exists = await _fetch_inputs(pool, uuid.uuid4(), RehabRequest())
    assert exists is False


@pytest.mark.asyncio
async def test_fetch_inputs_reads_sqft_from_db(pool, prop):
    from services.rehab_engine.main import _fetch_inputs
    from services.rehab_engine.models import RehabRequest

    inputs, exists = await _fetch_inputs(pool, prop, RehabRequest())
    assert exists is True
    assert inputs.sqft == 1200.0


@pytest.mark.asyncio
async def test_fetch_inputs_sqft_override_takes_precedence(pool, prop):
    from services.rehab_engine.main import _fetch_inputs
    from services.rehab_engine.models import RehabRequest

    inputs, exists = await _fetch_inputs(pool, prop, RehabRequest(sqft=2000))
    assert exists is True
    assert inputs.sqft == 2000.0


@pytest.mark.asyncio
async def test_fetch_inputs_rehab_level_override(pool, prop):
    from services.rehab_engine.main import _fetch_inputs
    from services.rehab_engine.models import RehabRequest

    inputs, exists = await _fetch_inputs(pool, prop, RehabRequest(rehab_level="heavy"))
    assert exists is True
    assert inputs.rehab_level == "heavy"


# ── _persist_rehab ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_rehab_writes_correct_columns(pool, prop):
    from services.rehab_engine.main import _persist_rehab
    from services.rehab_engine.estimator import RehabEstimator, RehabInputs

    result = RehabEstimator().estimate(RehabInputs(sqft=1200, rehab_level="medium"))
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_rehab(pool, prop, result, calculated_at)

    row = await pool.fetchrow(
        """
        SELECT record_type, rehab_level, rehab_cost, rehab_cost_sqft
        FROM   analysis
        WHERE  property_id = $1
        """,
        prop,
    )
    assert row is not None
    assert row["record_type"] == "rehab"
    assert row["rehab_level"] == "medium"
    assert float(row["rehab_cost"]) == pytest.approx(result.total_cost, rel=1e-4)
    assert float(row["rehab_cost_sqft"]) == pytest.approx(result.cost_per_sqft, rel=1e-4)


@pytest.mark.asyncio
async def test_persist_rehab_stores_sqft_and_line_items_in_notes(pool, prop):
    from services.rehab_engine.main import _persist_rehab
    from services.rehab_engine.estimator import RehabEstimator, RehabInputs

    result = RehabEstimator().estimate(RehabInputs(sqft=1200, rehab_level="light"))
    await _persist_rehab(pool, prop, result, datetime.now(tz=timezone.utc))

    row = await pool.fetchrow(
        "SELECT notes FROM analysis WHERE property_id = $1",
        prop,
    )
    notes = json.loads(row["notes"])
    assert notes["sqft"] == 1200.0
    assert "paint" in notes["line_items"]
    assert notes["rehab_version"] == "1.0"


# ── isolation: non-rehab rows must not appear ─────────────────────────────────

@pytest.mark.asyncio
async def test_mao_row_not_returned_by_rehab_query(pool, prop):
    """An analysis row with record_type='mao' must not satisfy the rehab GET query."""
    await pool.execute(
        """
        INSERT INTO analysis
            (property_id, record_type, rehab_cost, calculated_at)
        VALUES ($1, 'mao', 99999.00, NOW())
        """,
        prop,
    )
    row = await pool.fetchrow(
        """
        SELECT id FROM analysis
        WHERE  property_id = $1
          AND  record_type  = 'rehab'
          AND  rehab_cost  IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert row is None


# ── POST→persist round-trip ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_round_trip_sqft_and_line_items_survive_db(pool, prop):
    from services.rehab_engine.main import _persist_rehab
    from services.rehab_engine.estimator import RehabEstimator, RehabInputs

    result = RehabEstimator().estimate(
        RehabInputs(sqft=1200, rehab_level="medium", overrides={"hvac": 7.00})
    )
    await _persist_rehab(pool, prop, result, datetime.now(tz=timezone.utc))

    row = await pool.fetchrow(
        """
        SELECT notes FROM analysis
        WHERE  property_id = $1
          AND  record_type  = 'rehab'
          AND  rehab_cost  IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    notes = json.loads(row["notes"])
    assert notes["sqft"] == 1200.0
    assert notes["line_items"]["hvac"] == pytest.approx(7.00 * 1200)


# ── latest ordering ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_latest_rehab_returned_after_multiple_inserts(pool, prop):
    from services.rehab_engine.main import _persist_rehab
    from services.rehab_engine.estimator import RehabEstimator, RehabInputs

    now = datetime.now(tz=timezone.utc)

    older = RehabEstimator().estimate(RehabInputs(sqft=1200, rehab_level="light"))
    await _persist_rehab(pool, prop, older, now - timedelta(hours=2))

    newer = RehabEstimator().estimate(RehabInputs(sqft=1200, rehab_level="heavy"))
    await _persist_rehab(pool, prop, newer, now)

    row = await pool.fetchrow(
        """
        SELECT rehab_level FROM analysis
        WHERE  property_id = $1
          AND  record_type  = 'rehab'
          AND  rehab_cost  IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert row["rehab_level"] == "heavy"
