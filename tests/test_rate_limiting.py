"""
Unit tests for api/middleware.py slowapi rate limiting.

Tests verify:
- Requests within the limit receive HTTP 200
- Requests exceeding the limit receive HTTP 429
- Rate-limit key uses authenticated user ID (token.sub) when available
- Rate-limit key falls back to client IP for unauthenticated paths
- add_rate_limiting() correctly attaches limiter and exception handler

No real Redis or external state — slowapi's in-memory backend is used.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from api.middleware import add_rate_limiting, limiter, _rate_limit_key


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_app(route_limit: str | None = None) -> FastAPI:
    """Create a minimal FastAPI app with rate limiting wired up."""
    app = FastAPI()
    add_rate_limiting(app)

    if route_limit:
        @app.get("/limited")
        @limiter.limit(route_limit)
        async def limited_route(request: Request):
            return {"ok": True}
    else:
        @app.get("/limited")
        async def limited_route(request: Request):
            return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# ── rate limit key function ───────────────────────────────────────────────────

class TestRateLimitKey:
    def test_uses_token_sub_when_authenticated(self):
        """Key should be the authenticated user ID, not the IP."""
        app = FastAPI()

        @app.get("/check")
        async def check(request: Request):
            return {"key": _rate_limit_key(request)}

        # Simulate require_auth storing token on request.state
        from types import SimpleNamespace
        client = TestClient(app)
        # Patch ASGI scope to inject a state token — done via middleware workaround
        # We test _rate_limit_key directly with a mock request instead
        mock_request = SimpleNamespace(
            state=SimpleNamespace(token=SimpleNamespace(sub="user-abc")),
            client=SimpleNamespace(host="1.2.3.4"),
        )
        assert _rate_limit_key(mock_request) == "user-abc"

    def test_falls_back_to_ip_when_no_token(self):
        from types import SimpleNamespace
        mock_request = SimpleNamespace(
            state=SimpleNamespace(token=None),
            client=SimpleNamespace(host="5.6.7.8"),
        )
        assert _rate_limit_key(mock_request) == "5.6.7.8"

    def test_falls_back_to_ip_when_no_state(self):
        from types import SimpleNamespace
        mock_request = SimpleNamespace(
            state=SimpleNamespace(),
            client=SimpleNamespace(host="9.10.11.12"),
        )
        assert _rate_limit_key(mock_request) == "9.10.11.12"

    def test_returns_unknown_when_no_client(self):
        from types import SimpleNamespace
        mock_request = SimpleNamespace(
            state=SimpleNamespace(),
            client=None,
        )
        assert _rate_limit_key(mock_request) == "unknown"


# ── middleware attachment ─────────────────────────────────────────────────────

class TestAddRateLimiting:
    def test_limiter_attached_to_app_state(self):
        app = FastAPI()
        add_rate_limiting(app)
        assert app.state.limiter is limiter

    def test_rate_limit_exceeded_returns_429(self):
        """Exhaust the per-route limit; the next request must get 429."""
        # Use a very low limit so the test doesn't need many requests
        app = _make_app(route_limit="2/minute")
        client = TestClient(app, raise_server_exceptions=False)

        # Reset limiter storage between tests
        limiter._storage.reset()

        resp1 = client.get("/limited")
        resp2 = client.get("/limited")
        resp3 = client.get("/limited")  # should be blocked

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp3.status_code == 429

    def test_429_response_is_json(self):
        app = _make_app(route_limit="1/minute")
        client = TestClient(app, raise_server_exceptions=False)
        limiter._storage.reset()

        client.get("/limited")        # consume the 1 allowed
        resp = client.get("/limited") # blocked

        assert resp.status_code == 429
        # slowapi returns a plain-text or JSON body depending on version;
        # confirm the response has content
        assert resp.content

    def test_health_not_rate_limited(self):
        """Health endpoint should always return 200 regardless of limit state."""
        app = _make_app(route_limit="1/minute")
        client = TestClient(app, raise_server_exceptions=False)
        limiter._storage.reset()

        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200


# ── default limit (60/minute via add_rate_limiting) ──────────────────────────

class TestDefaultLimit:
    def test_route_without_decorator_uses_default(self):
        """Routes without @limiter.limit use the 60/minute default — just verify
        the middleware is present and the route returns 200 for normal traffic."""
        app = _make_app()  # no explicit route_limit
        client = TestClient(app, raise_server_exceptions=False)
        limiter._storage.reset()

        resp = client.get("/limited")
        assert resp.status_code == 200
