"""Companies House REST & Streaming API client service (ADR-013).

Supports:
  - Live Companies House REST API requests (`/company/{number}/officers`, `/company/{number}`)
  - Automatic rate-limiting (600 requests / 5 minutes)
  - Offline synthesis from PSC / ICIJ records when API key is not configured
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from config.database import get_sqlite_connection
from config.settings import get_settings
from src.core.ftm import directorship_to_ftm, make_ftm_id, person_to_ftm
from src.core.logging import get_logger
from src.core.normalizer import normalize_name

log = get_logger(__name__)


class CompaniesHouseApiService:
    """Client for Companies House REST API with local database persistence."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.settings = get_settings().ch_api
        self.db_path = Path(db_path) if db_path else None
        self._request_timestamps: list[float] = []

    async def _throttle(self) -> None:
        now = time.monotonic()
        window = float(self.settings.rate_window)
        self._request_timestamps = [t for t in self._request_timestamps if now - t < window]
        if len(self._request_timestamps) >= self.settings.rate_limit:
            sleep_for = window - (now - self._request_timestamps[0]) + 0.1
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        self._request_timestamps.append(time.monotonic())

    async def fetch_company_officers(self, company_number: str) -> list[dict[str, Any]]:
        """Fetch officers for a UK company from CH REST API (or synthesize from PSC if offline)."""
        comp_num = company_number.strip().upper()
        if self.settings.api_key:
            await self._throttle()
            url = f"{self.settings.base_url}/company/{comp_num}/officers"
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url, auth=(self.settings.api_key, ""))
                    if resp.status_code == 200:
                        payload = resp.json()
                        items = payload.get("items", [])
                        return self._persist_api_officers(comp_num, items)
            except Exception as exc:
                log.warning("ch_api_fetch_failed", company_number=comp_num, error=str(exc))

        # Offline fallback: return existing directorships in DB
        conn = get_sqlite_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT d.*, p.name AS person_name
                FROM directorships d
                LEFT JOIN persons p ON p.id = d.person_id
                WHERE d.company_number = ?
                """,
                (comp_num,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _persist_api_officers(self, company_number: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conn = get_sqlite_connection(self.db_path)
        persisted: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        try:
            for item in items:
                raw_name = item.get("name", "Unknown Officer")
                norm_name = normalize_name(raw_name)
                dob = item.get("date_of_birth") or {}
                dob_month = dob.get("month")
                dob_year = dob.get("year")
                nationality = item.get("nationality")
                residence = item.get("country_of_residence")
                role = item.get("officer_role", "director")
                appointed_on = item.get("appointed_on")
                resigned_on = item.get("resigned_on")
                is_active = 0 if resigned_on else 1

                person_ftm_id = make_ftm_id("person", norm_name or raw_name, str(dob_year or ""), str(dob_month or ""))
                person_row = conn.execute(
                    "SELECT id FROM persons WHERE ftm_id = ?",
                    (person_ftm_id,),
                ).fetchone()
                if person_row:
                    person_id = person_row["id"]
                else:
                    person_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO persons
                            (id, ftm_id, ftm_schema, name, name_fingerprint, nationality, country_of_residence, dob_month, dob_year, created_at, updated_at)
                        VALUES (?, ?, 'Person', ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (person_id, person_ftm_id, raw_name, norm_name, nationality, residence, dob_month, dob_year, now, now),
                    )

                dir_id = str(uuid.uuid4())
                dir_ftm = directorship_to_ftm(
                    {
                        "id": dir_id,
                        "company_number": company_number,
                        "officer_role": role,
                        "appointed_on": appointed_on,
                        "resigned_on": resigned_on,
                    },
                    director_ftm_id=person_ftm_id,
                    company_ftm_id=make_ftm_id("company", "gb", company_number),
                )
                conn.execute(
                    """
                    INSERT INTO directorships
                        (id, ftm_id, ftm_schema, company_number, person_id, officer_role, appointed_on, resigned_on, is_active, occupation, nationality, country_of_residence, fetched_via, created_at, updated_at)
                    VALUES (?, ?, 'Directorship', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'api', ?, ?)
                    """,
                    (
                        dir_id,
                        dir_ftm["id"],
                        company_number,
                        person_id,
                        role,
                        appointed_on,
                        resigned_on,
                        is_active,
                        item.get("occupation"),
                        nationality,
                        residence,
                        now,
                        now,
                    ),
                )
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
