"""Settings saved in the database from the Settings page (`app_settings` table).

The Companies House REST and Streaming keys are stored here when the user enters them in the app.
`config.settings` reads them at start (an environment variable still wins, the keyring is the
fallback); `save_ch_keys` writes them and reloads the running settings, so no restart is needed.
The browser only ever receives the last four characters of a key.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from config.settings import CH_KEY_NAMES, get_settings
from src.services.db_service import DatabaseService

# Companies House keys are UUIDs; accept any token without spaces so a format change does not lock users out
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{16,128}$")
# a company that always exists: used to check the REST key
_PROBE_COMPANY = "00000006"
_TITLES = {"api_key": "REST API key", "streaming_key": "Streaming key"}


def describe_ch_keys() -> dict[str, dict[str, Any]]:
    ch = get_settings().ch
    return {
        field: {
            "configured": bool(getattr(ch, field)),
            "source": ch.key_sources.get(field),
            "hint": f"…{getattr(ch, field)[-4:]}" if getattr(ch, field) else None,
        }
        for field in CH_KEY_NAMES
    }


def save_ch_keys(db: DatabaseService, values: dict[str, str | None]) -> dict[str, Any]:
    """Save (non-empty value) or remove (None or "") each key given, then reload the running settings.

    Raises ValueError for a value that cannot be a key, before anything is written.
    """
    cleaned: dict[str, str | None] = {}
    for field, value in values.items():
        if field not in CH_KEY_NAMES:
            raise ValueError(f"Unknown key: {field}")
        value = (value or "").strip()
        half = len(value) // 2
        if value and len(value) % 2 == 0 and value[:half] == value[half:]:
            raise ValueError(f"The {_TITLES[field]} was pasted twice: paste it once")
        if value and not _KEY_PATTERN.match(value):
            raise ValueError(f"The {_TITLES[field]} does not look like a Companies House key: copy it again with the Copy link")
        cleaned[field] = value or None
    now = datetime.now(UTC).isoformat()
    conn = db.connect()
    try:
        for field, value in cleaned.items():
            if value:
                conn.execute(
                    "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (CH_KEY_NAMES[field], value, now),
                )
            else:
                conn.execute("DELETE FROM app_settings WHERE key = ?", (CH_KEY_NAMES[field],))
        conn.commit()
    finally:
        conn.close()
    get_settings().resolve_ch_keys(db.db_path)
    keys = describe_ch_keys()
    overridden = [f for f in cleaned if keys[f]["source"] == "environment"]
    return {"keys": keys, "overridden_by_environment": overridden}


async def test_ch_keys() -> dict[str, dict[str, Any]]:
    """Ask Companies House whether each configured key is accepted (REST: one company; Streaming: open and close)."""
    ch = get_settings().ch
    results: dict[str, dict[str, Any]] = {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        for field, url in (
            ("api_key", f"{ch.api_base_url}/company/{_PROBE_COMPANY}"),
            ("streaming_key", f"{ch.streaming_base_url}/companies"),
        ):
            key = getattr(ch, field)
            if not key:
                results[field] = {"ok": False, "message": "No key saved"}
                continue
            try:
                async with client.stream("GET", url, auth=(key, "")) as resp:
                    status = resp.status_code
            except httpx.HTTPError as exc:
                results[field] = {"ok": False, "message": f"Companies House not reachable: {type(exc).__name__}"}
                continue
            results[field] = {"ok": status == 200, "status": status, "message": _status_message(field, status)}
    return results


def _status_message(field: str, status: int) -> str:
    if status == 200:
        return "Accepted by Companies House"
    if status == 401:
        other = "Streaming" if field == "api_key" else "REST"
        return f"Refused (401): wrong key, or a {other} key in this field"
    if status == 429:
        return "Rate limit reached (429): try again in a few minutes"
    return f"Companies House answered HTTP {status}"
