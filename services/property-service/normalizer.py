"""Property normalization service — address parsing, dedup, and CAD enrichment."""

import logging
from typing import Optional

import asyncpg

from ingestion.shared.address_normalizer import infer_city_from_county, parse_address, usps_validate
from ingestion.shared.apn_matcher import match_or_create_property, normalize_apn
from ingestion.shared.models import NormalizedAddress

log = logging.getLogger(__name__)


class PropertyNormalizer:
    """
    Normalizes a raw property record coming from any ingestion pipeline.

    Steps:
      1. Parse + USPS-validate address
      2. Clean/standardize APN format
      3. Upsert into properties table, matching on APN or address
      4. Return property UUID for event linkage
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def normalize_and_upsert(
        self,
        raw_address: str,
        county: str,
        raw_apn: Optional[str] = None,
        extra_fields: Optional[dict] = None,
    ) -> tuple[str, NormalizedAddress]:
        """
        Normalize address and upsert property. Returns (property_uuid, NormalizedAddress).
        """
        addr = parse_address(raw_address)
        addr = await usps_validate(addr)

        if not addr.city:
            addr.city = infer_city_from_county(county)

        apn_clean = normalize_apn(raw_apn) if raw_apn else None

        prop_data: dict = {
            "address": raw_address,
            "address_norm": addr.normalized or raw_address,
            "city": addr.city or "",
            "county": county,
            "state": addr.state or "TX",
            "zip_code": addr.zip_code,
            **(extra_fields or {}),
        }
        if apn_clean:
            prop_data["apn"] = apn_clean

        property_id = await match_or_create_property(
            self.pool,
            addr.normalized or raw_address,
            county,
            prop_data,
        )

        log.debug(
            "Normalized '%s' → '%s' | APN=%s | property_id=%s",
            raw_address,
            addr.normalized,
            apn_clean,
            property_id,
        )
        return property_id, addr

    async def bulk_normalize(self, records: list[dict]) -> list[dict]:
        """
        Process a list of raw property dicts.
        Each dict must have at minimum: address, county.
        Returns the input list with property_id and address_norm added.
        """
        for rec in records:
            try:
                pid, addr = await self.normalize_and_upsert(
                    raw_address=rec["address"],
                    county=rec["county"],
                    raw_apn=rec.get("apn"),
                    extra_fields={
                        k: v for k, v in rec.items()
                        if k not in {"address", "county", "apn"}
                    },
                )
                rec["property_id"] = pid
                rec["address_norm"] = addr.normalized
            except Exception as exc:
                log.warning("Failed to normalize record %s: %s", rec.get("address"), exc)
                rec["property_id"] = None
                rec["address_norm"] = None
        return records
