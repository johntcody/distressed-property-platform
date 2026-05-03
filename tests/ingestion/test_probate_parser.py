"""
Unit tests for the probate Odyssey HTML parser.

Tests table recognition, field extraction, date parsing,
deduplication by case_number, and dedup_key behavior.
"""

from datetime import date

import pytest

from ingestion.probate.parser import _parse_date, parse


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("01/15/2025", date(2025, 1, 15)),
    ("01/15/25",   date(2025, 1, 15)),
    ("2025-01-15", date(2025, 1, 15)),
    ("",           None),
    (None,         None),
    ("bad date",   None),
])
def test_parse_date(raw, expected):
    assert _parse_date(raw) == expected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _odyssey_table(headers: list[str], rows: list[list[str]]) -> bytes:
    header_cells = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for row in rows:
        cells = "".join(f"<td>{c}</td>" for c in row)
        body += f"<tr>{cells}</tr>"
    return f"<table><tr>{header_cells}</tr>{body}</table>".encode("utf-8")


# ---------------------------------------------------------------------------
# Standard Odyssey table
# ---------------------------------------------------------------------------

def test_parse_standard_odyssey_table():
    html = _odyssey_table(
        ["Case Number", "Style", "Filed", "Case Type"],
        [
            ["2025-PR-0001", "Estate of JANE DOE", "01/10/2025", "Probate"],
            ["2025-PR-0002", "Estate of JOHN SMITH", "01/12/2025", "Probate"],
        ],
    )
    events = parse(html, "Probate", "travis", "http://example.com/search")
    assert len(events) == 2
    assert events[0].case_number == "2025-PR-0001"
    assert events[0].decedent_name == "JANE DOE"
    assert events[0].filing_date == date(2025, 1, 10)
    assert events[0].county == "travis"


def test_parse_extracts_executor_from_style():
    html = _odyssey_table(
        ["Case Number", "Style", "Filed", "Case Type"],
        [["2025-PR-0010", "Estate of BOB WHITE; Executor: ALICE WHITE", "02/01/2025", "Estate"]],
    )
    events = parse(html, "Estate", "hays", "http://example.com")
    assert len(events) == 1
    assert events[0].executor_name and "ALICE WHITE" in events[0].executor_name


# ---------------------------------------------------------------------------
# Deduplication by case_number
# ---------------------------------------------------------------------------

def test_parse_deduplicates_by_case_number():
    html = _odyssey_table(
        ["Case Number", "Style", "Filed", "Case Type"],
        [
            ["2025-PR-0042", "Estate of DUP ONE", "01/01/2025", "Probate"],
            ["2025-PR-0042", "Estate of DUP ONE", "01/01/2025", "Probate"],
        ],
    )
    events = parse(html, "Probate", "travis", "http://example.com")
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_parse_empty_bytes_returns_empty():
    assert parse(b"", "Probate", "travis", "http://example.com") == []


def test_parse_no_matching_table_returns_empty():
    html = b"<html><body><p>No results</p></body></html>"
    assert parse(html, "Probate", "travis", "http://example.com") == []


def test_parse_table_without_required_headers_returns_empty():
    html = _odyssey_table(
        ["First Name", "Last Name", "Amount"],
        [["John", "Doe", "500"]],
    )
    assert parse(html, "Probate", "travis", "http://example.com") == []


# ---------------------------------------------------------------------------
# dedup_key
# ---------------------------------------------------------------------------

def test_probate_dedup_key_requires_case_number():
    from ingestion.shared.models import ProbateEvent
    e = ProbateEvent(county="travis", filing_date=date(2025, 1, 1))
    assert e.dedup_key is None


def test_probate_dedup_key_set_when_case_number_present():
    from ingestion.shared.models import ProbateEvent
    e = ProbateEvent(county="travis", case_number="2025-PR-0001")
    assert e.dedup_key == "travis|probate|2025-PR-0001"


def test_probate_dedup_key_ignores_whitespace_in_case_number():
    from ingestion.shared.models import ProbateEvent
    e = ProbateEvent(county="hays", case_number="  2025-PR-0001  ")
    assert e.dedup_key == "hays|probate|2025-PR-0001"
