"""
Estated API client with cache-aware fetch logic.

Cache rule: reuse the most recent valuation for a property when it is
younger than AVM_MAX_AGE_DAYS (default 60).  Only call Estated when no
fresh valuation exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
import asyncpg

_ESTATED_BASE = "https://api.estated.com/property/v3"
_AVM_MAX_AGE_DAYS = int(os.environ.get("AVM_MAX_AGE_DAYS", "60"))


@dataclass
class AvmResult:
    avm: float
    confidence_score: Optional[float]
    valuation_date: date
    provider: str
    raw_response: dict
    from_cache: bool  # True when served from valuations table without an API call


async def _fetch_cached(
    pool: asyncpg.Pool, property_id: UUID
) -> Optional[AvmResult]:
    """Return a cached valuation if one exists and is still fresh."""
    row = await pool.fetchrow(
        """
        SELECT avm, confidence_score, valuation_date
        FROM   valuations
        WHERE  property_id = $1
          AND  provider    = 'estated'
          AND  avm IS NOT NULL
          AND  valuation_date >= (CURRENT_DATE - $2::int)
        ORDER  BY valuation_date DESC NULLS LAST
        LIMIT  1
        """,
        property_id,
        _AVM_MAX_AGE_DAYS,
    )
    if row is None:
        return None
    return AvmResult(
        avm=float(row["avm"]),
        confidence_score=float(row["confidence_score"]) if row["confidence_score"] is not None else None,
        valuation_date=row["valuation_date"],
        provider="estated",
        raw_response={},
        from_cache=True,
    )


async def _call_estated(address: str, city: str, state: str, zip_code: str) -> dict:
    api_key = os.environ["ESTATED_API_KEY"]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            _ESTATED_BASE,
            params={
                "token": api_key,
                "address": address,
                "city": city,
                "state": state,
                "zip": zip_code,
            },
        )
        r.raise_for_status()
        return r.json()


def _parse_estated_response(data: dict) -> tuple[float, Optional[float], date]:
    """Extract avm, confidence, and valuation_date from an Estated response."""
    prop = data.get("data", {})

    # Estated v3 returns estimated_value under assessments.estimated_value
    # and a valuation object under valuations[0]
    valuations = prop.get("valuations") or []
    if valuations:
        v = valuations[0]
        avm = float(v.get("value") or 0)
        confidence = float(v.get("confidence") or 0) or None
        val_date_str = v.get("date")
        val_date = date.fromisoformat(val_date_str) if val_date_str else date.today()
    else:
        # Fallback: use assessed value
        assessment = prop.get("assessments") or [{}]
        a = assessment[0] if assessment else {}
        avm = float(a.get("total_assessed_value") or 0)
        confidence = None
        val_date = date.today()

    return avm, confidence, val_date


async def _persist_valuation(
    pool: asyncpg.Pool,
    property_id: UUID,
    result: AvmResult,
) -> None:
    await pool.execute(
        """
        INSERT INTO valuations
            (property_id, avm, confidence_score, raw_response, valuation_date,
             provider, calculated_at)
        VALUES ($1, $2, $3, $4, $5, 'estated', $6)
        """,
        property_id,
        result.avm,
        result.confidence_score,
        result.raw_response,
        result.valuation_date,
        datetime.now(tz=timezone.utc),
    )


async def get_avm(
    pool: asyncpg.Pool,
    property_id: UUID,
    address: str,
    city: str,
    state: str = "TX",
    zip_code: str = "",
    force_refresh: bool = False,
) -> AvmResult:
    """Return AVM for a property, using cache when fresh enough.

    Set force_refresh=True to bypass the cache and always call Estated.
    Raises httpx.HTTPError on API failure.
    """
    if not force_refresh:
        cached = await _fetch_cached(pool, property_id)
        if cached:
            return cached

    raw = await _call_estated(address, city, state, zip_code)
    avm, confidence, val_date = _parse_estated_response(raw)

    result = AvmResult(
        avm=avm,
        confidence_score=confidence,
        valuation_date=val_date,
        provider="estated",
        raw_response=raw,
        from_cache=False,
    )
    await _persist_valuation(pool, property_id, result)
    return result
