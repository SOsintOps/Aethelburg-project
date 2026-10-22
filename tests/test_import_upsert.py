"""Re-importing a company updates registry fields without wiping analysis results."""
from __future__ import annotations

from src.etl.import_companies import parse_ch_company_row, upsert_company_record
from src.services.db_service import DatabaseService

ROW = {
    "CompanyName": "AETHELBURG TEST LIMITED",
    " CompanyNumber": "12345678",
    "RegAddress.AddressLine1": "71-75 SHELTON STREET",
    "RegAddress.PostTown": "LONDON",
    "RegAddress.PostCode": "WC2H 9JQ",
    "CompanyStatus": "Active",
    "IncorporationDate": "01/02/2024",
}


def test_reimport_preserves_analysis_fields(tmp_path):
    db = DatabaseService(tmp_path / "upsert.sqlite")
    conn = db.connect()
    try:
        source_id = db.register_data_source("test", "test", conn=conn)
        upsert_company_record(conn, db, parse_ch_company_row(ROW), source_id)
        conn.execute(
            "UPDATE companies SET risk_score = 77, is_flagged = 1, ft3_techniques = 'FT3-SC-001', "
            "officers_fetched_at = '2026-10-22' WHERE company_number = '12345678'"
        )

        upsert_company_record(conn, db, parse_ch_company_row({**ROW, "CompanyStatus": "Dissolved"}), source_id)
        row = conn.execute("SELECT * FROM companies WHERE company_number = '12345678'").fetchone()
        assert row["company_status"] == "Dissolved"
        assert row["risk_score"] == 77 and row["is_flagged"] == 1
        assert row["ft3_techniques"] == "FT3-SC-001" and row["officers_fetched_at"] == "2026-10-22"

        count = conn.execute("SELECT company_count FROM addresses").fetchone()["company_count"]
        assert count == 1
    finally:
        conn.close()
