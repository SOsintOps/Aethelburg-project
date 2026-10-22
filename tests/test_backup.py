"""Backups are consistent, rotated, restorable, and names are validated."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from config.settings import get_settings
from src.datasources import backup


@pytest.fixture()
def data(tmp_path, monkeypatch):
    db = tmp_path / "aethelburg.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE t (v)")
        conn.execute("INSERT INTO t VALUES (1)")
    monkeypatch.setattr(get_settings().paths, "data_dir", tmp_path)
    monkeypatch.setattr(get_settings().db, "sqlite_path", db)
    monkeypatch.setenv("AETHELBURG_CONFIG", str(tmp_path / "config.toml"))
    return db


class _Clock:
    """Distinct timestamps for backups made within the same second."""

    def __init__(self) -> None:
        self.n = 0

    def now(self) -> datetime:
        self.n += 1
        return datetime(2030, 1, 1) + timedelta(seconds=self.n)

    fromtimestamp = staticmethod(datetime.fromtimestamp)


def test_backup_rotate_and_restore(data, monkeypatch):
    monkeypatch.setattr(backup, "datetime", _Clock())
    oldest = backup.create_backup("manual")["name"]
    with sqlite3.connect(data) as conn:
        conn.execute("UPDATE t SET v = 2")
    for _ in range(5):
        backup.create_backup("auto")
    assert len(backup.list_backups()) == 6

    res = backup.restore_backup(oldest)
    with sqlite3.connect(data) as conn:
        assert conn.execute("SELECT v FROM t").fetchone()[0] == 1
    assert res["safety_backup"].endswith("before-restore.sqlite")
    assert len(backup.list_backups()) == 7  # rotation keeps the newest 7

    for _ in range(3):
        backup.create_backup("auto")
    assert len(backup.list_backups()) == 7


def test_invalid_names_are_rejected(data):
    with pytest.raises(ValueError):
        backup.restore_backup("../aethelburg.sqlite")
