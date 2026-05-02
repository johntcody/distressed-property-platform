"""Async Postgres connection pool shared across all ingestion workers."""

import asyncio
import os
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    global _pool
    # Double-checked locking — avoids creating multiple pools under concurrent startup
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                dsn = os.environ.get("DATABASE_URL")
                if not dsn:
                    raise RuntimeError("DATABASE_URL environment variable is not set")
                _pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=2,
                    max_size=10,
                    command_timeout=30,
                )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def upsert_property(pool: asyncpg.Pool, data: dict) -> str:
    """Insert or update a property record; returns the property UUID."""
    row = await pool.fetchrow(
        """
        INSERT INTO properties (
            apn, address, address_norm, city, county, state, zip_code,
            lat, lon, owner_name, sqft, beds, baths, year_built,
            land_value, improvement_value, legal_description
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17
        )
        ON CONFLICT (apn) DO UPDATE SET
            address_norm      = EXCLUDED.address_norm,
            owner_name        = COALESCE(EXCLUDED.owner_name, properties.owner_name),
            sqft              = COALESCE(EXCLUDED.sqft, properties.sqft),
            beds              = COALESCE(EXCLUDED.beds, properties.beds),
            baths             = COALESCE(EXCLUDED.baths, properties.baths),
            year_built        = COALESCE(EXCLUDED.year_built, properties.year_built),
            land_value        = COALESCE(EXCLUDED.land_value, properties.land_value),
            improvement_value = COALESCE(EXCLUDED.improvement_value, properties.improvement_value),
            updated_at        = NOW()
        RETURNING id
        """,
        data.get("apn"),
        data["address"],
        data.get("address_norm"),
        data["city"],
        data["county"],
        data.get("state", "TX"),
        data.get("zip_code"),
        data.get("lat"),
        data.get("lon"),
        data.get("owner_name"),
        data.get("sqft"),
        data.get("beds"),
        data.get("baths"),
        data.get("year_built"),
        data.get("land_value"),
        data.get("improvement_value"),
        data.get("legal_description"),
    )
    return str(row["id"])


async def insert_event(pool: asyncpg.Pool, data: dict) -> Optional[str]:
    """Insert an event; skip silently on duplicate dedup_key. Returns UUID or None."""
    import json

    row = await pool.fetchrow(
        """
        INSERT INTO events (
            property_id, event_type, county, filing_date, auction_date,
            foreclosure_stage, borrower_name, lender_name, trustee_name, loan_amount,
            tax_amount_owed, years_delinquent,
            case_number, decedent_name, executor_name,
            lp_instrument_number, lp_keywords,
            legal_description, source_url, raw_data, dedup_key
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21
        )
        ON CONFLICT (dedup_key) DO NOTHING
        RETURNING id
        """,
        data.get("property_id"),
        data["event_type"],
        data["county"],
        data.get("filing_date"),
        data.get("auction_date"),
        data.get("foreclosure_stage"),
        data.get("borrower_name"),
        data.get("lender_name"),
        data.get("trustee_name"),
        data.get("loan_amount"),
        data.get("tax_amount_owed"),
        data.get("years_delinquent"),
        data.get("case_number"),
        data.get("decedent_name"),
        data.get("executor_name"),
        data.get("lp_instrument_number"),
        data.get("lp_keywords"),
        data.get("legal_description"),
        data.get("source_url"),
        json.dumps(data.get("raw_data")) if data.get("raw_data") else None,
        data.get("dedup_key"),
    )
    return str(row["id"]) if row else None
