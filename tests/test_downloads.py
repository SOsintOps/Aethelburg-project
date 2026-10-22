"""Catalogue parsing and resumable, idempotent downloads (no network)."""
from __future__ import annotations

import io
import zipfile

import httpx
import pytest

from config.settings import get_settings
from src.datasources import downloader
from src.datasources.catalog import Release, latest_release
from src.services.db_service import DatabaseService

CH_PAGE = """
<a href="BasicCompanyDataAsOneFile-2026-09-01.zip">old</a>
<a href="BasicCompanyDataAsOneFile-2026-10-01.zip">new</a>
"""
ARCGIS = {"results": [
    {"id": "guide", "title": "ONS Postcode Directory (August 2026) User Guide"},
    {"id": "may", "title": "ONS Postcode Directory (May 2026)"},
    {"id": "aug", "title": "ONS Postcode Directory (August 2026)"},
]}


def test_catalogue_picks_newest_release():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("en_output.html"):
            return httpx.Response(200, text=CH_PAGE)
        if "sanctionslist" in request.url.host:
            return httpx.Response(206, text="Report Date: 16-Oct-2026\nLast Updated;...")
        return httpx.Response(200, json=ARCGIS)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert latest_release("ch_companies", client).version == "2026-10-01"
    assert latest_release("uk_sanctions", client).version == "2026-10-16"
    onspd = latest_release("onspd", client)
    assert onspd.version == "2026-08-01" and "/items/aug/" in onspd.url and onspd.filename == "ONSPD_AUG_2026.zip"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings().paths, "data_dir", tmp_path)
    return tmp_path


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BasicCompanyDataAsOneFile-2026-10-01.csv", "CompanyName, CompanyNumber\nX LTD,00000001\n")
    return buf.getvalue()


def test_download_resumes_and_is_not_repeated(data_dir, monkeypatch):
    payload = _zip_bytes()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = int(request.headers.get("Range", "bytes=0-")[6:].rstrip("-"))
        status = 206 if start else 200
        return httpx.Response(status, content=payload[start:], headers={"Content-Length": str(len(payload) - start)})

    real_client = httpx.Client
    monkeypatch.setattr(downloader.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))

    release = Release("ch_companies", "2026-10-01", "https://example.test/x.zip", "x.zip")
    target = downloader.release_dir(release)
    target.mkdir(parents=True)
    (target / "x.zip.part").write_bytes(payload[:100])  # interrupted earlier

    db = DatabaseService(data_dir / "dl.sqlite")
    first = downloader.download_source("ch_companies", release, db=db)
    assert first["status"] == "downloaded"
    assert requests[0].headers["Range"] == "bytes=100-"
    assert downloader.latest_local_file("ch_companies").read_text().startswith("CompanyName")

    second = downloader.download_source("ch_companies", release, db=db)
    assert second["status"] == "already-downloaded" and len(requests) == 1
