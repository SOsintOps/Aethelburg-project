"""Officers (directors, secretaries, LLP members) for many companies at once.

Companies House publishes officers only through the API (no free bulk file), one company at a
time, 600 requests per 5 minutes: about 7,000 companies per hour. The batch is resumable: a
company whose officers were fetched less than `max_age_days` ago is skipped.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.logging import get_logger
from src.services.api_service import CompaniesHouseApiError, CompaniesHouseApiService
from src.services.db_service import DatabaseService

log = get_logger(__name__)

SCOPES = {
    "flagged": "SELECT company_number FROM companies WHERE is_flagged = 1 ORDER BY risk_score DESC",
    "case": "SELECT entity_id FROM casework_investigation_entities WHERE entity_type = 'company'",
    "subset": "SELECT company_number FROM subset_members",
}
COMPANIES_PER_HOUR = 7000


def pending_companies(db: DatabaseService, scope: str, max_age_days: int = 30) -> list[str]:
    if scope not in SCOPES:
        raise ValueError(f"Unknown scope {scope!r}: {', '.join(SCOPES)}")
    cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
    conn = db.connect()
    try:
        wanted = [r[0] for r in conn.execute(SCOPES[scope])]
        fresh = {
            r[0] for r in conn.execute("SELECT company_number FROM companies WHERE officers_fetched_at >= ?", (cutoff,))
        }
    finally:
        conn.close()
    return [n for n in wanted if n not in fresh]


def fetch_officers_batch(
    scope: str = "flagged",
    limit: int | None = None,
    max_age_days: int = 30,
    db: DatabaseService | None = None,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    db = db or DatabaseService()
    todo = pending_companies(db, scope, max_age_days)[: limit or None]
    api = CompaniesHouseApiService(db.db_path)
    done = failed = 0

    async def run() -> None:
        nonlocal done, failed
        for number in todo:
            try:
                await api.fetch_company_officers(number)
                done += 1
            except CompaniesHouseApiError as exc:
                if exc.status in (401, 429):
                    raise  # key problem or rate limit: stop, the next run resumes
                failed += 1
                log.warning("officers_fetch_failed", company_number=number, status=exc.status)
            if progress:
                progress("officers", done + failed, len(todo))

    asyncio.run(run())
    return {"scope": scope, "companies": len(todo), "fetched": done, "failed": failed}
