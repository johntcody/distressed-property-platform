"""Property Service routes."""

import os
from typing import List, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from .models import Property, PropertyCreate
from .normalizer import PropertyNormalizer

router = APIRouter()

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10, command_timeout=30)
    return _pool


def _row_to_property(row: asyncpg.Record) -> Property:
    return Property(
        id=str(row["id"]),
        address=row["address"],
        city=row["city"],
        county=row["county"],
        state=row["state"],
        zip_code=row["zip_code"] or "",
        distress_type=row["distress_type"],
        owner_name=row.get("owner_name"),
        parcel_id=row.get("apn"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/properties", response_model=List[Property])
async def list_properties(
    county: Optional[str] = None,
    distress_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    pool: asyncpg.Pool = Depends(_get_pool),
):
    """List properties with optional county/distress_type filters. Joins latest event for distress_type."""
    filters = []
    params: list = []

    if county:
        params.append(county.lower())
        filters.append(f"p.county = ${len(params)}")
    if distress_type:
        params.append(distress_type)
        filters.append(f"latest_event.event_type = ${len(params)}")

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [limit, offset]

    rows = await pool.fetch(
        f"""
        SELECT
            p.id, p.apn, p.address, p.city, p.county, p.state, p.zip_code,
            p.owner_name, p.created_at, p.updated_at,
            COALESCE(latest_event.event_type, 'foreclosure') AS distress_type
        FROM properties p
        LEFT JOIN LATERAL (
            SELECT event_type
            FROM events
            WHERE property_id = p.id
            ORDER BY filing_date DESC NULLS LAST
            LIMIT 1
        ) latest_event ON true
        {where}
        ORDER BY p.updated_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )
    return [_row_to_property(r) for r in rows]


@router.get("/properties/{property_id}", response_model=Property)
async def get_property(property_id: str, pool: asyncpg.Pool = Depends(_get_pool)):
    try:
        UUID(property_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    row = await pool.fetchrow(
        """
        SELECT
            p.id, p.apn, p.address, p.city, p.county, p.state, p.zip_code,
            p.owner_name, p.created_at, p.updated_at,
            COALESCE(latest_event.event_type, 'foreclosure') AS distress_type
        FROM properties p
        LEFT JOIN LATERAL (
            SELECT event_type
            FROM events
            WHERE property_id = p.id
            ORDER BY filing_date DESC NULLS LAST
            LIMIT 1
        ) latest_event ON true
        WHERE p.id = $1
        """,
        property_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")
    return _row_to_property(row)


@router.post("/properties", response_model=Property, status_code=201)
async def create_property(payload: PropertyCreate, pool: asyncpg.Pool = Depends(_get_pool)):
    normalizer = PropertyNormalizer(pool)
    property_data = {
        "address": payload.address,
        "city": payload.city,
        "county": payload.county.lower(),
        "state": "TX",
        "zip_code": payload.zip_code,
        "owner_name": payload.owner_name,
        "apn": payload.parcel_id,
    }
    property_id, _ = await normalizer.normalize_and_upsert(
        raw_address=payload.address,
        county=payload.county,
        property_data=property_data,
    )
    row = await pool.fetchrow(
        """
        SELECT
            p.id, p.apn, p.address, p.city, p.county, p.state, p.zip_code,
            p.owner_name, p.created_at, p.updated_at,
            $2::text AS distress_type
        FROM properties p
        WHERE p.id = $1
        """,
        property_id,
        payload.distress_type.value,
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve created property")
    return _row_to_property(row)


@router.delete("/properties/{property_id}", status_code=204)
async def delete_property(property_id: str, pool: asyncpg.Pool = Depends(_get_pool)):
    try:
        UUID(property_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    result = await pool.execute("DELETE FROM properties WHERE id = $1", property_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Property not found")
