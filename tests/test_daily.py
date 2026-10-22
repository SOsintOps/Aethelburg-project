"""Daily schedule and bulk officers."""
from __future__ import annotations

from datetime import datetime

import httpx

from src.datasources import daily, officers
from src.services.api_service import CompaniesHouseApiService
from src.services.db_service import DatabaseService


def test_next_run_catches_up_and_runs_once_a_day():
    morning = datetime(2026, 10, 23, 5, 0)
    assert daily.next_run(morning, "06:00", None) == datetime(2026, 10, 23, 6, 0)
    late = datetime(2026, 10, 23, 14, 0)
    assert daily.next_run(late, "06:00", "2026-10-22") == late  # missed this morning: run now
    assert daily.next_run(late, "06:00", "2026-10-23") == datetime(2026, 10, 24, 6, 0)


def test_officers_batch_skips_failures_and_fresh_companies(tmp_path, monkeypatch):
    db = DatabaseService(tmp_path / "off.sqlite")
    conn = db.connect()
    for n, fetched in (("00000001", None), ("00000002", None), ("00000003", "2999-01-01")):
        conn.execute(
            "INSERT INTO companies (company_number, company_name, is_flagged, officers_fetched_at) VALUES (?, 'X', 1, ?)",
            (n, fetched),
        )
    conn.commit()
    conn.close()

    def handler(request: httpx.Request) -> httpx.Response:
        if "00000002" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json={"items": [{"name": "DOE, Jane", "officer_role": "director"}], "total_results": 1})

    real = CompaniesHouseApiService.__init__

    def patched(self, db_path=None, transport=None):
        real(self, db_path, transport=httpx.MockTransport(handler))
        self.settings = self.settings.model_copy(update={"api_key": "k"})

    monkeypatch.setattr(CompaniesHouseApiService, "__init__", patched)
    res = officers.fetch_officers_batch("flagged", db=db)
    assert res == {"scope": "flagged", "companies": 2, "fetched": 1, "failed": 1}
