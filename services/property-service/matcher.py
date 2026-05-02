"""Property matching — resolves duplicate property records using APN and address similarity."""

import logging
import re
from typing import Optional

import asyncpg

log = logging.getLogger(__name__)

_STREET_ABBREVS = {
    "street": "st", "avenue": "ave", "boulevard": "blvd", "drive": "dr",
    "road": "rd", "lane": "ln", "court": "ct", "circle": "cir",
    "trail": "trl", "way": "wy", "place": "pl", "terrace": "ter",
}


def _street_key(address: str) -> str:
    """Reduce an address to a compact comparison key."""
    s = address.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    tokens = s.split()
    tokens = [_STREET_ABBREVS.get(t, t) for t in tokens]
    return " ".join(tokens)


async def find_duplicate_property(
    pool: asyncpg.Pool,
    apn: Optional[str],
    address_norm: Optional[str],
    county: str,
) -> Optional[str]:
    """
    Returns the UUID of an existing property that matches apn or normalized address.
    Priority: APN exact match > address key match.
    """
    if apn:
        row = await pool.fetchrow("SELECT id FROM properties WHERE apn = $1", apn)
        if row:
            return str(row["id"])

    if address_norm:
        key = _street_key(address_norm)
        rows = await pool.fetch(
            "SELECT id, address_norm FROM properties WHERE county = $1 AND address_norm IS NOT NULL",
            county.lower(),
        )
        for row in rows:
            if _street_key(row["address_norm"]) == key:
                return str(row["id"])

    return None


async def merge_duplicate_events(pool: asyncpg.Pool, keep_id: str, drop_id: str) -> int:
    """Re-link all events from drop_id to keep_id, then delete the orphaned property."""
    # RETURNING returns rows, not aggregates — collect them and count in Python
    rows = await pool.fetch(
        "UPDATE events SET property_id = $1 WHERE property_id = $2 RETURNING id",
        keep_id,
        drop_id,
    )
    updated = len(rows)
    await pool.execute("DELETE FROM properties WHERE id = $1", drop_id)
    log.info("Merged property %s → %s (%d events re-linked)", drop_id, keep_id, updated)
    return updated
