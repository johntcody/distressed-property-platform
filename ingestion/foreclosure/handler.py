"""
Lambda-style handler for the foreclosure ingestion worker.

Invocation:
  handler({"county": "travis"}, {})          # single county
  handler({"county": "all"}, {})             # all configured counties
  handler({}, {})                            # defaults to all counties
"""

import asyncio
import logging
import os
from typing import Any, Dict

import asyncpg

from ..shared.address_normalizer import infer_city_from_county, parse_address, usps_validate
from ..shared.apn_matcher import match_or_create_property
from ..shared.db import close_pool, get_pool, insert_event
from .config import COUNTY_CONFIGS, COUNTY_MAP
from .parser import parse_pdf
from .scraper import ForeclosureScraper

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


async def _process_county(county_name: str) -> Dict[str, Any]:
    config = COUNTY_MAP.get(county_name.lower())
    if not config:
        log.error("Unknown county: %s", county_name)
        return {"county": county_name, "downloaded": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    pool = await get_pool()
    scraper = ForeclosureScraper(config)
    pdfs = await scraper.run()

    downloaded = len(pdfs)
    parsed = inserted = skipped = errors = 0

    for source_url, pdf_bytes in pdfs:
        events = parse_pdf(pdf_bytes, county_name, source_url)
        parsed += len(events)

        for event in events:
            try:
                # 1. Normalize address
                if event.address:
                    addr = parse_address(event.address)
                    addr = await usps_validate(addr)
                    if not addr.city:
                        addr.city = infer_city_from_county(county_name) or ""
                else:
                    addr = None
                    log.warning("Foreclosure event has no address (county=%s, borrower=%s)", county_name, event.borrower_name)

                # 2. Match or create property record
                property_id = None
                if addr and addr.normalized:
                    prop_data = {
                        "address": event.address,
                        "address_norm": addr.normalized,
                        "city": addr.city or "",
                        "county": county_name,
                        "state": "TX",
                        "zip_code": addr.zip_code,
                        "owner_name": event.borrower_name,
                        "legal_description": event.legal_description,
                    }
                    property_id = await match_or_create_property(
                        pool, addr.normalized, county_name, prop_data
                    )

                # 3. Insert event (skip on duplicate dedup_key)
                event_data = {
                    **event.model_dump(),
                    "property_id": property_id,
                    "dedup_key": event.dedup_key,
                }
                result = await insert_event(pool, event_data)
                if result:
                    inserted += 1
                else:
                    skipped += 1

            except asyncpg.PostgresError as exc:
                errors += 1
                log.error(
                    "DB error processing foreclosure event (county=%s, address=%s): %s",
                    county_name, event.address, exc,
                )
            except Exception as exc:
                errors += 1
                log.error(
                    "Unexpected error processing foreclosure event (county=%s, address=%s): %s",
                    county_name, event.address, exc,
                )

    stats = {
        "county": county_name,
        "downloaded": downloaded,
        "parsed": parsed,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    log.info("Foreclosure ingestion complete: %s", stats)
    return stats


async def _run(event: Dict[str, Any]) -> Dict[str, Any]:
    county = event.get("county", "all")
    counties = (
        [c.name for c in COUNTY_CONFIGS] if county == "all" else [county]
    )

    results = await asyncio.gather(*[_process_county(name) for name in counties])
    await close_pool()
    return {"results": list(results)}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda / cron entrypoint."""
    return asyncio.run(_run(event))


if __name__ == "__main__":
    import sys
    county_arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(handler({"county": county_arg}, {}))
