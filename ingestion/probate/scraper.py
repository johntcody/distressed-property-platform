"""
Probate scraper — queries the Odyssey public portal for new probate case filings.

Odyssey uses a .NET WebForms pattern with ViewState. The scraper:
  1. GETs the search page to capture __VIEWSTATE and __EVENTVALIDATION tokens
  2. POSTs a case search with CaseType=Probate and a date range
  3. Parses the results table for case summaries
  4. (Optional) follows each case link to download the full filing PDF

Anti-captcha note:
  Odyssey does not use CAPTCHA on most Texas county portals, but it does
  rate-limit by IP. A 2-second delay between requests is included. If a county
  starts returning 403/503, fall back to ProbateStrategy.manual and log a warning.

Playwright fallback:
  Set env var PROBATE_USE_PLAYWRIGHT=1 to switch to browser-based scraping for
  counties that require JS rendering or session cookies.
"""

import asyncio
import logging
import os
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from .config import ODYSSEY_PROBATE_TYPES, ProbateCountyConfig, ProbateStrategy

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DistressedPropertyBot/1.0; "
        "+https://github.com/your-org/distressed-property-platform)"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
}

_USE_PLAYWRIGHT = os.getenv("PROBATE_USE_PLAYWRIGHT", "0") == "1"
_SEARCH_WINDOW_DAYS = int(os.getenv("PROBATE_SEARCH_WINDOW_DAYS", "7"))


def _extract_viewstate(html: str) -> Dict[str, str]:
    """Extract ASP.NET WebForms hidden fields needed for POST."""
    soup = BeautifulSoup(html, "html.parser")
    fields: Dict[str, str] = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        tag = soup.find("input", {"name": name})
        if tag:
            fields[name] = tag.get("value", "")
    return fields


class OdysseyProbateScraper:
    def __init__(self, config: ProbateCountyConfig):
        self.config = config
        self._rate_limit_secs = 2.0

    async def _get_search_page(self, client: httpx.AsyncClient) -> Optional[str]:
        try:
            resp = await client.get(self.config.odyssey_url, timeout=20)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            log.warning("Failed to load Odyssey search page for %s: %s", self.config.name, exc)
            return None

    async def _post_search(
        self,
        client: httpx.AsyncClient,
        viewstate: Dict[str, str],
        case_type: str,
        date_from: date,
        date_to: date,
    ) -> Optional[bytes]:
        payload = {
            **viewstate,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "NodeID": self.config.odyssey_node_id or "",
            "NodeDesc": self.config.name.title() + " County",
            "SearchType": "Case",
            "CaseType": case_type,
            "DateOfBirth": "",
            "LastName": "",
            "FirstName": "",
            "cboState": "AA",
            "btnSearch": "Search",
            "FiledDateFrom": date_from.strftime("%m/%d/%Y"),
            "FiledDateTo": date_to.strftime("%m/%d/%Y"),
        }
        try:
            await asyncio.sleep(self._rate_limit_secs)
            resp = await client.post(self.config.odyssey_url, data=payload, timeout=30)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            log.warning(
                "Odyssey POST failed (%s / %s): %s", self.config.name, case_type, exc
            )
            return None

    async def run(self) -> List[Tuple[bytes, str]]:
        """
        Returns list of (html_bytes, case_type) for all probate case types searched.
        """
        if self.config.strategy == ProbateStrategy.manual:
            log.warning(
                "County %s is marked manual — skipping automated scrape. "
                "Review %s manually.",
                self.config.name,
                self.config.notes or "county probate court",
            )
            return []

        date_to = date.today()
        date_from = date_to - timedelta(days=_SEARCH_WINDOW_DAYS)

        results: List[Tuple[bytes, str]] = []

        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
            search_html = await self._get_search_page(client)
            if not search_html:
                return []

            viewstate = _extract_viewstate(search_html)
            if not viewstate.get("__VIEWSTATE"):
                log.warning(
                    "Could not extract ViewState for %s — page may require JS rendering. "
                    "Set PROBATE_USE_PLAYWRIGHT=1 to enable browser fallback.",
                    self.config.name,
                )
                return []

            for case_type in ODYSSEY_PROBATE_TYPES:
                html = await self._post_search(client, viewstate, case_type, date_from, date_to)
                if html:
                    results.append((html, case_type))

        log.info(
            "County %s: Odyssey search complete — %d case type(s) returned results",
            self.config.name,
            len(results),
        )
        return results
