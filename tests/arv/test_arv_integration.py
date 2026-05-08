"""
Integration tests for the ARV engine against a live DB.
Requires DATABASE_URL to be set (Neon test branch).

Covers:
  - _fetch_subject returns (SubjectProperty, False) for unknown property
  - _fetch_subject returns (SubjectProperty, True) with correct zip_code
  - _fetch_subject reads sqft/beds/baths from DB
  - _fetch_subject caller override (sqft) takes precedence over DB value
  - _persist_arv writes arv, arv_confidence, comp_count, method, arv_version
  - GET latest: returns 404 when property has no ARV score
  - GET latest: AVM-only row in valuations does not satisfy ARV query
  - POST→persist round-trip: arv and arv_confidence stored match result
  - Multiple persisted rows: latest returned (ORDER BY calculated_at DESC)
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
    """Seed a property with known sqft/beds/baths; clean up on teardown."""
    prop_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO properties
            (id, address, city, county, zip_code, sqft, beds, baths,
             land_value, improvement_value)
        VALUES ($1, '456 ARV Test Ave', 'Austin', 'Travis', '78702',
                1500, 3, 2.0, 120000.00, 180000.00)
        """,
        prop_id,
    )
    yield prop_id
    await pool.execute("DELETE FROM valuations  WHERE property_id = $1", prop_id)
    await pool.execute("DELETE FROM properties  WHERE id          = $1", prop_id)


# ── _fetch_subject ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_subject_unknown_property(pool):
    from services.arv_engine.main import _fetch_subject
    from services.arv_engine.models import ARVRequest

    _, exists = await _fetch_subject(pool, uuid.uuid4(), ARVRequest())
    assert exists is False


@pytest.mark.asyncio
async def test_fetch_subject_returns_zip_code(pool, prop):
    from services.arv_engine.main import _fetch_subject
    from services.arv_engine.models import ARVRequest

    subject, exists = await _fetch_subject(pool, prop, ARVRequest())
    assert exists is True
    assert subject.zip_code == "78702"


@pytest.mark.asyncio
async def test_fetch_subject_reads_sqft_beds_baths(pool, prop):
    from services.arv_engine.main import _fetch_subject
    from services.arv_engine.models import ARVRequest

    subject, exists = await _fetch_subject(pool, prop, ARVRequest())
    assert exists is True
    assert subject.sqft == 1500.0
    assert subject.beds == 3
    assert subject.baths == 2.0


@pytest.mark.asyncio
async def test_fetch_subject_override_sqft_takes_precedence(pool, prop):
    from services.arv_engine.main import _fetch_subject
    from services.arv_engine.models import ARVRequest

    subject, exists = await _fetch_subject(pool, prop, ARVRequest(sqft=2000))
    assert exists is True
    assert subject.sqft == 2000.0


# ── _persist_arv ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_arv_writes_correct_values(pool, prop):
    from services.arv_engine.main import _persist_arv
    from services.arv_engine.arv import ARVResult

    result = ARVResult(
        property_id=str(prop),
        arv=375_000.0,
        arv_confidence=70.0,
        comp_count=4,
        method="price_per_sqft",
        arv_version="1.0",
    )
    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_arv(pool, prop, result, calculated_at)

    row = await pool.fetchrow(
        """
        SELECT arv, arv_confidence, comp_count, method, arv_version
        FROM   valuations
        WHERE  property_id = $1
        """,
        prop,
    )
    assert row is not None
    assert float(row["arv"]) == pytest.approx(375_000.0, rel=1e-4)
    assert float(row["arv_confidence"]) == pytest.approx(70.0)
    assert row["comp_count"] == 4
    assert row["method"] == "price_per_sqft"
    assert row["arv_version"] == "1.0"


@pytest.mark.asyncio
async def test_persist_arv_null_arv_when_no_comps(pool, prop):
    """Stub provider → arv=None should be stored as NULL."""
    from services.arv_engine.main import _persist_arv
    from services.arv_engine.arv import ARVResult

    result = ARVResult(
        property_id=str(prop),
        arv=None,
        arv_confidence=0.0,
        comp_count=0,
        method="price_per_sqft",
        arv_version="1.0",
    )
    await _persist_arv(pool, prop, result, datetime.now(tz=timezone.utc))

    row = await pool.fetchrow(
        "SELECT arv FROM valuations WHERE property_id = $1",
        prop,
    )
    assert row is not None
    assert row["arv"] is None


# ── latest query isolation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_arv_row_returns_none(pool, prop):
    """Property exists but has never been ARV-scored — query must return nothing."""
    row = await pool.fetchrow(
        """
        SELECT arv FROM valuations
        WHERE  property_id = $1 AND arv_confidence IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert row is None


@pytest.mark.asyncio
async def test_avm_only_row_not_returned_by_arv_query(pool, prop):
    """An AVM-only row (arv_confidence IS NULL) must not satisfy the ARV query."""
    await pool.execute(
        """
        INSERT INTO valuations (property_id, avm, calculated_at)
        VALUES ($1, 350000.00, NOW())
        """,
        prop,
    )
    row = await pool.fetchrow(
        """
        SELECT arv FROM valuations
        WHERE  property_id = $1 AND arv_confidence IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert row is None


# ── POST→persist round-trip ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_round_trip_arv_survives_db(pool, prop):
    """ARV written then read back must equal the original result."""
    from services.arv_engine.main import _persist_arv
    from services.arv_engine.arv import ARVCalculator, SubjectProperty, Comp
    from datetime import date

    subject = SubjectProperty(
        property_id=str(prop), sqft=1500, beds=3, baths=2.0, zip_code="78702"
    )
    comp = Comp(
        sale_price=450_000,
        sqft=1500,
        beds=3,
        baths=2.0,
        sale_date=date.today() - timedelta(days=30),
        distance_miles=0.3,
    )
    with patch("services.arv_engine.arv._get_comps", return_value=[comp]):
        result = ARVCalculator().estimate(subject)

    assert result.arv == pytest.approx(450_000.0)

    calculated_at = datetime.now(tz=timezone.utc)
    await _persist_arv(pool, prop, result, calculated_at)

    row = await pool.fetchrow(
        """
        SELECT arv, arv_confidence, comp_count
        FROM   valuations
        WHERE  property_id = $1 AND arv_confidence IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert float(row["arv"]) == pytest.approx(450_000.0, rel=1e-4)
    assert float(row["arv_confidence"]) == pytest.approx(50.0)
    assert row["comp_count"] == 1


# ── latest ordering ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_latest_score_returned_after_multiple_inserts(pool, prop):
    """Two ARV rows inserted; the one with later calculated_at must be returned."""
    from services.arv_engine.main import _persist_arv
    from services.arv_engine.arv import ARVResult

    now = datetime.now(tz=timezone.utc)

    older = ARVResult(
        property_id=str(prop), arv=300_000.0, arv_confidence=50.0,
        comp_count=2, method="price_per_sqft",
    )
    await _persist_arv(pool, prop, older, now - timedelta(hours=2))

    newer = ARVResult(
        property_id=str(prop), arv=400_000.0, arv_confidence=70.0,
        comp_count=4, method="price_per_sqft",
    )
    await _persist_arv(pool, prop, newer, now)

    row = await pool.fetchrow(
        """
        SELECT arv FROM valuations
        WHERE  property_id = $1 AND arv_confidence IS NOT NULL
        ORDER  BY calculated_at DESC LIMIT 1
        """,
        prop,
    )
    assert float(row["arv"]) == pytest.approx(400_000.0, rel=1e-4)
