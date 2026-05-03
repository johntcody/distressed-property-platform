"""APN (Assessor Parcel Number) matching against the CAD property database."""

import re
from typing import Optional

import asyncpg


async def lookup_apn_by_address(pool: asyncpg.Pool, address_norm: str, county: str) -> Optional[str]:
    """
    Search the properties table for an existing APN by normalized address + county.
    Returns APN string if found, None otherwise.
    """
    row = await pool.fetchrow(
        """
        SELECT apn FROM properties
        WHERE county = $1
          AND (address_norm ILIKE $2 OR address ILIKE $2)
          AND apn IS NOT NULL
        LIMIT 1
        """,
        county.lower(),
        f"%{address_norm.strip()}%",
    )
    return row["apn"] if row else None


async def lookup_property_id_by_apn(pool: asyncpg.Pool, apn: str) -> Optional[str]:
    """Return property UUID for a known APN."""
    row = await pool.fetchrow("SELECT id FROM properties WHERE apn = $1", apn)
    return str(row["id"]) if row else None


async def lookup_property_id_by_address(
    pool: asyncpg.Pool, address_norm: str, county: str
) -> Optional[str]:
    """Fuzzy address match — used when APN is unknown."""
    row = await pool.fetchrow(
        """
        SELECT id FROM properties
        WHERE county = $1
          AND (address_norm ILIKE $2 OR address ILIKE $2)
        LIMIT 1
        """,
        county.lower(),
        f"%{address_norm.strip()}%",
    )
    return str(row["id"]) if row else None


def normalize_apn(raw: str) -> str:
    """Strip non-alphanumeric separators so APNs can be compared uniformly."""
    return re.sub(r"[\s\-\.]", "", raw).upper()


async def match_or_create_property(
    pool: asyncpg.Pool,
    address_norm: str,
    county: str,
    property_data: dict,
) -> str:
    """
    Try to match an existing property by APN or address.
    Creates a new property record if no match is found.
    Returns property UUID.
    """
    from .db import upsert_property

    # 1. Match by APN if provided
    apn = property_data.get("apn")
    if apn:
        apn_clean = normalize_apn(apn)
        pid = await lookup_property_id_by_apn(pool, apn_clean)
        if pid:
            return pid
        property_data["apn"] = apn_clean

    # 2. Match by normalized address
    if address_norm:
        pid = await lookup_property_id_by_address(pool, address_norm, county)
        if pid:
            return pid

    # 3. Create new property record — normalize county to lowercase for consistency
    property_data.setdefault("address_norm", address_norm)
    property_data["county"] = county.lower()
    return await upsert_property(pool, property_data)
