"""Foreclosure scraper — discovers and downloads county clerk posting PDFs."""

import logging
import re
from typing import List, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .config import CountyConfig

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DistressedPropertyBot/1.0; "
        "+https://github.com/your-org/distressed-property-platform)"
    )
}


class ForeclosureScraper:
    def __init__(self, config: CountyConfig):
        self.config = config

    async def fetch_pdf_links(self) -> List[str]:
        """Scrape the county listing page and return absolute URLs of posting PDFs."""
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
            try:
                resp = await client.get(self.config.listing_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("Failed to fetch listing page for %s: %s", self.config.name, exc)
                return []

        soup = BeautifulSoup(resp.text, "html.parser")
        pattern = re.compile(self.config.link_pattern)
        links: List[str] = []

        for tag in soup.find_all("a", href=True):
            href: str = tag["href"]
            if pattern.search(href):
                absolute = href if href.startswith("http") else urljoin(self.config.pdf_base_url, href)
                if absolute not in links:
                    links.append(absolute)

        log.info("County %s: found %d PDF link(s)", self.config.name, len(links))
        return links

    async def download_pdf(self, url: str) -> Tuple[str, bytes]:
        """Download a PDF and return (url, raw_bytes)."""
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return url, resp.content

    async def run(self) -> List[Tuple[str, bytes]]:
        """Fetch listing page, discover PDFs, download each. Returns list of (url, bytes)."""
        links = await self.fetch_pdf_links()
        results: List[Tuple[str, bytes]] = []
        for url in links:
            try:
                results.append(await self.download_pdf(url))
            except httpx.HTTPError as exc:
                log.warning("Failed to download PDF %s: %s", url, exc)
        return results
