"""Alert Engine — two entry points:

  1. FastAPI app  (GET /health, POST /digest)
       uvicorn services.alert_engine.main:app

  2. SQS consumer loop
       python -m services.alert_engine.main --consumer
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
from fastapi import FastAPI

logger = logging.getLogger(__name__)

from .consumer import run_consumer
from .digest import build_digest_rows, format_digest
from .notifier import dispatch

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


app = FastAPI(title="Alert Engine", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "alert-engine"}


@app.post("/api/v1/digest", summary="Send daily digest to all users with alerts in last 24 h")
async def send_digest():
    pool = app.state.pool
    entries = await build_digest_rows(pool)
    sent = failed = 0
    for entry in entries:
        subject, body = format_digest(entry)
        try:
            dispatch(entry.channel, entry.contact, subject, body)
            sent += 1
        except Exception:
            logger.exception("Failed to send digest to %s via %s", entry.contact, entry.channel)
            failed += 1
    return {"digests_sent": sent, "digests_failed": failed}


# ── CLI consumer entry point ──────────────────────────────────────────────────

async def _run_consumer_standalone():
    dsn = os.environ.get("DATABASE_URL")
    pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10, command_timeout=30)
    try:
        await run_consumer(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    if "--consumer" in sys.argv:
        asyncio.run(_run_consumer_standalone())
    else:
        import uvicorn
        uvicorn.run("services.alert_engine.main:app", host="0.0.0.0", port=8004, reload=False)
