"""
Shared FastAPI dependencies for JWT authentication.

All services import require_auth from this module and pass it as a global
app dependency: FastAPI(dependencies=[Depends(require_auth)]).

Token requirements:
  - Algorithm: RS256 only (HS256 with a shared secret is rejected)
  - Issuer: configured via JWKS_ISSUER env var (Cognito or Auth0 URL)
  - Public key: fetched lazily from the identity provider's JWKS endpoint
    on the first authenticated request and cached for the process lifetime.
    Key rotation takes effect on the next ECS task restart or Lambda cold start.
  - Access tokens expire in 15 minutes; this module enforces expiry

Row-level scoping:
  - require_auth returns the decoded token payload (TokenPayload)
  - User-owned resources must enforce WHERE user_id = payload.sub —
    never trust a client-supplied user ID parameter
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWTClaimsError
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# ── Configuration ──────────────────────────────────────────────────────────────

def _jwks_uri() -> str:
    uri = os.environ.get("JWKS_URI")
    if not uri:
        raise RuntimeError(
            "JWKS_URI environment variable not set. "
            "Set it to your identity provider's JWKS endpoint, e.g.: "
            "https://cognito-idp.us-east-1.amazonaws.com/<pool-id>/.well-known/jwks.json"
        )
    return uri


def _jwt_issuer() -> Optional[str]:
    return os.environ.get("JWKS_ISSUER")


def _jwt_audience() -> Optional[str]:
    return os.environ.get("JWKS_AUDIENCE")


# ── JWKS key cache ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    """Fetch JWKS from the identity provider and cache for the process lifetime.

    Called once at first authenticated request. If the IDP rotates signing keys,
    the new JWKS takes effect on the next ECS task restart or Lambda cold start.
    """
    uri = _jwks_uri()
    try:
        resp = httpx.get(uri, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to fetch JWKS from {uri}: {exc}") from exc


# ── Token model ────────────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub: str                        # user ID — use for row-level scoping
    email: Optional[str] = None
    roles: list[str] = []
    exp: int = 0


# ── Core verification ──────────────────────────────────────────────────────────

def _verify_token(token: str, request: Optional["Request"] = None) -> TokenPayload:
    """Decode and verify an RS256 JWT. Raises HTTPException on any failure."""
    jwks = _get_jwks()

    client_ip = request.client.host if request and request.client else "unknown"
    path = request.url.path if request else "unknown"

    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=_jwt_issuer(),
            audience=_jwt_audience(),
            options={"verify_aud": _jwt_audience() is not None},
        )
    except ExpiredSignatureError:
        logger.warning("auth_failure error=token_expired path=%s client_ip=%s", path, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "token_expired", "message": "Access token has expired"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTClaimsError as exc:
        logger.warning("auth_failure error=invalid_claims path=%s client_ip=%s detail=%s", path, client_ip, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_claims", "message": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        logger.warning("auth_failure error=invalid_token path=%s client_ip=%s", path, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Token signature verification failed"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub") or ""
    exp = payload.get("exp") or 0
    if not sub or not exp:
        logger.warning("auth_failure error=invalid_claims path=%s client_ip=%s detail=missing sub or exp", path, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_claims", "message": "Token is missing required claims (sub, exp)"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPayload(
        sub=sub,
        email=payload.get("email"),
        roles=payload.get("cognito:groups", payload.get("roles", [])),
        exp=exp,
    )


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def require_auth(
    request: "Request",
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> TokenPayload | None:
    """FastAPI dependency that enforces JWT authentication on a route.

    Applied as a global app dependency — automatically exempts /health so
    load balancer health checks work without credentials.

    Returns None on /health (routes must accept Optional[TokenPayload] or use
    require_auth only on protected routes). Returns TokenPayload on success.
    Raises HTTP 401 on missing, expired, or tampered tokens on all other paths.
    Raises HTTP 503 if the JWKS endpoint is unreachable at startup.

    Usage:
        from api.deps import require_auth, TokenPayload

        @app.get("/api/v1/resource")
        async def my_route(token: TokenPayload = Depends(require_auth)):
            user_id = token.sub  # use for WHERE user_id = $1
    """
    if request.url.path == "/health":
        return None

    if credentials is None:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("auth_failure error=missing_token path=%s client_ip=%s", request.url.path, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_token", "message": "Authorization: Bearer <token> header required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = _verify_token(credentials.credentials, request)
        # Store on request.state so slowapi's rate-limit key function can read
        # the authenticated user ID without re-decoding the token.
        request.state.token = token
        return token
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "jwks_unavailable", "message": str(exc)},
        ) from exc
