"""Light index and subset selection on small synthetic bulk files."""
from __future__ import annotations

import csv
import json
from datetime import date

from src.datasources.subset import (
    SubsetConfig,
    _is_uk,
    _nationality_set,
    build_company_index,
    nationality_match,
    select_subset,
)
from src.services.db_service import DatabaseService

HEADER = [
    "CompanyName", " CompanyNumber", "RegAddress.AddressLine1", " RegAddress.AddressLine2", "RegAddress.PostTown",
    "RegAddress.PostCode", "CompanyCategory", "CompanyStatus", "IncorporationDate",
]
RECENT = date.today().replace(year=date.today().year - 1).strftime("%d/%m/%Y")


def _companies(tmp_path):
    rows = [
        # three companies at one formation-agent address
        ["AGENT ONE LTD", "00000001", "1 HUB STREET", "", "LONDON", "EC1V 2NX", "Private Limited Company", "Active", "01/01/2010"],
        ["AGENT TWO LTD", "00000002", "1 HUB STREET", "", "LONDON", "EC1V 2NX", "Private Limited Company", "Active", "01/01/2010"],
        ["AGENT THREE LTD", "00000003", "1 HUB STREET", "", "LONDON", "EC1V 2NX", "Private Limited Company", "Dissolved", "01/01/2010"],
        ["NEW START LTD", "00000004", "2 OTHER ROAD", "", "LEEDS", "LS1 1AA", "Private Limited Company", "Active", RECENT],
        ["OFFSHORE OWNED LTD", "00000005", "3 QUIET LANE", "", "BATH", "BA1 1AA", "Private Limited Company", "Active", "01/01/2000"],
        ["SISTER LTD", "00000006", "4 QUIET LANE", "", "BATH", "BA1 1AB", "Private Limited Company", "Active", "01/01/2000"],
        ["PLAIN LTD", "00000007", "5 QUIET LANE", "", "BATH", "BA1 1AC", "Private Limited Company", "Active", "01/01/2000"],
    ]
    path = tmp_path / "companies.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def _psc(tmp_path):
    person = {
        "kind": "individual-person-with-significant-control",
        "name": "Mr Shared Owner",
        "date_of_birth": {"year": 1970, "month": 5},
    }
    lines = [
        {"company_number": "00000005", "data": {
            "kind": "corporate-entity-person-with-significant-control", "name": "BVI HOLDCO LTD",
            "identification": {"country_registered": "British Virgin Islands"}}},
        {"company_number": "00000005", "data": person},
        {"company_number": "00000006", "data": person},  # one hop from 00000005
        {"company_number": "00000007", "data": {
            "kind": "corporate-entity-person-with-significant-control", "name": "UK PARENT LTD",
            "identification": {"country_registered": "England And Wales"}}},
        {"company_number": "00000004", "data": {"kind": "super-secure-person-with-significant-control"}},
    ]
    path = tmp_path / "psc.txt"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


def test_index_and_subset(tmp_path):
    db = DatabaseService(tmp_path / "subset.sqlite")
    conn = db.connect()
    try:
        assert build_company_index(conn, _companies(tmp_path), "2026-10-01") == 7
        cfg = SubsetConfig(mass_address_min_companies=3, recent_years=3, broad_criteria_mode="or", psc_nationalities=[])
        counts = select_subset(conn, cfg, _psc(tmp_path), None, None)
        members = dict(conn.execute("SELECT company_number, reasons FROM subset_members"))
    finally:
        conn.close()

    assert members["00000005"] == "offshore_psc"
    assert members["00000006"] == "psc_one_hop"
    assert "00000007" not in members  # UK corporate parent is not a risk link
    assert set(members["00000004"].split(",")) == {"recent", "super_secure_psc"}
    assert "mass_address" in members["00000001"] and "mass_address" in members["00000002"]
    assert "00000003" not in members  # dissolved: broad criteria apply to live companies only
    assert counts["total"] == len(members) == 5


def test_index_resumes_after_interruption(tmp_path):
    db = DatabaseService(tmp_path / "resume.sqlite")
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO ingest_runs (id, task, source, source_version, file, status, last_row, rows_read, rows_written) "
            "VALUES ('r1', 'company_index', 'ch_companies', '2026-10-01', ?, 'interrupted', 5, 5, 5)",
            (str(tmp_path / "companies.csv"),),
        )
        conn.commit()
        build_company_index(conn, _companies(tmp_path), "2026-10-01")
        assert conn.execute("SELECT COUNT(*) FROM company_index").fetchone()[0] == 2  # rows 6-7 only
        run = conn.execute("SELECT status, rows_read FROM ingest_runs WHERE id = 'r1'").fetchone()
        assert tuple(run) == ("completed", 7)
    finally:
        conn.close()


def test_uk_jurisdiction_detection():
    for text in ("England And Wales", "United Kingdom", "Companies House", "Scotland", "UK"):
        assert _is_uk(text), text
    for text in ("Ukraine", "British Virgin Islands", "Cyprus", "Delaware, USA"):
        assert not _is_uk(text), text


def test_and_mode_and_nationality(tmp_path):
    # a recent company at the mass address, and an Italian PSC on an old company
    companies = _companies(tmp_path)
    with companies.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(
            ["FRESH AGENT LTD", "00000008", "1 HUB STREET", "", "LONDON", "EC1V 2NX", "Private Limited Company", "Active", RECENT]
        )
    psc = tmp_path / "psc_it.txt"
    psc.write_text(json.dumps({"company_number": "00000007", "data": {
        "kind": "individual-person-with-significant-control", "name": "Sig. Mario Rossi",
        "nationality": "British,Italian", "date_of_birth": {"year": 1960, "month": 1}}}) + "\n", encoding="utf-8")

    db = DatabaseService(tmp_path / "and.sqlite")
    conn = db.connect()
    try:
        build_company_index(conn, companies, "2026-10-01")
        select_subset(conn, SubsetConfig(mass_address_min_companies=3, risk_links=False), psc, None, None)
        members = dict(conn.execute("SELECT company_number, reasons FROM subset_members"))
    finally:
        conn.close()

    assert members == {"00000008": "mass_address,recent", "00000007": "nationality_italian"}


def test_nationality_spellings():
    italian = _nationality_set(["Italian"])
    for text in ("Italian", "british,italian", "Italian,", "Italy", " ITALIAN "):
        assert nationality_match(text, italian) == "italian", text
    for text in ("Italo-American", "British", "", None):
        assert nationality_match(text, italian) is None, text
