"""REST endpoints for Companies House refresh, data folder, bulk downloads/imports and streaming."""
from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings import get_settings
from config.user_config import save_user_config
from src.datasources.catalog import SOURCES, latest_release
from src.datasources.downloader import download_source, local_releases
from src.datasources.pipeline import refresh_all
from src.datasources.storage import describe_location, set_location
from src.datasources.streaming import StreamWorker
from src.datasources.subset import SubsetConfig
from src.intelligence.risk_scorer import RiskScorer
from src.services.api_service import CompaniesHouseApiError, CompaniesHouseApiService
from src.services.db_service import DatabaseService


class LocationRequest(BaseModel):
    path: str
    move: bool = False


class DownloadRequest(BaseModel):
    sources: list[str] | None = None


class SubsetRequest(BaseModel):
    risk_links: bool | None = None
    risk_links_one_hop: bool | None = None
    mass_address: bool | None = None
    mass_address_min_companies: int | None = None
    recent: bool | None = None
    recent_years: int | None = None
    broad_criteria_active_only: bool | None = None


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
                   "started_at": _now(), "finished_at": None, "result": None, "error": None}
            self.current = job

        def progress(stage: str, value: int) -> None:
            job["stage"], job["progress"] = stage, value

        def run() -> None:
            try:
                job["result"] = fn(progress)
                job["status"] = "completed"
            except Exception as exc:  # reported to the UI
                job["status"], job["error"] = "failed", f"{type(exc).__name__}: {exc}"
            job["finished_at"] = _now()
            self.history.insert(0, job)
            del self.history[20:]

        threading.Thread(target=run, daemon=True, name=f"aethelburg-{kind}").start()
        return job


def build_data_router(db: DatabaseService) -> APIRouter:
    router = APIRouter()
    ch_api = CompaniesHouseApiService(db.db_path)
    jobs = _Jobs()
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
        if rescore:
            await asyncio.to_thread(RiskScorer(db).run_all_detections)
        summary["dossier"] = db.get_company_dossier(summary["company_number"])
        return summary

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
            if check_remote:
                try:
                    entry["latest_version"] = (await asyncio.to_thread(latest_release, key)).version
                except Exception as exc:
                    entry["latest_error"] = str(exc)
            sources.append(entry)
        conn = db.connect()
        try:
            runs = [dict(r) for r in conn.execute("SELECT * FROM ingest_runs ORDER BY started_at DESC LIMIT 20")]
            index_rows = conn.execute("SELECT COUNT(*) FROM company_index").fetchone()[0]
            members = conn.execute("SELECT reasons FROM subset_members").fetchall()
        finally:
            conn.close()
        by_reason: dict[str, int] = {}
        for (reasons,) in members:
            for r in reasons.split(","):
                by_reason[r] = by_reason.get(r, 0) + 1
        return {
            "location": describe_location(),
            "sources": sources,
            "index_rows": index_rows,
            "subset": {"config": SubsetConfig.load().__dict__, "members": len(members), "by_reason": by_reason},
            "runs": runs,
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
                results.append(download_source(key, progress=lambda done, total, k=key: progress(k, done), db=db))
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


GUIDE_DIR = Path(__file__).resolve().parents[2] / "docs" / "guide"


def _guide_chapters() -> list[tuple[str, str, Path]]:
    chapters = []
    for path in sorted(GUIDE_DIR.glob("[0-9][0-9]-*.md")):
        slug = path.stem[3:]
        first = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else slug
        chapters.append((slug, first.lstrip("# ").strip() or slug, path))
    return chapters


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
