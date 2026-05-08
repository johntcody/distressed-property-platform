"""
Integration tests for the MAO engine against a live DB.
Requires DATABASE_URL to be set (Neon test branch).

Covers:
  - _fetch_inputs returns (MAOInputs, False) for unknown property
  - _fetch_inputs reads ARV from valuations
  - _fetch_inputs reads rehab_cost from analysis (record_type='rehab')
  - _fetch_inputs caller arv override takes precedence over DB value
  - _fetch_inputs caller rehab_cost override takes precedence over DB value
  - _persist_mao writes record_type='mao', rehab_level=NULL, correct columns
  - GET isolation: rehab row not returned by MAO query
  - POST→persist round-trip: arv, rehab_cost, mao survive DB write
  - Multiple persisted rows: latest returned (ORDER BY calculated_at DESC)
"""

from __future__ import annotations

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
    """Seed a bare property; clean up analysis + valuations + property on teardown."""
    prop_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO properties
            (id, address, city, county, zip_code, sqft,
             land_value, improvement_value)
        VALUES ($1, '789 MAO Test Blvd', 'Austin', 'Travis', '78703',
                1500, 110000.00, 160000.00)
        """,
        prop_id,
    )
    yield prop_id
    await pool.execute("DELETE FROM analysis   WHERE property_id = $1", prop_id)
    await pool.execute("DELETE FROM valuations  WHERE property_id = $1", prop_id)
    await pool.execute("DELETE FROM properties  WHERE id          = $1", prop_id)


@pytest.fixture
async def prop_with_arv_and_rehab(pool, prop):
    """Seed ARV in valuations and rehab_cost in analysis for the test property."""
    await pool.execute(
        """
        INSERT INTO valuations (property_id, arv, arv_confidence, comp_count, method, calculated_at)
        VALUES ($1, 350000.00, 70.0, 4, 'price_per_sqft', NOW())
        """,
        prop,
    )
    await pool.execute(
        """
        INSERT INTO analysis
            (property_id, record_type, rehab_level, rehab_cost, rehab_cost_sqft, calculated_at)
        VALUES ($1, 'rehab', 'medium', 45000.00, 30.00, NOW())
        """,
        prop,
    )
    return prop


# ── _fetch_inputs ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_inputs_unknown_property(pool):
    from services.mao_engine.main import _fetch_inputs
    from services.mao_engine.models import MAORequest

    _, exists = await _fetch_inputs(pool, uuid.uuid4(), MAORequest())
    assert exists is False


@pytest.mark.asyncio
async def test_fetch_inputs_reads_arv_from_valuations(pool, prop_with_arv_and_rehab):
    from services.mao_engine.main import _fetch_inputs
    from services.mao_engine.models import MAORequest

    inputs, exists = await _fetch_inputs(pool, prop_with_arv_and_rehab, MAORequest())
    assert exists is True
    assert inputs.arv == pytest.approx(350_000.0)


@pytest.mark.asyncio
async def test_fetch_inputs_reads_rehab_cost_from_analysis(pool, prop_with_arv_and_rehab):
    from services.mao_engine.main import _fetch_inputs
    from services.mao_engine.models import MAORequest

    inputs, exists = await _fetch_inputs(pool, prop_with_arv_and_rehab, MAORequest())
    assert exists is True
    assert inputs.rehab_cost == pytest.approx(45_000.0)


@pytest.mark.asyncio
async def test_fetch_inputs_arv_override_takes_precedence(pool, prop_with_arv_and_rehab):
    from services.mao_engine.main import _fetch_inputs
    from services.mao_engine.models import MAORequest

    inputs, _ = await _fetch_inputs(pool, prop_with_arv_and_rehab, MAORequest(arv=400_000))
    assert inputs.arv == pytest.approx(400_000.0)


@pytest.mark.asyncio
async def test_fetch_inputs_rehab_override_takes_precedence(pool, prop_with_arv_and_rehab):
    from services.mao_engine.main import _fetch_inputs
    from services.mao_engine.models import MAORequest

    inputs, _ = await _fetch_inputs(pool, prop_with_arv_and_rehab, MAORequest(rehab_cost=60_000))
    assert inputs.rehab_cost == pytest.approx(60_000.0)


# ── _persist_mao ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_mao_writes_correct_columns(pool, prop_with_arv_and_rehab):
    from services.mao_engine.main import _persist_mao
    from services.mao_engine.calculator import MAOCalculator, MAOInputs

    result = MAOCalculator().calculate(MAOInputs(arv=350_000, rehab_cost=45_000))
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_mao(pool, prop_with_arv_and_rehab, result, calculated_at)

    row = await pool.fetchrow(
        """
        SELECT record_type, rehab_level, arv_used, discount_pct, rehab_cost, mao, mao_version
        FROM   analysis
        WHERE  property_id = $1 AND record_type = 'mao'
        """,
        prop_with_arv_and_rehab,
    )
    assert row is not None
    assert row["record_type"] == "mao"
    assert row["rehab_level"] is None
    assert float(row["arv_used"]) == pytest.approx(350_000.0)
    assert float(row["discount_pct"]) == pytest.approx(70.0)
    assert float(row["rehab_cost"]) == pytest.approx(45_000.0)
    # (350000 * 0.70) - 45000 = 200000
    assert float(row["mao"]) == pytest.approx(200_000.0)
    assert row["mao_version"] == "1.0"


# ── isolation ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rehab_row_not_returned_by_mao_query(pool, prop_with_arv_and_rehab):
    """A rehab row (record_type='rehab') must not appear in the MAO query."""
    row = await pool.fetchrow(
        """
        SELECT id FROM analysis
        WHERE  property_id = $1
          AND  record_type  = 'mao'
          AND  mao          IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop_with_arv_and_rehab,
    )
    assert row is None


