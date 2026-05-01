"""Tax delinquency scraper — fetches properties with delinquent tax records."""

from typing import List, Dict, Any


class TaxDelinquencyScraper:
    def __init__(self, county: str):
        self.county = county
        # TODO: configure per-county appraisal district endpoints

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        """Fetch delinquent tax records from county appraisal district."""
        # TODO: implement scraping logic
        raise NotImplementedError

    async def run(self) -> List[Dict[str, Any]]:
        raw = await self.fetch_listings()
        # TODO: validate records
        return raw
