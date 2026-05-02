"""
Test plan item: Run handler({"county": "travis"}, {}) for each pipeline against
a test DB and verify event rows are inserted.

Strategy: mock the scraper and parser layers (no live county sites) so that
each handler drives the full normalize → match_or_create → insert_event path
against the real Neon test branch.  Inserted rows are cleaned up by a fixture.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Must import handler modules before patch() can resolve their dotted paths
import ingestion.foreclosure.handler       # noqa: F401
import ingestion.probate.handler           # noqa: F401
import ingestion.tax_delinquency.handler   # noqa: F401
import ingestion.preforeclosure.handler    # noqa: F401

from ingestion.shared.db import close_pool, get_pool
from ingestion.shared.models import (
    ForeclosureEvent,
    ForeclosureStage,
    ProbateEvent,
    PreforeclosureEvent,
    TaxDelinquencyEvent,
)


# ---------------------------------------------------------------------------
# Fixture — tags inserted rows via source_url for targeted cleanup
# ---------------------------------------------------------------------------

@pytest.fixture
async def run_id():
    rid = str(uuid.uuid4())
    yield rid
    pool = await get_pool()
    await pool.execute("DELETE FROM events     WHERE source_url LIKE $1", f"%{rid}%")
    await pool.execute("DELETE FROM properties WHERE address    LIKE $1", f"%{rid}%")
    await close_pool()


# ---------------------------------------------------------------------------
# Foreclosure handler integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_foreclosure_handler_inserts_travis_events(run_id):
    events = [
        ForeclosureEvent(
            county="travis",
            filing_date=date(2025, 3, 1),
            auction_date=date(2025, 4, 1),
            borrower_name=f"Integration Borrower {run_id}",
            lender_name="Test Bank",
            address=f"501 Congress Ave Austin TX 78701",
            foreclosure_stage=ForeclosureStage.NTS,
            source_url=f"https://example.com/{run_id}",
        )
    ]

    with (
        patch("ingestion.foreclosure.handler.ForeclosureScraper") as MockScraper,
        patch("ingestion.foreclosure.handler.parse_pdf", return_value=events),
        patch("ingestion.foreclosure.handler.COUNTY_MAP") as mock_map,
        patch("ingestion.foreclosure.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
    ):
        mock_config = MagicMock()
        mock_config.listing_url = "http://example.com"
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = [(f"https://example.com/{run_id}", b"%PDF fake")]
        MockScraper.return_value = scraper_instance

        mock_addr = MagicMock()
        mock_addr.normalized = f"501 Congress Ave, Austin, TX, 78701 {run_id}"
        mock_addr.city = "Austin"
        mock_addr.zip_code = "78701"
        mock_usps.return_value = mock_addr

        from ingestion.foreclosure.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 0, f"Unexpected errors: {stats}"
    assert stats["inserted"] >= 1, f"Expected at least 1 inserted: {stats}"

    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM events WHERE source_url LIKE $1 AND event_type='foreclosure'",
        f"%{run_id}%",
    )
    assert count >= 1


# ---------------------------------------------------------------------------
# Tax delinquency handler integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tax_handler_inserts_travis_events(run_id):
    events = [
        TaxDelinquencyEvent(
            county="travis",
            filing_date=date(2025, 1, 1),
            owner_name=f"Tax Owner {run_id}",
            address=f"200 Lavaca St Austin TX 78701",
            tax_amount_owed=4500.00,
            years_delinquent=3,
            source_url=f"https://example.com/{run_id}",
        )
    ]

    with (
        patch("ingestion.tax_delinquency.handler.TaxDelinquencyScraper") as MockScraper,
        patch("ingestion.tax_delinquency.handler.parse", return_value=events),
        patch("ingestion.tax_delinquency.handler.TAX_COUNTY_MAP") as mock_map,
        patch("ingestion.tax_delinquency.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
    ):
        mock_config = MagicMock()
        mock_config.listing_url = "http://example.com"
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = ("csv", b"fake,csv,data")
        MockScraper.return_value = scraper_instance

        mock_addr = MagicMock()
        mock_addr.normalized = f"200 Lavaca St, Austin, TX, 78701 {run_id}"
        mock_addr.city = "Austin"
        mock_addr.zip_code = "78701"
        mock_usps.return_value = mock_addr

        from ingestion.tax_delinquency.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 0, f"Unexpected errors: {stats}"
    assert stats["inserted"] >= 1

    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM events WHERE source_url LIKE $1 AND event_type='tax_delinquency'",
        f"%{run_id}%",
    )
    assert count >= 1


# ---------------------------------------------------------------------------
# Probate handler integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_probate_handler_inserts_travis_events(run_id):
    events = [
        ProbateEvent(
            county="travis",
            filing_date=date(2025, 2, 15),
            case_number=f"PROB-{run_id[:8]}",
            decedent_name=f"Decedent {run_id}",
            executor_name="Executor Name",
            source_url=f"https://example.com/{run_id}",
        )
    ]

    with (
        patch("ingestion.probate.handler.OdysseyProbateScraper") as MockScraper,
        patch("ingestion.probate.handler.parse", return_value=events),
        patch("ingestion.probate.handler.PROBATE_COUNTY_MAP") as mock_map,
        patch("ingestion.probate.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
    ):
        mock_config = MagicMock()
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = [(b"<html>fake</html>", "Probate")]
        MockScraper.return_value = scraper_instance

        mock_addr = MagicMock()
        mock_addr.normalized = None  # no address on probate — tests the None path
        mock_addr.city = None
        mock_addr.zip_code = None
        mock_usps.return_value = mock_addr

        from ingestion.probate.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 0, f"Unexpected errors: {stats}"
    assert stats["inserted"] >= 1

    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM events WHERE case_number LIKE $1 AND event_type='probate'",
        f"PROB-{run_id[:8]}%",
    )
    assert count >= 1


# ---------------------------------------------------------------------------
# Pre-foreclosure handler integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preforeclosure_handler_inserts_travis_events(run_id):
    events = [
        PreforeclosureEvent(
            county="travis",
            filing_date=date(2025, 3, 20),
            borrower_name=f"LP Borrower {run_id}",
            lp_instrument_number=f"LP-{run_id[:8]}",
            address=f"750 E 2nd St Austin TX 78702",
            lp_keywords=["lis pendens", "foreclosure"],
            source_url=f"https://example.com/{run_id}",
        )
    ]

    with (
        patch("ingestion.preforeclosure.handler.PreforeclosureScraper") as MockScraper,
        patch("ingestion.preforeclosure.handler.parse", return_value=events),
        patch("ingestion.preforeclosure.handler.PREFORECLOSURE_COUNTY_MAP") as mock_map,
        patch("ingestion.preforeclosure.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
    ):
        mock_config = MagicMock()
        mock_config.search_url = "http://example.com"
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = [(b"<html>fake</html>", "lis pendens")]
        MockScraper.return_value = scraper_instance

        mock_addr = MagicMock()
        mock_addr.normalized = f"750 E 2nd St, Austin, TX, 78702 {run_id}"
        mock_addr.city = "Austin"
        mock_addr.zip_code = "78702"
        mock_usps.return_value = mock_addr

        from ingestion.preforeclosure.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 0, f"Unexpected errors: {stats}"
    assert stats["inserted"] >= 1

    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM events WHERE lp_instrument_number LIKE $1 AND event_type='preforeclosure'",
        f"LP-{run_id[:8]}%",
    )
    assert count >= 1


# ---------------------------------------------------------------------------
# Re-run: handler with same data → skipped (dedup)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handler_reruns_skip_duplicates(run_id):
    """Running the same handler twice must insert once and skip on the second run."""
    events = [
        ForeclosureEvent(
            county="travis",
            filing_date=date(2025, 5, 1),
            borrower_name=f"Dedup Borrower {run_id}",
            address="123 Dedup St Austin TX 78701",
            source_url=f"https://example.com/{run_id}",
        )
    ]

    patch_args = dict(
        scraper="ingestion.foreclosure.handler.ForeclosureScraper",
        parse="ingestion.foreclosure.handler.parse_pdf",
        county_map="ingestion.foreclosure.handler.COUNTY_MAP",
        usps="ingestion.foreclosure.handler.usps_validate",
    )

    def _run_handler():
        from ingestion.foreclosure.handler import _process_county
        import asyncio
        return asyncio.get_event_loop().run_until_complete(_process_county("travis"))

    mock_addr = MagicMock()
    mock_addr.normalized = f"123 Dedup St, Austin, TX, 78701 {run_id}"
    mock_addr.city = "Austin"
    mock_addr.zip_code = "78701"

    for run_num in range(2):
        with (
            patch(patch_args["scraper"]) as MockScraper,
            patch(patch_args["parse"], return_value=events),
            patch(patch_args["county_map"]) as mock_map,
            patch(patch_args["usps"], new_callable=AsyncMock, return_value=mock_addr),
        ):
            mock_config = MagicMock()
            mock_config.listing_url = "http://example.com"
            mock_map.get.return_value = mock_config

            scraper_instance = AsyncMock()
            scraper_instance.run.return_value = [(f"https://example.com/{run_id}", b"%PDF fake")]
            MockScraper.return_value = scraper_instance

            from ingestion.foreclosure.handler import _process_county
            stats = await _process_county("travis")

        if run_num == 0:
            assert stats["inserted"] == 1, f"First run should insert 1: {stats}"
        else:
            assert stats["inserted"] == 0, f"Second run should skip (dedup): {stats}"
            assert stats["skipped"] == 1

    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM events WHERE source_url LIKE $1",
        f"%{run_id}%",
    )
    assert count == 1, "Exactly 1 row must exist after two identical runs"
