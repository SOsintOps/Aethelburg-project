"""REST endpoints for Companies House refresh, data folder, bulk downloads/imports and streaming."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from config.settings import get_settings
from config.user_config import load_user_config, save_user_config
from src.core.normalizer import normalize_name
from src.datasources.backup import create_backup, list_backups, restore_backup
from src.datasources.catalog import SOURCES, latest_release
from src.datasources.daily import last_run_day, run_daily_update, schedule, scheduler_loop
from src.datasources.downloader import download_source, local_releases
from src.datasources.officers import COMPANIES_PER_HOUR, fetch_officers_batch, pending_companies
from src.datasources.pipeline import refresh_all
from src.datasources.storage import describe_location, set_location
from src.datasources.streaming import StreamWorker
from src.datasources.subset import SubsetConfig, subset_counts
from src.etl.company_changes import CHANGE_TYPES, change_counts, changes_csv, list_changes
from src.intelligence.risk_scorer import RiskScorer
from src.services.api_service import CompaniesHouseApiError, CompaniesHouseApiService
from src.services.db_service import DatabaseService
from src.services.documents import fetch_filing_history
from src.ui.documents_api import add_document_routes


class LocationRequest(BaseModel):
    path: str
    move: bool = False


class DownloadRequest(BaseModel):
    sources: list[str] | None = None


class OfficersRequest(BaseModel):
    scope: Literal["flagged", "case", "subset"] = "flagged"
    limit: int | None = None


class DailyRequest(BaseModel):
    enabled: bool
    time: str = "06:00"
    documents: bool = False


class SubsetRequest(BaseModel):
    risk_links: bool | None = None
    risk_links_one_hop: bool | None = None
    mass_address: bool | None = None
    mass_address_min_companies: int | None = None
    recent: bool | None = None
    recent_years: int | None = None
    broad_criteria_mode: Literal["and", "or"] | None = None
    broad_criteria_active_only: bool | None = None
    psc_nationalities: list[str] | None = None


class _Jobs:
    """Long tasks run in a worker thread; one at a time, progress readable by the UI."""

    def __init__(self) -> None:
        self.current: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def start(self, kind: str, fn: Any) -> dict[str, Any]:
        with self._lock:
            if self.current and self.current["status"] == "running":
                raise HTTPException(status_code=409, detail=f"Another task is running: {self.current['kind']}")
            job = {"id": str(uuid.uuid4()), "kind": kind, "status": "running", "stage": None, "progress": None,
                   "total": None, "started_at": _now(), "finished_at": None, "result": None, "error": None}
            self.current = job

        def progress(stage: str, value: int, total: int | None = None) -> None:
            job["stage"], job["progress"], job["total"] = stage, value, total

        def run() -> None:
            try:
                job["result"] = fn(progress)
                job["status"] = "completed"
            except Exception as exc:  # reported to the UI and to the log file
                job["status"], job["error"] = "failed", f"{type(exc).__name__}: {exc}"
                logging.getLogger("aethelburg.jobs").error("task %s failed", kind, exc_info=exc)
            job["finished_at"] = _now()
            self.history.insert(0, job)
            del self.history[20:]

        threading.Thread(target=run, daemon=True, name=f"aethelburg-{kind}").start()
        return job


class _ReleaseCache:
    """Latest published release per source, kept 10 minutes so the Data tab does not hit publishers on every refresh."""

    TTL_SECONDS = 600

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, key: str, refresh: bool = True) -> dict[str, Any] | None:
        hit = self._data.get(key)
        if hit and time.monotonic() - hit[0] < self.TTL_SECONDS:
            return hit[1]
        if not refresh:
            return None
        try:
            value: dict[str, Any] = {"latest_version": latest_release(key).version, "checked_at": _now()}
        except Exception as exc:  # network down or page layout changed: shown in the table
            value = {"latest_error": str(exc), "checked_at": _now()}
        self._data[key] = (time.monotonic(), value)
        return value

    def forget(self, key: str) -> None:
        self._data.pop(key, None)


def build_data_router(db: DatabaseService) -> APIRouter:
    router = APIRouter()
    ch_api = CompaniesHouseApiService(db.db_path)
    jobs = _Jobs()
    releases = _ReleaseCache()
    worker: dict[str, StreamWorker] = {}

    def stream_worker() -> StreamWorker:
        if "w" not in worker:
            worker["w"] = StreamWorker(db)
        return worker["w"]

    # ------------------------------------------------------------------ #
    # COMPANIES HOUSE REST                                               #
    # ------------------------------------------------------------------ #

    @router.get("/api/ch/status")
    async def ch_status() -> dict[str, Any]:
        settings = get_settings().ch
        return {"api_key_configured": bool(settings.api_key), "streaming_key_configured": bool(settings.streaming_key)}

    @router.post("/api/companies/{company_number}/refresh")
    async def refresh_company(company_number: str, rescore: bool = True) -> dict[str, Any]:
        try:
            summary = await ch_api.refresh_company(company_number)
        except CompaniesHouseApiError as exc:
            status = exc.status if exc.status in (400, 401, 404, 429) else 502
            raise HTTPException(status_code=status, detail=exc.message) from exc
        try:
            summary["filings"] = await fetch_filing_history(ch_api, summary["company_number"])
        except CompaniesHouseApiError as exc:  # the profile, officers and PSC are already saved
            summary["filings_error"] = exc.message
            logging.getLogger(__name__).warning("filing history of %s: %s", company_number, exc.message)
        if rescore:
            # scoring covers the whole register and can take a long time: it runs as a background
            # task and the dossier below shows the scores as they are now
            summary["rescore"] = _start_rescore()
        summary["dossier"] = await asyncio.to_thread(db.get_company_dossier, summary["company_number"])
        return summary

    def _start_rescore() -> dict[str, Any]:
        try:
            job = jobs.start("score", lambda progress: RiskScorer(db).run_all_detections())
        except HTTPException as exc:
            return {"status": "busy", "detail": exc.detail}
        return {"status": job["status"], "job_id": job["id"]}

    @router.post("/api/score/run")
    async def run_scoring() -> dict[str, Any]:
        """Re-run entity resolution and every FT3 rule on the whole database, as a background task."""
        return _start_rescore()

    add_document_routes(router, db, ch_api)

    @router.get("/api/persons/search")
    async def persons_search(q: str, limit: int = 15) -> dict[str, Any]:
        """People (PSC controllers and officers) whose name contains every word typed, with their companies."""
        return {"items": await asyncio.to_thread(_person_search, db, q, min(max(limit, 1), 50))}

    @router.get("/api/ch/officers/search")
    async def ch_officer_search(q: str) -> dict[str, Any]:
        try:
            return {"items": await ch_api.search_officers(q)}
        except CompaniesHouseApiError as exc:
            raise HTTPException(status_code=exc.status if exc.status in (400, 401, 429) else 502, detail=exc.message) from exc

    @router.get("/api/ch/officers/{officer_id}/appointments")
    async def ch_officer_appointments(officer_id: str) -> dict[str, Any]:
        try:
            return await ch_api.officer_appointments(officer_id)
        except CompaniesHouseApiError as exc:
            raise HTTPException(status_code=exc.status if exc.status in (400, 401, 404, 429) else 502, detail=exc.message) from exc

    @router.get("/api/index/search")
    async def index_search(q: str, limit: int = 20) -> dict[str, Any]:
        """Companies in the light register index that are not fully imported (fetchable on demand)."""
        return {"items": _index_search(db, q, min(max(limit, 1), 100))}

    # ------------------------------------------------------------------ #
    # DATA FOLDER, SOURCES, IMPORTS                                      #
    # ------------------------------------------------------------------ #

    @router.get("/api/data/status")
    async def data_status(check_remote: bool = False) -> dict[str, Any]:
        sources = []
        for key, info in SOURCES.items():
            local = local_releases(key)
            entry: dict[str, Any] = {
                "key": key, "title": info.title, "licence": info.licence, "frequency": info.update_frequency,
                "local_version": local[0]["version"] if local else None,
                "local_file": local[0]["data_file"] if local else None,
                "downloaded_at": local[0]["downloaded_at"] if local else None,
            }
            # cached result (<10 min) is always shown; check_remote asks publishers when it is stale
            cached = await asyncio.to_thread(releases.get, key) if check_remote else releases.get(key, refresh=False)
            if cached is not None:
                entry.update(cached)
            sources.append(entry)
        conn = db.connect()
        try:
            runs = [dict(r) for r in conn.execute("SELECT * FROM ingest_runs ORDER BY started_at DESC LIMIT 20")]
            index_rows = conn.execute("SELECT COUNT(*) FROM company_index").fetchone()[0]
            by_reason = subset_counts(conn)
        finally:
            conn.close()
        members = by_reason.pop("total", 0)
        return {
            "location": describe_location(),
            "sources": sources,
            "index_rows": index_rows,
            "subset": {"config": SubsetConfig.load().__dict__, "members": members, "by_reason": by_reason},
            "runs": runs,
            "backups": list_backups()[:5],
            "daily": {"enabled": schedule()[0], "time": schedule()[1], "last_run": last_run_day(db),
                      "documents": bool(load_user_config().get("documents_auto_download", False))},
            "job": jobs.current,
            "job_history": jobs.history,
            "stream": stream_worker().status(),
        }

    @router.post("/api/data/location")
    async def data_location(req: LocationRequest) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(set_location, Path(req.path), req.move)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/data/download")
    async def data_download(req: DownloadRequest) -> dict[str, Any]:
        keys = req.sources or list(SOURCES)
        unknown = [k for k in keys if k not in SOURCES]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown sources: {unknown}")

        def task(progress: Any) -> list[dict[str, Any]]:
            results = []
            for key in keys:
                res = download_source(key, progress=lambda done, total, k=key: progress(k, done, total), db=db)
                results.append({"source": key, "title": SOURCES[key].title, "status": res["status"],
                                "version": res["version"], "bytes": res.get("bytes")})
                releases.forget(key)
            return results

        return jobs.start("download", task)

    @router.post("/api/data/import")
    async def data_import(score: bool = True) -> dict[str, Any]:
        return jobs.start("import", lambda progress: refresh_all(db=db, progress=progress, score=score))

    @router.post("/api/data/subset")
    async def data_subset(req: SubsetRequest) -> dict[str, Any]:
        updates = {f"subset_{k}": v for k, v in req.model_dump().items() if v is not None}
        save_user_config(updates)
        return {"config": SubsetConfig.load().__dict__, "note": "Applied at the next import"}

    @router.post("/api/data/stream/{action}")
    async def data_stream(action: str) -> dict[str, Any]:
        w = stream_worker()
        if action == "start":
            try:
                w.start()
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        elif action == "stop":
            await w.stop()
        else:
            raise HTTPException(status_code=400, detail="action must be start or stop")
        return w.status()

    # ------------------------------------------------------------------ #
    # OFFICERS IN BULK, DAILY UPDATE                                     #
    # ------------------------------------------------------------------ #

    @router.post("/api/data/officers")
    async def officers_batch(req: OfficersRequest) -> dict[str, Any]:
        todo = len(await asyncio.to_thread(pending_companies, db, req.scope))
        todo = min(todo, req.limit) if req.limit else todo
        job = jobs.start("officers", lambda progress: fetch_officers_batch(req.scope, req.limit, db=db, progress=progress))
        return {**job, "companies": todo, "hours": round(todo / COMPANIES_PER_HOUR, 1)}

    @router.post("/api/data/daily")
    async def daily_settings(req: DailyRequest) -> dict[str, Any]:
        hh, _, mm = req.time.partition(":")
        if not (hh.isdigit() and mm.isdigit() and int(hh) < 24 and int(mm) < 60):
            raise HTTPException(status_code=400, detail="Time must be HH:MM")
        save_user_config({"daily_update_enabled": req.enabled, "daily_update_time": f"{int(hh):02d}:{int(mm):02d}",
                          "documents_auto_download": req.documents})
        return {"enabled": req.enabled, "time": f"{int(hh):02d}:{int(mm):02d}", "documents": req.documents}

    @router.post("/api/data/daily/run")
    async def daily_run_now() -> dict[str, Any]:
        return jobs.start("daily", lambda progress: run_daily_update(db, progress))

    @asynccontextmanager
    async def daily_scheduler(_app: Any) -> AsyncIterator[None]:
        task = asyncio.get_running_loop().create_task(scheduler_loop(db, jobs.start))
        yield
        task.cancel()

    router.lifespan_context = daily_scheduler  # merged into the app's lifespan by include_router

    # ------------------------------------------------------------------ #
    # CHANGE HISTORY                                                     #
    # ------------------------------------------------------------------ #

    @router.get("/api/data/changes", response_model=None)
    async def changes(
        change_type: str | None = None,
        company_number: str | None = None,
        subset_only: bool = False,
        limit: int = 100,
        format: Literal["json", "csv"] = "json",
    ) -> dict[str, Any] | Response:
        if change_type and change_type not in CHANGE_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown change type: {change_type}")
        number = (company_number or "").strip().upper() or None
        conn = db.connect()
        try:
            rows = list_changes(conn, number, change_type, subset_only, limit if format == "json" else 100_000)
            counts = change_counts(conn)
        finally:
            conn.close()
        if format == "csv":
            return Response(
                content=changes_csv(rows),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="aethelburg_changes.csv"'},
            )
        return {"items": rows, "counts": counts, "types": list(CHANGE_TYPES)}

    # ------------------------------------------------------------------ #
    # BACKUPS                                                            #
    # ------------------------------------------------------------------ #

    @router.get("/api/data/backups")
    async def backups() -> dict[str, Any]:
        return {"items": list_backups()}

    @router.post("/api/data/backups")
    async def backup_now() -> dict[str, Any]:
        return jobs.start("backup", lambda progress: create_backup("manual"))

    @router.post("/api/data/backups/{name}/restore")
    async def backup_restore(name: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(restore_backup, name)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ------------------------------------------------------------------ #
    # USER GUIDE (docs/guide/NN-slug.md)                                 #
    # ------------------------------------------------------------------ #

    @router.get("/api/help")
    async def help_index() -> dict[str, Any]:
        return {"chapters": [{"slug": slug, "title": title} for slug, title, _ in _guide_chapters()]}

    @router.get("/api/help/{slug}")
    async def help_chapter(slug: str) -> dict[str, Any]:
        for chapter_slug, title, path in _guide_chapters():
            if chapter_slug == slug:  # only known chapters are served: no path from the request
                return {"slug": slug, "title": title, "markdown": path.read_text(encoding="utf-8")}
        raise HTTPException(status_code=404, detail=f"No guide chapter {slug!r}")

    return router


PROJECT_DIR = Path(__file__).resolve().parents[2]
GUIDE_DIR = PROJECT_DIR / "docs" / "guide"
# Extra chapters after the numbered guide: fixed list, never a path taken from the request
EXTRA_CHAPTERS = (("faq", "FAQ", PROJECT_DIR / "docs" / "FAQ.md"),
                  ("version-history", "Version history", PROJECT_DIR / "CHANGELOG.md"))


def _guide_chapters() -> list[tuple[str, str, Path]]:
    chapters = []
    for path in sorted(GUIDE_DIR.glob("[0-9][0-9]-*.md")):
        slug = path.stem[3:]
        first = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else slug
        chapters.append((slug, first.lstrip("# ").strip() or slug, path))
    chapters.extend(c for c in EXTRA_CHAPTERS if c[2].exists())
    return chapters


def _person_search(db: DatabaseService, q: str, limit: int) -> list[dict[str, Any]]:
    words = [w for w in normalize_name(q or "", is_company=False).split() if len(w) >= 2]
    if not words:
        return []
    conn = db.connect()
    try:
        where = " AND ".join("p.name_fingerprint LIKE ?" for _ in words)
        people = conn.execute(
            f"""
            SELECT p.id, p.name, p.nationality, p.country_of_residence, p.dob_month, p.dob_year
            FROM persons p WHERE {where}
            ORDER BY p.name LIMIT ?
            """,
            [*(f"%{w}%" for w in words), limit],
        ).fetchall()
        result = []
        for p in people:
            companies = conn.execute(
                """
                SELECT c.company_number, c.company_name, c.company_status, c.risk_score,
                       GROUP_CONCAT(DISTINCT link.role) AS role
                FROM (
                    SELECT company_number, 'PSC' AS role FROM psc_ownerships WHERE person_id = ?
                    UNION
                    SELECT company_number, COALESCE(officer_role, 'officer') AS role FROM directorships WHERE person_id = ?
                ) link
                JOIN companies c ON c.company_number = link.company_number
                GROUP BY c.company_number
                ORDER BY c.risk_score DESC LIMIT 12
                """,
                (p["id"], p["id"]),
            ).fetchall()
            result.append({**dict(p), "companies": [dict(c) for c in companies]})
        return result
    finally:
        conn.close()


def _index_search(db: DatabaseService, q: str, limit: int) -> list[dict[str, Any]]:
    q = (q or "").strip().upper()
    if len(q) < 2:
        return []
    conn = db.connect()
    try:
        if q.isalnum() and any(ch.isdigit() for ch in q) and len(q) <= 8:
            number = q.zfill(8) if q.isdigit() else q
            sql, params = "ci.company_number = ?", [number]
        else:
            # company names are upper-case in the register: a range scan uses the index
            sql, params = "ci.company_name >= ? AND ci.company_name < ?", [q, q + "￿"]
        rows = conn.execute(
            f"""
            SELECT ci.company_number, ci.company_name, ci.postcode, ci.company_status, ci.incorporation_date
            FROM company_index ci
            WHERE {sql} AND NOT EXISTS (SELECT 1 FROM companies c WHERE c.company_number = ci.company_number)
            ORDER BY ci.company_name LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()
