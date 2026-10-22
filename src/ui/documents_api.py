"""Endpoints for the Companies House filing history and the optional document download."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.services.api_service import CompaniesHouseApiError, CompaniesHouseApiService
from src.services.db_service import DatabaseService
from src.services.documents import (
    download_category,
    download_document,
    fetch_filing_history,
    list_filings,
    resolve_document,
)


def add_document_routes(router: APIRouter, db: DatabaseService, ch_api: CompaniesHouseApiService) -> None:
    def _ch_error(exc: CompaniesHouseApiError) -> HTTPException:
        status = exc.status if exc.status in (400, 401, 404, 415, 429) else 502
        return HTTPException(status_code=status, detail=exc.message)

    @router.get("/api/companies/{company_number}/filings")
    async def filings(company_number: str) -> dict[str, Any]:
        number = company_number.strip().upper()
        return {"company_number": number, "items": await asyncio.to_thread(list_filings, db, number)}

    @router.post("/api/companies/{company_number}/filings/refresh")
    async def filings_refresh(company_number: str) -> dict[str, Any]:
        try:
            count = await fetch_filing_history(ch_api, company_number)
        except CompaniesHouseApiError as exc:
            raise _ch_error(exc) from exc
        number = company_number.strip().upper()
        return {"filings": count, "items": await asyncio.to_thread(list_filings, db, number)}

    @router.post("/api/companies/{company_number}/documents/{transaction_id}")
    async def document_download(company_number: str, transaction_id: str) -> dict[str, Any]:
        try:
            path = await download_document(ch_api, company_number, transaction_id)
        except CompaniesHouseApiError as exc:
            raise _ch_error(exc) from exc
        return {"file_name": path.name, "url": f"/api/documents/{company_number.strip().upper()}/{path.name}"}

    @router.post("/api/companies/{company_number}/documents")
    async def documents_by_category(company_number: str, category: str = "accounts") -> dict[str, Any]:
        if not category.isalpha():
            raise HTTPException(status_code=400, detail=f"Invalid category: {category!r}")
        try:
            return await download_category(ch_api, company_number, category)
        except CompaniesHouseApiError as exc:
            raise _ch_error(exc) from exc

    @router.get("/api/documents/{company_number}/{file_name}")
    async def document_file(company_number: str, file_name: str) -> FileResponse:
        try:
            path = resolve_document(company_number, file_name)
        except CompaniesHouseApiError as exc:
            raise _ch_error(exc) from exc
        return FileResponse(str(path), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{path.name}"'})
