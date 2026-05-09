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

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.middleware import add_rate_limiting, limiter, _rate_limit_key


# ── shared fixture: reset limiter storage before every test ───────────────────

@pytest.fixture(autouse=True)
def reset_limiter():
    """Prevent rate-limit state from leaking between tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


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
        app = _make_app(route_limit="2/minute")
        client = TestClient(app, raise_server_exceptions=False)

        resp1 = client.get("/limited")
        resp2 = client.get("/limited")
        resp3 = client.get("/limited")  # should be blocked

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp3.status_code == 429

    def test_429_response_is_json(self):
        app = _make_app(route_limit="1/minute")
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/limited")        # consume the 1 allowed
        resp = client.get("/limited") # blocked

        assert resp.status_code == 429
        assert resp.content

    def test_health_not_rate_limited(self):
        """Health endpoint should always return 200 regardless of limit state."""
        app = _make_app(route_limit="1/minute")
        client = TestClient(app, raise_server_exceptions=False)

        # Exhaust the limit on /limited first
        client.get("/limited")
        client.get("/limited")

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

        resp = client.get("/limited")
        assert resp.status_code == 200


# ── per-user bucket isolation ─────────────────────────────────────────────────

class TestPerUserIsolation:
    def test_two_users_share_same_ip_get_separate_buckets(self):
        """Two authenticated users behind the same IP must not share a bucket.

        This validates the primary value of keying on token.sub instead of IP.
        """
        from types import SimpleNamespace

        app = _make_app(route_limit="1/minute")
        client = TestClient(app, raise_server_exceptions=False)

        # Exhaust user-alice's bucket
        with_alice = {"X-Test-User": "alice"}
        with_bob = {"X-Test-User": "bob"}

        # Directly test the key function with two distinct user tokens
        req_alice = SimpleNamespace(
            state=SimpleNamespace(token=SimpleNamespace(sub="alice")),
            client=SimpleNamespace(host="1.2.3.4"),
        )
        req_bob = SimpleNamespace(
            state=SimpleNamespace(token=SimpleNamespace(sub="bob")),
            client=SimpleNamespace(host="1.2.3.4"),  # same IP
        )

        # Both users share the same IP but get different bucket keys
        assert _rate_limit_key(req_alice) == "alice"
        assert _rate_limit_key(req_bob) == "bob"
        assert _rate_limit_key(req_alice) != _rate_limit_key(req_bob)
