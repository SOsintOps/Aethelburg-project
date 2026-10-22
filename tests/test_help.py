"""User guide: every chapter is served, internal links resolve, every UI tab has a chapter."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from src.ui.web_app import create_app

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "ui" / "frontend"


def test_guide_is_complete_and_consistent(tmp_path):
    client = TestClient(create_app(tmp_path / "help.sqlite"))
    chapters = client.get("/api/help").json()["chapters"]
    slugs = {c["slug"] for c in chapters}
    assert len(chapters) >= 14

    for slug in slugs:
        res = client.get(f"/api/help/{slug}")
        assert res.status_code == 200
        for target in re.findall(r"\]\(([^)\s]+)\)", res.json()["markdown"]):
            if not target.startswith("http"):
                assert target in slugs, f"{slug} links to missing chapter {target!r}"

    tabs = set(re.findall(r'data-tab="([a-z]+)"', (FRONTEND / "index.html").read_text(encoding="utf-8")))
    mapping = dict(re.findall(r"(\w+): \"([a-z0-9-]+)\"",(FRONTEND / "help.js").read_text(encoding="utf-8")))
    assert tabs and all(mapping.get(t) in slugs for t in tabs), (tabs, mapping)

    assert client.get("/api/help/..%2F..%2Fpyproject").status_code == 404


def test_person_search_groups_roles_per_company(tmp_path):
    from src.etl.import_companies import parse_ch_company_row, upsert_company_record
    from src.etl.import_psc import ingest_psc_record
    from src.services.db_service import DatabaseService

    db = DatabaseService(tmp_path / "people.sqlite")
    conn = db.connect()
    sid = db.register_data_source("t", "t", conn=conn)
    upsert_company_record(conn, db, parse_ch_company_row({"CompanyName": "ROSSI TRADING LTD", " CompanyNumber": "00000009"}), sid)
    counts = dict.fromkeys(("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities"), 0)
    ingest_psc_record(conn, db, "00000009", {
        "kind": "individual-person-with-significant-control", "name": "Mr Mario Rossi", "nationality": "Italian",
        "date_of_birth": {"year": 1960, "month": 1}, "links": {"self": "/x"}}, sid, "2026-10-22", {"00000009"}, counts)
    conn.commit()
    conn.close()

    items = TestClient(create_app(tmp_path / "people.sqlite")).get("/api/persons/search", params={"q": "ROSSI mario"}).json()["items"]
    assert len(items) == 1 and items[0]["nationality"] == "Italian"
    assert [c["company_number"] for c in items[0]["companies"]] == ["00000009"]
