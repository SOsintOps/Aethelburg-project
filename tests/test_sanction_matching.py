"""People are matched to sanctions on name and date of birth, not on name alone."""
from __future__ import annotations

import json

from src.core.normalizer import normalize_name
from src.etl.import_psc import ingest_psc_record
from src.etl.import_sanctions import parse_birth_date
from src.intelligence.entity_resolver import EntityResolver, compare_birth_dates
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
    assert compare_birth_dates(dates, 1978, 11) == "match"
    assert compare_birth_dates(dates, 1977, 2) == "conflict"
    assert compare_birth_dates(dates, 1980, 1) == "conflict"
    assert compare_birth_dates([], 1977, 1) == "unknown"
    assert compare_birth_dates(dates, None, None) == "unknown"


def _psc(company: str, name: str, year: int, month: int) -> dict:
    return {
        "kind": "individual-person-with-significant-control",
        "name": name,
        "notified_on": "2020-01-01",
        "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
        "date_of_birth": {"month": month, "year": year},
        "links": {"self": f"/company/{company}/persons-with-significant-control/individual/{company}"},
    }


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
            "00000001": ("Mr Joseph Wilson", 1977, 1),  # same name, born 1974 on the list: a homonym
            "00000002": ("Ahmad Taheri", 1976, 6),      # same name and month/year: kept, high confidence
            "00000003": ("Muhammad Ibrahim", 1993, 2),  # no date on the list: kept, low confidence
            "00000004": ("Xin Yu", 1988, 5),            # a sanctioned company, not a person
        }
        for company, (name, year, month) in people.items():
            ingest_psc_record(conn, db, company, _psc(company, name, year, month), None, "2026-10-22", set(),
                              dict.fromkeys(COUNTS, 0))
        _sanction(conn, "T1", "WILSON JOSEPH", "Person", [{"year": 1974, "month": 5, "day": 2}])
        _sanction(conn, "T2", "Ahmad TAHERI", "Person", [{"year": 1976, "month": None, "day": None}])
        _sanction(conn, "T3", "Muhammad Ibrahim", "Person", [])
        _sanction(conn, "T4", "XIN YU LLC", "Company", [])
        conn.commit()
    finally:
        conn.close()

    matches = {m["company_number"]: m for m in EntityResolver(db).resolve_all()["sanction_matches"]}
    assert set(matches) == {"00000002", "00000003"}
    assert matches["00000002"]["match_type"] == "psc_name_and_dob"
    assert (matches["00000002"]["unodc_grade"], matches["00000002"]["confidence"]) == ("A2", "high")
    assert matches["00000003"]["match_type"] == "psc_name_only"
    assert (matches["00000003"]["unodc_grade"], matches["00000003"]["confidence"]) == ("B3", "low")
