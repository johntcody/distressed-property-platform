"""Property Detail API — four endpoints per property ID."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import FastAPI, HTTPException

from .models import (
    AnalysisItem,
    AnalysisResponse,
    EventItem,
    EventsResponse,
    PropertyDetail,
    ValuationItem,
    ValuationsResponse,
)
from .queries import (
    ANALYSIS_SQL,
    EQUITY_SQL,
    EVENTS_SQL,
    PROPERTY_DETAIL_SQL,
    PROPERTY_EXISTS_SQL,
    VALUATIONS_SQL,
)

_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    dsn = os.environ.get("DATABASE_URL")
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10, command_timeout=30)
    app.state.pool = _pool
    yield
    await _pool.close()
    _pool = None


app = FastAPI(title="Property Detail API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "property-detail"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _not_found(property_id: UUID) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Property {property_id} not found")


async def _require_property(pool, property_id: UUID) -> None:
    """Raise 404 if the property does not exist."""
    row = await pool.fetchrow(PROPERTY_EXISTS_SQL, property_id)
    if row is None:
        raise _not_found(property_id)


def _float(val) -> Optional[float]:
    return float(val) if val is not None else None


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/properties/{property_id}", response_model=PropertyDetail)
async def get_property(property_id: UUID):
    pool = app.state.pool
    row = await pool.fetchrow(PROPERTY_DETAIL_SQL, property_id)
    if row is None:
        raise _not_found(property_id)
    return PropertyDetail(
        property_id=row["property_id"],
        apn=row["apn"],
        address_raw=row["address_raw"],
        address_norm=row["address_norm"],
        city=row["city"],
        county=row["county"],
        state=row["state"],
        zip_code=row["zip_code"],
        legal_description=row["legal_description"],
        owner_name=row["owner_name"],
        sqft=row["sqft"],
        bedrooms=row["bedrooms"],
        bathrooms=_float(row["bathrooms"]),
        year_built=row["year_built"],
        land_value=_float(row["land_value"]),
        improvement_value=_float(row["improvement_value"]),
        total_cad_value=_float(row["total_cad_value"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        distress_score=_float(row["distress_score"]),
        equity_pct=_float(row["equity_pct"]),
        equity_amount=_float(row["equity_amount"]),
        avm=_float(row["avm"]),
        market_score=_float(row["market_score"]),
        estimated_liens=_float(row["estimated_liens"]),
        tax_owed=_float(row["tax_owed"]),
        score_calculated_at=row["score_calculated_at"],
    )


@app.get("/api/v1/properties/{property_id}/events", response_model=EventsResponse)
async def get_events(property_id: UUID):
    pool = app.state.pool
    await _require_property(pool, property_id)
    rows = await pool.fetch(EVENTS_SQL, property_id)
    items = [
        EventItem(
            event_id=row["event_id"],
            event_type=row["event_type"],
            county=row["county"],
            filing_date=row["filing_date"],
            auction_date=row["auction_date"],
            foreclosure_stage=row["foreclosure_stage"],
            borrower_name=row["borrower_name"],
            lender_name=row["lender_name"],
            trustee_name=row["trustee_name"],
            loan_amount=_float(row["loan_amount"]),
            tax_amount_owed=_float(row["tax_amount_owed"]),
            years_delinquent=row["years_delinquent"],
            case_number=row["case_number"],
            source_url=row["source_url"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return EventsResponse(property_id=property_id, total=len(items), items=items)


@app.get("/api/v1/properties/{property_id}/analysis", response_model=AnalysisResponse)
async def get_analysis(property_id: UUID):
    pool = app.state.pool
    await _require_property(pool, property_id)
    rows = await pool.fetch(ANALYSIS_SQL, property_id)
    items = [
        AnalysisItem(
            analysis_id=row["analysis_id"],
            record_type=row["record_type"],
            rehab_level=row["rehab_level"],
            rehab_cost=_float(row["rehab_cost"]),
            rehab_cost_sqft=_float(row["rehab_cost_sqft"]),
            arv_used=_float(row["arv_used"]),
            discount_pct=_float(row["discount_pct"]),
            holding_costs=_float(row["holding_costs"]),
            closing_costs=_float(row["closing_costs"]),
            mao=_float(row["mao"]),
            mao_version=row["mao_version"],
            notes=row["notes"],
            calculated_at=row["calculated_at"],
            valuation_arv=_float(row["valuation_arv"]),
            arv_confidence=_float(row["arv_confidence"]),
            comp_count=row["comp_count"],
            method=row["method"],
            provider=row["provider"],
        )
        for row in rows
    ]
    return AnalysisResponse(property_id=property_id, items=items)


@app.get("/api/v1/properties/{property_id}/valuations", response_model=ValuationsResponse)
async def get_valuations(property_id: UUID):
    pool = app.state.pool
    await _require_property(pool, property_id)
    rows, equity_row = await _fetch_valuations(pool, property_id)
    items = [
        ValuationItem(
            valuation_id=row["valuation_id"],
            avm=_float(row["avm"]),
            arv=_float(row["arv"]),
            arv_confidence=_float(row["arv_confidence"]),
            comp_count=row["comp_count"],
            method=row["method"],
            provider=row["provider"],
            confidence_score=_float(row["confidence_score"]),
            valuation_date=row["valuation_date"],
            arv_version=row["arv_version"],
            calculated_at=row["calculated_at"],
        )
        for row in rows
    ]
    return ValuationsResponse(
        property_id=property_id,
        equity_pct=_float(equity_row["equity_pct"]) if equity_row else None,
        equity_amount=_float(equity_row["equity_amount"]) if equity_row else None,
        estimated_liens=_float(equity_row["estimated_liens"]) if equity_row else None,
        tax_owed=_float(equity_row["tax_owed"]) if equity_row else None,
        items=items,
    )


async def _fetch_valuations(pool, property_id):
    rows, equity_row = await asyncio.gather(
        pool.fetch(VALUATIONS_SQL, property_id),
        pool.fetchrow(EQUITY_SQL, property_id),
    )
    return rows, equity_row
