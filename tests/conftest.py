"""Shared test fixtures."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture()
def settings():
    """Return Settings with test overrides."""
    env_overrides = {
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "aethelburg_test",
        "APP_ENV": "development",
        "APP_DEBUG": "false",
    }
    with patch.dict(os.environ, env_overrides):
        from config.settings import Settings
        yield Settings()


@pytest.fixture()
def db_url() -> str:
    """Test database URL."""
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://aethelburg:test@127.0.0.1:5432/aethelburg_test",
    )
