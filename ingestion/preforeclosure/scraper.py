"""
Pre-foreclosure scraper — searches district clerk portals for Lis Pendens
and foreclosure-related civil filings.
"""

import logging
import re
from typing import List, Tuple
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from .config import LP_KEYWORDS, PreforeclosureCountyConfig

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DistressedPropertyBot/1.0; "
        "+https://github.com/your-org/distressed-property-platform)"
    )
}

# Raw HTML rows returned from a keyword search — (html_bytes, keyword_used)
SearchResult = Tuple[bytes, str]


class PreforeclosureScraper:
    def __init__(self, config: PreforeclosureCountyConfig):
        self.config = config

    async def _search_keyword(self, client: httpx.AsyncClient, keyword: str) -> bytes:
        """POST or GET a keyword search against the district clerk portal."""
        params = {
            "CaseStyle": keyword,
            "SearchType": "CaseStyle",
            "NodeDesc": "All",
            "NodeID": "",
        }
        try:
            # Most Texas district clerk portals accept GET with query params
            resp = await client.get(
                self.config.search_url,
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            log.warning("Keyword search failed (%s / %s): %s", self.config.name, keyword, exc)
            return b""

    async def run(self) -> List[SearchResult]:
        """Search each keyword; return list of (html_bytes, keyword) tuples."""
        results: List[SearchResult] = []
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
            for keyword in LP_KEYWORDS:
                html = await self._search_keyword(client, keyword)
                if html:
                    results.append((html, keyword))
        log.info(
            "County %s: completed %d keyword search(es), %d returned results",
            self.config.name,
            len(LP_KEYWORDS),
            len(results),
        )
        return results
