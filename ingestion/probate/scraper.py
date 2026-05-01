"""Probate scraper — fetches probate filings from county clerk records."""

from typing import List, Dict, Any


class ProbateScraper:
    def __init__(self, county: str):
        self.county = county
        # TODO: configure county clerk portal endpoints

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        """Fetch probate case filings."""
        # TODO: implement scraping logic
        raise NotImplementedError

    async def run(self) -> List[Dict[str, Any]]:
        raw = await self.fetch_listings()
        return raw
