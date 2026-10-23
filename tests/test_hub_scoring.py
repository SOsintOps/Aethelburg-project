"""FT3-SC-001: a shared address is context with a low score and never flags a company on its own."""
from __future__ import annotations

import json

from src.core.normalizer import normalize_name
from src.etl.import_psc import ingest_psc_record
from src.intelligence.risk_scorer import (
    DEFAULT_MASS_ADDRESS_THRESHOLD,
    RiskScorer,
    mass_address_score,
    mass_address_threshold_setting,
)
from src.services.db_service import DatabaseService

COUNTS = ("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities")


def test_mass_address_score_falls_for_the_largest_hubs():
    assert mass_address_score(20) == (10.0, "shared address")
    assert mass_address_score(150)[0] == 8.0
    assert mass_address_score(60933)[0] == 6.0


def test_threshold_comes_from_the_user_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    monkeypatch.setenv("AETHELBURG_CONFIG", str(cfg))
    assert mass_address_threshold_setting() == DEFAULT_MASS_ADDRESS_THRESHOLD
    cfg.write_text("mass_address_threshold = 50\n", encoding="utf-8")
    assert mass_address_threshold_setting() == 50
    cfg.write_text("mass_address_threshold = 1\n", encoding="utf-8")
    assert mass_address_threshold_setting() == 5  # kept within range
    cfg.write_text("mass_address_threshold = 'many'\n", encoding="utf-8")
    assert mass_address_threshold_setting() == DEFAULT_MASS_ADDRESS_THRESHOLD


def _company(conn, number: str, line1: str, postcode: str) -> None:
    conn.execute(
        """
        INSERT INTO companies (company_number, company_name, reg_address_line1, reg_address_postcode,
                               address_fingerprint, company_status)
        VALUES (?, ?, ?, ?, ?, 'Active')
        """,
        (number, f"COMPANY {number} LTD", line1, postcode, f"{line1} {postcode}".lower()),
    )


def test_hub_alone_does_not_flag_but_adds_to_other_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHELBURG_CONFIG", str(tmp_path / "config.toml"))
    db = DatabaseService(tmp_path / "hub.sqlite")
    conn = db.connect()
    try:
        for n in range(1, 4):
            _company(conn, f"1000000{n}", "1 HUB STREET", "EC1V 2NX")
        _company(conn, "20000001", "9 LONE ROAD", "LS1 1AA")
        # a fourth company at the hub whose controller is on a sanctions list
        _company(conn, "10000004", "1 HUB STREET", "EC1V 2NX")
        ingest_psc_record(
            conn, db, "10000004",
            {
                "kind": "individual-person-with-significant-control",
                "name": "Igor Petrov",
                "notified_on": "2020-01-01",
                "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
                "date_of_birth": {"month": 1, "year": 1966},
                "links": {"self": "/company/10000004/persons-with-significant-control/individual/x"},
            },
            None, "2026-10-23", set(), dict.fromkeys(COUNTS, 0),
        )
        conn.execute(
            """
            INSERT INTO sanctions (id, ftm_id, ftm_schema, subject_ftm_id, name, name_fingerprint, entity_type,
                                   list_name, source, opensanctions_id, raw_properties)
            VALUES ('T5', 's-T5', 'Sanction', 'subj-T5', 'Igor PETROV', ?, 'Person', 'Test regime', 'uk_ofsi', 'T5', ?)
            """,
            (normalize_name("Igor PETROV"), json.dumps({"birth_dates": [{"year": 1966, "month": 1, "day": 12}]})),
        )
        conn.commit()
    finally:
        conn.close()

    # default threshold (20) is above the four companies: no hub at all
    summary = RiskScorer(db).run_all_detections()
    assert summary["techniques_detected"]["FT3-SC-001"] == 0

    summary = RiskScorer(db).run_all_detections(mass_address_threshold=3)
    assert summary["techniques_detected"]["FT3-SC-001"] == 4
    assert summary["flagged_companies"] == 1

    conn = db.connect()
    try:
        rows = {
            r["company_number"]: (r["risk_score"], json.loads(r["ft3_techniques"]), r["is_flagged"])
            for r in conn.execute("SELECT company_number, risk_score, ft3_techniques, is_flagged FROM companies")
        }
        flag = conn.execute(
            "SELECT score_contribution, evidence FROM risk_flags WHERE company_number = '10000001' AND ft3_technique = 'FT3-SC-001'"
        ).fetchone()
    finally:
        conn.close()
    assert rows["10000001"] == (10.0, ["FT3-SC-001"], 0)
    assert rows["20000001"] == (0.0, [], 0)
    assert rows["10000004"][1] == ["FT3-SC-001", "FT3-SC-007"] and rows["10000004"][2] == 1
    assert rows["10000004"][0] == 55.0
    evidence = json.loads(flag["evidence"])
    assert flag["score_contribution"] == 10.0
    assert (evidence["unodc_grade"], evidence["confidence"], evidence["colocated_companies_count"]) == ("B2", "moderate", 4)
