"""
Lambda-style handler for the pre-foreclosure (Lis Pendens) ingestion worker. Runs daily.

  handler({"county": "travis"}, {})
  handler({"county": "all"}, {})
"""

import asyncio
import logging
import os
from typing import Any, Dict

import asyncpg

from ..shared.address_normalizer import infer_city_from_county, parse_address, usps_validate
from ..shared.apn_matcher import match_or_create_property
from ..shared.db import close_pool, get_pool, insert_event
from .config import PREFORECLOSURE_COUNTY_CONFIGS, PREFORECLOSURE_COUNTY_MAP
from .parser import parse
from .scraper import PreforeclosureScraper

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


async def _process_county(county_name: str) -> Dict[str, Any]:
    config = PREFORECLOSURE_COUNTY_MAP.get(county_name.lower())
    if not config:
        log.error("Unknown county: %s", county_name)
        return {"county": county_name, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    pool = await get_pool()
    scraper = PreforeclosureScraper(config)
    search_results = await scraper.run()

    inserted = skipped = total_parsed = errors = 0
    for html_bytes, keyword in search_results:
        events = parse(html_bytes, keyword, county_name, config.search_url)
        total_parsed += len(events)

        for event in events:
            try:
                if event.address:
                    addr = parse_address(event.address)
                    addr = await usps_validate(addr)
                    if not addr.city:
                        addr.city = infer_city_from_county(county_name) or ""
                else:
                    addr = None
                    log.warning("Pre-foreclosure event has no address (county=%s, instrument=%s)", county_name, event.lp_instrument_number)

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

                event_data = {**event.dict(), "property_id": property_id, "dedup_key": event.dedup_key}
                result = await insert_event(pool, event_data)
                if result:
                    inserted += 1
                else:
                    skipped += 1

            except asyncpg.PostgresError as exc:
                errors += 1
                log.error("DB error processing pre-foreclosure event (county=%s, address=%s): %s", county_name, event.address, exc)
            except Exception as exc:
                errors += 1
                log.error("Unexpected error processing pre-foreclosure event (county=%s, address=%s): %s", county_name, event.address, exc)

    stats = {"county": county_name, "parsed": total_parsed, "inserted": inserted, "skipped": skipped, "errors": errors}
    log.info("Pre-foreclosure ingestion complete: %s", stats)
    return stats


async def _run(event: Dict[str, Any]) -> Dict[str, Any]:
    county = event.get("county", "all")
    counties = [c.name for c in PREFORECLOSURE_COUNTY_CONFIGS] if county == "all" else [county]
    results = [await _process_county(name) for name in counties]
    await close_pool()
    return {"results": results}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return asyncio.run(_run(event))


if __name__ == "__main__":
    import sys
    county_arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(handler({"county": county_arg}, {}))
