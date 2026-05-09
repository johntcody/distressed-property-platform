"""
Shared runtime configuration for all FastAPI services and Lambda scrapers.

Secrets are fetched from AWS Secrets Manager at startup and cached in module
memory for the lifetime of the process.  Services must never read credentials
from environment variables in production; use get_secret() instead.

Local / CI override: if the environment variable AWS_SECRETS_MANAGER_ENDPOINT
is set to "local", get_secret() reads from os.environ instead of Secrets
Manager.  The secret name is mapped to an env var key by replacing all "/",
".", and "-" characters with "_" and uppercasing the result, e.g.:
  dpip/db/app_user  ->  DPIP_DB_APP_USER
  dpip/avm/attom_api_key  ->  DPIP_AVM_ATTOM_API_KEY
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError


def _is_local() -> bool:
    """Re-evaluated each call so tests can toggle the env var after import."""
    return os.environ.get("AWS_SECRETS_MANAGER_ENDPOINT", "").lower() == "local"


def _client():
    """Return a boto3 Secrets Manager client.

    Constructed per-call; boto3 clients are cheap and thread-safe.
    lru_cache on get_secret() prevents excess Secrets Manager API calls.
    """
    return boto3.client(
        "secretsmanager",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def _secret_name_to_env_key(name: str) -> str:
    """Convert a secret name to the equivalent local env var key.

    Replaces "/", ".", and "-" with "_" then uppercases.
    e.g. "dpip/db/app_user" -> "DPIP_DB_APP_USER"
    """
    return name.replace("/", "_").replace(".", "_").replace("-", "_").upper()


def _get_secret_local(name: str) -> str:
    """Read secret from environment (local/CI mode). Never cached."""
    env_key = _secret_name_to_env_key(name)
    value = os.environ.get(env_key)
    if value is None:
        raise RuntimeError(
            f"Local mode: environment variable {env_key!r} not set "
            f"(maps to secret {name!r})"
        )
    return value


@lru_cache(maxsize=64)
def _get_secret_remote(name: str) -> str:
    """Fetch secret from Secrets Manager and cache for the process lifetime.

    Secret rotation takes effect on the next ECS task restart or Lambda
    cold start — the cache does not auto-refresh mid-process.
    """
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
            # str() coercion ensures return type is always str even if JSON value is numeric.
            return str(next(iter(parsed.values())))
        return secret
    except (json.JSONDecodeError, StopIteration):
        return secret


def get_secret(name: str) -> str:
    """Return the secret string for *name*.

    In local mode (AWS_SECRETS_MANAGER_ENDPOINT=local) reads from env vars —
    never cached so toggles mid-test take effect immediately.
    In production mode reads from Secrets Manager with process-lifetime caching.
    """
    if _is_local():
        return _get_secret_local(name)
    return _get_secret_remote(name)


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


def get_attom_api_key() -> str:
    """ATTOM Data API key for the AVM service."""
    return get_secret("dpip/avm/attom_api_key")
