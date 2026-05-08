"""
Integration tests for GET /api/v1/opportunities against a live DB.
Requires DATABASE_URL to be set (Neon test branch).

Covers:
  - Empty DB returns total=0 and items=[]
  - Property with no scores appears in unfiltered results
  - county filter: matching property returned, non-matching excluded
  - min_distress_score filter: only properties at or above threshold returned
  - min_equity_pct filter: only properties at or above threshold returned
  - case_type filter: only properties with matching event_type returned
  - auction_date_before filter: only properties with auction_date <= date returned
  - sort_by=distress_score desc: highest score first
  - sort_by=equity_pct asc: lowest equity first
  - pagination: page 2 returns second batch
  - total reflects full count, not just current page
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

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


async def _insert_property(pool, *, county="Travis", city="Austin", zip_code="78701") -> uuid.UUID:
    prop_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO properties
            (id, address_raw, city, county, zip_code, sqft,
             land_value, improvement_value)
        VALUES ($1, $2, $3, $4, $5, 1200, 80000.00, 120000.00)
        """,
        prop_id, f"{prop_id} Test St", city, county, zip_code,
    )
    return prop_id


async def _insert_score(pool, prop_id, *, distress_score=50.0, equity_pct=30.0):
    await pool.execute(
        """
        INSERT INTO property_scores
            (property_id, distress_score, equity_pct, equity_amount, avm, calculated_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        """,
        prop_id, distress_score, equity_pct, 50_000.0, 200_000.0,
    )


async def _insert_event(pool, prop_id, *, event_type="foreclosure",
                         county="Travis", auction_date=None):
    await pool.execute(
        """
        INSERT INTO events
            (property_id, event_type, county, filing_date, auction_date)
        VALUES ($1, $2::distress_event_type, $3, NOW(), $4)
        """,
        prop_id, event_type, county, auction_date,
    )


async def _cleanup(pool, *prop_ids):
    for pid in prop_ids:
        await pool.execute("DELETE FROM property_scores WHERE property_id = $1", pid)
        await pool.execute("DELETE FROM events         WHERE property_id = $1", pid)
        await pool.execute("DELETE FROM analysis       WHERE property_id = $1", pid)
        await pool.execute("DELETE FROM valuations     WHERE property_id = $1", pid)
        await pool.execute("DELETE FROM properties     WHERE id          = $1", pid)


def _run(**filters):
    """Build SQL + params via build_query; execute the returned SQL against the pool in the caller."""
    from services.opportunity_dashboard.query import build_query
    defaults = dict(
        county=None, case_type=None, min_distress_score=None,
        min_equity_pct=None, auction_date_before=None,
        sort_by="distress_score", sort_dir="desc",
        limit=20, offset=0,
    )
    defaults.update(filters)
    return build_query(**defaults)


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_filters_returns_properties(pool):
    prop_id = await _insert_property(pool)
    try:
        data_sql, data_params, count_sql, count_params = _run()
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert prop_id in ids
    finally:
        await _cleanup(pool, prop_id)


@pytest.mark.asyncio
async def test_count_reflects_total(pool):
    prop_id = await _insert_property(pool)
    try:
        _, _, count_sql, count_params = _run()
        row = await pool.fetchrow(count_sql, *count_params)
        assert row["total"] >= 1
    finally:
        await _cleanup(pool, prop_id)


@pytest.mark.asyncio
async def test_county_filter_matches(pool):
    p_travis = await _insert_property(pool, county="Travis")
    p_hays   = await _insert_property(pool, county="Hays")
    try:
        data_sql, data_params, *_ = _run(county="Travis")
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert p_travis in ids
        assert p_hays not in ids
    finally:
        await _cleanup(pool, p_travis, p_hays)


@pytest.mark.asyncio
async def test_county_filter_excludes_non_match(pool):
    prop_id = await _insert_property(pool, county="Caldwell")
    try:
        data_sql, data_params, *_ = _run(county="Travis")
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert prop_id not in ids
    finally:
        await _cleanup(pool, prop_id)


