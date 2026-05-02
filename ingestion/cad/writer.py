"""
CAD parcel database writer.

Upserts normalized parcel dicts into the `properties` table using APN as
the conflict key. CAD data is the authoritative source for property attributes;
on conflict it overwrites all CAD-owned columns and records the refresh timestamp.

Address normalization (USPS API) is stubbed — replace stub with real call
before going to production.
"""

import logging
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO properties (
    apn, county, state,
    owner_name, address_raw, address_norm,
    city, zip_code,
    land_value, improvement_value, total_cad_value,
    sqft, year_built, bedrooms, bathrooms,
    cad_refreshed_at
)
VALUES (
    %(apn)s, %(county)s, %(state)s,
    %(owner_name)s, %(address_raw)s, %(address_norm)s,
    %(city)s, %(zip_code)s,
    %(land_value)s, %(improvement_value)s, %(total_cad_value)s,
    %(sqft)s, %(year_built)s, %(bedrooms)s, %(bathrooms)s,
    NOW()
)
ON CONFLICT (apn) DO UPDATE SET
    owner_name          = EXCLUDED.owner_name,
    address_raw         = EXCLUDED.address_raw,
    address_norm        = EXCLUDED.address_norm,
    city                = EXCLUDED.city,
    zip_code            = EXCLUDED.zip_code,
    land_value          = EXCLUDED.land_value,
    improvement_value   = EXCLUDED.improvement_value,
    total_cad_value     = EXCLUDED.total_cad_value,
    sqft                = EXCLUDED.sqft,
    year_built          = EXCLUDED.year_built,
    bedrooms            = EXCLUDED.bedrooms,
    bathrooms           = EXCLUDED.bathrooms,
    cad_refreshed_at    = NOW(),
    updated_at          = NOW()
RETURNING (xmax = 0) AS is_insert;
"""


def _normalize_address_stub(address_raw: Optional[str]) -> Optional[str]:
    """
    TODO: Replace with real USPS / SmartyStreets / Google Maps call.
    Returns the raw address unchanged until normalization service is wired up.
    """
    return address_raw


def upsert_parcels(conn: "psycopg2.connection", parcels: list[dict]) -> dict:
    """
    Upsert a list of normalized parcel dicts, one row at a time.

    Returns a summary dict: {inserted, updated, errors}.

    Each row is wrapped in a SAVEPOINT so a constraint violation or bad value
    on one row rolls back only that row, leaving all prior successes in the
    transaction intact. This rules out execute_batch/execute_values, which
    send rows in bulk and cannot wrap individual rows in savepoints.
    """
    for p in parcels:
        p["address_norm"] = _normalize_address_stub(p.get("address_raw"))

    inserted = updated = errors = 0

    with conn.cursor() as cur:
        for row in parcels:
            try:
                cur.execute("SAVEPOINT upsert_row")
                cur.execute(_UPSERT_SQL, row)
                cur.execute("RELEASE SAVEPOINT upsert_row")
                (is_insert,) = cur.fetchone()
                if is_insert:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                logger.error("Upsert failed for APN %s — %s", row.get("apn"), exc)
                cur.execute("ROLLBACK TO SAVEPOINT upsert_row")
                cur.execute("RELEASE SAVEPOINT upsert_row")
                errors += 1

        conn.commit()

    return {"inserted": inserted, "updated": updated, "errors": errors}


def upsert_parcels_batch(conn: "psycopg2.connection", parcels: list[dict], batch_size: int = 500) -> dict:
    """
    Stream upserts in configurable batches to cap memory usage on large county files.
    Commits after each batch so partial progress is preserved on failure.
    """
    totals = {"inserted": 0, "updated": 0, "errors": 0}

    batch: list[dict] = []
    for parcel in parcels:
        batch.append(parcel)
        if len(batch) >= batch_size:
            result = upsert_parcels(conn, batch)
            for k in totals:
                totals[k] += result[k]
            batch.clear()

    if batch:
        result = upsert_parcels(conn, batch)
        for k in totals:
            totals[k] += result[k]

    return totals
