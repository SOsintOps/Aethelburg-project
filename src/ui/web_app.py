"""FastAPI Web & Desktop Backend for Aethelburg Corporate Intelligence Platform.

Exposes:
  - Interactive 3-panel Intelligence UI at `/`
  - Static assets (`/assets/*`, `/static/*`)
  - REST API for Search, Company Dossiers, Multi-Hop Graphs, GeoJSON/Hotspots,
    FollowTheMoney (`FtM v3.x`) ontology inspection & JSONL import/export,
    FT3 Risk Scoring, Casework Investigations, and 10-Section Intelligence Reports.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config.settings import get_settings
from src.core.ftm import load_ftm_schema
from src.graph.graph_exporter import export_graph_dot, export_graph_gexf, export_graph_graphml
from src.graph.graph_service import GraphService
from src.graph.patterns import GraphPatternDetector
from src.intelligence.ft3_mapper import (
    CONFIDENCE_LEVELS,
    UNODC_INFO_CREDIBILITY,
    UNODC_SOURCE_RELIABILITY,
    list_all_techniques,
)
from src.intelligence.risk_scorer import RiskScorer
from src.reports.export_service import ExportService
from src.reports.pdf_generator import ReportGenerator
from src.services.db_service import DatabaseService
from src.services.geo_service import GeoService
from src.services.vector_service import VectorService
from src.ui.data_api import build_data_router
from src.ui.settings_api import build_settings_router

PROJECT_ROOT = Path(__file__).parent.parent.parent
FRONTEND_DIR = Path(__file__).parent / "frontend"
ASSETS_DIR = PROJECT_ROOT / "assets"


class CreateInvestigationRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    description: str = ""
    hypothesis: str = ""
    priority: str = "high"
    classification: str = "CONFIDENTIAL"


class AddCaseEntityRequest(BaseModel):
    entity_type: str = "company"
    entity_id: str
    role_in_case: str = "subject"
    notes: str = ""


class AddAnnotationRequest(BaseModel):
    entity_type: str | None = "company"
    entity_id: str | None = None
    annotation_text: str = Field(..., min_length=2)
    annotation_type: str = "finding"
    confidence: str = "high"
    source_grade: str = "A1"


def create_app(db_path: Path | str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    db = DatabaseService(db_path)
    graph_svc = GraphService(db)
    pattern_detector = GraphPatternDetector(db)
    geo_svc = GeoService(db.db_path)
    vector_svc = VectorService(db.db_path)
    export_svc = ExportService(db)
    report_gen = ReportGenerator(db)

    app = FastAPI(
        title="Aethelburg — Corporate Intelligence & Shell Company Detection",
        version=settings.version,
        description=(
            "Investigative corporate intelligence platform compatible with the FollowTheMoney (FtM v3.x) "
            "ontology, Stripe FT3 taxonomy, and UNODC 4x4 / ICD 203 analytic standards."
        ),
    )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        # One id ties the message shown in the UI to the traceback in the log file
        error_id = uuid.uuid4().hex[:8]
        logging.getLogger("aethelburg.web").error(
            "unhandled error %s on %s %s", error_id, request.method, request.url.path, exc_info=exc
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Unexpected error ({type(exc).__name__}: {exc}). Error id {error_id}: see logs/aethelburg.log",
                "error_id": error_id,
            },
        )

    app.include_router(build_data_router(db))
    app.include_router(build_settings_router(db))

    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_file = FRONTEND_DIR / "index.html"
        if not index_file.exists():
            return HTMLResponse("<h1>Aethelburg UI not found</h1>", status_code=404)
        return HTMLResponse(index_file.read_text(encoding="utf-8"))

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        ico_path = ASSETS_DIR / "aethelburg.ico"
        if ico_path.exists():
            return FileResponse(str(ico_path), media_type="image/x-icon")
        return Response(status_code=204)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        ftm_stats = db.get_ftm_stats()
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.version,
            "ontology": "FollowTheMoney v3.x",
            "ftm_entities": ftm_stats["total_entities"],
        }

    @app.get("/api/stats")
    async def stats() -> dict[str, Any]:
        return db.get_dashboard_stats()

    @app.get("/api/ft3/techniques")
    async def ft3_techniques() -> dict[str, Any]:
        return {
            "techniques": list_all_techniques(),
            "unodc_source_reliability": UNODC_SOURCE_RELIABILITY,
            "unodc_info_credibility": UNODC_INFO_CREDIBILITY,
            "confidence_levels": CONFIDENCE_LEVELS,
        }

    @app.get("/api/companies")
    async def search_companies(
        q: str = Query(default="", description="Search query (company name, CRN, postcode)"),
        status: str | None = Query(default=None),
        min_risk: float = Query(default=0.0, ge=0.0, le=100.0),
        ft3: str | None = Query(default=None, description="FT3 technique filter, e.g. FT3-SC-007"),
        flagged_only: bool = Query(default=False),
        postcode: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=250),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return db.search_companies(
            query=q,
            status=status,
            min_risk=min_risk,
            ft3_technique=ft3,
            flagged_only=flagged_only,
            postcode=postcode,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/companies/{company_number}")
    async def company_dossier(company_number: str) -> dict[str, Any]:
        dossier = db.get_company_dossier(company_number)
        if not dossier:
            raise HTTPException(status_code=404, detail=f"Company '{company_number}' not found")
        return dossier

    @app.get("/api/companies/{company_number}/graph")
    async def company_graph(
        company_number: str,
        hops: int = Query(default=2, ge=1, le=3),
    ) -> dict[str, Any]:
        return graph_svc.build_ego_graph(company_number, hops=hops)

    @app.get("/api/graph/overview")
    async def graph_overview(limit: int = Query(default=25, ge=5, le=100)) -> dict[str, Any]:
        return graph_svc.build_overview_graph(limit_companies=limit)

    @app.get("/api/graph/patterns")
    async def graph_patterns() -> dict[str, Any]:
        return pattern_detector.detect_all_patterns()

    @app.get("/api/geo/map")
    async def geo_map(
        flagged_only: bool = Query(default=False),
        min_risk: float = Query(default=0.0),
        limit: int = Query(default=400, ge=10, le=2000),
    ) -> dict[str, Any]:
        return geo_svc.get_map_geojson(flagged_only=flagged_only, min_risk=min_risk, limit=limit)

    @app.get("/api/geo/hotspots")
    async def geo_hotspots(
        min_companies: int = Query(default=3, ge=2, le=500),
        limit: int = Query(default=50, ge=1, le=250),
    ) -> dict[str, Any]:
        return {"hotspots": geo_svc.get_address_hotspots(min_companies=min_companies, limit=limit)}

    @app.get("/api/similarity")
    async def similarity_search(
        name: str = Query(..., min_length=2),
        threshold: float = Query(default=0.70, ge=0.3, le=1.0),
    ) -> dict[str, Any]:
        return {"query": name, "matches": vector_svc.search_similar_entities(name, threshold=threshold)}

    # ------------------------------------------------------------------ #
    # FOLLOW THE MONEY (FtM v3.x) ONTOLOGY ENDPOINTS                     #
    # ------------------------------------------------------------------ #

    @app.get("/api/ftm/stats")
    async def ftm_stats() -> dict[str, Any]:
        stats_data = db.get_ftm_stats()
        schema_defs = load_ftm_schema()
        stats_data["supported_schemas_count"] = len(schema_defs)
        stats_data["core_schemas"] = [
            "Company",
            "Person",
            "LegalEntity",
            "Organization",
            "Address",
            "Ownership",
            "Directorship",
            "Sanction",
            "Representation",
            "UnknownLink",
        ]
        return stats_data

    @app.get("/api/ftm/entity/{ftm_id}")
    async def get_ftm_entity(ftm_id: str) -> dict[str, Any]:
        ent = db.get_ftm_entity(ftm_id)
        if not ent:
            raise HTTPException(status_code=404, detail=f"FtM entity '{ftm_id}' not found")
        return ent

    @app.get("/api/ftm/entities")
    async def list_ftm_entities(
        schema: str | None = Query(default=None),
        dataset: str | None = Query(default=None),
        target_only: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        items = list(
            db.iter_ftm_entities(
                schema=schema,
                dataset=dataset,
                target_only=target_only,
                limit=limit,
            )
        )
        return {"count": len(items), "items": items}

    # ------------------------------------------------------------------ #
    # CASEWORK & INVESTIGATIONS                                          #
    # ------------------------------------------------------------------ #

    @app.get("/api/investigations")
    async def list_investigations() -> dict[str, Any]:
        return {"items": db.list_investigations()}

    @app.post("/api/investigations")
    async def create_investigation(req: CreateInvestigationRequest) -> dict[str, Any]:
        return db.create_investigation(
            title=req.title,
            description=req.description,
            hypothesis=req.hypothesis,
            priority=req.priority,
            classification=req.classification,
        )

    @app.get("/api/investigations/{investigation_id}")
    async def get_investigation(investigation_id: str) -> dict[str, Any]:
        inv = db.get_investigation(investigation_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return inv

    @app.post("/api/investigations/{investigation_id}/entities")
    async def add_entity_to_investigation(
        investigation_id: str,
        req: AddCaseEntityRequest,
    ) -> dict[str, Any]:
        return db.add_entity_to_investigation(
            investigation_id=investigation_id,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            role_in_case=req.role_in_case,
            notes=req.notes,
        )

    @app.post("/api/investigations/{investigation_id}/annotations")
    async def add_annotation(
        investigation_id: str,
        req: AddAnnotationRequest,
    ) -> dict[str, Any]:
        return db.add_annotation(
            investigation_id=investigation_id,
            annotation_text=req.annotation_text,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            annotation_type=req.annotation_type,
            confidence=req.confidence,
            source_grade=req.source_grade,
        )

    # ------------------------------------------------------------------ #
    # REPORTS & MULTI-FORMAT EXPORTS                                     #
    # ------------------------------------------------------------------ #

    @app.get("/api/reports/company/{company_number}", response_class=HTMLResponse)
    async def company_html_report(
        company_number: str,
        classification: str = Query(default="CONFIDENTIAL"),
        download: bool = Query(default=False),
    ) -> Response:
        try:
            rep = report_gen.generate_company_report(
                company_number=company_number,
                classification=classification,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="aethelburg_dossier_{company_number}.html"'
        return HTMLResponse(content=rep["html"], headers=headers)

    @app.get("/api/export/{fmt}")
    async def export_data(
        fmt: str,
        company_number: str | None = Query(default=None),
        flagged_only: bool = Query(default=True),
    ) -> Response:
        fmt_clean = fmt.lower().strip()
        if fmt_clean in ("ftm", "ftm_json", "ftm.json"):
            data = export_svc.export_ftm_jsonl_bytes(company_number=company_number, target_only=flagged_only)
            fname = f"aethelburg_{company_number or 'entities'}.ftm.json"
            return Response(
                content=data,
                media_type="application/x-ndjson",
                headers={"Content-Disposition": f'attachment; filename="{fname}"'},
            )
        if fmt_clean == "xlsx":
            data = export_svc.export_xlsx_bytes(flagged_only=flagged_only)
            return Response(
                content=data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": 'attachment; filename="aethelburg_intelligence.xlsx"'},
            )
        if fmt_clean == "csv":
            data = export_svc.export_csv_bytes(flagged_only=flagged_only)
            return Response(
                content=data,
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="aethelburg_companies.csv"'},
            )
        if fmt_clean == "gexf":
            graph_payload = (
                graph_svc.build_ego_graph(company_number, hops=2)
                if company_number
                else graph_svc.build_overview_graph()
            )
            xml_str = export_graph_gexf(graph_payload)
            return Response(
                content=xml_str.encode("utf-8"),
                media_type="application/gexf+xml",
                headers={"Content-Disposition": f'attachment; filename="aethelburg_{company_number or "network"}.gexf"'},
            )
        if fmt_clean == "graphml":
            graph_payload = (
                graph_svc.build_ego_graph(company_number, hops=2)
                if company_number
                else graph_svc.build_overview_graph()
            )
            xml_str = export_graph_graphml(graph_payload)
            return Response(
                content=xml_str.encode("utf-8"),
                media_type="application/xml",
                headers={"Content-Disposition": f'attachment; filename="aethelburg_{company_number or "network"}.graphml"'},
            )
        if fmt_clean == "dot":
            graph_payload = (
                graph_svc.build_ego_graph(company_number, hops=2)
                if company_number
                else graph_svc.build_overview_graph()
            )
            dot_str = export_graph_dot(graph_payload)
            return Response(
                content=dot_str.encode("utf-8"),
                media_type="text/vnd.graphviz",
                headers={"Content-Disposition": f'attachment; filename="aethelburg_{company_number or "network"}.dot"'},
            )
        if fmt_clean == "geojson":
            geojson_obj = geo_svc.get_map_geojson(flagged_only=flagged_only)
            return JSONResponse(
                content=geojson_obj,
                headers={"Content-Disposition": 'attachment; filename="aethelburg_geo.geojson"'},
            )
        if fmt_clean == "kml":
            kml_bytes = export_svc.export_kml_bytes(flagged_only=flagged_only)
            return Response(
                content=kml_bytes,
                media_type="application/vnd.google-earth.kml+xml",
                headers={"Content-Disposition": 'attachment; filename="aethelburg_geo.kml"'},
            )
        raise HTTPException(status_code=400, detail=f"Unsupported export format: {fmt}")

    @app.post("/api/score/run")
    async def run_scoring() -> dict[str, Any]:
        scorer = RiskScorer(db)
        return scorer.run_all_detections()

    return app
