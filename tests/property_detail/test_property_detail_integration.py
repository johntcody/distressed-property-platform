"""
Integration tests for the Property Detail API.

Requires a live Postgres database with all migrations applied (001–012).
Set DATABASE_URL to run; all tests are skipped otherwise.

Each test inserts its own isolated rows and cleans up in a finally block,
so tests are safe to run against a shared dev database.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio

pytest.importorskip("asyncpg")
import asyncpg  # noqa: E402

from services.property_detail.queries import (
    ANALYSIS_SQL,
    EQUITY_SQL,
    EVENTS_SQL,
    PROPERTY_DETAIL_SQL,
    PROPERTY_EXISTS_SQL,
    VALUATIONS_SQL,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live-DB integration tests",
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def pool():
    p = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=3, command_timeout=15)
    yield p
    await p.close()


# ── insert helpers ────────────────────────────────────────────────────────────

async def _insert_property(pool, *, county="travis") -> uuid.UUID:
    pid = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO properties
            (id, address_raw, city, county, state, zip_code)
        VALUES ($1, $2, $3, $4, 'TX', '78701')
        """,
        pid, f"{pid} Main St", "Austin", county,
    )
    return pid


async def _insert_score(pool, pid: uuid.UUID, *, distress=75.0, equity_pct=40.0):
    await pool.execute(
        """
        INSERT INTO property_scores
            (property_id, distress_score, equity_pct, equity_amount, avm,
             market_score, estimated_liens, tax_owed)
        VALUES ($1, $2, $3, 80000, 200000, 65, 50000, 3000)
        """,
        pid, distress, equity_pct,
    )


async def _insert_event(pool, pid: uuid.UUID, *, event_type="foreclosure",
                        filing_date=date(2025, 3, 1), auction_date=None):
    eid = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO events
            (id, property_id, event_type, county, filing_date, auction_date)
        VALUES ($1, $2, $3::distress_event_type, 'travis', $4, $5)
        """,
        eid, pid, event_type, filing_date, auction_date,
    )
    return eid


async def _insert_valuation(pool, pid: uuid.UUID, *, arv=250000.0, avm=200000.0) -> uuid.UUID:
    vid = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO valuations
            (id, property_id, avm, arv, arv_confidence, comp_count,
             method, provider, confidence_score, arv_version)
        VALUES ($1, $2, $3, $4, 85.0, 5, 'idw', 'test-provider', 90.0, '1.0')
        """,
        vid, pid, avm, arv,
    )
    return vid


async def _insert_analysis(pool, pid: uuid.UUID, vid: uuid.UUID,
                            *, record_type="rehab", mao=None) -> uuid.UUID:
    aid = uuid.uuid4()
    if record_type == "rehab":
        await pool.execute(
            """
            INSERT INTO analysis
                (id, property_id, valuation_id, record_type, rehab_level,
                 rehab_cost, arv_used, discount_pct, holding_costs, closing_costs)
            VALUES ($1, $2, $3, 'rehab', 'medium', 30000, 250000, 70, 5000, 3000)
            """,
            aid, pid, vid,
        )
    else:
        await pool.execute(
            """
            INSERT INTO analysis
                (id, property_id, valuation_id, record_type,
                 arv_used, discount_pct, holding_costs, closing_costs, mao, mao_version)
            VALUES ($1, $2, $3, 'mao', 250000, 70, 5000, 3000, $4, '1.0')
            """,
            aid, pid, vid, mao or 137000.0,
        )
    return aid


async def _cleanup(pool, pid: uuid.UUID):
    await pool.execute("DELETE FROM analysis        WHERE property_id = $1", pid)
    await pool.execute("DELETE FROM valuations      WHERE property_id = $1", pid)
    await pool.execute("DELETE FROM events          WHERE property_id = $1", pid)
    await pool.execute("DELETE FROM property_scores WHERE property_id = $1", pid)
    await pool.execute("DELETE FROM properties      WHERE id = $1", pid)


# ── PROPERTY_DETAIL_SQL ───────────────────────────────────────────────────────

@skip_no_db
class TestPropertyDetailIntegration:
    @pytest.mark.asyncio
    async def test_returns_property_row(self, pool):
        pid = await _insert_property(pool, county="travis")
        try:
            row = await pool.fetchrow(PROPERTY_DETAIL_SQL, pid)
            assert row is not None
            assert row["property_id"] == pid
            assert row["county"] == "travis"
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_includes_latest_score(self, pool):
        pid = await _insert_property(pool)
        await _insert_score(pool, pid, distress=88.0, equity_pct=50.0)
        try:
            row = await pool.fetchrow(PROPERTY_DETAIL_SQL, pid)
            assert float(row["distress_score"]) == pytest.approx(88.0)
            assert float(row["equity_pct"]) == pytest.approx(50.0)
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_id(self, pool):
        row = await pool.fetchrow(PROPERTY_DETAIL_SQL, uuid.uuid4())
        assert row is None

    @pytest.mark.asyncio
    async def test_scores_null_when_no_score_row(self, pool):
        pid = await _insert_property(pool)
        try:
            row = await pool.fetchrow(PROPERTY_DETAIL_SQL, pid)
            assert row["distress_score"] is None
        finally:
            await _cleanup(pool, pid)


# ── EVENTS_SQL ────────────────────────────────────────────────────────────────