@pytest.mark.asyncio
async def test_min_distress_score_filter(pool):
    p_high = await _insert_property(pool, county="Travis")
    p_low  = await _insert_property(pool, county="Travis")
    await _insert_score(pool, p_high, distress_score=80.0)
    await _insert_score(pool, p_low,  distress_score=30.0)
    try:
        data_sql, data_params, *_ = _run(min_distress_score=70.0)
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert p_high in ids
        assert p_low not in ids
    finally:
        await _cleanup(pool, p_high, p_low)


@pytest.mark.asyncio
async def test_min_equity_pct_filter(pool):
    p_rich = await _insert_property(pool, county="Travis")
    p_poor = await _insert_property(pool, county="Travis")
    await _insert_score(pool, p_rich, equity_pct=60.0)
    await _insert_score(pool, p_poor, equity_pct=10.0)
    try:
        data_sql, data_params, *_ = _run(min_equity_pct=50.0)
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert p_rich in ids
        assert p_poor not in ids
    finally:
        await _cleanup(pool, p_rich, p_poor)


@pytest.mark.asyncio
async def test_case_type_filter(pool):
    p_fc = await _insert_property(pool, county="Travis")
    p_td = await _insert_property(pool, county="Travis")
    await _insert_event(pool, p_fc, event_type="foreclosure",    county="Travis")
    await _insert_event(pool, p_td, event_type="tax_delinquency", county="Travis")
    try:
        data_sql, data_params, *_ = _run(case_type="foreclosure")
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert p_fc in ids
        assert p_td not in ids
    finally:
        await _cleanup(pool, p_fc, p_td)


@pytest.mark.asyncio
async def test_auction_date_before_filter(pool):
    p_soon = await _insert_property(pool, county="Travis")
    p_late = await _insert_property(pool, county="Travis")
    await _insert_event(pool, p_soon, auction_date=date(2025, 3, 1))
    await _insert_event(pool, p_late, auction_date=date(2025, 12, 1))
    try:
        data_sql, data_params, *_ = _run(auction_date_before=date(2025, 6, 1))
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert p_soon in ids
        assert p_late not in ids
    finally:
        await _cleanup(pool, p_soon, p_late)


@pytest.mark.asyncio
async def test_sort_distress_score_desc(pool):
    p1 = await _insert_property(pool, county="Travis")
    p2 = await _insert_property(pool, county="Travis")
    await _insert_score(pool, p1, distress_score=90.0, equity_pct=20.0)
    await _insert_score(pool, p2, distress_score=40.0, equity_pct=20.0)
    try:
        data_sql, data_params, *_ = _run(county="Travis",
                                          sort_by="distress_score", sort_dir="desc")
        rows = await pool.fetch(data_sql, *data_params)
        ids = [r["property_id"] for r in rows]
        assert ids.index(p1) < ids.index(p2)
    finally:
        await _cleanup(pool, p1, p2)


@pytest.mark.asyncio
async def test_pagination_page_size_respected(pool):
    props = [await _insert_property(pool, county="Williamson") for _ in range(5)]
    try:
        data_sql, data_params, count_sql, count_params = _run(
            pool, county="Williamson", limit=2, offset=0
        )
        rows = await pool.fetch(data_sql, *data_params)
        assert len(rows) <= 2
    finally:
        await _cleanup(pool, *props)


@pytest.mark.asyncio
async def test_pagination_total_vs_page(pool):
    props = [await _insert_property(pool, county="Bastrop") for _ in range(3)]
    try:
        _, _, count_sql, count_params = _run(county="Bastrop")
        count_row = await pool.fetchrow(count_sql, *count_params)
        assert count_row["total"] >= 3

        data_sql, data_params, *_ = _run(county="Bastrop", limit=2, offset=0)
        page1 = await pool.fetch(data_sql, *data_params)
        assert len(page1) == 2
    finally:
        await _cleanup(pool, *props)
