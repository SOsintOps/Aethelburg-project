"""Unexpected errors reach the user with an id that matches the log; downloads retry transient failures."""
from __future__ import annotations

import logging

import httpx
from fastapi.testclient import TestClient

from config.settings import get_settings
from src.datasources import downloader
from src.datasources.catalog import Release
from src.services.db_service import DatabaseService
from src.ui.web_app import create_app


def test_unhandled_error_returns_error_id_and_logs_it(tmp_path, caplog):
    app = create_app(tmp_path / "err.sqlite")

    @app.get("/api/boom")
    async def boom() -> None:
        raise ValueError("kaboom")

    with caplog.at_level(logging.ERROR, logger="aethelburg.web"):
        res = TestClient(app, raise_server_exceptions=False).get("/api/boom")
    body = res.json()
    assert res.status_code == 500 and "kaboom" in body["detail"]
    assert body["error_id"] in caplog.text


def test_download_retries_after_server_error(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings().paths, "data_dir", tmp_path)
    monkeypatch.setattr(downloader.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"Report Date: 16-Oct-2026\n", headers={"Content-Length": "25"})

    real_client = httpx.Client
    monkeypatch.setattr(downloader.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    release = Release("uk_sanctions", "2026-10-16", "https://example.test/list.txt", "UK-Sanctions-List.txt")
    res = downloader.download_source("uk_sanctions", release, db=DatabaseService(tmp_path / "d.sqlite"))
    assert res["status"] == "downloaded" and calls["n"] == 2
