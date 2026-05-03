"""
Unit tests for the pre-foreclosure (Lis Pendens) district clerk HTML parser.

Tests table recognition, field extraction, keyword detection,
deduplication by instrument number, and dedup_key behavior.
"""

from datetime import date

import pytest

from ingestion.preforeclosure.parser import _detect_keywords, _parse_date, parse


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("01/20/2025",       date(2025, 1, 20)),
    ("01/20/25",         date(2025, 1, 20)),
    ("2025-01-20",       date(2025, 1, 20)),
    ("January 20, 2025", date(2025, 1, 20)),
    ("",                 None),
    ("bad",              None),
])
def test_parse_date(raw, expected):
    assert _parse_date(raw) == expected


# ---------------------------------------------------------------------------
# _detect_keywords
# ---------------------------------------------------------------------------

def test_detect_keywords_finds_lis_pendens():
    found = _detect_keywords("This is a Lis Pendens filing")
    assert "lis pendens" in [k.lower() for k in found]


def test_detect_keywords_returns_empty_for_unrelated():
    assert _detect_keywords("Regular civil case: boundary dispute between neighbors") == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clerk_table(headers: list[str], rows: list[list[str]]) -> bytes:
    header_cells = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for row in rows:
        cells = "".join(f"<td>{c}</td>" for c in row)
        body += f"<tr>{cells}</tr>"
    return f"<table><tr>{header_cells}</tr>{body}</table>".encode("utf-8")


# ---------------------------------------------------------------------------
# Standard district clerk table
# ---------------------------------------------------------------------------

def test_parse_standard_table():
    html = _clerk_table(
        ["Case Number", "Case Style", "Filed", "Instrument"],
        [
            ["2025-DC-0001", "Lis Pendens - JONES MARY vs WELLS FARGO", "02/01/2025", "INS-001"],
            ["2025-DC-0002", "Foreclosure Default - DOE JOHN vs BANK", "02/03/2025", "INS-002"],
        ],
    )
    events = parse(html, "Lis Pendens", "travis", "http://example.com/search")
    assert len(events) == 2
    assert events[0].lp_instrument_number == "INS-001"
    assert events[0].filing_date == date(2025, 2, 1)
    assert events[0].county == "travis"


def test_parse_keywords_detected_in_row():
    html = _clerk_table(
        ["Case Number", "Case Style", "Filed"],
        [["2025-DC-0003", "Lis Pendens Default SMITH vs BANK", "03/01/2025"]],
    )
    events = parse(html, "Lis Pendens", "hays", "http://example.com")
    assert len(events) == 1
    kws = [k.lower() for k in (events[0].lp_keywords or [])]
    assert "lis pendens" in kws


# ---------------------------------------------------------------------------
# Deduplication by instrument number
# ---------------------------------------------------------------------------

def test_parse_deduplicates_by_instrument_number():
    html = _clerk_table(
        ["Case Number", "Case Style", "Filed", "Instrument"],
        [
            ["2025-DC-0010", "Lis Pendens DUP", "01/01/2025", "DUP-INS-001"],
            ["2025-DC-0010", "Lis Pendens DUP", "01/01/2025", "DUP-INS-001"],
        ],
    )
    events = parse(html, "Lis Pendens", "travis", "http://example.com")
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_parse_empty_bytes_returns_empty():
    assert parse(b"", "Lis Pendens", "travis", "http://example.com") == []


def test_parse_no_matching_table_returns_empty():
    html = b"<html><body><p>No results found</p></body></html>"
    assert parse(html, "Lis Pendens", "travis", "http://example.com") == []


def test_parse_table_without_required_headers_returns_empty():
    html = _clerk_table(
        ["First Name", "Last Name"],
        [["John", "Doe"]],
    )
    assert parse(html, "Foreclosure", "travis", "http://example.com") == []


# ---------------------------------------------------------------------------
# dedup_key
# ---------------------------------------------------------------------------

def test_preforeclosure_dedup_key_requires_instrument():
    from ingestion.shared.models import PreforeclosureEvent
    e = PreforeclosureEvent(county="travis", filing_date=date(2025, 1, 1))
    assert e.dedup_key is None


def test_preforeclosure_dedup_key_requires_filing_date_when_no_instrument():
    from ingestion.shared.models import PreforeclosureEvent
    e = PreforeclosureEvent(county="travis")
    assert e.dedup_key is None


def test_preforeclosure_dedup_key_set_with_instrument():
    from ingestion.shared.models import PreforeclosureEvent
    e = PreforeclosureEvent(county="travis", lp_instrument_number="INS-001", filing_date=date(2025, 1, 15))
    assert e.dedup_key == "travis|preforeclosure|INS-001|2025-01-15"


def test_preforeclosure_dedup_key_includes_empty_date_when_only_instrument():
    from ingestion.shared.models import PreforeclosureEvent
    e = PreforeclosureEvent(county="hays", lp_instrument_number="INS-999")
    assert e.dedup_key == "hays|preforeclosure|INS-999|"
