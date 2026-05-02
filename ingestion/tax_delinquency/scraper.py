"""Tax delinquency scraper — fetches delinquent roll data from county CAD sites."""

import logging
from typing import Optional, Tuple

import httpx

from .config import SourceFormat, TaxCountyConfig

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DistressedPropertyBot/1.0; "
        "+https://github.com/your-org/distressed-property-platform)"
    )
}


class TaxDelinquencyScraper:
    def __init__(self, config: TaxCountyConfig):
        self.config = config

    async def fetch(self) -> Tuple[SourceFormat, bytes]:
        """Download the delinquent roll resource. Returns (format, raw_bytes)."""
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=30) as client:
            try:
                resp = await client.get(self.config.listing_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("Failed to fetch tax delinquency data for %s: %s", self.config.name, exc)
                return self.config.source_format, b""

        log.info(
            "County %s: fetched %d bytes (%s)",
            self.config.name,
            len(resp.content),
            self.config.source_format.value,
        )
        return self.config.source_format, resp.content

    async def run(self) -> Tuple[SourceFormat, bytes]:
        return await self.fetch()
