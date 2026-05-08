"""Opportunity Dashboard API — GET /api/v1/opportunities."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

import asyncio

import asyncpg
from fastapi import FastAPI, Query

from .models import OpportunitiesResponse, OpportunityItem, SortDir, SortField
from .query import build_query

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


app = FastAPI(title="Opportunity Dashboard API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "opportunity-dashboard"}


@app.get("/api/v1/opportunities", response_model=OpportunitiesResponse)
async def list_opportunities(
    county:              Optional[str]   = Query(None, description="Filter by county name"),
    case_type:           Optional[str]   = Query(None, description="foreclosure | tax_delinquency | probate | preforeclosure"),
    min_distress_score:  Optional[float] = Query(None, ge=0, le=100, description="Minimum distress score (0–100)"),
    min_equity_pct:      Optional[float] = Query(None, description="Minimum equity percentage"),
    auction_date_before: Optional[date]  = Query(None, description="Only properties with auction_date ≤ this date"),
    sort_by:  SortField = Query("distress_score", description="Field to sort results by"),
    sort_dir: SortDir   = Query("desc",           description="Sort direction: asc or desc"),
    page:      int = Query(1,   ge=1,          description="1-based page number"),
    page_size: int = Query(20,  ge=1, le=200,  description="Rows per page"),
):
    pool = app.state.pool
    offset = (page - 1) * page_size

    data_sql, data_params, count_sql, count_params = build_query(
        county=county,
        case_type=case_type,
        min_distress_score=min_distress_score,
        min_equity_pct=min_equity_pct,
        auction_date_before=auction_date_before,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=page_size,
        offset=offset,
    )

    rows, count_row = await _fetch(pool, data_sql, data_params, count_sql, count_params)

    total = count_row["total"] if count_row else 0

    items = [
        OpportunityItem(
            property_id=row["property_id"],
            address=row["address"],
            city=row["city"],
            county=row["county"],
            zip_code=row["zip_code"],
            sqft=row["sqft"],
            bedrooms=row["bedrooms"],
            bathrooms=float(row["bathrooms"]) if row["bathrooms"] is not None else None,
            year_built=row["year_built"],
            owner_name=row["owner_name"],
            distress_score=float(row["distress_score"]) if row["distress_score"] is not None else None,
            equity_pct=float(row["equity_pct"])         if row["equity_pct"]     is not None else None,
            equity_amount=float(row["equity_amount"])   if row["equity_amount"]  is not None else None,
            avm=float(row["avm"])                       if row["avm"]            is not None else None,
            arv=float(row["arv"])                       if row["arv"]            is not None else None,
            mao=float(row["mao"])                       if row["mao"]            is not None else None,
            event_type=row["event_type"],
            foreclosure_stage=row["foreclosure_stage"],
            filing_date=row["filing_date"],
            auction_date=row["auction_date"],
        )
        for row in rows
    ]

    return OpportunitiesResponse(total=total, page=page, page_size=page_size, items=items)


async def _fetch(pool, data_sql, data_params, count_sql, count_params):
    rows, count_row = await asyncio.gather(
        pool.fetch(data_sql, *data_params),
        pool.fetchrow(count_sql, *count_params),
    )
    return rows, count_row
