"""End-to-end integration tests for Aethelburg Beta (Database, FT3 Scoring, Graph, Geo, Reports, FastAPI UI)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from src.core.service_registry import ServiceRegistry
from src.graph.graph_exporter import export_graph_dot, export_graph_gexf, export_graph_graphml
from src.graph.graph_service import GraphService
from src.graph.patterns import GraphPatternDetector
from src.intelligence.ft3_mapper import list_all_techniques
from src.reports.export_service import ExportService
from src.reports.pdf_generator import ReportGenerator
from src.services.db_service import DatabaseService
from src.services.geo_service import GeoService
from src.services.vector_service import VectorService
from src.ui.web_app import create_app


def test_service_registry_lifecycle():
    reg = ServiceRegistry()
    events = []
    reg.subscribe(lambda st: events.append(st))
    reg._check_sqlite_sync() if hasattr(reg, "_check_sqlite_sync") else None
    assert "onspd" in reg.status
    assert reg.is_available("onspd") is True


def _has_demo_data(db: DatabaseService) -> bool:
    """The e2e test needs a populated database (the demo company 14900101 among others)."""
    try:
        conn = db.connect()
        try:
            return conn.execute("SELECT 1 FROM companies WHERE company_number = '14900101'").fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def test_beta_services_and_exports_e2e():
    db = DatabaseService()
    if not _has_demo_data(db):
        pytest.skip("needs a populated database: set SQLITE_PATH to a copy of one")
    graph_svc = GraphService(db)
    pattern_detector = GraphPatternDetector(db)
    geo_svc = GeoService(db.db_path)
    vector_svc = VectorService(db.db_path)
    export_svc = ExportService(db)
    report_gen = ReportGenerator(db)

    # 1. Dashboard & FtM Ontology Stats
    stats = db.get_dashboard_stats()
    counts = stats["counts"]
    assert counts["companies"] > 1000
    assert counts["flagged_companies"] > 50
    assert counts["sanctions"] > 1000
    assert counts["ftm_entities"] > 5000

    ftm_stats = db.get_ftm_stats()
    assert ftm_stats["ontology_version"] == "FollowTheMoney v3.x"
    assert "Company" in ftm_stats["by_schema"]
    assert "Ownership" in ftm_stats["by_schema"]
    assert "Sanction" in ftm_stats["by_schema"]

    # 2. Search & Company Dossier
    search_res = db.search_companies(flagged_only=True, limit=15)
    assert search_res["total"] > 50
    assert len(search_res["items"]) == 15

    dossier = db.get_company_dossier("14900101")
    assert dossier is not None
    assert dossier["company"]["company_number"] == "14900101"
    assert dossier["ftm_entity"]["schema"] == "Company"
    assert len(dossier["risk_flags"]) >= 3
    assert len(dossier["icij_matches"]) >= 1

    # 3. Multi-hop Ego Graph & Topological Patterns
    ego = graph_svc.build_ego_graph("14900101", hops=2)
    assert ego["stats"]["node_count"] >= 4
    assert ego["stats"]["edge_count"] >= 4

    patterns = pattern_detector.detect_all_patterns()
    assert len(patterns["circular_ownership_cycles"]) >= 1
    assert len(patterns["star_controllers"]) >= 1

    # 4. Geospatial Map & Hotspots
    geojson = geo_svc.get_map_geojson(flagged_only=True, limit=100)
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) > 10

    hotspots = geo_svc.get_address_hotspots(min_companies=2)
    assert len(hotspots) >= 1

    # 5. Similarity Search & FT3 Metadata
    sim_matches = vector_svc.search_similar_entities("AETHELBURG MERIDIAN HOLDINGS", threshold=0.65)
    assert len(sim_matches) >= 1
    assert len(list_all_techniques()) == 11

    # 6. 10-Section Intelligence Dossier Report (BLUF, UNODC 4x4, ICD 203)
    rep = report_gen.generate_company_report("14900101")
    assert "Bottom Line Up Front (BLUF)" in rep["html"]
    assert "UNODC" in rep["html"]
    assert "FollowTheMoney" in rep["html"]
    assert len(rep["sha256_hash"]) == 64

    # 7. All 8 Export Formats
    ftm_bytes = export_svc.export_ftm_jsonl_bytes(company_number="14900101")
    first_ftm_line = json.loads(ftm_bytes.decode("utf-8").splitlines()[0])
    assert first_ftm_line["schema"] == "Company"

    xlsx_bytes = export_svc.export_xlsx_bytes(flagged_only=True, limit=50)
    assert xlsx_bytes[:2] == b"PK"  # Valid ZIP/XLSX header

    csv_bytes = export_svc.export_csv_bytes(flagged_only=True, limit=50)
    assert b"company_number,company_name,ftm_id" in csv_bytes

    gexf_str = export_graph_gexf(ego)
    assert "<gexf" in gexf_str

    graphml_str = export_graph_graphml(ego)
    assert "<graphml" in graphml_str

    dot_str = export_graph_dot(ego)
    assert "digraph Aethelburg" in dot_str

    kml_bytes = export_svc.export_kml_bytes(flagged_only=True, limit=50)
    assert b"<kml" in kml_bytes

    # 8. FastAPI App instantiation & route registration check
    app = create_app()
    route_paths = {getattr(r, "path", "") for r in app.routes}
    for expected_route in (
        "/",
        "/api/health",
        "/api/stats",
        "/api/companies",
        "/api/companies/{company_number}",
        "/api/companies/{company_number}/graph",
        "/api/geo/map",
        "/api/ftm/stats",
        "/api/investigations",
        "/api/reports/company/{company_number}",
        "/api/export/{fmt}",
    ):
        assert expected_route in route_paths, f"Missing route: {expected_route}"
