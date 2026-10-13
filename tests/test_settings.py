"""Tests for config.settings."""
from __future__ import annotations

import os
from unittest.mock import patch

from config.settings import Settings, get_settings


def test_default_settings_load():
    with patch.dict(os.environ, {"POSTGRES_PASSWORD": "test", "APP_ENV": "development"}):
        s = Settings()
        assert s.db.name == "aethelburg"
        assert s.app.env == "development"


def test_database_sync_url_format():
    with patch.dict(os.environ, {"POSTGRES_PASSWORD": "test", "APP_ENV": "development"}):
        s = Settings()
        url = s.db.sync_url
        assert url.startswith("postgresql+psycopg2://")
        assert "aethelburg" in url


def test_database_async_url_format():
    with patch.dict(os.environ, {"POSTGRES_PASSWORD": "test", "APP_ENV": "development"}):
        s = Settings()
        url = s.db.async_url
        assert "asyncpg" in url


def test_data_dir_default():
    with patch.dict(os.environ, {"POSTGRES_PASSWORD": "test", "APP_ENV": "development"}):
        s = Settings()
        assert "dati" in str(s.paths.data_dir)


def test_singleton_pattern():
    get_settings.cache_clear()
    with patch.dict(os.environ, {"POSTGRES_PASSWORD": "test", "APP_ENV": "development"}):
        a = get_settings()
        b = get_settings()
        assert a is b
    get_settings.cache_clear()
