"""Data folder management: where downloads, the database and exports are kept."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from config.settings import get_settings
from config.user_config import DB_FILENAME, check_data_dir, load_user_config, save_user_config, user_config_path

_COPIED_DIRS = ("downloads", "exports", "onspd")


def describe_location() -> dict[str, Any]:
    """Current data folder, where the setting comes from, and disk space."""
    settings = get_settings()
    data_dir = settings.paths.data_dir
    if os.environ.get("DATA_DIR"):
        origin = "DATA_DIR environment variable"
    elif load_user_config().get("data_dir"):
        origin = f"user config ({user_config_path()})"
    elif data_dir.name == "dati":
        origin = "legacy project folder (no data folder configured yet)"
    else:
        origin = "default"
    info = check_data_dir(data_dir)
    db_path = settings.db.sqlite_path
    info.update(
        {
            "origin": origin,
            "config_file": str(user_config_path()),
            "database": str(db_path),
            "database_gb": round(db_path.stat().st_size / 1024**3, 3) if db_path.exists() else 0.0,
        }
    )
    return info


def set_location(target: Path, move: bool = False) -> dict[str, Any]:
    """Point the application at `target`; with `move`, copy the database and data sub-folders there.

    The source is never deleted. The new folder is used after the application restarts.
    """
    target = target.expanduser().resolve()
    check = check_data_dir(target)
    if not check["writable"]:
        raise ValueError(f"Data folder is not writable: {target} ({check.get('error', 'unknown error')})")

    report: dict[str, Any] = {"target": str(target), "copied": []}
    if move:
        source_dir = get_settings().paths.data_dir.resolve()
        if source_dir == target:
            raise ValueError("The new data folder is the current one.")
        needed = _size(source_dir / DB_FILENAME) + sum(_size(source_dir / d) for d in _COPIED_DIRS)
        if needed > shutil.disk_usage(target).free:
            raise ValueError(f"Not enough free space in {target}: {needed / 1024**3:.1f} GB needed")
        report["copied"] = copy_data(source_dir, target)
        report["source_kept"] = str(source_dir)

    report["config_file"] = str(save_user_config({"data_dir": str(target)}))
    report["restart_required"] = True
    return report


def copy_data(source_dir: Path, target: Path) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    src_db = source_dir / DB_FILENAME
    if src_db.exists():
        dst_db = target / DB_FILENAME
        if dst_db.exists():
            raise ValueError(f"A database already exists in the new folder: {dst_db}")
        src_conn, dst_conn = sqlite3.connect(src_db), sqlite3.connect(dst_db)
        try:
            src_conn.backup(dst_conn)  # consistent copy even while the server is running
        finally:
            src_conn.close()
            dst_conn.close()
        copied.append({"item": DB_FILENAME, "bytes": _size(dst_db)})
    for name in _COPIED_DIRS:
        src = source_dir / name
        if not src.is_dir():
            continue
        shutil.copytree(src, target / name, dirs_exist_ok=True)
        if _size(target / name) < _size(src):
            raise OSError(f"Copy of {src} is incomplete")
        copied.append({"item": name, "bytes": _size(target / name)})
    return copied


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return 0
