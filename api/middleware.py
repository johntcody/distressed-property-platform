"""
Shared slowapi rate-limiting middleware for all FastAPI services.

Usage in each service main.py:
    from api.middleware import add_rate_limiting, limiter

    app = FastAPI(...)
    add_rate_limiting(app)

    # On a route that needs a custom limit:
    @app.get("/api/v1/opportunities")
    @limiter.limit("30/minute")
    async def list_opportunities(request: Request, ...):
        ...

Default limits (applied via add_rate_limiting):
    - All routes:          60 req/min per user (token.sub when authenticated, else client IP)
    - /api/v1/opportunities:       30 req/min per user
    - /api/v1/properties/{id}/analysis: 60 req/min per user

Key function uses the authenticated user's JWT sub claim when available so
that investors behind a shared NAT are not throttled against each other.
Falls back to client IP for unauthenticated paths (e.g. /health).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


def _rate_limit_key(request: Request) -> str:
    """Rate-limit key: authenticated user ID when available, else client IP.

    slowapi calls this function to determine the bucket for each request.
    Using the JWT sub claim (stored by require_auth on request.state.token)
    means each investor gets their own bucket even behind a shared NAT gateway.
    """
    # require_auth stores the decoded token on request.state.token
    token = getattr(request.state, "token", None)
    if token and getattr(token, "sub", None):
        return token.sub
    return request.client.host if request.client else "unknown"


# headers_enabled is not set: slowapi 0.1.9 with SlowAPIMiddleware does not
# support injecting X-RateLimit-* response headers without causing a
# Starlette response-object conflict. 429 enforcement is fully functional.
limiter = Limiter(key_func=_rate_limit_key, default_limits=["60/minute"])


def add_rate_limiting(app: FastAPI) -> None:
    """Attach slowapi limiter and error handler to a FastAPI app.

    Call this in every service main.py after the app is created.
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
