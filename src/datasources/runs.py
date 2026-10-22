"""Bookkeeping for long bulk tasks (`ingest_runs`): progress, resume point, outcome.

A task over a given file version resumes from `last_row` of its unfinished run, so an import
stopped half-way (closed window, crash, power cut) does not start again from the first row.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class Run:
    id: str
    task: str
    resume_from: int  # rows already processed by an earlier, unfinished run
    rows_read: int = 0
    rows_written: int = 0


def start_run(
    conn: sqlite3.Connection,
    task: str,
    source: str | None,
    source_version: str | None,
    file: str | None,
) -> Run:
    row = conn.execute(
        """
        SELECT id, last_row, rows_written FROM ingest_runs
        WHERE task = ? AND source_version IS ? AND file IS ? AND status IN ('running', 'interrupted')
        ORDER BY started_at DESC LIMIT 1
        """,
        (task, source_version, file),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE ingest_runs SET status = 'running', message = NULL, heartbeat_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), row["id"]),
        )
        conn.commit()
        return Run(row["id"], task, int(row["last_row"]), int(row["last_row"]), int(row["rows_written"]))
    run = Run(str(uuid.uuid4()), task, 0)
    conn.execute(
        "INSERT INTO ingest_runs (id, task, source, source_version, file, heartbeat_at) VALUES (?, ?, ?, ?, ?, ?)",
        (run.id, task, source, source_version, file, datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return run


def checkpoint(conn: sqlite3.Connection, run: Run) -> None:
    """Persist progress and commit the work done so far in the same transaction."""
    conn.execute(
        "UPDATE ingest_runs SET rows_read = ?, rows_written = ?, last_row = ?, heartbeat_at = ? WHERE id = ?",
        (run.rows_read, run.rows_written, run.rows_read, datetime.now(UTC).isoformat(), run.id),
    )
    conn.commit()


def finish_run(conn: sqlite3.Connection, run: Run, status: str = "completed", message: str | None = None) -> None:
    conn.execute(
        """
        UPDATE ingest_runs
        SET status = ?, message = ?, finished_at = ?, rows_read = ?, rows_written = ?, last_row = ?
        WHERE id = ?
        """,
        (status, message, datetime.now(UTC).isoformat(), run.rows_read, run.rows_written, run.rows_read, run.id),
    )
    conn.commit()


STALE_AFTER = timedelta(minutes=10)


def mark_interrupted(conn: sqlite3.Connection) -> int:
    """Flag runs left 'running' by a process that stopped (no checkpoint for 10 minutes).

    A run still checkpointing in another process (e.g. `data import` while the server starts)
    is left alone.
    """
    cutoff = (datetime.now(UTC) - STALE_AFTER).isoformat()
    cur = conn.execute(
        """
        UPDATE ingest_runs SET status = 'interrupted'
        WHERE status = 'running' AND (heartbeat_at IS NULL OR heartbeat_at < ?)
        """,
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount
