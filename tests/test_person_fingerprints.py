"""People imported with the old fingerprint (titles kept) are renamed or merged into the new one."""
from __future__ import annotations

from src.core import normalizer
from src.etl import import_psc
from src.etl.import_psc import ingest_psc_record
from src.etl.migrate_person_fingerprints import migrate_person_fingerprints, person_ftm_id
from src.services.db_service import DatabaseService

COUNTS = ("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities")


def _psc(company: str, name: str, link: str) -> dict:
    return {
        "kind": "individual-person-with-significant-control",
        "name": name,
        "notified_on": "2020-01-01",
        "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
        "date_of_birth": {"month": 2, "year": 1980},
        "links": {"self": f"/company/{company}/persons-with-significant-control/individual/{link}"},
    }


def _ingest(conn, db, company, data, now):
    ingest_psc_record(conn, db, company, data, None, now, set(), dict.fromkeys(COUNTS, 0))


def test_old_fingerprints_are_renamed_or_merged(tmp_path, monkeypatch):
    db = DatabaseService(tmp_path / "people.sqlite")
    conn = db.connect()
    real = normalizer.normalize_name
    try:
        # before the fix: person names normalised as company names (titles kept)
        monkeypatch.setattr(import_psc, "normalize_name", lambda name, is_company=True: real(name))
        _ingest(conn, db, "00000001", _psc("00000001", "Mr John Smith", "a"), "2026-10-01")
        _ingest(conn, db, "00000002", _psc("00000002", "Mrs Anna Bianchi", "b"), "2026-10-01")
        monkeypatch.undo()
        # after the fix the same John Smith arrives again for another company
        _ingest(conn, db, "00000003", _psc("00000003", "Mr John Smith", "c"), "2026-10-22")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0] == 3
    finally:
        conn.close()

    counts = migrate_person_fingerprints(db)
    assert counts["merged"] == 1 and counts["renamed"] == 1

    conn = db.connect()
    try:
        people = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM persons")}
        assert set(people) == {"Mr John Smith", "Mrs Anna Bianchi"}
        smith = people["Mr John Smith"]
        assert smith["name_fingerprint"] == "john smith"
        assert smith["ftm_id"] == person_ftm_id("john smith", "Mr John Smith", 1980, 2)
        companies = {r[0] for r in conn.execute("SELECT company_number FROM psc_ownerships WHERE person_id = ?", (smith["id"],))}
        assert companies == {"00000001", "00000003"}
        assert people["Mrs Anna Bianchi"]["name_fingerprint"] == "anna bianchi"
        # no FtM entity or reference left on the old ids
        person_entities = conn.execute("SELECT id FROM ftm_entities WHERE schema = 'Person'").fetchall()
        assert {r[0] for r in person_entities} == {p["ftm_id"] for p in people.values()}
        ownership = conn.execute(
            "SELECT properties FROM ftm_entities WHERE id = (SELECT ftm_id FROM psc_ownerships WHERE company_number = '00000001')"
        ).fetchone()[0]
        assert smith["ftm_id"] in ownership
        orphans = conn.execute(
            "SELECT COUNT(*) FROM directorships WHERE person_id NOT IN (SELECT id FROM persons)"
        ).fetchone()[0]
        assert orphans == 0
    finally:
        conn.close()

    again = migrate_person_fingerprints(db)
    assert again["merged"] == 0 and again["renamed"] == 0
