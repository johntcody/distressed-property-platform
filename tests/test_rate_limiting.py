"""
Unit tests for api/middleware.py slowapi rate limiting.

Tests verify:
- Requests within the limit receive HTTP 200
- Requests exceeding the limit receive HTTP 429
- Rate-limit key uses authenticated user ID (token.sub) when available
- Rate-limit key falls back to client IP for unauthenticated paths
- add_rate_limiting() correctly attaches limiter and exception handler

Each test that exercises the 429 path creates its own isolated Limiter +
FastAPI app so no shared state is touched. This avoids relying on
slowapi's private _storage attribute for resets.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.middleware import _rate_limit_key, add_rate_limiting, limiter


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_isolated_app(route_limit: str | None = None) -> FastAPI:
    """Create a FastAPI app with its own isolated Limiter instance.

    Using a fresh Limiter per app avoids any shared in-memory state between
    tests without relying on slowapi's private _storage attribute.
    """
    isolated_limiter = Limiter(key_func=_rate_limit_key, default_limits=["60/minute"])

    app = FastAPI()
    app.state.limiter = isolated_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    if route_limit:
        @app.get("/limited")
        @isolated_limiter.limit(route_limit)
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
        from types import SimpleNamespace
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
        app = _make_isolated_app(route_limit="2/minute")
        client = TestClient(app, raise_server_exceptions=False)

        resp1 = client.get("/limited")
        resp2 = client.get("/limited")
        resp3 = client.get("/limited")  # should be blocked

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp3.status_code == 429

    def test_429_response_has_content(self):
        app = _make_isolated_app(route_limit="1/minute")
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/limited")        # consume the 1 allowed
        resp = client.get("/limited") # blocked

        assert resp.status_code == 429
        assert resp.content

    def test_health_not_rate_limited(self):
        """/health returns 200 even after the route limit on /limited is exhausted.

        /health has no @limiter.limit decorator; its 60/min default applies
        to a separate bucket so exhausting /limited does not affect it.
        """
        app = _make_isolated_app(route_limit="1/minute")
        client = TestClient(app, raise_server_exceptions=False)

        # Exhaust /limited so rate-limit state is active
        client.get("/limited")
        client.get("/limited")

        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200


# ── default limit (60/minute) ─────────────────────────────────────────────────

class TestDefaultLimit:
    def test_route_without_decorator_uses_default(self):
        """Routes without @limiter.limit use the 60/minute default — verify
        normal traffic passes through."""
        app = _make_isolated_app()  # no explicit route_limit
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/limited")
        assert resp.status_code == 200


# ── per-user bucket isolation ─────────────────────────────────────────────────

class TestPerUserIsolation:
    def test_two_users_share_same_ip_get_separate_buckets(self):
        """Two authenticated users behind the same IP must not share a bucket.

        Validates that keying on token.sub (not client IP) gives each investor
        an independent rate-limit counter.
        """
        from types import SimpleNamespace

        req_alice = SimpleNamespace(
            state=SimpleNamespace(token=SimpleNamespace(sub="alice")),
            client=SimpleNamespace(host="1.2.3.4"),
        )
        req_bob = SimpleNamespace(
            state=SimpleNamespace(token=SimpleNamespace(sub="bob")),
            client=SimpleNamespace(host="1.2.3.4"),  # same IP as alice
        )

        assert _rate_limit_key(req_alice) == "alice"
        assert _rate_limit_key(req_bob) == "bob"
        assert _rate_limit_key(req_alice) != _rate_limit_key(req_bob)
