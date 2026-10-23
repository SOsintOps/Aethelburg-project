"""People are matched to sanctions on name and date of birth, not on name alone."""
from __future__ import annotations

import json

from src.core.normalizer import normalize_name
from src.etl.import_psc import ingest_psc_record
from src.etl.import_sanctions import parse_birth_date
from src.intelligence.entity_resolver import EntityResolver, compare_birth_dates
from src.intelligence.risk_scorer import RiskScorer
from src.services.db_service import DatabaseService

COUNTS = ("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities")


def test_parse_birth_date():
    assert parse_birth_date("07/03/1961") == {"year": 1961, "month": 3, "day": 7}
    assert parse_birth_date("dd/mm/1945") == {"year": 1945, "month": None, "day": None}
    assert parse_birth_date("dd/03/1945") == {"year": 1945, "month": 3, "day": None}
    assert parse_birth_date("1970") == {"year": 1970, "month": None, "day": None}
    assert parse_birth_date("Russia") is None
    assert parse_birth_date("") is None


def test_compare_birth_dates():
    dates = [{"year": 1977, "month": 1, "day": 5}, {"year": 1978, "month": None, "day": None}]
    assert compare_birth_dates(dates, 1977, 1) == "match"
    assert compare_birth_dates(dates, 1978, 11) == "year_only"  # the list gives no month
    assert compare_birth_dates(dates, 1977, None) == "year_only"  # the register gives no month
    assert compare_birth_dates(dates, 1977, 2) == "conflict"
    assert compare_birth_dates(dates, 1980, 1) == "conflict"
    assert compare_birth_dates([], 1977, 1) == "unknown"
    assert compare_birth_dates(dates, None, None) == "unknown"


def _psc(company: str, name: str, year: int, month: int, ceased_on: str | None = None) -> dict:
    record = {
        "kind": "individual-person-with-significant-control",
        "name": name,
        "notified_on": "2020-01-01",
        "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
        "date_of_birth": {"month": month, "year": year},
        "links": {"self": f"/company/{company}/persons-with-significant-control/individual/{company}"},
    }
    if ceased_on:
        record["ceased_on"] = ceased_on
    return record


def _sanction(conn, uid: str, name: str, entity_type: str, birth_dates: list[dict]) -> None:
    conn.execute(
        """
        INSERT INTO sanctions (id, ftm_id, ftm_schema, subject_ftm_id, name, name_fingerprint, entity_type,
                               list_name, source, opensanctions_id, raw_properties)
        VALUES (?, ?, 'Sanction', ?, ?, ?, ?, 'Test regime', 'uk_ofsi', ?, ?)
        """,
        (uid, f"s-{uid}", f"subj-{uid}", name, normalize_name(name, is_company=entity_type != "Person"),
         entity_type, uid, json.dumps({"birth_dates": birth_dates})),
    )


def test_psc_sanction_match_uses_the_date_of_birth(tmp_path):
    db = DatabaseService(tmp_path / "sanctions.sqlite")
    conn = db.connect()
    try:
        people = {
            "00000001": ("Mr Joseph Wilson", 1977, 1, None),   # same name, born 1974 on the list: a homonym
            "00000002": ("Ahmad Taheri", 1976, 6, None),       # same name, the list gives the year only: moderate
            "00000003": ("Muhammad Ibrahim", 1993, 2, None),   # no date on the list: kept, low confidence
            "00000004": ("Xin Yu", 1988, 5, None),             # a sanctioned company, not a person
            "00000005": ("Igor Petrov", 1966, 1, None),        # same month and year: high confidence
            "00000006": ("Igor Petrov", 1966, 1, "2017-08-10"),  # the same person, a former controller
        }
        for company, (name, year, month, ceased) in people.items():
            ingest_psc_record(conn, db, company, _psc(company, name, year, month, ceased), None, "2026-10-22",
                              set(), dict.fromkeys(COUNTS, 0))
        _sanction(conn, "T1", "WILSON JOSEPH", "Person", [{"year": 1974, "month": 5, "day": 2}])
        _sanction(conn, "T2", "Ahmad TAHERI", "Person", [{"year": 1976, "month": None, "day": None}])
        _sanction(conn, "T3", "Muhammad Ibrahim", "Person", [])
        _sanction(conn, "T4", "XIN YU LLC", "Company", [])
        _sanction(conn, "T5", "Igor PETROV", "Person", [{"year": 1966, "month": 1, "day": 12}])
        conn.commit()
    finally:
        conn.close()

    matches = {m["company_number"]: m for m in EntityResolver(db).resolve_all()["sanction_matches"]}
    assert set(matches) == {"00000002", "00000003", "00000005", "00000006"}
    assert matches["00000002"]["match_type"] == "psc_name_and_birth_year"
    assert (matches["00000002"]["unodc_grade"], matches["00000002"]["confidence"]) == ("B2", "moderate")
    assert matches["00000003"]["match_type"] == "psc_name_only"
    assert (matches["00000003"]["unodc_grade"], matches["00000003"]["confidence"]) == ("B3", "low")
    assert matches["00000005"]["match_type"] == "psc_name_and_dob"
    assert (matches["00000005"]["unodc_grade"], matches["00000005"]["confidence"]) == ("A2", "high")
    assert matches["00000005"]["controller_ceased_on"] is None
    assert matches["00000006"]["controller_ceased_on"] == "2017-08-10"

    # the flag scores a former controller lower and says so
    RiskScorer(db).run_all_detections()
    conn = db.connect()
    try:
        flags = {
            r["company_number"]: (r["score_contribution"], json.loads(r["evidence"])["summary"])
            for r in conn.execute("SELECT company_number, score_contribution, evidence FROM risk_flags WHERE ft3_technique = 'FT3-SC-007'")
        }
    finally:
        conn.close()
    assert flags["00000005"][0] == 45.0
    assert flags["00000006"][0] == 27.0 and "former controller, ceased on 2017-08-10" in flags["00000006"][1]
    assert flags["00000002"][0] == 35.0 and "same year of birth" in flags["00000002"][1]
    assert flags["00000003"][0] == 25.0
