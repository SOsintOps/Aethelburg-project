"""Companies House REST API client with local persistence (ADR-013).

`refresh_company()` downloads a company's profile, every officer appointment and every PSC
statement, and writes them with the same code paths as the bulk importers, so a company that
is not in the local database yet is created first and repeated refreshes never duplicate rows.

Rate limit: 600 requests per 5 minutes per key (shared by one service instance).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from config.database import get_sqlite_connection
from config.settings import get_settings
from src.core.ftm import directorship_to_ftm, make_ftm_id, person_to_ftm
from src.core.logging import get_logger
from src.core.normalizer import normalize_name
from src.etl.import_companies import upsert_company_record
from src.etl.import_psc import ingest_psc_record
from src.services.ch_mapping import profile_to_record
from src.services.db_service import DatabaseService

log = get_logger(__name__)

_PAGE_SIZE = 100
_MAX_RETRY_AFTER = 60.0


class CompaniesHouseApiError(Exception):
    """A Companies House request failed; `status` is the HTTP status (0 = network error)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class CompaniesHouseApiService:
    """Client for the Companies House REST API with local database persistence."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = get_settings().ch_api
        self.db = DatabaseService(db_path)
        self.db_path = self.db.db_path
        self._transport = transport
        self._request_timestamps: list[float] = []

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.api_key)

    # ------------------------------------------------------------------ #
    # HTTP                                                               #
    # ------------------------------------------------------------------ #

    async def _throttle(self) -> None:
        now = time.monotonic()
        window = float(self.settings.rate_window)
        self._request_timestamps = [t for t in self._request_timestamps if now - t < window]
        if len(self._request_timestamps) >= self.settings.rate_limit:
            sleep_for = window - (now - self._request_timestamps[0]) + 0.1
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        self._request_timestamps.append(time.monotonic())

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.settings.api_key:
            raise CompaniesHouseApiError(
                401,
                "No Companies House API key configured. Store one with: "
                "python -m keyring set aethelburg ch_api_key",
            )
        url = f"{self.settings.base_url}{path}"
        for attempt in range(2):
            await self._throttle()
            try:
                async with httpx.AsyncClient(timeout=20.0, transport=self._transport) as client:
                    resp = await client.get(url, params=params, auth=(self.settings.api_key, ""))
            except httpx.HTTPError as exc:
                raise CompaniesHouseApiError(0, f"Companies House unreachable: {exc}") from exc

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 and attempt == 0:
                wait = _retry_after_seconds(resp)
                log.warning("ch_api_rate_limited", path=path, retry_after=wait)
                await asyncio.sleep(wait)
                continue
            log.warning("ch_api_http_error", path=path, status=resp.status_code)
            raise CompaniesHouseApiError(resp.status_code, _error_message(resp.status_code, path))
        raise CompaniesHouseApiError(429, "Companies House rate limit still exceeded after waiting.")

    async def _get_all_items(self, path: str) -> list[dict[str, Any]]:
        """Follow `start_index` pagination until `total_results` items are collected."""
        items: list[dict[str, Any]] = []
        while True:
            page = await self._get(path, {"items_per_page": _PAGE_SIZE, "start_index": len(items)})
            batch = page.get("items") or []
            items.extend(batch)
            total = int(page.get("total_results") or 0)
            if not batch or len(items) >= total:
                return items

    # ------------------------------------------------------------------ #
    # RESOURCES                                                          #
    # ------------------------------------------------------------------ #

    async def fetch_company_profile(self, company_number: str) -> dict[str, Any]:
        """Download `/company/{n}` and upsert it (creates the company if it is not stored yet)."""
        number = _clean_number(company_number)
        profile = await self._get(f"/company/{number}")
        rec = profile_to_record(profile)
        if rec is None:
            raise CompaniesHouseApiError(502, f"Unexpected company profile for {number}")
        conn = self.db.connect()
        try:
            upsert_company_record(conn, self.db, rec, self._source_id(conn))
            conn.commit()
        finally:
            conn.close()
        return rec

    async def fetch_company_officers(self, company_number: str) -> list[dict[str, Any]]:
        """Download every officer appointment of a stored company and upsert it."""
        number = _clean_number(company_number)
        items = await self._get_all_items(f"/company/{number}/officers")
        return self._persist_officers(number, items)

    async def fetch_company_psc(self, company_number: str) -> dict[str, int]:
        """Download every PSC statement of a company and upsert it via the bulk PSC code path."""
        number = _clean_number(company_number)
        try:
            items = await self._get_all_items(f"/company/{number}/persons-with-significant-control")
        except CompaniesHouseApiError as exc:
            if exc.status == 404:  # companies exempt from PSC (e.g. listed PLCs) return 404
                return {"psc_ownerships": 0}
            raise
        counts = dict.fromkeys(
            ("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities"), 0
        )
        conn = self.db.connect()
        try:
            source_id = self._source_id(conn)
            now = _now()
            for item in items:
                ingest_psc_record(conn, self.db, number, item, source_id, now, {number}, counts)
            conn.commit()
        finally:
            conn.close()
        return counts

    async def refresh_company(self, company_number: str) -> dict[str, Any]:
        """Profile + officers + PSC for one company; returns a summary of what was written."""
        number = _clean_number(company_number)
        profile = await self.fetch_company_profile(number)
        officers = await self.fetch_company_officers(number)
        psc = await self.fetch_company_psc(number)
        return {
            "company_number": number,
            "company_name": profile["company_name"],
            "company_status": profile.get("company_status"),
            "officers": len(officers),
            "active_officers": sum(1 for o in officers if o["is_active"]),
            "psc_statements": psc["psc_ownerships"],
            "fetched_at": _now(),
        }

    # ------------------------------------------------------------------ #
    # PERSISTENCE                                                        #
    # ------------------------------------------------------------------ #

    def _source_id(self, conn: Any) -> str:
        return self.db.register_data_source(
            source_name="Companies House REST API",
            source_type="ch_api",
            source_version=datetime.now(UTC).strftime("%Y-%m-%d"),
            source_url=self.settings.base_url,
            notes="On-demand company profile, officers and PSC",
            conn=conn,
        )

    def _persist_officers(self, company_number: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conn = get_sqlite_connection(self.db_path)
        persisted: list[dict[str, Any]] = []
        now = _now()
        company_ftm_id = make_ftm_id("Company", "gb", company_number)
        try:
            source_id = self._source_id(conn)
            for item in items:
                raw_name = item.get("name") or "Unknown Officer"
                fp = normalize_name(raw_name)
                dob = item.get("date_of_birth") or {}
                role = item.get("officer_role") or "director"
                appointed_on = item.get("appointed_on")
                resigned_on = item.get("resigned_on")
                is_active = 0 if resigned_on else 1
                officer_link = ((item.get("links") or {}).get("officer") or {}).get("appointments") or ""
                api_person_id = officer_link.strip("/").split("/")[1] if officer_link.count("/") >= 2 else None

                p_rec = {
                    "name": raw_name,
                    "name_fingerprint": fp,
                    "nationality": item.get("nationality"),
                    "country_of_residence": item.get("country_of_residence"),
                    "dob_month": dob.get("month"),
                    "dob_year": dob.get("year"),
                }
                p_ftm = person_to_ftm(p_rec)
                person = conn.execute("SELECT id FROM persons WHERE ftm_id = ?", (p_ftm["id"],)).fetchone()
                if person:
                    person_id = person["id"]
                else:
                    person_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO persons
                            (id, ftm_id, ftm_schema, name, name_fingerprint, nationality, country_of_residence,
                             dob_month, dob_year, source_id, created_at, updated_at)
                        VALUES (?, ?, 'Person', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (person_id, p_ftm["id"], raw_name, fp, p_rec["nationality"], p_rec["country_of_residence"],
                         p_rec["dob_month"], p_rec["dob_year"], source_id, now, now),
                    )
                    self.db.upsert_ftm_entity(p_ftm, source_id=source_id, conn=conn)

                # Deterministic id: refreshing the same appointment updates it instead of duplicating it
                dir_id = str(uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    f"dir-api:{company_number}:{api_person_id or p_ftm['id']}:{role}:{appointed_on or ''}",
                ))
                dir_ftm = directorship_to_ftm(
                    {"id": dir_id, "company_number": company_number, "officer_role": role,
                     "appointed_on": appointed_on, "resigned_on": resigned_on},
                    director_ftm_id=p_ftm["id"],
                    company_ftm_id=company_ftm_id,
                )
                conn.execute(
                    """
                    INSERT INTO directorships
                        (id, ftm_id, ftm_schema, company_number, person_id, officer_role, appointed_on,
                         resigned_on, is_active, occupation, nationality, country_of_residence, api_person_id,
                         source_id, fetched_via, created_at, updated_at)
                    VALUES (?, ?, 'Directorship', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'api', ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        resigned_on = excluded.resigned_on,
                        is_active = excluded.is_active,
                        occupation = excluded.occupation,
                        updated_at = excluded.updated_at
                    """,
                    (dir_id, dir_ftm["id"], company_number, person_id, role, appointed_on, resigned_on,
                     is_active, item.get("occupation"), p_rec["nationality"], p_rec["country_of_residence"],
                     api_person_id, source_id, now, now),
                )
                self.db.upsert_ftm_entity(dir_ftm, source_id=source_id, conn=conn)
                persisted.append(
                    {
                        "id": dir_id,
                        "company_number": company_number,
                        "person_id": person_id,
                        "person_name": raw_name,
                        "officer_role": role,
                        "appointed_on": appointed_on,
                        "resigned_on": resigned_on,
                        "is_active": bool(is_active),
                    }
                )
            conn.execute(
                "UPDATE companies SET officers_fetched_at = ?, updated_at = ? WHERE company_number = ?",
                (now, now, company_number),
            )
            conn.commit()
            return persisted
        finally:
            conn.close()


def _clean_number(company_number: str) -> str:
    number = (company_number or "").strip().upper()
    if not number.isalnum() or not 1 <= len(number) <= 8:
        raise CompaniesHouseApiError(400, f"Invalid company number: {company_number!r}")
    return number.zfill(8) if number.isdigit() else number


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _retry_after_seconds(resp: httpx.Response) -> float:
    try:
        return min(_MAX_RETRY_AFTER, max(1.0, float(resp.headers.get("Retry-After", "10"))))
    except ValueError:
        return 10.0


def _error_message(status: int, path: str) -> str:
    if status == 401:
        return "Companies House rejected the API key (401). Check the key stored in the OS keyring."
    if status == 404:
        return f"Not found on Companies House: {path}"
    if status == 429:
        return "Companies House rate limit exceeded (600 requests per 5 minutes)."
    return f"Companies House returned HTTP {status} for {path}"
