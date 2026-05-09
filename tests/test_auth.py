"""
Unit tests for api/deps.py JWT authentication.

Tests generate a real RSA-2048 key pair and produce valid/invalid JWTs
to exercise every code path — no network calls, no AWS, no mocks of the
crypto layer.
"""

from __future__ import annotations

import time
from typing import Optional
from unittest.mock import patch

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

# ── RSA key pair (generated once per test session) ────────────────────────────

@pytest.fixture(scope="session")
def rsa_private_key():
    return rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )


@pytest.fixture(scope="session")
def rsa_public_key(rsa_private_key):
    return rsa_private_key.public_key()


@pytest.fixture(scope="session")
def jwks(rsa_public_key):
    """Minimal JWKS document containing the test public key."""
    from jose.backends import RSAKey
    key = RSAKey(rsa_public_key, algorithm="RS256")
    return {"keys": [key.public_key().to_dict()]}


# ── Token factory ─────────────────────────────────────────────────────────────

def make_token(
    private_key,
    sub: str = "user-123",
    exp_offset: int = 900,       # seconds from now; negative = already expired
    algorithm: str = "RS256",
    extra_claims: Optional[dict] = None,
) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "iat": now,
        "exp": now + exp_offset,
        "email": f"{sub}@test.example",
    }
    if extra_claims:
        claims.update(extra_claims)

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(claims, pem, algorithm=algorithm)


# ── Fixture: test FastAPI app with require_auth applied ───────────────────────

@pytest.fixture()
def auth_app(jwks, monkeypatch):
    """A minimal FastAPI app with require_auth as a global dependency."""
    monkeypatch.setenv("JWKS_URI", "https://fake-idp.example.com/.well-known/jwks.json")
    monkeypatch.delenv("JWKS_AUDIENCE", raising=False)
    monkeypatch.delenv("JWKS_ISSUER", raising=False)

    # Patch _get_jwks to return our in-memory JWKS — no HTTP call
    import api.deps as deps
    deps._get_jwks.cache_clear()

    with patch.object(deps, "_get_jwks", return_value=jwks):
        from fastapi import Depends
        from api.deps import TokenPayload, require_auth

        app = FastAPI()

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.get("/api/v1/resource")
        def protected(token: TokenPayload = Depends(require_auth)):
            return {"user_id": token.sub}

        app.dependency_overrides = {}
        yield app


@pytest.fixture()
def client(auth_app):
    return TestClient(auth_app, raise_server_exceptions=False)


# ── /health is always open ────────────────────────────────────────────────────

class TestHealthBypass:
    def test_health_no_token_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_with_token_returns_200(self, client, rsa_private_key):
        token = make_token(rsa_private_key)
        resp = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


# ── Valid token ───────────────────────────────────────────────────────────────

class TestValidToken:
    def test_valid_token_returns_200(self, client, rsa_private_key):
        token = make_token(rsa_private_key, sub="alice")
        resp = client.get("/api/v1/resource", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_valid_token_sub_in_response(self, client, rsa_private_key):
        token = make_token(rsa_private_key, sub="alice")
        resp = client.get("/api/v1/resource", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["user_id"] == "alice"


# ── Missing token ─────────────────────────────────────────────────────────────

class TestMissingToken:
    def test_no_auth_header_returns_401(self, client):
        resp = client.get("/api/v1/resource")
        assert resp.status_code == 401

    def test_no_auth_header_error_code(self, client):
        resp = client.get("/api/v1/resource")
        assert resp.json()["detail"]["error"] == "missing_token"

    def test_non_bearer_scheme_treated_as_missing_token(self, client):
        # HTTPBearer with auto_error=False returns None for non-Bearer schemes,
        # so the error code is missing_token, not an invalid-scheme error.
        resp = client.get("/api/v1/resource", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"


# ── Expired token ─────────────────────────────────────────────────────────────

class TestExpiredToken:
    def test_expired_token_returns_401(self, client, rsa_private_key):
        token = make_token(rsa_private_key, exp_offset=-10)
        resp = client.get("/api/v1/resource", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_expired_token_error_code(self, client, rsa_private_key):
        token = make_token(rsa_private_key, exp_offset=-10)
        resp = client.get("/api/v1/resource", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["detail"]["error"] == "token_expired"


# ── Tampered / invalid token ──────────────────────────────────────────────────

class TestTamperedToken:
    def test_tampered_signature_returns_401(self, client, rsa_private_key):
        token = make_token(rsa_private_key)
        # Flip last character of signature
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        resp = client.get("/api/v1/resource", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.status_code == 401

    def test_tampered_error_code(self, client, rsa_private_key):
        token = make_token(rsa_private_key)
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        resp = client.get("/api/v1/resource", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.json()["detail"]["error"] == "invalid_token"

    def test_random_string_returns_401(self, client):
        resp = client.get("/api/v1/resource", headers={"Authorization": "Bearer notavalidjwt"})
        assert resp.status_code == 401

    def test_hs256_token_rejected(self, client):
        """HS256 tokens must be rejected even if the payload is valid."""
        token = jwt.encode(
            {"sub": "attacker", "exp": int(time.time()) + 900},
            "shared-secret",
            algorithm="HS256",
        )
        resp = client.get("/api/v1/resource", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_www_authenticate_header_present_on_401(self, client):
        resp = client.get("/api/v1/resource")
        assert "www-authenticate" in resp.headers
        assert resp.headers["www-authenticate"] == "Bearer"


# ── JWKS fetch failure ────────────────────────────────────────────────────────

class TestJwksFetchFailure:
    def test_jwks_unreachable_returns_503(self, monkeypatch):
        """If _get_jwks raises RuntimeError (IDP unreachable), require_auth must return 503."""
        monkeypatch.setenv("JWKS_URI", "https://fake-idp.example.com/.well-known/jwks.json")
        monkeypatch.delenv("JWKS_AUDIENCE", raising=False)
        monkeypatch.delenv("JWKS_ISSUER", raising=False)

        import api.deps as deps
        deps._get_jwks.cache_clear()

        from unittest.mock import patch
        from fastapi import Depends
        from fastapi.testclient import TestClient
        from api.deps import TokenPayload, require_auth

        app_503 = __import__("fastapi").FastAPI()

        @app_503.get("/api/v1/resource")
        def protected(token: TokenPayload = Depends(require_auth)):
            return {"user_id": token.sub}

        import jose.jwt as _jwt
        import time as _time
        dummy_token = _jwt.encode(
            {"sub": "x", "exp": int(_time.time()) + 900},
            "ignored",
            algorithm="HS256",
        )

        with patch.object(deps, "_get_jwks", side_effect=RuntimeError("IDP unreachable")):
            client_503 = TestClient(app_503, raise_server_exceptions=False)
            resp = client_503.get(
                "/api/v1/resource",
                headers={"Authorization": f"Bearer {dummy_token}"},
            )

        assert resp.status_code == 503
        assert resp.json()["detail"]["error"] == "jwks_unavailable"
