"""Companies House REST client: pagination, idempotent refresh, explicit errors, unknown companies."""
from __future__ import annotations

import httpx
import pytest

from src.services.api_service import CompaniesHouseApiError, CompaniesHouseApiService

NUMBER = "09999999"
PROFILE = {
    "company_number": NUMBER,
    "company_name": "NOT YET LOCAL LIMITED",
    "company_status": "active",
    "company_status_detail": "active-proposal-to-strike-off",
    "type": "ltd",
    "date_of_creation": "2024-03-01",
    "registered_office_address": {"address_line_1": "71-75 Shelton Street", "locality": "London", "postal_code": "WC2H 9JQ"},
    "accounts": {"last_accounts": {"type": "dormant", "made_up_to": "2025-03-31"}},
    "sic_codes": ["99999"],
}


def _officer(i: int) -> dict:
    return {
        "name": f"EXAMPLE, Person {i}",
        "officer_role": "director",
        "appointed_on": "2024-03-01",
        "date_of_birth": {"month": 1, "year": 1980},
        "links": {"officer": {"appointments": f"/officers/off{i}/appointments"}},
    }


OFFICERS = [_officer(i) for i in range(52)]
PSC = [
    {
        "kind": "corporate-entity-person-with-significant-control",
        "name": "OFFSHORE HOLDINGS LTD",
        "identification": {"country_registered": "British Virgin Islands"},
        "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
        "notified_on": "2024-03-01",
        "links": {"self": f"/company/{NUMBER}/persons-with-significant-control/corporate-entity/abc"},
    }
]


def _paged(items: list[dict], request: httpx.Request) -> httpx.Response:
    start = int(request.url.params.get("start_index", 0))
    size = min(int(request.url.params.get("items_per_page", 35)), 35)  # API caps the page size
    return httpx.Response(200, json={"items": items[start:start + size], "total_results": len(items)})


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == f"/company/{NUMBER}":
        return httpx.Response(200, json=PROFILE)
    if path.endswith("/officers"):
        return _paged(OFFICERS, request)
    if path.endswith("/persons-with-significant-control"):
        return _paged(PSC, request)
    return httpx.Response(404, json={"errors": [{"error": "company-profile-not-found"}]})


def _service(tmp_path, handler=_handler, key="test-key") -> CompaniesHouseApiService:
    svc = CompaniesHouseApiService(tmp_path / "ch.sqlite", transport=httpx.MockTransport(handler))
    svc.settings = svc.settings.model_copy(update={"api_key": key})
    return svc


async def test_refresh_creates_company_and_reads_every_page(tmp_path):
    svc = _service(tmp_path)
    summary = await svc.refresh_company("9999999")  # leading zero restored
    assert summary["officers"] == 52 and summary["psc_statements"] == 1

    conn = svc.db.connect()
    try:
        row = conn.execute("SELECT * FROM companies WHERE company_number = ?", (NUMBER,)).fetchone()
        assert row["company_status"] == "Active - Proposal to Strike off"
        assert row["accounts_account_category"] == "DORMANT"
        assert row["officers_fetched_at"]
        assert conn.execute("SELECT COUNT(*) FROM directorships WHERE fetched_via = 'api'").fetchone()[0] == 52
    finally:
        conn.close()


async def test_second_refresh_does_not_duplicate(tmp_path):
    svc = _service(tmp_path)
    await svc.refresh_company(NUMBER)
    await svc.refresh_company(NUMBER)
    conn = svc.db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM directorships WHERE fetched_via = 'api'").fetchone()[0] == 52
        assert conn.execute("SELECT COUNT(*) FROM psc_ownerships").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM legal_entities").fetchone()[0] == 1
    finally:
        conn.close()


async def test_errors_are_explicit(tmp_path):
    with pytest.raises(CompaniesHouseApiError) as missing_key:
        await _service(tmp_path, key="").refresh_company(NUMBER)
    assert missing_key.value.status == 401 and "keyring" in missing_key.value.message

    rejected = _service(tmp_path, handler=lambda r: httpx.Response(401, json={}))
    with pytest.raises(CompaniesHouseApiError) as bad_key:
        await rejected.refresh_company(NUMBER)
    assert bad_key.value.status == 401

    with pytest.raises(CompaniesHouseApiError) as not_found:
        await _service(tmp_path).refresh_company("00000000")
    assert not_found.value.status == 404

    with pytest.raises(CompaniesHouseApiError) as invalid:
        await _service(tmp_path).refresh_company("../etc")
    assert invalid.value.status == 400


async def test_rate_limit_waits_and_retries(tmp_path, monkeypatch):
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("src.services.api_service.asyncio.sleep", fake_sleep)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return _handler(request)

    await _service(tmp_path, handler=handler).fetch_company_profile(NUMBER)
    assert waits == [7.0]


async def test_officer_search_keeps_only_full_name_matches(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/officers":
            return httpx.Response(200, json={"total_results": 3, "items": [
                {"title": "Mario ROSSI", "links": {"self": "/officers/abc/appointments"}, "appointment_count": 2},
                {"title": "Mario BIANCHI", "links": {"self": "/officers/def/appointments"}},
                {"title": "ROSSI MARIO LIMITED", "links": {"self": "/officers/ghi/appointments"}},
            ]})
        return httpx.Response(200, json={"total_results": 1, "items": [
            {"officer_role": "director", "appointed_on": "2020-01-01",
             "appointed_to": {"company_number": "12345678", "company_name": "X LTD", "company_status": "active"}}]})

    svc = _service(tmp_path, handler=handler)
    found = await svc.search_officers("rossi mario")
    assert [f["officer_id"] for f in found] == ["abc", "ghi"]
    appointments = (await svc.officer_appointments("abc"))["appointments"]
    assert appointments[0]["company_number"] == "12345678"
