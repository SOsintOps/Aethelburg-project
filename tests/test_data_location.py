"""Data folder: precedence of the settings sources and copying data to a new folder."""
from __future__ import annotations

import sqlite3

import pytest

from config import user_config
from config.settings import get_settings
from src.datasources.storage import set_location


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHELBURG_CONFIG", str(tmp_path / "cfg" / "config.toml"))
    monkeypatch.setattr(user_config, "LEGACY_DATA_DIR", tmp_path / "no-legacy")
    for var in ("DATA_DIR", "SQLITE_PATH"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_precedence(isolated, monkeypatch):
    assert user_config.resolve_data_dir() == user_config.default_data_dir()

    legacy = isolated / "legacy"
    legacy.mkdir()
    (legacy / "aethelburg.sqlite").write_bytes(b"")
    monkeypatch.setattr(user_config, "LEGACY_DATA_DIR", legacy)
    assert user_config.resolve_data_dir() == legacy

    user_config.save_user_config({"data_dir": str(isolated / "C' folder")})  # quote-safe
    assert user_config.resolve_data_dir() == isolated / "C' folder"

    monkeypatch.setenv("DATA_DIR", str(isolated / "env"))
    assert get_settings().paths.data_dir == isolated / "env"


def test_move_copies_database_and_keeps_source(isolated, monkeypatch):
    old = isolated / "old"
    (old / "downloads" / "sanctions").mkdir(parents=True)
    (old / "downloads" / "sanctions" / "list.csv").write_text("x", encoding="utf-8")
    with sqlite3.connect(old / "aethelburg.sqlite") as conn:
        conn.execute("CREATE TABLE t (v)")
        conn.execute("INSERT INTO t VALUES (42)")
    monkeypatch.setenv("DATA_DIR", str(old))
    get_settings.cache_clear()

    new = isolated / "new"
    report = set_location(new, move=True)

    assert report["restart_required"] is True
    with sqlite3.connect(new / "aethelburg.sqlite") as conn:
        assert conn.execute("SELECT v FROM t").fetchone()[0] == 42
    assert (new / "downloads" / "sanctions" / "list.csv").exists()
    assert (old / "aethelburg.sqlite").exists()
    assert user_config.load_user_config()["data_dir"] == str(new.resolve())


def test_unwritable_target_is_rejected(isolated):
    blocker = isolated / "file-not-folder"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not writable"):
        set_location(blocker / "sub")
