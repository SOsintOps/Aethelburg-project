"""Filing history (paginated with total_count) and on-request PDF download through the Document API."""
from __future__ import annotations

import httpx
import pytest

from src.services import documents
from src.services.api_service import CompaniesHouseApiError, CompaniesHouseApiService
from src.services.documents import (
    download_category,
    download_document,
    fetch_filing_history,
    list_filings,
)

NUMBER = "09368902"
DOC_HOST = "https://document-api.company-information.service.gov.uk"
PDF = b"%PDF-1.4 test document"


def _filing(i: int, category: str = "accounts", with_doc: bool = True) -> dict:
    item = {
        "transaction_id": f"TX{i:03d}",
        "type": "AA" if category == "accounts" else "CS01",
        "date": f"2020-01-{(i % 28) + 1:02d}",
        "category": category,
        "description": "accounts-with-accounts-type-micro-entity",
        "description_values": {"made_up_date": "2019-12-31"},
        "pages": 3,
        "links": {"self": f"/company/{NUMBER}/filing-history/TX{i:03d}"},
    }
    if with_doc:
        item["links"]["document_metadata"] = f"{DOC_HOST}/document/DOC{i:03d}"
    return item


FILINGS = [_filing(i) for i in range(120)] + [_filing(200, "confirmation-statement", with_doc=False)]


def _handler(calls: list[str]):
    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if request.url.path == f"/company/{NUMBER}/filing-history":
            start = int(request.url.params.get("start_index", 0))
            size = int(request.url.params.get("items_per_page", 35))
            return httpx.Response(200, json={"items": FILINGS[start:start + size], "total_count": len(FILINGS)})
        if request.url.host == "document-api.company-information.service.gov.uk":
            doc = request.url.path.split("/")[2]
            if doc == "DOC404":
                return httpx.Response(404)
            assert request.headers.get("authorization"), "the Document API needs the key"
            if request.url.path.endswith("/content"):
                assert request.headers["accept"] == "application/pdf"
                return httpx.Response(302, headers={"location": f"https://s3.example.test/{doc}.pdf?sig=1"})
            return httpx.Response(200, json={
                "links": {"document": f"{DOC_HOST}/document/{doc}/content"},
                "resources": {"application/pdf": {"content_length": len(PDF)}},
            })
        if request.url.host == "s3.example.test":
            assert "authorization" not in request.headers, "the key must not go to the signed address"
            return httpx.Response(200, content=PDF)
        return httpx.Response(404)
    return handle


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "documents_dir", lambda: tmp_path / "documents")
    calls: list[str] = []
    service = CompaniesHouseApiService(tmp_path / "docs.sqlite", transport=httpx.MockTransport(_handler(calls)))
    service.settings = service.settings.model_copy(update={"api_key": "test-key"})
    service.calls = calls
    return service


async def test_filing_history_reads_every_page(svc):
    assert await fetch_filing_history(svc, NUMBER) == len(FILINGS)
    items = list_filings(svc.db, NUMBER)
    assert len(items) == len(FILINGS)
    assert items[-1]["description_text"] == "Accounts with accounts type micro entity (made up to 2019-12-31)"
    assert await fetch_filing_history(svc, NUMBER) == len(FILINGS)  # a refresh does not duplicate
    assert len(list_filings(svc.db, NUMBER)) == len(FILINGS)


async def test_pdf_is_downloaded_once(svc):
    await fetch_filing_history(svc, NUMBER)
    path = await download_document(svc, NUMBER, "TX005")
    assert path.read_bytes() == PDF and path.name == "2020-01-06-AA-TX005.pdf"
    before = len(svc.calls)
    assert await download_document(svc, NUMBER, "TX005") == path
    assert len(svc.calls) == before  # already on disk: no request
    assert next(f for f in list_filings(svc.db, NUMBER) if f["transaction_id"] == "TX005")["downloaded"]


async def test_missing_document_and_bad_input_are_explicit(svc):
    await fetch_filing_history(svc, NUMBER)
    conn = svc.db.connect()
    conn.execute("UPDATE filings SET document_metadata_url = ? WHERE transaction_id = 'TX001'", (f"{DOC_HOST}/document/DOC404",))
    conn.execute("UPDATE filings SET document_metadata_url = 'https://evil.example/doc' WHERE transaction_id = 'TX002'")
    conn.commit()
    conn.close()
    with pytest.raises(CompaniesHouseApiError) as exc:
        await download_document(svc, NUMBER, "TX001")
    assert exc.value.status == 404
    with pytest.raises(CompaniesHouseApiError) as exc:
        await download_document(svc, NUMBER, "TX002")
    assert exc.value.status == 400
    with pytest.raises(CompaniesHouseApiError) as exc:
        await download_document(svc, NUMBER, "TX200")  # filing without a document image
    assert exc.value.status == 404
    with pytest.raises(CompaniesHouseApiError):
        await download_document(svc, NUMBER, "../../etc")
    with pytest.raises(CompaniesHouseApiError):
        documents.resolve_document(NUMBER, "..\\aethelburg.sqlite")


async def test_download_all_accounts_counts_failures(svc):
    await fetch_filing_history(svc, NUMBER)
    conn = svc.db.connect()
    conn.execute("UPDATE filings SET document_metadata_url = ? WHERE transaction_id = 'TX119'", (f"{DOC_HOST}/document/DOC404",))
    conn.commit()
    conn.close()
    res = await download_category(svc, NUMBER, "accounts", limit=3)
    assert res["documents"] + len(res["failed"]) == 3
    assert len(res["failed"]) <= 1
