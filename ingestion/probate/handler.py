"""
Lambda-style handler for the probate ingestion worker. Runs daily.

  handler({"county": "hays"}, {})
  handler({"county": "all"}, {})

Counties with strategy=manual are skipped with a warning log entry.
"""

import asyncio
import logging
import os
from typing import Any, Dict

import asyncpg

from ..shared.address_normalizer import infer_city_from_county, parse_address, usps_validate
from ..shared.apn_matcher import match_or_create_property
from ..shared.db import close_pool, get_pool, insert_event
from .config import PROBATE_COUNTY_CONFIGS, PROBATE_COUNTY_MAP
from .parser import parse
from .scraper import OdysseyProbateScraper

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


async def _process_county(county_name: str) -> Dict[str, Any]:
    config = PROBATE_COUNTY_MAP.get(county_name.lower())
    if not config:
        log.error("Unknown county: %s", county_name)
        return {"county": county_name, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    pool = await get_pool()
    scraper = OdysseyProbateScraper(config)
    search_results = await scraper.run()

    inserted = skipped = total_parsed = errors = 0
    for html_bytes, case_type in search_results:
        events = parse(html_bytes, case_type, county_name, config.odyssey_url or "")
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
                    log.warning("Probate event has no address (county=%s, case=%s)", county_name, event.case_number)

                property_id = None
                if addr and addr.normalized:
                    prop_data = {
                        "address": event.address,
                        "address_norm": addr.normalized,
                        "city": addr.city or "",
                        "county": county_name,
                        "state": "TX",
                        "zip_code": addr.zip_code,
                        "owner_name": event.decedent_name,
                    }
                    property_id = await match_or_create_property(
                        pool, addr.normalized, county_name, prop_data
                    )

                event_data = {**event.model_dump(), "property_id": property_id, "dedup_key": event.dedup_key}
                result = await insert_event(pool, event_data)
                if result:
                    inserted += 1
                else:
                    skipped += 1

            except asyncpg.PostgresError as exc:
                errors += 1
                log.error("DB error processing probate event (county=%s, case=%s): %s", county_name, event.case_number, exc)
            except Exception as exc:
                errors += 1
                log.error("Unexpected error processing probate event (county=%s, case=%s): %s", county_name, event.case_number, exc)

    stats = {"county": county_name, "parsed": total_parsed, "inserted": inserted, "skipped": skipped, "errors": errors}
    log.info("Probate ingestion complete: %s", stats)
    return stats


async def _run(event: Dict[str, Any]) -> Dict[str, Any]:
    county = event.get("county", "all")
    counties = [c.name for c in PROBATE_COUNTY_CONFIGS] if county == "all" else [county]
    results = await asyncio.gather(*[_process_county(name) for name in counties])
    await close_pool()
    return {"results": list(results)}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return asyncio.run(_run(event))


if __name__ == "__main__":
    import sys
    county_arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(handler({"county": county_arg}, {}))
