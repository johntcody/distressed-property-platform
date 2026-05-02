"""
Test plan item: Verify a bad record does not abort the full county run (per-record try/except).

All four handlers wrap each event in an isolated try/except so that a DB error on
record N does not prevent records N+1..M from being processed.

Strategy: mock insert_event to raise asyncpg.PostgresError on the first call,
then succeed on subsequent calls.  Assert the handler returns stats with
errors=1 and inserted > 0 for the remaining records.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

# Must import handler modules before patch() can resolve their dotted paths
import ingestion.foreclosure.handler  # noqa: F401
import ingestion.probate.handler      # noqa: F401
import ingestion.tax_delinquency.handler   # noqa: F401
import ingestion.preforeclosure.handler    # noqa: F401

from ingestion.shared.models import (
    ForeclosureEvent,
    ForeclosureStage,
    ProbateEvent,
    PreforeclosureEvent,
    TaxDelinquencyEvent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_foreclosure_events(n: int):
    return [
        ForeclosureEvent(
            county="travis",
            filing_date=date(2025, 1, i + 1),
            borrower_name=f"Borrower {i}",
            address=f"{100 + i} Main St Austin TX",
            foreclosure_stage=ForeclosureStage.NTS,
        )
        for i in range(n)
    ]


def _make_probate_events(n: int):
    return [
        ProbateEvent(
            county="travis",
            filing_date=date(2025, 2, i + 1),
            case_number=f"PROB-{i:04d}",
            decedent_name=f"Decedent {i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Foreclosure handler — error isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_foreclosure_handler_continues_after_db_error():
    """A postgres error on event[0] must not abort processing of events[1..4]."""
    events = _make_foreclosure_events(5)
    call_count = 0

    async def _flaky_insert(pool, data):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise asyncpg.PostgresError("mock constraint violation")
        return f"mock-uuid-{call_count}"

    mock_pool = AsyncMock()

    with (
        patch("ingestion.foreclosure.handler.get_pool", return_value=mock_pool),
        patch("ingestion.foreclosure.handler.close_pool", new_callable=AsyncMock),
        patch("ingestion.foreclosure.handler.ForeclosureScraper") as MockScraper,
        patch("ingestion.foreclosure.handler.parse_pdf", return_value=events),
        patch("ingestion.foreclosure.handler.parse_address") as mock_parse,
        patch("ingestion.foreclosure.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
        patch("ingestion.foreclosure.handler.match_or_create_property", new_callable=AsyncMock, return_value="prop-uuid"),
        patch("ingestion.foreclosure.handler.insert_event", side_effect=_flaky_insert),
        patch("ingestion.foreclosure.handler.COUNTY_MAP") as mock_map,
    ):
        mock_addr = MagicMock()
        mock_addr.normalized = "100 Main St, Austin, TX, 78701"
        mock_addr.city = "Austin"
        mock_addr.zip_code = "78701"
        mock_parse.return_value = mock_addr
        mock_usps.return_value = mock_addr

        mock_config = MagicMock()
        mock_config.listing_url = "http://example.com"
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = [("http://example.com/test.pdf", b"%PDF fake")]
        MockScraper.return_value = scraper_instance

        from ingestion.foreclosure.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 1,   f"Expected 1 error, got {stats['errors']}"
    assert stats["inserted"] == 4, f"Expected 4 inserted, got {stats['inserted']}"
    assert stats["parsed"] == 5


# ---------------------------------------------------------------------------
# Probate handler — error isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_probate_handler_continues_after_db_error():
    events = _make_probate_events(3)
    call_count = 0

    async def _flaky_insert(pool, data):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise asyncpg.PostgresError("mock FK violation")
        return f"mock-uuid-{call_count}"

    mock_pool = AsyncMock()

    with (
        patch("ingestion.probate.handler.get_pool", return_value=mock_pool),
        patch("ingestion.probate.handler.close_pool", new_callable=AsyncMock),
        patch("ingestion.probate.handler.OdysseyProbateScraper") as MockScraper,
        patch("ingestion.probate.handler.parse") as mock_parse_fn,
        patch("ingestion.probate.handler.parse_address") as mock_pa,
        patch("ingestion.probate.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
        patch("ingestion.probate.handler.match_or_create_property", new_callable=AsyncMock, return_value="prop-uuid"),
        patch("ingestion.probate.handler.insert_event", side_effect=_flaky_insert),
        patch("ingestion.probate.handler.PROBATE_COUNTY_MAP") as mock_map,
    ):
        mock_addr = MagicMock()
        mock_addr.normalized = "100 Main St, Austin, TX, 78701"
        mock_addr.city = "Austin"
        mock_addr.zip_code = "78701"
        mock_pa.return_value = mock_addr
        mock_usps.return_value = mock_addr

        mock_config = MagicMock()
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = [(b"<html>fake</html>", "Probate")]
        MockScraper.return_value = scraper_instance

        mock_parse_fn.return_value = events

        from ingestion.probate.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 1
    assert stats["inserted"] == 2


# ---------------------------------------------------------------------------
# Tax delinquency handler — error isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tax_handler_continues_after_db_error():
    events = [
        TaxDelinquencyEvent(
            county="travis",
            owner_name=f"Owner {i}",
            address=f"{200 + i} Oak Ave Austin TX",
            tax_amount_owed=1000.0 * (i + 1),
        )
        for i in range(4)
    ]
    call_count = 0

    async def _flaky_insert(pool, data):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise asyncpg.PostgresError("mock error")
        return f"mock-uuid-{call_count}"

    mock_pool = AsyncMock()

    with (
        patch("ingestion.tax_delinquency.handler.get_pool", return_value=mock_pool),
        patch("ingestion.tax_delinquency.handler.close_pool", new_callable=AsyncMock),
        patch("ingestion.tax_delinquency.handler.TaxDelinquencyScraper") as MockScraper,
        patch("ingestion.tax_delinquency.handler.parse", return_value=events),
        patch("ingestion.tax_delinquency.handler.parse_address") as mock_pa,
        patch("ingestion.tax_delinquency.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
        patch("ingestion.tax_delinquency.handler.match_or_create_property", new_callable=AsyncMock, return_value="prop-uuid"),
        patch("ingestion.tax_delinquency.handler.insert_event", side_effect=_flaky_insert),
        patch("ingestion.tax_delinquency.handler.TAX_COUNTY_MAP") as mock_map,
    ):
        mock_addr = MagicMock()
        mock_addr.normalized = "200 Oak Ave, Austin, TX, 78702"
        mock_addr.city = "Austin"
        mock_addr.zip_code = "78702"
        mock_pa.return_value = mock_addr
        mock_usps.return_value = mock_addr

        mock_config = MagicMock()
        mock_config.listing_url = "http://example.com"
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = ("csv", b"fake,csv")
        MockScraper.return_value = scraper_instance

        from ingestion.tax_delinquency.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 1
    assert stats["inserted"] == 3


# ---------------------------------------------------------------------------
# Pre-foreclosure handler — error isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preforeclosure_handler_continues_after_db_error():
    events = [
        PreforeclosureEvent(
            county="travis",
            borrower_name=f"Borrower {i}",
            lp_instrument_number=f"INST-{i:04d}",
            address=f"{300 + i} Elm St Austin TX",
        )
        for i in range(3)
    ]
    call_count = 0

    async def _flaky_insert(pool, data):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise asyncpg.PostgresError("mock error")
        return f"mock-uuid-{call_count}"

    mock_pool = AsyncMock()

    with (
        patch("ingestion.preforeclosure.handler.get_pool", return_value=mock_pool),
        patch("ingestion.preforeclosure.handler.close_pool", new_callable=AsyncMock),
        patch("ingestion.preforeclosure.handler.PreforeclosureScraper") as MockScraper,
        patch("ingestion.preforeclosure.handler.parse") as mock_parse_fn,
        patch("ingestion.preforeclosure.handler.parse_address") as mock_pa,
        patch("ingestion.preforeclosure.handler.usps_validate", new_callable=AsyncMock) as mock_usps,
        patch("ingestion.preforeclosure.handler.match_or_create_property", new_callable=AsyncMock, return_value="prop-uuid"),
        patch("ingestion.preforeclosure.handler.insert_event", side_effect=_flaky_insert),
        patch("ingestion.preforeclosure.handler.PREFORECLOSURE_COUNTY_MAP") as mock_map,
    ):
        mock_addr = MagicMock()
        mock_addr.normalized = "300 Elm St, Austin, TX, 78703"
        mock_addr.city = "Austin"
        mock_addr.zip_code = "78703"
        mock_pa.return_value = mock_addr
        mock_usps.return_value = mock_addr

        mock_config = MagicMock()
        mock_config.search_url = "http://example.com"
        mock_map.get.return_value = mock_config

        scraper_instance = AsyncMock()
        scraper_instance.run.return_value = [(b"<html>fake</html>", "lis pendens")]
        MockScraper.return_value = scraper_instance

        mock_parse_fn.return_value = events

        from ingestion.preforeclosure.handler import _process_county
        stats = await _process_county("travis")

    assert stats["errors"] == 1
    assert stats["inserted"] == 2
