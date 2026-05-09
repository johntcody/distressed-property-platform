"""
AVM client with pluggable provider support.

Provider is selected at runtime via the AVM_PROVIDER environment variable:
  - "attom"  — ATTOM Data API (production)
  - anything else / unset — no external call; caller falls back to CAD value

Cache rule: reuse the most recent valuation for a property when it is
younger than AVM_MAX_AGE_DAYS (default 60).  Only call the provider when
no fresh valuation exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
import asyncpg

_AVM_PROVIDER    = os.environ.get("AVM_PROVIDER", "").lower()   # "attom" in production
_AVM_MAX_AGE_DAYS = int(os.environ.get("AVM_MAX_AGE_DAYS", "60"))

_ATTOM_BASE = "https://api.gateway.attomdata.com/propertyapi/v1.0.0/property/detail"


@dataclass
class AvmResult:
    avm: float
    confidence_score: Optional[float]
    valuation_date: date
    provider: str
    raw_response: dict
    from_cache: bool  # True when served from valuations table without an API call


# ── cache ─────────────────────────────────────────────────────────────────────

async def _fetch_cached(
    pool: asyncpg.Pool, property_id: UUID, provider: str
) -> Optional[AvmResult]:
    """Return a fresh cached valuation for the given provider, or None."""
    row = await pool.fetchrow(
        """
        SELECT avm, confidence_score, valuation_date
        FROM   valuations
        WHERE  property_id = $1
          AND  provider    = $2
          AND  avm IS NOT NULL
          AND  valuation_date >= (CURRENT_DATE - $3::int)
        ORDER  BY valuation_date DESC NULLS LAST
        LIMIT  1
        """,
        property_id,
        provider,
        _AVM_MAX_AGE_DAYS,
    )
    if row is None:
        return None
    return AvmResult(
        avm=float(row["avm"]),
        confidence_score=float(row["confidence_score"]) if row["confidence_score"] is not None else None,
        valuation_date=row["valuation_date"],
        provider=provider,
        raw_response={},
        from_cache=True,
    )


# ── ATTOM provider ────────────────────────────────────────────────────────────

async def _call_attom(address: str, city: str, state: str, zip_code: str) -> dict:
    """Call the ATTOM Property Detail endpoint and return the raw JSON."""
    from services.config import get_attom_api_key
    api_key = get_attom_api_key()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            _ATTOM_BASE,
            headers={"apikey": api_key, "accept": "application/json"},
            params={
                "address1": address,
                "address2": f"{city}, {state} {zip_code}".strip(),
            },
        )
        r.raise_for_status()
        return r.json()


def _parse_attom_response(data: dict) -> tuple[float, Optional[float], date]:
    """Extract avm, confidence, and valuation_date from an ATTOM Property Detail response.

    ATTOM returns assessed value under property[0].assessment.assessed.assdttlvalue.
    A market AVM is available under property[0].avm.amount.value when the
    AVM add-on is enabled on the subscription.
    """
    properties = data.get("property") or []
    prop = properties[0] if properties else {}

    # Prefer AVM add-on value; fall back to assessed total
    avm_block = prop.get("avm", {})
    avm_value = avm_block.get("amount", {}).get("value") if avm_block else None

    if avm_value:
        avm = float(avm_value)
        confidence_raw = avm_block.get("amount", {}).get("high")
        # ATTOM doesn't return a 0–100 confidence score; derive a proxy from
        # the high/low spread as a % of value (tighter spread = higher confidence).
        low  = float(avm_block.get("amount", {}).get("low")  or avm)
        high = float(avm_block.get("amount", {}).get("high") or avm)
        spread_pct = (high - low) / avm * 100 if avm > 0 else 100
        confidence: Optional[float] = round(max(0.0, 100 - spread_pct), 2)
    else:
        assessment = prop.get("assessment", {}).get("assessed", {})
        avm = float(assessment.get("assdttlvalue") or 0)
        confidence = None

    # ATTOM assessment year → use Jan 1 of that year as valuation_date
    assessment_year = prop.get("assessment", {}).get("tax", {}).get("taxyear")
    if assessment_year:
        val_date = date(int(assessment_year), 1, 1)
    else:
        val_date = date.today()

    return avm, confidence, val_date


# ── persistence ───────────────────────────────────────────────────────────────

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
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        property_id,
        result.avm,
        result.confidence_score,
        result.raw_response,
        result.valuation_date,
        result.provider,
        datetime.now(tz=timezone.utc),
    )


# ── public entry point ────────────────────────────────────────────────────────

async def get_avm(
    pool: asyncpg.Pool,
    property_id: UUID,
    address: str,
    city: str,
    state: str = "TX",
    zip_code: str = "",
    force_refresh: bool = False,
) -> Optional[AvmResult]:
    """Return AVM for a property.

    Returns None when no provider is configured (AVM_PROVIDER unset).
    Callers should fall back to CAD data in that case.

    In production set AVM_PROVIDER=attom and ATTOM_API_KEY.
    Cache is bypassed when force_refresh=True.
    """
    provider = _AVM_PROVIDER
    if not provider:
        return None  # no provider configured — caller uses CAD fallback

    if not force_refresh:
        cached = await _fetch_cached(pool, property_id, provider)
        if cached:
            return cached

    if provider == "attom":
        raw = await _call_attom(address, city, state, zip_code)
        avm, confidence, val_date = _parse_attom_response(raw)
    else:
        raise ValueError(f"Unknown AVM_PROVIDER: {provider!r}")

    result = AvmResult(
        avm=avm,
        confidence_score=confidence,
        valuation_date=val_date,
        provider=provider,
        raw_response=raw,
        from_cache=False,
    )
    await _persist_valuation(pool, property_id, result)
    return result
