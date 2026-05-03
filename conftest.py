"""Root conftest — sets DATABASE_URL for all async DB tests."""

import os

# Resolve test DSN from environment; fall back to a local Postgres instance.
# For CI/Neon: set TEST_DATABASE_URL in the environment or .env.test (gitignored).
_TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://localhost/distressed_test",
)


def pytest_configure(config):
    os.environ.setdefault("DATABASE_URL", _TEST_DSN)
