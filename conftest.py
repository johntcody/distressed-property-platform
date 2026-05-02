"""Root conftest — sets DATABASE_URL for all async DB tests."""

import os
import pytest

# Neon test branch (test-distressed-platform) — safe to commit, read-only branch
_TEST_DSN = (
    "postgresql://neondb_owner:npg_rCR7EkNgzP4X"
    "@ep-billowing-wildflower-aeui7pka-pooler.c-2.us-east-2.aws.neon.tech"
    "/neondb?channel_binding=require&sslmode=require"
)


def pytest_configure(config):
    os.environ.setdefault("DATABASE_URL", _TEST_DSN)
