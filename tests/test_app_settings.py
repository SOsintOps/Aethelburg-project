"""Companies House keys entered on the Settings page are saved in the database and used at once."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.settings import Settings, get_settings, read_app_settings
from src.services.app_settings import save_ch_keys
from src.services.db_service import DatabaseService
from src.ui.settings_api import build_settings_router

REST = "11111111-2222-4333-8444-555555555555"
STREAM = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
NO_ENV_KEYS = {"CH_API_KEY": "", "CH_STREAMING_KEY": "", "APP_ENV": "development"}


@pytest.fixture
def db(tmp_path):
    yield DatabaseService(tmp_path / "settings.sqlite")
    with patch.dict(os.environ, NO_ENV_KEYS):
        get_settings().resolve_ch_keys()  # back to the configured database / keyring


def test_saved_keys_are_used_at_once_and_after_a_restart(db):
    with patch.dict(os.environ, NO_ENV_KEYS), patch("keyring.get_password", return_value=None):
        result = save_ch_keys(db, {"api_key": f" {REST}\n", "streaming_key": STREAM})
        ch = get_settings().ch
        assert (ch.api_key, ch.streaming_key) == (REST, STREAM)
        assert result["keys"]["api_key"] == {"configured": True, "source": "database", "hint": "…5555"}
        assert read_app_settings(db.db_path, ["ch_api_key", "ch_streaming_key"]) == {
            "ch_api_key": REST, "ch_streaming_key": STREAM}

        fresh = Settings()  # a new process reads the same database
        fresh.resolve_ch_keys(db.db_path)
        assert fresh.ch.api_key == REST and fresh.ch.key_sources["api_key"] == "database"

        save_ch_keys(db, {"streaming_key": ""})
        assert get_settings().ch.streaming_key == "" and get_settings().ch.api_key == REST


def test_an_environment_variable_wins_over_the_saved_key(db):
    with patch.dict(os.environ, NO_ENV_KEYS):
        save_ch_keys(db, {"api_key": REST})
    with patch.dict(os.environ, {**NO_ENV_KEYS, "CH_API_KEY": "env-key-0123456789"}):
        s = Settings()
        s.resolve_ch_keys(db.db_path)
    assert s.ch.api_key == "env-key-0123456789" and s.ch.key_sources["api_key"] == "environment"


def test_a_value_that_is_not_a_key_is_refused(db):
    with pytest.raises(ValueError):
        save_ch_keys(db, {"api_key": "two words"})
    with pytest.raises(ValueError):
        save_ch_keys(db, {"api_key": REST + REST})  # pasted twice
    with pytest.raises(ValueError):
        save_ch_keys(db, {"api_key": REST * 4 + "x"})
    assert read_app_settings(db.db_path, ["ch_api_key"]) == {}


def test_the_page_never_receives_a_whole_key(db):
    app = FastAPI()
    app.include_router(build_settings_router(db))
    client = TestClient(app)
    with patch.dict(os.environ, NO_ENV_KEYS), patch("keyring.get_password", return_value=None):
        assert client.post("/api/settings/ch-keys", json={"api_key": REST}).status_code == 200
        assert client.post("/api/settings/ch-keys", json={"api_key": "bad key"}).status_code == 400
        page = client.get("/api/settings")
    assert page.status_code == 200
    assert REST not in page.text
    assert page.json()["ch_keys"]["api_key"]["hint"] == "…5555"
