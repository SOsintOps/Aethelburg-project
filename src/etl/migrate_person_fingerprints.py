"""Recompute person fingerprints written before person names were normalised without titles.

Until 0.3.0-beta.1 PSC and officer names were normalised as company names: titles stayed in the
fingerprint (`mr john smith`), and the FtM id of a person is derived from it. A later import with
the fixed rule creates the same person again as `john smith`. This migration:

1. recomputes `normalize_name(name, is_company=False)` for every person;
2. when the person with the new id already exists, moves PSC statements, appointments and case
   references to it and deletes the old row (duplicate PSC-derived appointments are dropped);
3. otherwise renames the person (fingerprint, FtM id, FtM entity) in place;
4. rewrites the old FtM id inside the Ownership and Directorship entities that pointed to it.

Idempotent: a second run finds nothing to do. Records an `ingest_runs` row (task `person_fingerprints`).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.core.ftm import make_ftm_id
from src.core.logging import get_logger
from src.core.normalizer import normalize_name
from src.datasources.runs import checkpoint, finish_run, start_run
from src.services.db_service import DatabaseService

log = get_logger(__name__)
_BATCH = 5_000


def person_ftm_id(fingerprint: str, name: str, dob_year: Any, dob_month: Any) -> str:
    """Same id as the PSC importer and `person_to_ftm`."""
    return make_ftm_id("Person", fingerprint or name, str(dob_year or ""), str(dob_month or ""))


def migrate_person_fingerprints(
    db: DatabaseService | None = None, progress: Callable[..., None] | None = None
) -> dict[str, int]:
    db = db or DatabaseService()
    conn = db.connect()
    counts = {"checked": 0, "renamed": 0, "merged": 0, "duplicate_appointments_removed": 0}
    run = start_run(conn, "person_fingerprints", None, "0.3.0-beta.1", None)
    try:
        rows = conn.execute(
            "SELECT id, ftm_id, name, name_fingerprint, dob_year, dob_month FROM persons"
        ).fetchall()
        pending = 0
        for p in rows:
            counts["checked"] += 1
            new_fp = normalize_name(p["name"], is_company=False)
            new_ftm = person_ftm_id(new_fp, p["name"], p["dob_year"], p["dob_month"])
            if new_fp == p["name_fingerprint"] and new_ftm == p["ftm_id"]:
                continue
            keep = conn.execute(
                "SELECT id FROM persons WHERE ftm_id = ? AND id != ?", (new_ftm, p["id"])
            ).fetchone()
            if keep:
                counts["duplicate_appointments_removed"] += _merge(conn, p, keep["id"])
                counts["merged"] += 1
            else:
                _rename(conn, p, new_fp, new_ftm)
                counts["renamed"] += 1
            _repoint_references(conn, p["ftm_id"], new_ftm)
            pending += 1
            if pending >= _BATCH:
                run.rows_read, run.rows_written = counts["checked"], counts["renamed"] + counts["merged"]
                checkpoint(conn, run)  # commits and keeps the heartbeat fresh
                pending = 0
                if progress:
                    progress("person_fingerprints", counts["checked"], len(rows))
        run.rows_read, run.rows_written = counts["checked"], counts["renamed"] + counts["merged"]
        finish_run(conn, run, message=str(counts))
        conn.commit()
        log.info("person_fingerprints_migrated", **counts)
        return counts
    except Exception as exc:
        conn.rollback()
        finish_run(conn, run, status="failed", message=f"{type(exc).__name__}: {exc}")
        conn.commit()
        raise
    finally:
        conn.close()


def _rename(conn: Any, p: Any, new_fp: str, new_ftm: str) -> None:
    conn.execute(
        "UPDATE persons SET name_fingerprint = ?, ftm_id = ?, updated_at = datetime('now') WHERE id = ?",
        (new_fp, new_ftm, p["id"]),
    )
    if p["ftm_id"] != new_ftm:
        if conn.execute("SELECT 1 FROM ftm_entities WHERE id = ?", (new_ftm,)).fetchone():
            conn.execute("DELETE FROM ftm_entities WHERE id = ?", (p["ftm_id"],))
        else:
            conn.execute("UPDATE ftm_entities SET id = ? WHERE id = ?", (new_ftm, p["ftm_id"]))


def _merge(conn: Any, p: Any, keep_id: str) -> int:
    """Move everything from person `p` to `keep_id`, delete `p`; returns duplicate appointments removed."""
    conn.execute("UPDATE psc_ownerships SET person_id = ? WHERE person_id = ?", (keep_id, p["id"]))
    conn.execute("UPDATE directorships SET person_id = ? WHERE person_id = ?", (keep_id, p["id"]))
    # the PSC importer derives one appointment per (company, person): the moved one may now repeat
    dupes = conn.execute(
        """
        SELECT d.id, d.ftm_id FROM directorships d
        WHERE d.person_id = ? AND EXISTS (
            SELECT 1 FROM directorships o
            WHERE o.person_id = d.person_id AND o.company_number = d.company_number
              AND o.officer_role = d.officer_role AND IFNULL(o.appointed_on, '') = IFNULL(d.appointed_on, '')
              AND IFNULL(o.resigned_on, '') = IFNULL(d.resigned_on, '') AND o.rowid < d.rowid)
        """,
        (keep_id,),
    ).fetchall()
    for d in dupes:
        conn.execute("DELETE FROM directorships WHERE id = ?", (d["id"],))
        conn.execute("DELETE FROM ftm_entities WHERE id = ?", (d["ftm_id"],))
    for table in ("casework_investigation_entities", "casework_annotations"):
        conn.execute(f"UPDATE OR IGNORE {table} SET entity_id = ? WHERE entity_id = ?", (keep_id, p["id"]))
    conn.execute("DELETE FROM persons WHERE id = ?", (p["id"],))
    conn.execute("DELETE FROM ftm_entities WHERE id = ?", (p["ftm_id"],))
    return len(dupes)


def _repoint_references(conn: Any, old_ftm: str, new_ftm: str) -> None:
    """Ownership/Directorship entities and case references that named the old FtM id."""
    if old_ftm == new_ftm:
        return
    conn.execute(
        """
        UPDATE ftm_entities SET properties = REPLACE(properties, ?, ?)
        WHERE id IN (
            SELECT ftm_id FROM psc_ownerships WHERE person_id IN (SELECT id FROM persons WHERE ftm_id = ?)
            UNION
            SELECT ftm_id FROM directorships WHERE person_id IN (SELECT id FROM persons WHERE ftm_id = ?))
        """,
        (old_ftm, new_ftm, new_ftm, new_ftm),
    )
    for table in ("casework_investigation_entities", "casework_annotations"):
        conn.execute(f"UPDATE OR IGNORE {table} SET entity_id = ? WHERE entity_id = ?", (new_ftm, old_ftm))
