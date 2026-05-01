"""Foreclosure scraper — fetches raw foreclosure listings from county sources."""

import httpx
from typing import List, Dict, Any


class ForeclosureScraper:
    def __init__(self, county: str):
        self.county = county
        # TODO: configure per-county base URLs

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        """Fetch raw foreclosure listing pages."""
        # TODO: implement county-specific HTTP scraping logic
        raise NotImplementedError

    async def run(self) -> List[Dict[str, Any]]:
        """Entry point: scrape and return raw records."""
        raw = await self.fetch_listings()
        # TODO: validate and normalize raw records
        return raw
