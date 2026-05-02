"""
Test plan items:
  - Verify duplicate events are skipped (dedup_key partial index)
  - Run db/migrations/001-005 in order on a clean Postgres instance (schema verified here)

Uses the Neon test branch; DATABASE_URL is set by conftest.py.
"""

import uuid
from datetime import date

import asyncpg
import pytest

from ingestion.shared.db import close_pool, get_pool, insert_event, upsert_property


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def cleanup_test_rows(request):
    """Delete any rows this test inserted, keyed by a unique run_id tag in source_url."""
    run_id = str(uuid.uuid4())
    request.node._run_id = run_id
    yield run_id
    pool = await get_pool()
    await pool.execute("DELETE FROM events    WHERE source_url LIKE $1", f"%{run_id}%")
    await pool.execute("DELETE FROM properties WHERE address LIKE $1", f"%{run_id}%")
    await close_pool()


# ---------------------------------------------------------------------------
# Schema sanity (migration verification)
# ---------------------------------------------------------------------------

async def test_schema_tables_exist():
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' ORDER BY table_name"
    )
    names = {r["table_name"] for r in rows}
    expected = {
        "properties", "events", "property_scores", "valuations",
        "analysis", "users", "saved_properties", "notes",
        "search_filters", "alerts", "alert_subscriptions",
    }
    assert expected.issubset(names), f"Missing tables: {expected - names}"


async def test_dedup_key_partial_index_exists():
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE tablename='events' AND indexname='idx_events_dedup_key'"
    )
    assert row is not None, "Partial unique index idx_events_dedup_key not found"
    assert "WHERE" in row["indexdef"], "Index must be partial (WHERE clause)"
    assert "dedup_key IS NOT NULL" in row["indexdef"]


# ---------------------------------------------------------------------------
# upsert_property helper
# ---------------------------------------------------------------------------

async def _make_property(pool, run_id: str) -> str:
    return await upsert_property(pool, {
        "apn": f"TEST-APN-{run_id}",
        "address": f"100 Test St {run_id}",
        "address_norm": f"100 Test St {run_id}, Austin, TX, 78701",
        "city": "Austin",
        "county": "travis",
        "state": "TX",
        "zip_code": "78701",
    })


# ---------------------------------------------------------------------------
# Dedup tests
# ---------------------------------------------------------------------------

async def test_insert_event_returns_uuid_on_first_insert(cleanup_test_rows):
    run_id = cleanup_test_rows
    pool = await get_pool()
    prop_id = await _make_property(pool, run_id)

    event_id = await insert_event(pool, {
        "property_id": prop_id,
        "event_type": "foreclosure",
        "county": "travis",
        "filing_date": date(2025, 1, 15),
        "borrower_name": "Smith John",
        "dedup_key": f"travis|foreclosure|2025-01-15|smith john|{run_id}",
        "source_url": f"https://example.com/{run_id}",
    })
    assert event_id is not None
    assert len(event_id) == 36  # UUID


async def test_duplicate_dedup_key_returns_none(cleanup_test_rows):
    """Second insert with same dedup_key must be silently skipped (returns None)."""
    run_id = cleanup_test_rows
    pool = await get_pool()
    prop_id = await _make_property(pool, run_id)

    key = f"travis|foreclosure|2025-02-01|jones bob|{run_id}"
    data = {
        "property_id": prop_id,
        "event_type": "foreclosure",
        "county": "travis",
        "filing_date": date(2025, 2, 1),
        "borrower_name": "Jones Bob",
        "dedup_key": key,
        "source_url": f"https://example.com/{run_id}",
    }

    first  = await insert_event(pool, data)
    second = await insert_event(pool, data)

    assert first  is not None, "First insert should succeed"
    assert second is None,     "Duplicate insert should return None (skipped)"


async def test_only_one_row_in_db_after_duplicate(cleanup_test_rows):
    """DB row count must be 1 even after multiple inserts with the same dedup_key."""
    run_id = cleanup_test_rows
    pool = await get_pool()
    prop_id = await _make_property(pool, run_id)

    key = f"travis|tax_delinquency|2025-03-01||{run_id}"
    data = {
        "property_id": prop_id,
        "event_type": "tax_delinquency",
        "county": "travis",
        "dedup_key": key,
        "source_url": f"https://example.com/{run_id}",
    }

    for _ in range(5):
        await insert_event(pool, data)

    count = await pool.fetchval(
        "SELECT COUNT(*) FROM events WHERE dedup_key = $1", key
    )
    assert count == 1


async def test_null_dedup_key_allows_multiple_rows(cleanup_test_rows):
    """
    Events with dedup_key=None must NOT block each other.
    The partial index (WHERE dedup_key IS NOT NULL) intentionally
    allows unlimited NULLs so we don't silently drop valid events
    that lack key fields.
    """
    run_id = cleanup_test_rows
    pool = await get_pool()
    prop_id = await _make_property(pool, run_id)

    data = {
        "property_id": prop_id,
        "event_type": "probate",
        "county": "travis",
        "dedup_key": None,  # missing source fields → no dedup key
        "source_url": f"https://example.com/{run_id}",
    }

    id1 = await insert_event(pool, {**data})
    id2 = await insert_event(pool, {**data})

    assert id1 is not None
    assert id2 is not None
    assert id1 != id2, "Two NULL-key events must create two distinct rows"


# ---------------------------------------------------------------------------
# upsert_property — ON CONFLICT preserves existing data via COALESCE
# ---------------------------------------------------------------------------

async def test_upsert_property_preserves_existing_sqft(cleanup_test_rows):
    run_id = cleanup_test_rows
    pool = await get_pool()
    apn = f"COALESCE-TEST-{run_id}"

    # First insert with sqft
    pid = await upsert_property(pool, {
        "apn": apn,
        "address": f"200 Coalesce Rd {run_id}",
        "city": "Austin", "county": "travis", "state": "TX",
        "sqft": 1800,
    })

    # Second upsert without sqft — should not overwrite with NULL
    await upsert_property(pool, {
        "apn": apn,
        "address": f"200 Coalesce Rd {run_id}",
        "city": "Austin", "county": "travis", "state": "TX",
        "sqft": None,
    })

    row = await pool.fetchrow("SELECT sqft FROM properties WHERE id = $1", uuid.UUID(pid))
    assert row["sqft"] == 1800, "COALESCE upsert must preserve existing sqft"
