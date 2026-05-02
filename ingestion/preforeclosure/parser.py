"""Pre-foreclosure parser — extracts Lis Pendens and foreclosure filing data from district clerk HTML."""

import logging
import re
from datetime import date, datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from ..shared.models import PreforeclosureEvent
from .config import LP_KEYWORDS

log = logging.getLogger(__name__)

_DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y"]
_RE_ADDRESS   = re.compile(
    r"\b(\d{1,5}\s+[A-Z][^\n,]{3,60}(?:St|Ave|Rd|Dr|Ln|Blvd|Way|Ct|Cir|Trl)[^\n,]{0,20})",
    re.I,
)
_RE_BORROWER  = re.compile(r"(?:Plaintiff|Grantor|Borrower|Defendant)[:\s]+([A-Z][^\n,]{3,60})", re.I)
_RE_LENDER    = re.compile(r"(?:Defendant|Lender|Beneficiary|Bank)[:\s]+([A-Z][^\n,]{3,60})", re.I)


def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip().rstrip(".,")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _detect_keywords(text: str) -> List[str]:
    text_lower = text.lower()
    return [kw for kw in LP_KEYWORDS if kw in text_lower]


def _parse_case_table(soup: BeautifulSoup, county: str, keyword: str, source_url: str) -> List[PreforeclosureEvent]:
    events: List[PreforeclosureEvent] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        if not any(h in headers for h in ["case number", "case style", "filed", "filing date"]):
            continue

        col = {h: i for i, h in enumerate(headers)}

        def _cell(row, key_options):
            for key in key_options:
                idx = col.get(key)
                if idx is not None:
                    tds = row.find_all("td")
                    if idx < len(tds):
                        return tds[idx].get_text(strip=True)
            return None

        for tr in rows[1:]:
            tds = tr.find_all("td")
            if not tds:
                continue

            row_text = tr.get_text(" ", strip=True)
            matched_keywords = _detect_keywords(row_text) or [keyword]
            case_num   = _cell(tr, ["case number", "case no", "cause number"])
            case_style = _cell(tr, ["case style", "style", "parties"])
            filing_raw = _cell(tr, ["filed", "filing date", "date filed"])
            instrument = _cell(tr, ["instrument", "document", "doc #"])

            borrower = lender = address = None
            if case_style:
                m = _RE_BORROWER.search(case_style)
                borrower = m.group(1).strip() if m else None
                m = _RE_LENDER.search(case_style)
                lender = m.group(1).strip() if m else None
                m = _RE_ADDRESS.search(case_style)
                address = m.group(1).strip() if m else None

            events.append(PreforeclosureEvent(
                county=county,
                filing_date=_parse_date(filing_raw) if filing_raw else None,
                borrower_name=borrower,
                lender_name=lender,
                address=address,
                lp_instrument_number=instrument,
                lp_keywords=matched_keywords,
                source_url=source_url,
                raw_data={"case_style": case_style, "case_number": case_num},
            ))

    return events


def parse(html_bytes: bytes, keyword: str, county: str, source_url: str) -> List[PreforeclosureEvent]:
    if not html_bytes:
        return []

    soup = BeautifulSoup(html_bytes.decode("utf-8", errors="replace"), "html.parser")
    events = _parse_case_table(soup, county, keyword, source_url)

    seen: set = set()
    unique: List[PreforeclosureEvent] = []
    for e in events:
        key = e.lp_instrument_number or e.dedup_key
        if key not in seen:
            seen.add(key)
            unique.append(e)

    log.info("County %s / keyword '%s': parsed %d filing(s)", county, keyword, len(unique))
    return unique
