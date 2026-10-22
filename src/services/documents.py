"""Companies House filing history and documents (optional download).

- Filing history: `GET /company/{n}/filing-history` (REST key, paginated, `total_count`), stored in
  `filings`; fetched with "Update from CH" and shown in the timeline and in the dossier.
- Documents, only on request: the filing's `links.document_metadata` points to the Document API
  (`https://document-api.company-information.service.gov.uk/document/{id}`); its `/content` with
  `Accept: application/pdf` answers 302 to a signed download URL, fetched without the key.
  Files go to `<data folder>/documents/<CRN>/<date>-<type>-<transaction>.pdf` and are never
  downloaded twice.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from config.settings import get_settings
from src.core.logging import get_logger
from src.services.api_service import CompaniesHouseApiError, CompaniesHouseApiService, _clean_number

log = get_logger(__name__)

DOCUMENT_API_HOST = "document-api.company-information.service.gov.uk"
_SAFE_PART_RE = re.compile(r"[^A-Za-z0-9_-]+")
_TRANSACTION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def documents_dir() -> Path:
    return get_settings().paths.data_dir / "documents"


def describe(code: str | None, values: dict[str, Any] | None = None) -> str:
    """`gazette-dissolved-compulsory` -> `Gazette dissolved compulsory`, with the made-up date if any.

    Companies House publishes the full wording separately (api-enumerations); the code is enough
    to recognise the filing and the form type is shown next to it.
    """
    text = (code or "").replace("-", " ").strip().capitalize()
    made_up = (values or {}).get("made_up_date")
    return f"{text} (made up to {made_up})" if made_up else text


async def fetch_filing_history(svc: CompaniesHouseApiService, company_number: str) -> int:
    """Download the whole filing history of a company into `filings`; returns the number of filings."""
    number = _clean_number(company_number)
    try:
        items = await svc._get_all_items(f"/company/{number}/filing-history")
    except CompaniesHouseApiError as exc:
        if exc.status == 404:  # no filing history (e.g. very old or overseas records)
            return 0
        raise
    now = datetime.now(UTC).isoformat()
    conn = svc.db.connect()
    try:
        for it in items:
            tid = it.get("transaction_id")
            if not tid:
                continue
            conn.execute(
                """
                INSERT INTO filings
                    (transaction_id, company_number, date, category, type, description, description_values,
                     pages, paper_filed, document_metadata_url, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO UPDATE SET
                    date = excluded.date, category = excluded.category, type = excluded.type,
                    description = excluded.description, description_values = excluded.description_values,
                    pages = excluded.pages, paper_filed = excluded.paper_filed,
                    document_metadata_url = excluded.document_metadata_url, fetched_at = excluded.fetched_at
                """,
                (tid, number, it.get("date"), it.get("category"), it.get("type"), it.get("description"),
                 json.dumps(it.get("description_values") or {}, ensure_ascii=False), it.get("pages"),
                 1 if it.get("paper_filed") else 0, (it.get("links") or {}).get("document_metadata"), now),
            )
        conn.commit()
    finally:
        conn.close()
    return len(items)


def list_filings(db: Any, company_number: str) -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM filings WHERE company_number = ? ORDER BY date DESC, transaction_id",
            (company_number,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        f = dict(r)
        f["description_text"] = describe(f["description"], json.loads(f["description_values"] or "{}"))
        f["has_document"] = bool(f["document_metadata_url"])
        f["downloaded"] = bool(f["downloaded_path"]) and Path(f["downloaded_path"]).exists()
        f["file_name"] = Path(f["downloaded_path"]).name if f["downloaded"] else None
        out.append(f)
    return out


async def download_document(svc: CompaniesHouseApiService, company_number: str, transaction_id: str) -> Path:
    """PDF of one filing, saved once in the data folder; returns its path."""
    number = _clean_number(company_number)
    if not _TRANSACTION_RE.match(transaction_id or ""):
        raise CompaniesHouseApiError(400, f"Invalid transaction id: {transaction_id!r}")
    conn = svc.db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM filings WHERE company_number = ? AND transaction_id = ?", (number, transaction_id)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise CompaniesHouseApiError(404, f"Filing {transaction_id} of {number} is not in the database: update the company first")
    if row["downloaded_path"] and Path(row["downloaded_path"]).exists():
        return Path(row["downloaded_path"])
    meta_url = row["document_metadata_url"]
    if not meta_url:
        raise CompaniesHouseApiError(404, "Companies House has no document image for this filing")
    if urlparse(meta_url).hostname != DOCUMENT_API_HOST:
        raise CompaniesHouseApiError(400, f"Unexpected document address: {meta_url}")

    meta = (await _authorised_get(svc, meta_url)).json()
    resources = meta.get("resources") or {}
    if "application/pdf" not in resources:
        raise CompaniesHouseApiError(415, f"No PDF for this filing (formats: {', '.join(resources) or 'none'})")
    content_url = (meta.get("links") or {}).get("document") or f"{meta_url}/content"
    if urlparse(content_url).hostname != DOCUMENT_API_HOST:
        raise CompaniesHouseApiError(400, f"Unexpected document address: {content_url}")
    redirect = await _authorised_get(svc, content_url, accept="application/pdf")
    pdf = await _download(svc, redirect)

    target_dir = documents_dir() / number
    target_dir.mkdir(parents=True, exist_ok=True)
    parts = [row["date"] or "undated", row["type"] or "doc", transaction_id]
    target = target_dir / ("-".join(_SAFE_PART_RE.sub("_", p) for p in parts) + ".pdf")
    tmp = target.with_suffix(".part")
    tmp.write_bytes(pdf)
    tmp.replace(target)
    conn = svc.db.connect()
    try:
        conn.execute("UPDATE filings SET downloaded_path = ? WHERE transaction_id = ?", (str(target), transaction_id))
        conn.commit()
    finally:
        conn.close()
    log.info("document_downloaded", company=number, transaction=transaction_id, bytes=len(pdf))
    return target


async def download_category(
    svc: CompaniesHouseApiService, company_number: str, category: str = "accounts", limit: int | None = None
) -> dict[str, Any]:
    """Every document of one filing category (default: accounts), newest first; errors are counted, not raised."""
    number = _clean_number(company_number)
    wanted = [f for f in list_filings(svc.db, number) if f["category"] == category and f["has_document"]]
    done, failed = 0, []
    for f in wanted[:limit]:
        try:
            await download_document(svc, number, f["transaction_id"])
            done += 1
        except CompaniesHouseApiError as exc:
            failed.append({"transaction_id": f["transaction_id"], "error": exc.message})
    return {"company_number": number, "category": category, "documents": done, "failed": failed}


def resolve_document(company_number: str, file_name: str) -> Path:
    """Path of a downloaded document from a request, refusing anything outside the documents folder."""
    number = _clean_number(company_number)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.pdf", file_name or "") or ".." in file_name:
        raise CompaniesHouseApiError(400, f"Invalid document name: {file_name!r}")
    path = documents_dir() / number / file_name
    if not path.is_file():
        raise CompaniesHouseApiError(404, f"Document not downloaded: {file_name}")
    return path


async def _authorised_get(svc: CompaniesHouseApiService, url: str, accept: str = "application/json") -> httpx.Response:
    """Document API request with the REST key and the shared rate limit; redirects are not followed."""
    if not svc.settings.api_key:
        raise CompaniesHouseApiError(401, "No Companies House API key configured.")
    await svc._throttle()
    try:
        async with httpx.AsyncClient(timeout=30.0, transport=svc._transport) as client:
            resp = await client.get(url, headers={"Accept": accept}, auth=(svc.settings.api_key, ""))
    except httpx.HTTPError as exc:
        raise CompaniesHouseApiError(0, f"Companies House document service unreachable: {exc}") from exc
    if resp.status_code in (200, 302):
        return resp
    if resp.status_code == 404:
        raise CompaniesHouseApiError(404, "Document not found on Companies House")
    raise CompaniesHouseApiError(resp.status_code, f"Companies House document service returned HTTP {resp.status_code}")


async def _download(svc: CompaniesHouseApiService, resp: httpx.Response) -> bytes:
    """The PDF itself: inline (200) or from the signed address of a 302, requested without the key."""
    if resp.status_code == 200:
        body = resp.content
    else:
        location = resp.headers.get("location")
        if not location or urlparse(location).scheme != "https":
            raise CompaniesHouseApiError(502, "Companies House did not return a download address")
        try:
            async with httpx.AsyncClient(timeout=120.0, transport=svc._transport) as client:
                got = await client.get(location)
        except httpx.HTTPError as exc:
            raise CompaniesHouseApiError(0, f"Document download failed: {exc}") from exc
        if got.status_code != 200:
            raise CompaniesHouseApiError(got.status_code, f"Document download returned HTTP {got.status_code}")
        body = got.content
    if not body.startswith(b"%PDF"):
        raise CompaniesHouseApiError(502, "The downloaded document is not a PDF")
    return body


AUTO_DOWNLOAD_COMPANIES = 50  # filing history + 2 documents each: about 250 requests, under 5 minutes of quota


def auto_download_latest(db: Any, limit: int = AUTO_DOWNLOAD_COMPANIES) -> dict[str, Any]:
    """Latest accounts and confirmation statement of the highest-risk flagged companies.

    Used by the daily update when `documents_auto_download` is on (user config, default off).
    Companies whose newest filings are already on disk cost one request (the filing history).
    """
    svc = CompaniesHouseApiService(db.db_path)
    conn = db.connect()
    try:
        numbers = [r[0] for r in conn.execute(
            "SELECT company_number FROM companies WHERE is_flagged = 1 ORDER BY risk_score DESC LIMIT ?", (limit,)
        )]
    finally:
        conn.close()
    summary: dict[str, Any] = {"companies": 0, "documents": 0, "errors": 0}

    async def run() -> None:
        for number in numbers:
            try:
                await fetch_filing_history(svc, number)
                for category in ("accounts", "confirmation-statement"):
                    latest = next((f for f in list_filings(db, number)
                                   if f["category"] == category and f["has_document"]), None)
                    if latest and not latest["downloaded"]:
                        await download_document(svc, number, latest["transaction_id"])
                        summary["documents"] += 1
                summary["companies"] += 1
            except CompaniesHouseApiError as exc:
                summary["errors"] += 1
                log.warning("auto_document_failed", company=number, error=exc.message)

    asyncio.run(run())
    return summary
