"""Probate parser — extracts structured case data from Odyssey search HTML and manual CSV exports."""

import io
import logging
import re
from datetime import date, datetime
from typing import List, Optional

import pdfplumber
from bs4 import BeautifulSoup

from ..shared.models import ProbateEvent

log = logging.getLogger(__name__)

_DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"]
_RE_CASE_NUM  = re.compile(r"\b([A-Z0-9]{2,6}-\d{4,6}(?:-[A-Z0-9]+)?)\b")
_RE_ADDRESS   = re.compile(
    r"\b(\d{1,5}\s+[A-Z][^\n,]{3,60}(?:St|Ave|Rd|Dr|Ln|Blvd|Way|Ct|Cir|Trl)[^\n,]{0,20})",
    re.I,
)
_RE_ESTATE_OF = re.compile(r"(?:Estate\s+of|In\s+Re:?)\s+([A-Z][^\n,]{3,60})", re.I)
_RE_EXECUTOR  = re.compile(
    r"(?:Executor|Executrix|Administrator|Personal\s+Representative)[:\s]+([A-Z][^\n,]{3,60})",
    re.I,
)


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    raw = raw.strip().rstrip(".,")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_odyssey_table(soup: BeautifulSoup, county: str, case_type: str, source_url: str) -> List[ProbateEvent]:
    events: List[ProbateEvent] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        if not any(h in headers for h in ["case number", "style", "filed", "case type"]):
            continue

        col = {h: i for i, h in enumerate(headers)}

        def _cell(row, keys):
            for key in keys:
                idx = col.get(key)
                if idx is not None:
                    tds = row.find_all("td")
                    if idx < len(tds):
                        return tds[idx].get_text(strip=True)
            return None

        for tr in rows[1:]:
            if not tr.find("td"):
                continue
            case_num   = _cell(tr, ["case number", "case no"])
            case_style = _cell(tr, ["style", "case style", "parties"])
            filed_raw  = _cell(tr, ["filed", "filing date", "date filed"])

            decedent = executor = address = None
            if case_style:
                m = _RE_ESTATE_OF.search(case_style)
                decedent = m.group(1).strip().rstrip(",") if m else None
                m = _RE_EXECUTOR.search(case_style)
                executor = m.group(1).strip() if m else None
                m = _RE_ADDRESS.search(case_style)
                address = m.group(1).strip() if m else None
                if not case_num:
                    m = _RE_CASE_NUM.search(case_style)
                    case_num = m.group(1) if m else None

            events.append(ProbateEvent(
                county=county,
                filing_date=_parse_date(filed_raw),
                case_number=case_num,
                decedent_name=decedent,
                executor_name=executor,
                address=address,
                source_url=source_url,
                raw_data={"case_style": case_style, "case_type": case_type},
            ))

    return events


def extract_property_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """Scan a probate filing PDF for a property address."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages[:5])
        m = _RE_ADDRESS.search(text)
        return m.group(1).strip() if m else None
    except Exception as exc:
        log.warning("Failed to extract address from probate PDF: %s", exc)
        return None


def parse(html_bytes: bytes, case_type: str, county: str, source_url: str) -> List[ProbateEvent]:
    if not html_bytes:
        return []

    soup = BeautifulSoup(html_bytes.decode("utf-8", errors="replace"), "html.parser")
    events = _parse_odyssey_table(soup, county, case_type, source_url)

    seen: set = set()
    unique: List[ProbateEvent] = []
    for e in events:
        key = e.case_number or e.dedup_key
        if key not in seen:
            seen.add(key)
            unique.append(e)

    log.info("County %s / '%s': parsed %d probate case(s)", county, case_type, len(unique))
    return unique
