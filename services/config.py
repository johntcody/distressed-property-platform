"""
Shared runtime configuration for all FastAPI services and Lambda scrapers.

Secrets are fetched from AWS Secrets Manager at startup and cached in module
memory for the lifetime of the process.  Services must never read credentials
from environment variables in production; use get_secret() instead.

Local / CI override: if the environment variable AWS_SECRETS_MANAGER_ENDPOINT
is set to "local", get_secret() falls back to os.environ so that unit tests
and local docker-compose runs work without AWS credentials.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

_LOCAL_MODE = os.environ.get("AWS_SECRETS_MANAGER_ENDPOINT", "").lower() == "local"

_boto_client: Any = None


def _client():
    global _boto_client
    if _boto_client is None:
        _boto_client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _boto_client


@lru_cache(maxsize=64)
def get_secret(name: str) -> str:
    """Return the secret string for *name*.

    In local mode the secret name is used as an environment variable key
    (dots and slashes replaced with underscores, upper-cased).  This lets
    developers set DATABASE_URL etc. in .env files without touching AWS.

    In production the value is fetched from Secrets Manager once and cached
    for the lifetime of the process.  Rotation-safe: if Secrets Manager
    returns SecretRotationInProgress the client automatically retries with
    the new secret value.
    """
    if _LOCAL_MODE:
        env_key = name.replace("/", "_").replace(".", "_").replace("-", "_").upper()
        value = os.environ.get(env_key)
        if value is None:
            raise RuntimeError(
                f"Local mode: environment variable {env_key!r} not set "
                f"(maps to secret {name!r})"
            )
        return value

    try:
        response = _client().get_secret_value(SecretId=name)
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            raise RuntimeError(f"Secret {name!r} not found in Secrets Manager") from exc
        if error_code == "AccessDeniedException":
            raise RuntimeError(
                f"IAM role does not have secretsmanager:GetSecretValue on {name!r}"
            ) from exc
        raise

    secret = response.get("SecretString") or response.get("SecretBinary", b"").decode()
    # Secrets Manager stores JSON objects; unwrap single-value secrets automatically.
    try:
        parsed = json.loads(secret)
        if isinstance(parsed, dict) and len(parsed) == 1:
            return next(iter(parsed.values()))
        return secret
    except (json.JSONDecodeError, StopIteration):
        return secret


# ── Convenience accessors ──────────────────────────────────────────────────────
# Services import these directly instead of calling get_secret() with raw names.

def get_db_url() -> str:
    """Connection string for app_user (runtime DML — all FastAPI services)."""
    return get_secret("dpip/db/app_user")


def get_migrations_db_url() -> str:
    """Connection string for migrations_user (CI/CD migration runner only)."""
    return get_secret("dpip/db/migrations_user")


def get_sqs_queue_url() -> str:
    """SQS queue URL for the alert engine consumer and producers."""
    return get_secret("dpip/sqs/alert_queue_url")


def get_estated_api_key() -> str:
    """Estated AVM API key for the AVM service."""
    return get_secret("dpip/avm/estated_api_key")
