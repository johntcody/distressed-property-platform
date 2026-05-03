"""Foreclosure PDF parser — extracts structured fields from county clerk posting PDFs."""

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pdfplumber

from ..shared.models import ForeclosureEvent, ForeclosureStage

log = logging.getLogger(__name__)

# ── Regex patterns for common Texas foreclosure notice fields ──────────────────

_RE_BORROWER   = re.compile(r"(?:Grantor|Mortgagor|Borrower)[:\s]+([A-Z][^\n,]{2,60})", re.I)
_RE_LENDER     = re.compile(r"(?:Beneficiary|Mortgagee|Lender|Payee)[:\s]+([A-Z][^\n,]{2,80})", re.I)
_RE_TRUSTEE    = re.compile(r"(?:Trustee|Substitute Trustee)[:\s]+([A-Z][^\n,]{2,80})", re.I)
_RE_ADDRESS    = re.compile(
    r"\b(\d{1,5}\s+[A-Z][^\n,]{3,60}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|"
    r"Lane|Ln|Blvd|Boulevard|Way|Court|Ct|Circle|Cir|Trail|Trl)[^\n,]{0,30})",
    re.I,
)
_RE_LEGAL      = re.compile(r"(?:Legal Description|Property Description)[:\s]+([^\n]{10,200})", re.I)
_RE_AUCTION    = re.compile(
    r"(?:sale date|auction date|trustee.s sale)[:\s,]*"
    r"(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.I,
)
_RE_FILING     = re.compile(
    r"(?:filed|filing date|date of filing)[:\s,]*"
    r"(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.I,
)
_RE_LOAN_AMT   = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:principal|note|loan)", re.I)
_RE_NTS        = re.compile(r"notice of trustee.s sale|NTS", re.I)
_RE_NOD        = re.compile(r"notice of default|NOD", re.I)

_DATE_FORMATS  = ["%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%m/%d/%y"]


def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip().rstrip(".,")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _parse_loan_amount(text: str) -> Optional[float]:
    m = _RE_LOAN_AMT.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _detect_stage(text: str) -> ForeclosureStage:
    if _RE_NTS.search(text):
        return ForeclosureStage.NTS
    if _RE_NOD.search(text):
        return ForeclosureStage.NOD
    # Default for county clerk postings — most are NTS
    return ForeclosureStage.NTS


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF using pdfplumber."""
    text_pages: List[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_pages.append(page_text)
    return "\n".join(text_pages)


def parse_pdf(pdf_bytes: bytes, county: str, source_url: str) -> List[ForeclosureEvent]:
    """
    Parse a county clerk foreclosure posting PDF.
    Returns a list of ForeclosureEvent (one PDF may contain multiple notices).
    """
    try:
        full_text = extract_text_from_pdf(pdf_bytes)
    except Exception as exc:
        log.error("PDF extraction failed for %s/%s: %s", county, source_url, exc)
        return []

    # Split on common notice separators (page breaks, rule lines, notice numbers)
    blocks = re.split(r"(?:\n\s*\n\s*\n|_{5,}|-{5,}|\f)", full_text)
    events: List[ForeclosureEvent] = []

    for block in blocks:
        block = block.strip()
        if len(block) < 100:
            continue

        borrower    = _first_match(_RE_BORROWER, block)
        lender      = _first_match(_RE_LENDER, block)
        trustee     = _first_match(_RE_TRUSTEE, block)
        address_raw = _first_match(_RE_ADDRESS, block)
        legal       = _first_match(_RE_LEGAL, block)
        auction_raw = _first_match(_RE_AUCTION, block)
        filing_raw  = _first_match(_RE_FILING, block)
        loan_amt    = _parse_loan_amount(block)
        stage       = _detect_stage(block)

        if not any([borrower, address_raw, legal]):
            continue  # not enough signal — skip block

        event = ForeclosureEvent(
            county=county,
            foreclosure_stage=stage,
            borrower_name=borrower,
            lender_name=lender,
            trustee_name=trustee,
            address=address_raw,
            legal_description=legal,
            auction_date=_parse_date(auction_raw) if auction_raw else None,
            filing_date=_parse_date(filing_raw) if filing_raw else None,
            loan_amount=loan_amt,
            source_url=source_url,
            raw_data={"text_excerpt": block[:500]},
        )
        events.append(event)

    log.info("County %s: parsed %d notice(s) from %s", county, len(events), source_url)
    return events
