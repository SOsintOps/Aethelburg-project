"""Change history: what an update changed in a company already loaded, and nothing on the first load."""
from __future__ import annotations

from src.etl.company_changes import list_changes
from src.etl.import_companies import parse_ch_company_row, upsert_company_record
from src.etl.import_psc import ingest_psc_record
from src.services.api_service import CompaniesHouseApiService
from src.services.ch_mapping import profile_to_record
from src.services.db_service import DatabaseService

NUMBER = "12345678"
ROW = {
    "CompanyName": "AETHELBURG TEST LIMITED",
    " CompanyNumber": NUMBER,
    "RegAddress.AddressLine1": "71-75 SHELTON STREET",
    "RegAddress.PostTown": "LONDON",
    "RegAddress.PostCode": "WC2H 9JQ",
    "RegAddress.Country": "UNITED KINGDOM",
    "CompanyStatus": "Active",
    "IncorporationDate": "01/02/2024",
    "SICCode.SicText_1": "99999 - Dormant Company",
}


def _db(tmp_path):
    db = DatabaseService(tmp_path / "changes.sqlite")
    conn = db.connect()
    return db, conn, db.register_data_source("Companies House - Basic Company Data", "ch_companies", "2026-10-01", conn=conn)


def test_first_load_and_identical_reimport_record_nothing(tmp_path):
    db, conn, source_id = _db(tmp_path)
    try:
        upsert_company_record(conn, db, parse_ch_company_row(ROW), source_id)
        upsert_company_record(conn, db, parse_ch_company_row(ROW), source_id)
        assert list_changes(conn) == []
    finally:
        conn.close()


def test_reimport_records_address_and_status_with_source(tmp_path):
    db, conn, source_id = _db(tmp_path)
    try:
        upsert_company_record(conn, db, parse_ch_company_row(ROW), source_id)
        moved = {**ROW, "RegAddress.AddressLine1": "20-22 WENLOCK ROAD", "RegAddress.PostCode": "N1 7GU",
                 "CompanyStatus": "Dissolved", "DissolutionDate": "05/10/2026"}
        upsert_company_record(conn, db, parse_ch_company_row(moved), source_id)
        changes = {c["change_type"]: c for c in list_changes(conn, company_number=NUMBER)}
        assert set(changes) == {"ADDRESS_CHANGED", "STATUS_CHANGED", "DISSOLUTION_DATE_CHANGED"}
        addr = changes["ADDRESS_CHANGED"]
        assert "71-75 SHELTON STREET" in addr["old_value"] and "20-22 WENLOCK ROAD" in addr["new_value"]
        assert addr["source"] == "ch_companies 2026-10-01"
        assert changes["STATUS_CHANGED"]["effective_date"] == "2026-10-05"

        conn.commit()
        timeline = db.get_company_dossier(NUMBER)["timeline"]
        assert any(ev["event_type"] == "ADDRESS_CHANGED" for ev in timeline)
    finally:
        conn.close()


def test_api_profile_with_other_spelling_is_not_a_change(tmp_path):
    """The bulk product writes upper case and leaves county empty; the API does neither."""
    db, conn, source_id = _db(tmp_path)
    try:
        upsert_company_record(conn, db, parse_ch_company_row(ROW), source_id)
        profile = {
            "company_number": NUMBER,
            "company_name": "Aethelburg Test Limited",
            "company_status": "active",
            "type": "ltd",
            "registered_office_address": {"address_line_1": "71-75 Shelton Street", "locality": "London",
                                          "region": "Greater London", "country": "England", "postal_code": "WC2H 9JQ"},
            "sic_codes": ["99999"],
        }
        upsert_company_record(conn, db, profile_to_record(profile), source_id)
        assert list_changes(conn) == []
    finally:
        conn.close()


def _psc(name: str, ceased_on: str | None = None) -> dict:
    return {
        "kind": "individual-person-with-significant-control",
        "name": name,
        "notified_on": "2024-02-01",
        "ceased_on": ceased_on,
        "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
        "date_of_birth": {"month": 1, "year": 1980},
        "links": {"self": f"/company/{NUMBER}/persons-with-significant-control/individual/{name.split()[-1]}"},
    }


def test_psc_added_or_ceased_after_the_first_load(tmp_path):
    db, conn, source_id = _db(tmp_path)
    counts = dict.fromkeys(("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities"), 0)
    existing: set[str] = set()
    try:
        upsert_company_record(conn, db, parse_ch_company_row(ROW), source_id)
        existing.add(NUMBER)
        first = "2026-10-01T00:00:00+00:00"
        for name in ("Anna First", "Bruno Second"):  # two statements in the first load: no change
            ingest_psc_record(conn, db, NUMBER, _psc(name), source_id, first, existing, counts)
        assert list_changes(conn) == []

        later = "2026-10-22T00:00:00+00:00"
        ingest_psc_record(conn, db, NUMBER, _psc("Anna First", ceased_on="2026-10-20"), source_id, later, existing, counts)
        ingest_psc_record(conn, db, NUMBER, _psc("Bruno Second"), source_id, later, existing, counts)
        ingest_psc_record(conn, db, NUMBER, _psc("Carla Third"), source_id, later, existing, counts)
        got = sorted((c["change_type"], c["old_value"] or c["new_value"]) for c in list_changes(conn))
        assert got == [("PSC_ADDED", "Carla Third"), ("PSC_CEASED", "Anna First")]
        updated = conn.execute("SELECT created_at FROM psc_ownerships WHERE ceased_on IS NOT NULL").fetchone()
        assert updated[0] == first  # an update keeps the first-seen time
    finally:
        conn.close()


def _officer(name: str, resigned_on: str | None = None) -> dict:
    return {
        "name": name,
        "officer_role": "director",
        "appointed_on": "2024-02-01",
        "resigned_on": resigned_on,
        "date_of_birth": {"month": 1, "year": 1980},
        "links": {"officer": {"appointments": f"/officers/{name.split(',')[0].lower()}/appointments"}},
    }


def test_officer_appointed_or_resigned_after_the_first_fetch(tmp_path):
    db, conn, source_id = _db(tmp_path)
    try:
        upsert_company_record(conn, db, parse_ch_company_row(ROW), source_id)
        conn.commit()
    finally:
        conn.close()
    svc = CompaniesHouseApiService(tmp_path / "changes.sqlite")
    svc.persist_officers(NUMBER, [_officer("ROSSI, Mario")])
    svc.persist_officers(NUMBER, [_officer("ROSSI, Mario", resigned_on="2026-10-01"), _officer("BIANCHI, Luca")])
    conn = db.connect()
    try:
        got = sorted((c["change_type"], c["effective_date"]) for c in list_changes(conn))
        assert got == [("OFFICER_APPOINTED", "2024-02-01"), ("OFFICER_RESIGNED", "2026-10-01")]
    finally:
        conn.close()
