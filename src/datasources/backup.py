"""Database backups in `<data folder>/backups/` and restore.

A backup is a consistent copy made with SQLite's online backup API (safe while the server or an
import is running), checked with `PRAGMA integrity_check`, plus a copy of the user config file.
The newest `backup_keep` backups are kept (user config, default 7).
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import get_settings
from config.user_config import load_user_config, user_config_path

_NAME_RE = re.compile(r"^aethelburg-\d{8}-\d{6}(-[a-z0-9-]{1,40})?\.sqlite$")


def backups_dir() -> Path:
    return get_settings().paths.data_dir / "backups"


def create_backup(reason: str = "manual") -> dict[str, Any]:
    db_path = Path(get_settings().db.sqlite_path)
    if not db_path.exists():
        raise FileNotFoundError(f"No database to back up at {db_path}")
    target_dir = backups_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    tag = re.sub(r"[^a-z0-9-]+", "-", reason.lower()).strip("-")[:40] or "manual"
    target = target_dir / f"aethelburg-{datetime.now():%Y%m%d-%H%M%S}-{tag}.sqlite"

    src, dst = sqlite3.connect(db_path, timeout=60), sqlite3.connect(target)
    try:
        src.backup(dst)
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        src.close()
        dst.close()
    if check != "ok":
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Backup failed the integrity check: {check}")
    if user_config_path().exists():
        shutil.copy2(user_config_path(), target.with_suffix(".config.toml"))
    removed = _rotate(int(load_user_config().get("backup_keep", 7)))
    return {**_describe(target), "removed_old": removed}


def list_backups() -> list[dict[str, Any]]:
    folder = backups_dir()
    if not folder.is_dir():
        return []
    return [_describe(p) for p in sorted(folder.glob("aethelburg-*.sqlite"), reverse=True)]


def restore_backup(name: str) -> dict[str, Any]:
    """Replace the database with backup `name`; the current database is backed up first."""
    if not _NAME_RE.match(name):
        raise ValueError(f"Not a backup name: {name!r}")
    source = backups_dir() / name
    if not source.exists():
        raise FileNotFoundError(f"Backup not found: {name}")
    safety = create_backup("before-restore")
    db_path = Path(get_settings().db.sqlite_path)
    src, dst = sqlite3.connect(source), sqlite3.connect(db_path, timeout=60)
    try:
        src.backup(dst)  # overwrite in place: works while the file is open elsewhere
    finally:
        src.close()
        dst.close()
    return {"restored": name, "safety_backup": safety["name"], "restart_recommended": True}


def _rotate(keep: int) -> list[str]:
    backups = sorted(backups_dir().glob("aethelburg-*.sqlite"), reverse=True)
    removed = []
    for old in backups[max(keep, 1):]:
        old.unlink(missing_ok=True)
        old.with_suffix(".config.toml").unlink(missing_ok=True)
        removed.append(old.name)
    return removed


def _describe(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "gb": round(stat.st_size / 1024**3, 3),
        "created": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }
