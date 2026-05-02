"""Tax delinquency parser — handles CSV, HTML, and PDF delinquent roll formats."""

import io
import logging
import re
from datetime import date, datetime
from typing import List, Optional

import pdfplumber
from bs4 import BeautifulSoup

from ..shared.models import TaxDelinquencyEvent
from .config import SourceFormat

log = logging.getLogger(__name__)

_COL_OWNER   = {"owner", "owner name", "taxpayer", "taxpayer name", "name"}
_COL_ADDRESS = {"address", "property address", "situs address", "situs"}
_COL_AMOUNT  = {"amount", "amount due", "total due", "balance", "tax due", "delinquent amount"}
_COL_YEARS   = {"years", "years delinquent", "yrs delinquent", "yrs due"}
_COL_APN     = {"apn", "parcel", "account", "account number", "parcel id", "geo id"}

_RE_DOLLAR      = re.compile(r"[\$,\s]")
_RE_YEAR_IN_DATE = re.compile(r"\b(20\d{2}|19\d{2})\b")
_RE_TAX_BLOCK   = re.compile(
    r"(?P<apn>[\dA-Z\-\.]{5,20})\s+"
    r"(?P<owner>[A-Z][^\n]{5,60})\s+"
    r"(?P<address>\d{1,5}\s+[^\n]{5,60})\s+"
    r"\$?\s*(?P<amount>[\d,]+(?:\.\d{2})?)",
    re.MULTILINE,
)


def _normalize_col(name: str) -> str:
    return name.strip().lower().replace("_", " ")


def _find_col(headers: list, aliases: set) -> Optional[int]:
    for i, h in enumerate(headers):
        if _normalize_col(h) in aliases:
            return i
    return None


def _parse_amount(raw: str) -> Optional[float]:
    cleaned = _RE_DOLLAR.sub("", raw).strip()
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_years(raw: str) -> Optional[int]:
    try:
        return int(float(raw.strip()))
    except (ValueError, AttributeError):
        m = _RE_YEAR_IN_DATE.search(raw or "")
        if m:
            return datetime.now().year - int(m.group(1))
    return None


def _parse_csv(raw_bytes: bytes, county: str, source_url: str) -> List[TaxDelinquencyEvent]:
    import csv
    text = raw_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        return []

    headers = rows[0]
    i_owner   = _find_col(headers, _COL_OWNER)
    i_address = _find_col(headers, _COL_ADDRESS)
    i_amount  = _find_col(headers, _COL_AMOUNT)
    i_years   = _find_col(headers, _COL_YEARS)
    i_apn     = _find_col(headers, _COL_APN)

    events = []
    for row in rows[1:]:
        if not row or len(row) < 2:
            continue
        def _get(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else None
        events.append(TaxDelinquencyEvent(
            county=county,
            owner_name=_get(i_owner),
            address=_get(i_address),
            tax_amount_owed=_parse_amount(_get(i_amount) or ""),
            years_delinquent=_parse_years(_get(i_years) or ""),
            apn=_get(i_apn),
            filing_date=date.today(),
            source_url=source_url,
            raw_data={"row": row},
        ))
    return events


def _parse_html(raw_bytes: bytes, county: str, source_url: str) -> List[TaxDelinquencyEvent]:
    soup = BeautifulSoup(raw_bytes.decode("utf-8", errors="replace"), "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("No <table> found in HTML for county %s", county)
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    i_owner   = _find_col(headers, _COL_OWNER)
    i_address = _find_col(headers, _COL_ADDRESS)
    i_amount  = _find_col(headers, _COL_AMOUNT)
    i_years   = _find_col(headers, _COL_YEARS)
    i_apn     = _find_col(headers, _COL_APN)

    events = []
    for tr in rows[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if not cells:
            continue
        def _get(idx):
            return cells[idx] if idx is not None and idx < len(cells) else None
        events.append(TaxDelinquencyEvent(
            county=county,
            owner_name=_get(i_owner),
            address=_get(i_address),
            tax_amount_owed=_parse_amount(_get(i_amount) or ""),
            years_delinquent=_parse_years(_get(i_years) or ""),
            apn=_get(i_apn),
            filing_date=date.today(),
            source_url=source_url,
            raw_data={"cells": cells},
        ))
    return events


def _parse_pdf_tax(raw_bytes: bytes, county: str, source_url: str) -> List[TaxDelinquencyEvent]:
    try:
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as exc:
        log.error("PDF parse failed for %s: %s", county, exc)
        return []

    events = []
    for m in _RE_TAX_BLOCK.finditer(text):
        events.append(TaxDelinquencyEvent(
            county=county,
            apn=m.group("apn").strip(),
            owner_name=m.group("owner").strip(),
            address=m.group("address").strip(),
            tax_amount_owed=_parse_amount(m.group("amount")),
            filing_date=date.today(),
            source_url=source_url,
            raw_data={"match": m.group(0)[:200]},
        ))
    return events


def parse(
    raw_bytes: bytes,
    source_format: SourceFormat,
    county: str,
    source_url: str,
) -> List[TaxDelinquencyEvent]:
    if not raw_bytes:
        return []
    if source_format == SourceFormat.csv:
        events = _parse_csv(raw_bytes, county, source_url)
    elif source_format == SourceFormat.html:
        events = _parse_html(raw_bytes, county, source_url)
    else:
        events = _parse_pdf_tax(raw_bytes, county, source_url)
    log.info("County %s: parsed %d tax delinquency record(s)", county, len(events))
    return events