@skip_no_db
class TestEventsIntegration:
    @pytest.mark.asyncio
    async def test_returns_all_events(self, pool):
        pid = await _insert_property(pool)
        try:
            await _insert_event(pool, pid, filing_date=date(2025, 1, 1))
            await _insert_event(pool, pid, event_type="tax_delinquency", filing_date=date(2025, 2, 1))
            rows = await pool.fetch(EVENTS_SQL, pid)
            assert len(rows) == 2
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_ordered_by_filing_date_desc(self, pool):
        pid = await _insert_property(pool)
        try:
            await _insert_event(pool, pid, filing_date=date(2025, 1, 1))
            await _insert_event(pool, pid, filing_date=date(2025, 6, 1))
            rows = await pool.fetch(EVENTS_SQL, pid)
            assert rows[0]["filing_date"] == date(2025, 6, 1)
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_empty_for_property_with_no_events(self, pool):
        pid = await _insert_property(pool)
        try:
            rows = await pool.fetch(EVENTS_SQL, pid)
            assert rows == []
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_does_not_return_other_property_events(self, pool):
        pid_a = await _insert_property(pool)
        pid_b = await _insert_property(pool)
        try:
            await _insert_event(pool, pid_b, filing_date=date(2025, 5, 1))
            rows = await pool.fetch(EVENTS_SQL, pid_a)
            assert rows == []
        finally:
            await _cleanup(pool, pid_a)
            await _cleanup(pool, pid_b)


# ── ANALYSIS_SQL ──────────────────────────────────────────────────────────────

@skip_no_db
class TestAnalysisIntegration:
    @pytest.mark.asyncio
    async def test_returns_rehab_row(self, pool):
        pid = await _insert_property(pool)
        vid = await _insert_valuation(pool, pid)
        try:
            await _insert_analysis(pool, pid, vid, record_type="rehab")
            rows = await pool.fetch(ANALYSIS_SQL, pid)
            assert len(rows) == 1
            assert rows[0]["record_type"] == "rehab"
            assert rows[0]["rehab_level"] == "medium"
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_returns_mao_row(self, pool):
        pid = await _insert_property(pool)
        vid = await _insert_valuation(pool, pid)
        try:
            await _insert_analysis(pool, pid, vid, record_type="mao", mao=137000.0)
            rows = await pool.fetch(ANALYSIS_SQL, pid)
            assert len(rows) == 1
            assert rows[0]["record_type"] == "mao"
            assert float(rows[0]["mao"]) == pytest.approx(137000.0)
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_joins_valuation_arv(self, pool):
        pid = await _insert_property(pool)
        vid = await _insert_valuation(pool, pid, arv=260000.0)
        try:
            await _insert_analysis(pool, pid, vid, record_type="rehab")
            rows = await pool.fetch(ANALYSIS_SQL, pid)
            assert float(rows[0]["valuation_arv"]) == pytest.approx(260000.0)
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_returns_both_record_types(self, pool):
        pid = await _insert_property(pool)
        vid = await _insert_valuation(pool, pid)
        try:
            await _insert_analysis(pool, pid, vid, record_type="rehab")
            await _insert_analysis(pool, pid, vid, record_type="mao")
            rows = await pool.fetch(ANALYSIS_SQL, pid)
            types = {r["record_type"] for r in rows}
            assert types == {"rehab", "mao"}
        finally:
            await _cleanup(pool, pid)


# ── VALUATIONS_SQL + EQUITY_SQL ───────────────────────────────────────────────

@skip_no_db
class TestValuationsIntegration:
    @pytest.mark.asyncio
    async def test_returns_valuation_row(self, pool):
        pid = await _insert_property(pool)
        try:
            await _insert_valuation(pool, pid, arv=255000.0, avm=210000.0)
            rows = await pool.fetch(VALUATIONS_SQL, pid)
            assert len(rows) == 1
            assert float(rows[0]["arv"]) == pytest.approx(255000.0)
            assert float(rows[0]["avm"]) == pytest.approx(210000.0)
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_equity_sql_returns_score_fields(self, pool):
        pid = await _insert_property(pool)
        await _insert_score(pool, pid, equity_pct=45.0)
        try:
            row = await pool.fetchrow(EQUITY_SQL, pid)
            assert row is not None
            assert float(row["equity_pct"]) == pytest.approx(45.0)
            assert row["estimated_liens"] is not None
            assert row["tax_owed"] is not None
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_equity_sql_returns_none_for_unknown(self, pool):
        row = await pool.fetchrow(EQUITY_SQL, uuid.uuid4())
        assert row is None

    @pytest.mark.asyncio
    async def test_multiple_valuations_ordered_desc(self, pool):
        pid = await _insert_property(pool)
        try:
            vid1 = await _insert_valuation(pool, pid, arv=200000.0)
            await asyncio.sleep(0.01)
            vid2 = await _insert_valuation(pool, pid, arv=220000.0)
            rows = await pool.fetch(VALUATIONS_SQL, pid)
            assert len(rows) == 2
            # most recent first
            assert float(rows[0]["arv"]) == pytest.approx(220000.0)
        finally:
            await _cleanup(pool, pid)


# ── PROPERTY_EXISTS_SQL — 404 consistency ─────────────────────────────────────

@skip_no_db
class TestPropertyExistsIntegration:
    @pytest.mark.asyncio
    async def test_returns_row_for_known_property(self, pool):
        pid = await _insert_property(pool)
        try:
            row = await pool.fetchrow(PROPERTY_EXISTS_SQL, pid)
            assert row is not None
        finally:
            await _cleanup(pool, pid)

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_property(self, pool):
        row = await pool.fetchrow(PROPERTY_EXISTS_SQL, uuid.uuid4())
        assert row is None
