"""Pre-foreclosure scraper — fetches lis pendens and NOD filings."""

from typing import List, Dict, Any


class PreforeclosureScraper:
    def __init__(self, county: str):
        self.county = county
        # TODO: configure county district court endpoints

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        """Fetch lis pendens / NOD filings."""
        # TODO: implement scraping logic
        raise NotImplementedError

    async def run(self) -> List[Dict[str, Any]]:
        raw = await self.fetch_listings()
        return raw
