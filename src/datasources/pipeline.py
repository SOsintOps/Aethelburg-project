"""End-to-end bulk refresh: index -> subset selection -> full import of the subset -> scoring.

Every long step is an `ingest_runs` task committed in batches, so an interrupted run resumes
where it stopped. Re-running on the same release is cheap: finished tasks are skipped.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from config.settings import get_settings
from config.user_config import LEGACY_DATA_DIR
from src.core.logging import get_logger
from src.datasources.downloader import latest_local_file
from src.datasources.runs import checkpoint, finish_run, start_run
from src.datasources.subset import (
    SubsetConfig,
    _iter_company_rows,
    build_company_index,
    select_subset,
)
from src.etl.import_companies import parse_ch_company_row, upsert_company_record
from src.etl.import_onspd import import_onspd
from src.etl.import_psc import ingest_psc_record
from src.etl.import_sanctions import import_uk_sanctions_file
from src.intelligence.risk_scorer import RiskScorer
from src.services.db_service import DatabaseService

log = get_logger(__name__)

Progress = Callable[[str, int], None]
_BATCH = 5_000
ICIJ_DIRNAME = "ICIJ Offshore Leaks Database"


def icij_dir() -> Path | None:
    """ICIJ is a static archive (not downloaded): data folder first, then the legacy project folder."""
    for base in (get_settings().paths.data_dir, LEGACY_DATA_DIR):
        if (base / ICIJ_DIRNAME).is_dir():
            return base / ICIJ_DIRNAME
    return None


def refresh_all(
    db: DatabaseService | None = None,
    cfg: SubsetConfig | None = None,
    progress: Progress | None = None,
    score: bool = True,
) -> dict[str, Any]:
    """Run every step on the newest downloaded releases; returns a summary per step."""
    db = db or DatabaseService()
    cfg = cfg or SubsetConfig.load()
    companies_csv = latest_local_file("ch_companies")
    psc_file = latest_local_file("ch_psc")
    sanctions_file = latest_local_file("uk_sanctions")
    onspd_file = latest_local_file("onspd")
    if companies_csv is None:
        raise RuntimeError("Companies House Basic Company Data is not downloaded yet: run `data download` first")

    summary: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat()}
    conn = db.connect()
    try:
        version = companies_csv.parent.name
        if not _done(conn, "company_index", version):
            summary["index_rows"] = build_company_index(conn, companies_csv, version, progress)
        summary["subset"] = select_subset(conn, cfg, psc_file, sanctions_file, icij_dir(), progress)
        summary["companies"] = import_subset_companies(conn, db, companies_csv, progress)
        if psc_file:
            summary["psc"] = import_subset_psc(conn, db, psc_file, progress)
    finally:
        conn.close()

    if sanctions_file:
        summary["sanctions"] = import_uk_sanctions_file(sanctions_file, db_service=db)
    if onspd_file:
        summary["onspd"] = import_onspd(csv_path=onspd_file, db_service=db)
    if score:
        summary["scoring"] = RiskScorer(db).run_all_detections()
    summary["finished_at"] = datetime.now(UTC).isoformat()
    return summary


def import_subset_companies(conn: Any, db: DatabaseService, csv_path: Path, progress: Progress | None = None) -> int:
    """Full company records for every `subset_members` company (resumable)."""
    wanted = {r[0] for r in conn.execute("SELECT company_number FROM subset_members")}
    source_id = db.register_data_source(
        source_name="Companies House - Basic Company Data",
        source_type="ch_companies",
        source_version=csv_path.parent.name,
        source_url=str(csv_path),
        conn=conn,
    )
    run = start_run(conn, "subset_companies", "ch_companies", csv_path.parent.name, str(csv_path))
    pending = 0
    for idx, raw in enumerate(_iter_company_rows(csv_path)):
        if idx < run.resume_from:
            continue
        run.rows_read = idx + 1
        if raw.get("CompanyNumber", "").upper() not in wanted:
            continue
        rec = parse_ch_company_row(raw)
        if rec:
            upsert_company_record(conn, db, rec, source_id)
            run.rows_written += 1
            pending += 1
        if pending >= _BATCH:
            checkpoint(conn, run)
            pending = 0
            if progress:
                progress("subset_companies", run.rows_written)
    finish_run(conn, run)
    return run.rows_written


def import_subset_psc(conn: Any, db: DatabaseService, psc_path: Path, progress: Progress | None = None) -> int:
    """PSC statements of the subset companies (resumable)."""
    wanted = {r[0] for r in conn.execute("SELECT company_number FROM subset_members")}
    existing = {r[0] for r in conn.execute("SELECT company_number FROM companies")}
    source_id = db.register_data_source(
        source_name="Companies House - Persons with Significant Control snapshot",
        source_type="ch_psc",
        source_version=psc_path.parent.name,
        source_url=str(psc_path),
        conn=conn,
    )
    counts = dict.fromkeys(
        ("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities"), 0
    )
    now = datetime.now(UTC).isoformat()
    run = start_run(conn, "subset_psc", "ch_psc", psc_path.parent.name, str(psc_path))
    pending = 0
    with psc_path.open("rb") as fh:
        for idx, line in enumerate(fh):
            if idx < run.resume_from:
                continue
            run.rows_read = idx + 1
            try:
                obj = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            number = (obj.get("company_number") or "").strip().upper()
            data = obj.get("data")
            if number not in wanted or not isinstance(data, dict):
                continue
            ingest_psc_record(conn, db, number, data, source_id, now, existing, counts)
            run.rows_written += 1
            pending += 1
            if pending >= _BATCH:
                checkpoint(conn, run)
                pending = 0
                if progress:
                    progress("subset_psc", run.rows_written)
    finish_run(conn, run)
    return run.rows_written


def _done(conn: Any, task: str, version: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM ingest_runs WHERE task = ? AND source_version = ? AND status = 'completed'",
        (task, version),
    ).fetchone() is not None
