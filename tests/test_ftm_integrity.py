"""PSC ingestion must not duplicate controllers and every FtM link must point at a stored entity."""
from __future__ import annotations

import json

from src.etl.import_companies import parse_ch_company_row, upsert_company_record
from src.etl.import_psc import ingest_psc_record
from src.services.db_service import DatabaseService

INDIVIDUAL = {
    "kind": "individual-person-with-significant-control",
    "name": "Mr John Example",
    "name_elements": {"title": "Mr", "forename": "John", "surname": "Example"},
    "date_of_birth": {"month": 5, "year": 1970},
    "nationality": "British",
    "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
    "notified_on": "2020-01-01",
    "address": {"postal_code": "WC2H 9JQ"},
}
CORPORATE = {
    "kind": "corporate-entity-person-with-significant-control",
    "name": "EXAMPLE HOLDINGS LTD",
    "identification": {"country_registered": "British Virgin Islands", "registration_number": "123"},
    "natures_of_control": ["ownership-of-shares-25-to-50-percent"],
    "notified_on": "2020-01-01",
    "address": {"country": "British Virgin Islands"},
}


def _company(conn, db, source_id, number):
    row = {"CompanyName": f"TEST {number} LIMITED", " CompanyNumber": number, "RegAddress.PostCode": "WC2H 9JQ"}
    upsert_company_record(conn, db, parse_ch_company_row(row), source_id)


def test_psc_controllers_are_not_duplicated_and_links_resolve(tmp_path):
    db = DatabaseService(tmp_path / "ftm.sqlite")
    conn = db.connect()
    try:
        source_id = db.register_data_source("test", "test", conn=conn)
        existing: set[str] = set()
        counts = dict.fromkeys(
            ("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities"), 0
        )
        for number in ("00000001", "00000002"):
            _company(conn, db, source_id, number)
            existing.add(number)
            for i, data in enumerate((INDIVIDUAL, CORPORATE)):
                item = {**data, "links": {"self": f"/company/{number}/psc/{i}"}}
                ingest_psc_record(conn, db, number, item, source_id, "2026-10-22", existing, counts)
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM legal_entities").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM psc_ownerships").fetchone()[0] == 4

        ids = {r[0] for r in conn.execute("SELECT id FROM ftm_entities")}
        dangling = []
        for props, schema in conn.execute(
            "SELECT properties, schema FROM ftm_entities WHERE schema IN ('Ownership', 'Directorship')"
        ):
            for key in ("asset", "owner", "organization", "director"):
                dangling += [(schema, key, v) for v in json.loads(props).get(key, []) if v not in ids]
        assert dangling == []
    finally:
        conn.close()
