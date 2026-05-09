"""
Unit tests for services/config.py.

All tests run in local mode (AWS_SECRETS_MANAGER_ENDPOINT=local) and never
touch AWS — no boto3 calls are made.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def reload_config():
    """Re-import config fresh so lru_cache state is reset between tests."""
    mod_name = "services.config"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    import services.config as cfg
    return cfg


# ── local mode ────────────────────────────────────────────────────────────────

class TestLocalMode:
    def test_returns_env_var_value(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_DB_APP_USER", "postgres://app_user:pw@localhost/db")
        cfg = reload_config()
        assert cfg.get_secret("dpip/db/app_user") == "postgres://app_user:pw@localhost/db"

    def test_env_key_mapping_slashes(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_SQS_ALERT_QUEUE_URL", "https://sqs.example.com/queue")
        cfg = reload_config()
        assert cfg.get_secret("dpip/sqs/alert_queue_url") == "https://sqs.example.com/queue"

    def test_env_key_mapping_dashes(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_AVM_ATTOM_API_KEY", "key-abc-123")
        cfg = reload_config()
        assert cfg.get_secret("dpip/avm/attom_api_key") == "key-abc-123"

    def test_missing_env_var_raises_runtime_error(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.delenv("DPIP_DB_APP_USER", raising=False)
        cfg = reload_config()
        with pytest.raises(RuntimeError, match="DPIP_DB_APP_USER"):
            cfg.get_secret("dpip/db/app_user")

    def test_error_message_includes_secret_name(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.delenv("DPIP_DB_APP_USER", raising=False)
        cfg = reload_config()
        with pytest.raises(RuntimeError, match="dpip/db/app_user"):
            cfg.get_secret("dpip/db/app_user")

    def test_local_mode_not_cached_between_calls(self, monkeypatch):
        """Local mode reads env var live — changing it between calls works."""
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_DB_APP_USER", "first-value")
        cfg = reload_config()
        assert cfg.get_secret("dpip/db/app_user") == "first-value"
        monkeypatch.setenv("DPIP_DB_APP_USER", "second-value")
        assert cfg.get_secret("dpip/db/app_user") == "second-value"


# ── env key mapping ───────────────────────────────────────────────────────────

class TestSecretNameToEnvKey:
    def test_slashes_replaced(self):
        from services.config import _secret_name_to_env_key
        assert _secret_name_to_env_key("dpip/db/app_user") == "DPIP_DB_APP_USER"

    def test_dots_replaced(self):
        from services.config import _secret_name_to_env_key
        assert _secret_name_to_env_key("dpip.db.app_user") == "DPIP_DB_APP_USER"

    def test_dashes_replaced(self):
        from services.config import _secret_name_to_env_key
        assert _secret_name_to_env_key("dpip/avm/attom-api-key") == "DPIP_AVM_ATTOM_API_KEY"

    def test_uppercased(self):
        from services.config import _secret_name_to_env_key
        assert _secret_name_to_env_key("lower/case") == "LOWER_CASE"


# ── convenience accessors ─────────────────────────────────────────────────────

class TestConvenienceAccessors:
    def test_get_db_url(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_DB_APP_USER", "postgres://app_user:x@host/db")
        cfg = reload_config()
        assert cfg.get_db_url() == "postgres://app_user:x@host/db"

    def test_get_migrations_db_url(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_DB_MIGRATIONS_USER", "postgres://migrations_user:x@host/db")
        cfg = reload_config()
        assert cfg.get_migrations_db_url() == "postgres://migrations_user:x@host/db"

    def test_get_sqs_queue_url(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_SQS_ALERT_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
        cfg = reload_config()
        assert cfg.get_sqs_queue_url() == "https://sqs.us-east-1.amazonaws.com/123/queue"

    def test_get_attom_api_key(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRETS_MANAGER_ENDPOINT", "local")
        monkeypatch.setenv("DPIP_AVM_ATTOM_API_KEY", "attom-key-xyz")
        cfg = reload_config()
        assert cfg.get_attom_api_key() == "attom-key-xyz"


# ── production mode (mocked boto3) ───────────────────────────────────────────

class TestProductionMode:
    def test_calls_secrets_manager(self, monkeypatch):
        monkeypatch.delenv("AWS_SECRETS_MANAGER_ENDPOINT", raising=False)
        cfg = reload_config()

        fake_response = {"SecretString": "super-secret-value"}

        class FakeClient:
            def get_secret_value(self, SecretId):
                assert SecretId == "dpip/db/app_user"
                return fake_response

        monkeypatch.setattr(cfg, "_client", lambda: FakeClient())
        result = cfg._get_secret_remote.__wrapped__("dpip/db/app_user")
        assert result == "super-secret-value"

    def test_unwraps_single_key_json(self, monkeypatch):
        monkeypatch.delenv("AWS_SECRETS_MANAGER_ENDPOINT", raising=False)
        cfg = reload_config()

        class FakeClient:
            def get_secret_value(self, SecretId):
                return {"SecretString": '{"password": "hunter2"}'}

        monkeypatch.setattr(cfg, "_client", lambda: FakeClient())
        result = cfg._get_secret_remote.__wrapped__("any/secret")
        assert result == "hunter2"

    def test_unwrapped_value_is_always_str(self, monkeypatch):
        """Non-string JSON values (e.g. numeric) must be coerced to str."""
        monkeypatch.delenv("AWS_SECRETS_MANAGER_ENDPOINT", raising=False)
        cfg = reload_config()

        class FakeClient:
            def get_secret_value(self, SecretId):
                return {"SecretString": '{"port": 5432}'}

        monkeypatch.setattr(cfg, "_client", lambda: FakeClient())
        result = cfg._get_secret_remote.__wrapped__("any/secret")
        assert result == "5432"
        assert isinstance(result, str)

    def test_resource_not_found_raises_runtime_error(self, monkeypatch):
        from botocore.exceptions import ClientError

        monkeypatch.delenv("AWS_SECRETS_MANAGER_ENDPOINT", raising=False)
        cfg = reload_config()

        class FakeClient:
            def get_secret_value(self, SecretId):
                raise ClientError(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
                    "GetSecretValue",
                )

        monkeypatch.setattr(cfg, "_client", lambda: FakeClient())
        with pytest.raises(RuntimeError, match="not found in Secrets Manager"):
            cfg._get_secret_remote.__wrapped__("missing/secret")

    def test_access_denied_raises_runtime_error(self, monkeypatch):
        from botocore.exceptions import ClientError

        monkeypatch.delenv("AWS_SECRETS_MANAGER_ENDPOINT", raising=False)
        cfg = reload_config()

        class FakeClient:
            def get_secret_value(self, SecretId):
                raise ClientError(
                    {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
                    "GetSecretValue",
                )

        monkeypatch.setattr(cfg, "_client", lambda: FakeClient())
        with pytest.raises(RuntimeError, match="IAM role does not have"):
            cfg._get_secret_remote.__wrapped__("restricted/secret")
