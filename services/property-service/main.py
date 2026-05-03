"""Property Service — CRUD and lookup for distressed property records."""

import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from .routes import router

_pool: asyncpg.Pool | None = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10, command_timeout=30)
    app.state.pool = _pool
    yield
    await _pool.close()
    _pool = None


app = FastAPI(title="Property Service", version="0.1.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "property-service"}
