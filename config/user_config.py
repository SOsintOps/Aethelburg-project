"""Per-user configuration stored outside the repository.

Windows: `%APPDATA%\\Aethelburg\\config.toml`; elsewhere: `~/.config/aethelburg/config.toml`.
Only flat `key = value` pairs are written, e.g. `data_dir = 'C:\\AethelburgData'`.
"""
from __future__ import annotations

import os
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
LEGACY_DATA_DIR = PROJECT_ROOT / "dati"
DB_FILENAME = "aethelburg.sqlite"


def user_config_path() -> Path:
    override = os.environ.get("AETHELBURG_CONFIG")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "Aethelburg" / "config.toml"
    return Path.home() / ".config" / "aethelburg" / "config.toml"


def default_data_dir() -> Path:
    if sys.platform == "win32":
        return Path("C:/AethelburgData")
    return Path.home() / "AethelburgData"


def load_user_config() -> dict[str, Any]:
    path = user_config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def save_user_config(updates: dict[str, Any]) -> Path:
    """Merge `updates` into the user config file (None removes a key)."""
    data = load_user_config()
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path = user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key} = {_toml_value(value)}" for key, value in sorted(data.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def resolve_data_dir() -> Path:
    """Data folder when no DATA_DIR environment/.env value is set.

    Order: user config `data_dir` > legacy `<project>/dati` if it already holds a database > default.
    """
    configured = load_user_config().get("data_dir")
    if configured:
        return Path(configured)
    if (LEGACY_DATA_DIR / DB_FILENAME).exists():
        return LEGACY_DATA_DIR
    return default_data_dir()


def check_data_dir(path: Path) -> dict[str, Any]:
    """Report whether `path` can hold the data folder (created if missing)."""
    info: dict[str, Any] = {"path": str(path), "exists": path.exists(), "writable": False, "free_gb": None}
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".aethelburg-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        info["writable"] = True
        info["exists"] = True
        info["free_gb"] = round(shutil.disk_usage(path).free / 1024**3, 1)
    except OSError as exc:
        info["error"] = str(exc)
    return info


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    text = str(value)
    if "'" in text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"'{text}'"  # literal string: Windows backslashes need no escaping
