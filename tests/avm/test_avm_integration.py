"""
Integration tests for the AVM service against a live DB.
Requires DATABASE_URL to be set (Neon test branch).

Covers:
  - _fetch_cached returns None when no valuation exists
  - _fetch_cached returns a result when a fresh valuation exists
  - _fetch_cached returns None when valuation is older than AVM_MAX_AGE_DAYS
  - _persist_valuation writes all columns correctly
  - get_avm returns None when AVM_PROVIDER is unset (no external call)
  - get_avm hits cache and skips API when fresh valuation exists
  - equity engine _fetch_equity_inputs uses valuations.avm over CAD when present
  - equity engine _fetch_equity_inputs falls back to CAD when no valuation exists
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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
    """Seed a minimal property row; clean up valuations + property on teardown."""
    prop_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO properties (id, land_value, improvement_value)
        VALUES ($1, 120000.00, 180000.00)
        """,
        prop_id,
    )
    yield prop_id
    await pool.execute("DELETE FROM valuations   WHERE property_id = $1", prop_id)
    await pool.execute("DELETE FROM property_scores WHERE property_id = $1", prop_id)
    await pool.execute("DELETE FROM properties   WHERE id           = $1", prop_id)


# ── _fetch_cached ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_cached_no_valuation_returns_none(pool, prop):
    from services.avm_service.client import _fetch_cached
    result = await _fetch_cached(pool, prop, "attom")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_cached_fresh_valuation_returned(pool, prop):
    from services.avm_service.client import _fetch_cached

    await pool.execute(
        """
        INSERT INTO valuations
            (property_id, avm, confidence_score, valuation_date, provider, calculated_at)
        VALUES ($1, 350000.00, 88.5, $2, 'attom', $3)
        """,
        prop, date.today(), datetime.now(tz=timezone.utc),
    )

    result = await _fetch_cached(pool, prop, "attom")
    assert result is not None
    assert result.avm == pytest.approx(350_000.00)
    assert result.confidence_score == pytest.approx(88.5)
    assert result.from_cache is True
    assert result.provider == "attom"


@pytest.mark.asyncio
async def test_fetch_cached_stale_valuation_returns_none(pool, prop):
    from services.avm_service.client import _fetch_cached, _AVM_MAX_AGE_DAYS

    stale_date = date.today() - timedelta(days=_AVM_MAX_AGE_DAYS + 1)
    await pool.execute(
        """
        INSERT INTO valuations
            (property_id, avm, valuation_date, provider, calculated_at)
        VALUES ($1, 300000.00, $2, 'attom', $3)
        """,
        prop, stale_date, datetime.now(tz=timezone.utc),
    )

    result = await _fetch_cached(pool, prop, "attom")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_cached_ignores_other_providers(pool, prop):
    """A cached valuation under a different provider must not be returned."""
    from services.avm_service.client import _fetch_cached

    await pool.execute(
        """
        INSERT INTO valuations
            (property_id, avm, valuation_date, provider, calculated_at)
        VALUES ($1, 400000.00, $2, 'other_provider', $3)
        """,
        prop, date.today(), datetime.now(tz=timezone.utc),
    )

    result = await _fetch_cached(pool, prop, "attom")
    assert result is None


# ── _persist_valuation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_valuation_writes_all_columns(pool, prop):
    from services.avm_service.client import AvmResult, _persist_valuation

    result = AvmResult(
        avm=425_000.00,
        confidence_score=92.0,
        valuation_date=date.today(),
        provider="attom",
        raw_response={"test": True},
        from_cache=False,
    )
    await _persist_valuation(pool, prop, result)

    row = await pool.fetchrow(
        "SELECT avm, confidence_score, raw_response, provider FROM valuations WHERE property_id = $1",
        prop,
    )
    assert float(row["avm"]) == pytest.approx(425_000.00)
    assert float(row["confidence_score"]) == pytest.approx(92.0)
    assert row["raw_response"] == {"test": True}
    assert row["provider"] == "attom"


# ── get_avm: no provider ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_avm_no_provider_returns_none(pool, prop):
    from services.avm_service.client import get_avm

    with patch("services.avm_service.client._AVM_PROVIDER", ""):
        result = await get_avm(pool, prop, "123 Main St", "Austin")

    assert result is None


# ── get_avm: cache path (no real API call) ────────────────────────────────────

@pytest.mark.asyncio
async def test_get_avm_cache_hit_no_api_call(pool, prop):
    from services.avm_service.client import get_avm

    await pool.execute(
        """
        INSERT INTO valuations
            (property_id, avm, confidence_score, valuation_date, provider, calculated_at)
        VALUES ($1, 375000.00, 85.0, $2, 'attom', $3)
        """,
        prop, date.today(), datetime.now(tz=timezone.utc),
    )

    with patch("services.avm_service.client._AVM_PROVIDER", "attom"), \
         patch("services.avm_service.client._call_attom", new=AsyncMock()) as mock_api:
        result = await get_avm(pool, prop, "123 Main St", "Austin")

    mock_api.assert_not_awaited()
    assert result.from_cache is True
    assert result.avm == pytest.approx(375_000.00)


# ── equity engine AVM source ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_equity_engine_prefers_valuations_avm(pool, prop):
    """When a valuation exists, equity engine must use it over CAD (300k vs 120k+180k=300k CAD,
    but we insert 500k valuation to make the distinction unambiguous)."""
    from services.equity_engine.main import _fetch_equity_inputs

    await pool.execute(
        """
        INSERT INTO valuations
            (property_id, avm, valuation_date, provider, calculated_at)
        VALUES ($1, 500000.00, $2, 'attom', $3)
        """,
        prop, date.today(), datetime.now(tz=timezone.utc),
    )

    inputs, exists = await _fetch_equity_inputs(pool, prop)
    assert exists is True
    assert inputs.avm == pytest.approx(500_000.00)


@pytest.mark.asyncio
async def test_equity_engine_falls_back_to_cad_when_no_valuation(pool, prop):
    """With no valuation row, equity engine uses land+improvement from properties."""
    from services.equity_engine.main import _fetch_equity_inputs

    inputs, exists = await _fetch_equity_inputs(pool, prop)
    assert exists is True
    assert inputs.avm == pytest.approx(300_000.00)  # 120k land + 180k improvement
