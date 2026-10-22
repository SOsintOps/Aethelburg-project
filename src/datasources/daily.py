"""Daily update: download whatever the publishers released, re-import when something changed.

Run it from the command line (`data daily`, e.g. from Windows Task Scheduler) or let the server
run it every day at `daily_update_time` when `daily_update_enabled` is on (user config, Data tab).
The import itself is resumable and makes a backup first (see pipeline.refresh_all).
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from config.user_config import load_user_config
from src.core.logging import get_logger
from src.datasources.catalog import SOURCES
from src.datasources.downloader import download_source
from src.datasources.officers import fetch_officers_batch
from src.datasources.pipeline import refresh_all
from src.datasources.runs import finish_run, start_run
from src.services.db_service import DatabaseService
from src.services.documents import auto_download_latest

log = get_logger(__name__)
DEFAULT_TIME = "06:00"
NEW_FLAGGED_OFFICERS_LIMIT = 500  # about 5 minutes of API quota per day


def run_daily_update(db: DatabaseService | None = None, progress: Callable[..., None] | None = None) -> dict[str, Any]:
    db = db or DatabaseService()
    conn = db.connect()
    run = start_run(conn, "daily_update", None, datetime.now(UTC).date().isoformat(), None)
    conn.close()
    summary: dict[str, Any] = {"downloads": {}}
    try:
        for key in SOURCES:
            res = download_source(key, db=db)
            summary["downloads"][key] = f"{res['status']} {res['version']}"
        changed = any(v.startswith("downloaded") for v in summary["downloads"].values())
        if changed:
            summary["import"] = {k: v for k, v in refresh_all(db=db, progress=progress).items() if k != "scoring"}
            summary["officers"] = fetch_officers_batch("flagged", limit=NEW_FLAGGED_OFFICERS_LIMIT, db=db)
            if load_user_config().get("documents_auto_download", False):
                summary["documents"] = auto_download_latest(db)
        else:
            summary["import"] = "nothing new to import"
        status = "completed"
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        status = "failed"
        log.error("daily_update_failed", error=summary["error"])
    conn = db.connect()
    try:
        finish_run(conn, run, status=status, message=str(summary)[:4000])
    finally:
        conn.close()
    return summary


def schedule() -> tuple[bool, str]:
    cfg = load_user_config()
    return bool(cfg.get("daily_update_enabled", False)), str(cfg.get("daily_update_time", DEFAULT_TIME))


def next_run(now: datetime, at: str, last_run_day: str | None) -> datetime:
    """Next time to run: today at `at` (or now, if that time passed and today has no run yet)."""
    hour, minute = (int(x) for x in at.split(":"))
    today_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if last_run_day == now.date().isoformat():
        return today_at + timedelta(days=1)
    return max(today_at, now) if now >= today_at else today_at


def last_run_day(db: DatabaseService) -> str | None:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT MAX(source_version) FROM ingest_runs WHERE task = 'daily_update' AND status IN ('completed', 'failed')"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


async def scheduler_loop(db: DatabaseService, start_job: Callable[[str, Any], Any]) -> None:
    """Checked every minute inside the server; also catches up a day missed while it was off."""
    while True:
        enabled, at = schedule()
        if enabled:
            now = datetime.now()
            if now >= next_run(now, at, last_run_day(db)):
                try:
                    start_job("daily", lambda progress: run_daily_update(db, progress))
                except Exception:  # another task is running: try again next minute
                    pass
        await asyncio.sleep(60)
