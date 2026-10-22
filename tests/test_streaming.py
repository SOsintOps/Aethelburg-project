"""Streaming API worker: events, subset rules, timepoint resume and gap handling."""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from src.datasources.streaming import StreamGapError, StreamWorker
from src.services.db_service import DatabaseService

RECENT = date.today().replace(year=date.today().year - 1).isoformat()


def _event(tp: int, uri: str, data: dict, kind: str = "changed") -> str:
    return json.dumps(
        {"resource_uri": uri, "data": data, "event": {"timepoint": tp, "type": kind, "published_at": "2026-10-22T10:00:00"}}
    )


EVENTS = {
    "/companies": [
        _event(101, "/company/11111111", {"company_number": "11111111", "company_name": "OLD TRADING LIMITED",
                                          "company_status": "active", "date_of_creation": "1999-01-01"}),
        _event(102, "/company/22222222", {"company_number": "22222222", "company_name": "BRAND NEW LIMITED",
                                          "company_status": "active", "date_of_creation": RECENT}),
        "",  # heartbeat
    ],
    "/persons-with-significant-control": [
        _event(201, "/company/11111111/persons-with-significant-control/corporate-entity/x", {
            "kind": "corporate-entity-person-with-significant-control", "name": "GERMAN HOLDCO GMBH",
            "identification": {"country_registered": "Germany"},
            "links": {"self": "/company/11111111/persons-with-significant-control/corporate-entity/x"}}),
    ],
}


def _worker(tmp_path, handler) -> StreamWorker:
    worker = StreamWorker(DatabaseService(tmp_path / "stream.sqlite"), transport=httpx.MockTransport(handler))
    worker.cfg.recent_years = 3
    return worker


def _handler(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        lines = [e for e in EVENTS.get(request.url.path, [])
                 if not e or json.loads(e)["event"]["timepoint"] > int(request.url.params.get("timepoint", 0))]
        return httpx.Response(200, text="\n".join(lines) + "\n")
    return handler


@pytest.fixture(autouse=True)
def streaming_key(monkeypatch):
    from config.settings import get_settings

    monkeypatch.setattr(get_settings().ch, "streaming_key", "stream-key")


async def test_events_follow_subset_rules_and_resume(tmp_path):
    seen: list[httpx.Request] = []
    worker = _worker(tmp_path, _handler(seen))

    assert await worker.consume("company_profile") == 2
    conn = worker.db.connect()
    try:
        # new incorporation joins the subset; an old company outside the subset only reaches the index
        assert conn.execute("SELECT reasons FROM subset_members WHERE company_number='22222222'").fetchone()[0] == "recent"
        assert conn.execute("SELECT COUNT(*) FROM companies WHERE company_number='11111111'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM company_index").fetchone()[0] == 2
    finally:
        conn.close()

    # a PSC registered abroad pulls its company in, built from the light index (not a nameless stub)
    await worker.consume("psc")
    conn = worker.db.connect()
    try:
        row = conn.execute("SELECT company_name FROM companies WHERE company_number='11111111'").fetchone()
        assert row["company_name"] == "OLD TRADING LIMITED"
        assert conn.execute("SELECT reasons FROM subset_members WHERE company_number='11111111'").fetchone()[0] == "foreign_psc"
    finally:
        conn.close()

    # reconnecting resumes after the stored timepoint: nothing is replayed
    assert await worker.consume("company_profile") == 0
    assert seen[-1].url.params["timepoint"] == "102"
    assert worker.status()["streams"]["company_profile"]["timepoint"] == 102


async def test_too_old_timepoint_reports_a_gap(tmp_path):
    worker = _worker(tmp_path, lambda r: httpx.Response(416))
    worker._save_timepoint("officers", 5)
    with pytest.raises(StreamGapError, match="monthly bulk refresh"):
        await worker.consume("officers")
