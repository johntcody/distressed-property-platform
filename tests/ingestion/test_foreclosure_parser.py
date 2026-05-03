"""
Unit tests for the foreclosure PDF parser.

Tests regex field extraction, date parsing, stage detection,
block splitting, and dedup_key behavior.
"""

from datetime import date

import pytest

from ingestion.foreclosure.parser import (
    _detect_stage,
    _first_match,
    _parse_date,
    _parse_loan_amount,
    _RE_BORROWER,
    _RE_LENDER,
    _RE_TRUSTEE,
    _RE_AUCTION,
    _RE_FILING,
    parse_pdf,
)
from ingestion.shared.models import ForeclosureStage


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("January 5, 2025",   date(2025, 1, 5)),
    ("January 5 2025",    date(2025, 1, 5)),
    ("01/05/2025",        date(2025, 1, 5)),
    ("01/05/25",          date(2025, 1, 5)),
    ("",                  None),
    ("not a date",        None),
])
def test_parse_date(raw, expected):
    assert _parse_date(raw) == expected


# ---------------------------------------------------------------------------
# _first_match
# ---------------------------------------------------------------------------

def test_first_match_borrower():
    text = "Grantor: JOHN DOE\nSome other content"
    assert _first_match(_RE_BORROWER, text) == "JOHN DOE"


def test_first_match_lender():
    text = "Beneficiary: WELLS FARGO BANK NA\nother stuff"
    assert _first_match(_RE_LENDER, text) == "WELLS FARGO BANK NA"


def test_first_match_trustee():
    text = "Substitute Trustee: BARRETT DAFFIN FRAPPIER\nmore content"
    assert _first_match(_RE_TRUSTEE, text) == "BARRETT DAFFIN FRAPPIER"


def test_first_match_returns_none_when_no_match():
    assert _first_match(_RE_BORROWER, "No relevant parties in this notice") is None


# ---------------------------------------------------------------------------
# _parse_loan_amount
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("$125,000.00 principal balance", 125000.0),
    ("$50,000 note secured", 50000.0),
    ("no amount here", None),
])
def test_parse_loan_amount(text, expected):
    assert _parse_loan_amount(text) == expected


# ---------------------------------------------------------------------------
# _detect_stage
# ---------------------------------------------------------------------------

def test_detect_stage_nts():
    assert _detect_stage("Notice of Trustee's Sale filed") == ForeclosureStage.NTS


def test_detect_stage_nod():
    assert _detect_stage("Notice of Default and Election to Sell") == ForeclosureStage.NOD


def test_detect_stage_defaults_to_nts():
    assert _detect_stage("Some generic foreclosure text") == ForeclosureStage.NTS


# ---------------------------------------------------------------------------
# parse_pdf — corrupt/empty bytes
# ---------------------------------------------------------------------------

def test_parse_pdf_corrupt_bytes_returns_empty():
    events = parse_pdf(b"not a pdf", "travis", "http://example.com/bad.pdf")
    assert events == []


def test_parse_pdf_empty_bytes_returns_empty():
    events = parse_pdf(b"", "travis", "http://example.com/empty.pdf")
    assert events == []


# ---------------------------------------------------------------------------
# parse_pdf — real minimal PDF via fpdf (skipped if fpdf not installed)
# ---------------------------------------------------------------------------

def _make_foreclosure_pdf(text: str) -> bytes:
    try:
        import fpdf
        pdf = fpdf.FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        for line in text.split("\n"):
            pdf.cell(0, 5, line[:90], ln=True)
        return pdf.output(dest="S").encode("latin-1")
    except ImportError:
        return None


NOTICE_TEXT = (
    "NOTICE OF TRUSTEE'S SALE\n"
    "Grantor: SMITH JOHN A\n"
    "Beneficiary: FIRST NATIONAL BANK\n"
    "Substitute Trustee: ACME TRUSTEE SERVICES LLC\n"
    "123 Main Street Austin TX 78701\n"
    "Legal Description: LOT 5, BLOCK 3, RIVERSIDE ESTATES\n"
    "Sale Date: February 4, 2025\n"
    "Filing Date: January 10, 2025\n"
    "$175,000.00 principal balance on note\n"
)


@pytest.mark.skipif(
    _make_foreclosure_pdf(NOTICE_TEXT) is None,
    reason="fpdf not installed",
)
def test_parse_pdf_extracts_fields():
    pdf_bytes = _make_foreclosure_pdf(NOTICE_TEXT)
    events = parse_pdf(pdf_bytes, "travis", "http://example.com/notice.pdf")
    assert len(events) >= 1
    e = events[0]
    assert e.county == "travis"
    assert e.foreclosure_stage == ForeclosureStage.NTS
    assert e.borrower_name and "SMITH" in e.borrower_name
    assert e.loan_amount == 175000.0
    assert e.auction_date == date(2025, 2, 4)
    assert e.filing_date == date(2025, 1, 10)


# ---------------------------------------------------------------------------
# dedup_key — guards against silent collisions
# ---------------------------------------------------------------------------

def test_dedup_key_none_when_no_filing_date():
    from ingestion.shared.models import ForeclosureEvent
    e = ForeclosureEvent(county="travis", borrower_name="SMITH JOHN")
    assert e.dedup_key is None


def test_dedup_key_none_when_no_borrower_or_address():
    from ingestion.shared.models import ForeclosureEvent
    e = ForeclosureEvent(county="travis", filing_date=date(2025, 1, 1))
    assert e.dedup_key is None


def test_dedup_key_set_when_required_fields_present():
    from ingestion.shared.models import ForeclosureEvent
    e = ForeclosureEvent(county="travis", filing_date=date(2025, 1, 1), borrower_name="SMITH JOHN")
    assert e.dedup_key == "travis|foreclosure|2025-01-01|smith john|"


def test_dedup_key_uses_address_when_no_borrower():
    from ingestion.shared.models import ForeclosureEvent
    e = ForeclosureEvent(county="hays", filing_date=date(2025, 3, 15), address="123 Main St")
    assert e.dedup_key == "hays|foreclosure|2025-03-15||123 main st"