# ── POST→persist round-trip ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_round_trip_mao_survives_db(pool, prop_with_arv_and_rehab):
    from services.mao_engine.main import _persist_mao
    from services.mao_engine.calculator import MAOCalculator, MAOInputs

    result = MAOCalculator().calculate(
        MAOInputs(arv=350_000, rehab_cost=45_000, holding_costs=5_000, closing_costs=3_000)
    )
    await _persist_mao(pool, prop_with_arv_and_rehab, result, datetime.now(tz=timezone.utc))

    row = await pool.fetchrow(
        """
        SELECT arv_used, rehab_cost, holding_costs, closing_costs, mao
        FROM   analysis
        WHERE  property_id = $1 AND record_type = 'mao' AND mao IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop_with_arv_and_rehab,
    )
    # (350000 * 0.70) - 45000 - 5000 - 3000 = 192000
    assert float(row["arv_used"]) == pytest.approx(350_000.0)
    assert float(row["rehab_cost"]) == pytest.approx(45_000.0)
    assert float(row["holding_costs"]) == pytest.approx(5_000.0)
    assert float(row["closing_costs"]) == pytest.approx(3_000.0)
    assert float(row["mao"]) == pytest.approx(192_000.0)


# ── latest ordering ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_latest_mao_returned_after_multiple_inserts(pool, prop_with_arv_and_rehab):
    from services.mao_engine.main import _persist_mao
    from services.mao_engine.calculator import MAOCalculator, MAOInputs

    now = datetime.now(tz=timezone.utc)

    older = MAOCalculator().calculate(MAOInputs(arv=300_000, rehab_cost=40_000))
    await _persist_mao(pool, prop_with_arv_and_rehab, older, now - timedelta(hours=2))

    newer = MAOCalculator().calculate(MAOInputs(arv=400_000, rehab_cost=50_000, discount_pct=75.0))
    await _persist_mao(pool, prop_with_arv_and_rehab, newer, now)

    row = await pool.fetchrow(
        """
        SELECT arv_used FROM analysis
        WHERE  property_id = $1 AND record_type = 'mao' AND mao IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop_with_arv_and_rehab,
    )
    assert float(row["arv_used"]) == pytest.approx(400_000.0)
