"""Progressive updates from the Companies House Streaming API.

Streams: `/companies`, `/officers`, `/persons-with-significant-control` on
https://stream.companieshouse.gov.uk (HTTP basic auth with a *streaming* key). Each line is one
event `{resource_kind, resource_uri, data, event: {timepoint, type, published_at}}`; blank lines
are heartbeats. The last timepoint of every stream is stored in `streaming_checkpoints`, and a
restart resumes from it. If the stream refuses a timepoint (too old: HTTP 416) the gap is
reported and the monthly bulk refresh fills it.

Rules: events for companies already fully imported update them; new incorporations join the
subset when the "recent" criterion is on; a PSC registered offshore/abroad, super-secure or of a wanted
nationality pulls its company into the subset; every company event refreshes the light index.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx
import orjson

from config.settings import get_settings
from src.core.logging import get_logger
from src.core.normalizer import compute_address_fingerprint, normalize_name
from src.datasources.subset import (
    SubsetConfig,
    _nationality_set,
    nationality_match,
    psc_risk_reason,
)
from src.etl.import_companies import upsert_company_record
from src.etl.import_psc import ingest_psc_record
from src.intelligence.risk_scorer import RiskScorer
from src.services.api_service import CompaniesHouseApiService
from src.services.ch_mapping import profile_to_record
from src.services.db_service import DatabaseService

log = get_logger(__name__)

STREAM_BASE = "https://stream.companieshouse.gov.uk"
STREAMS = {  # checkpoint key -> path
    "company_profile": "/companies",
    "officers": "/officers",
    "psc": "/persons-with-significant-control",
}
_COMPANY_IN_URI = re.compile(r"^/company/([A-Z0-9]{8})")
_RESCORE_EVERY_S = 15 * 60
_MAX_BACKOFF_S = 300


class StreamGapError(RuntimeError):
    """The stored timepoint is no longer available on the stream."""


class StreamWorker:
    """Consumes the three streams, applies events and keeps checkpoints; status() for the UI."""

    def __init__(self, db: DatabaseService | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.db = db or DatabaseService()
        self.api = CompaniesHouseApiService(self.db.db_path)
        self.cfg = SubsetConfig.load()
        self._transport = transport
        self._tasks: list[asyncio.Task[None]] = []
        self._dirty_since: float | None = None
        self.state: dict[str, dict[str, Any]] = {
            key: {"connected": False, "events": 0, "applied": 0, "last_event_at": None, "error": None}
            for key in STREAMS
        }

    @property
    def key(self) -> str:
        return get_settings().ch.streaming_key

    def status(self) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            checkpoints = {r["stream_type"]: dict(r) for r in conn.execute("SELECT * FROM streaming_checkpoints")}
        finally:
            conn.close()
        return {
            "configured": bool(self.key),
            "running": any(not t.done() for t in self._tasks),
            "streams": {
                k: {**v, "timepoint": (checkpoints.get(k) or {}).get("last_seq_num")} for k, v in self.state.items()
            },
        }

    def start(self) -> None:
        if not self.key:
            raise RuntimeError(
                "No Companies House streaming key. Store one with: python -m keyring set aethelburg ch_streaming_key"
            )
        if any(not t.done() for t in self._tasks):
            return
        self._tasks = [asyncio.create_task(self._run_forever(k)) for k in STREAMS]
        self._tasks.append(asyncio.create_task(self._rescore_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        for st in self.state.values():
            st["connected"] = False

    # ------------------------------------------------------------------ #
    # STREAM LOOP                                                        #
    # ------------------------------------------------------------------ #

    async def _run_forever(self, stream: str) -> None:
        backoff = 5.0
        while True:
            try:
                await self.consume(stream)
                backoff = 5.0
            except asyncio.CancelledError:
                raise
            except StreamGapError as exc:
                self.state[stream]["error"] = str(exc)
                self._save_timepoint(stream, None)  # restart from "now"; the bulk refresh covers the gap
            except Exception as exc:  # network drop, 5xx, malformed line: retry with backoff
                self.state[stream]["error"] = f"{type(exc).__name__}: {exc}"
                log.warning("stream_error", stream=stream, error=str(exc))
            self.state[stream]["connected"] = False
            await asyncio.sleep(backoff)
            backoff = min(_MAX_BACKOFF_S, backoff * 2)

    async def consume(self, stream: str, max_events: int | None = None) -> int:
        """Read one connection of `stream`; returns the number of events read."""
        params = {}
        timepoint = self._load_timepoint(stream)
        if timepoint is not None:
            params["timepoint"] = timepoint
        timeout = httpx.Timeout(30.0, read=None)
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            async with client.stream("GET", STREAM_BASE + STREAMS[stream], params=params, auth=(self.key, "")) as resp:
                if resp.status_code == 416:
                    raise StreamGapError(
                        f"Timepoint {timepoint} is too old for the {stream} stream; "
                        "run the monthly bulk refresh to fill the gap"
                    )
                if resp.status_code == 401:
                    raise RuntimeError("Companies House rejected the streaming key (401)")
                if resp.status_code != 200:
                    raise RuntimeError(f"Stream {stream} returned HTTP {resp.status_code}")
                self.state[stream].update(connected=True, error=None)
                read = 0
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue  # heartbeat
                    event = orjson.loads(line)
                    read += 1
                    self.state[stream]["events"] += 1
                    if self.apply_event(stream, event):
                        self.state[stream]["applied"] += 1
                        self._dirty_since = self._dirty_since or time.monotonic()
                    tp = (event.get("event") or {}).get("timepoint")
                    if tp is not None:
                        self._save_timepoint(stream, int(tp), (event.get("event") or {}).get("published_at"))
                    if max_events and read >= max_events:
                        break
                return read

    # ------------------------------------------------------------------ #
    # EVENTS                                                             #
    # ------------------------------------------------------------------ #

    def apply_event(self, stream: str, event: dict[str, Any]) -> bool:
        """Apply one event; returns True when the full database changed."""
        self.state[stream]["last_event_at"] = (event.get("event") or {}).get("published_at")
        if (event.get("event") or {}).get("type") == "deleted":
            return False
        data = event.get("data") or {}
        match = _COMPANY_IN_URI.match(event.get("resource_uri") or "")
        number = (data.get("company_number") or (match.group(1) if match else "")).upper()
        if not number:
            return False
        if stream == "company_profile":
            return self._on_company(number, data)
        if stream == "officers":
            if not self._in_subset(number):
                return False
            self.api.persist_officers(number, [data], complete_list=False)
            return True
        if stream == "psc":
            return self._on_psc(number, data)
        return False

    def _on_company(self, number: str, profile: dict[str, Any]) -> bool:
        rec = profile_to_record({**profile, "company_number": number})
        if rec is None:
            return False
        conn = self.db.connect()
        try:
            self._index_company(conn, rec)
            changed = False
            joins = self.cfg.recent and _is_recent(rec.get("incorporation_date"), self.cfg.recent_years)
            if self._in_subset(number, conn) or joins:
                upsert_company_record(conn, self.db, rec, self._source_id(conn))
                if joins:
                    _add_member(conn, number, "recent")
                changed = True
            conn.commit()
            return changed
        finally:
            conn.close()

    def _on_psc(self, number: str, data: dict[str, Any]) -> bool:
        conn = self.db.connect()
        try:
            in_subset = self._in_subset(number, conn)
            reason = self._psc_reason(data)
            if not in_subset and reason is None:
                return False
            if not in_subset:
                self._company_from_index(conn, number)
                _add_member(conn, number, reason)
            existing = {number} if conn.execute(
                "SELECT 1 FROM companies WHERE company_number = ?", (number,)
            ).fetchone() else set()
            counts = dict.fromkeys(
                ("psc_ownerships", "persons", "legal_entities", "stub_companies", "directorships", "ftm_entities"), 0
            )
            ingest_psc_record(conn, self.db, number, data, self._source_id(conn), _now(), existing, counts)
            conn.commit()
            return True
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # HELPERS                                                            #
    # ------------------------------------------------------------------ #

    def _psc_reason(self, data: dict[str, Any]) -> str | None:
        """Same rules as the bulk selection: risk links, then wanted PSC nationalities."""
        if self.cfg.risk_links:
            reason = psc_risk_reason(data)
            if reason:
                return reason
        label = nationality_match(data.get("nationality"), _nationality_set(self.cfg.psc_nationalities))
        return f"nationality_{label}" if label else None

    def _in_subset(self, number: str, conn: Any = None) -> bool:
        own = conn is None
        c = conn or self.db.connect()
        try:
            return c.execute("SELECT 1 FROM companies WHERE company_number = ?", (number,)).fetchone() is not None
        finally:
            if own:
                c.close()

    @staticmethod
    def _index_company(conn: Any, rec: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO company_index
                (company_number, company_name, name_fingerprint, postcode, address_fingerprint,
                 company_status, company_category, incorporation_date, source_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'stream')
            """,
            (rec["company_number"], rec["company_name"], rec.get("name_fingerprint"), rec.get("reg_address_postcode"),
             rec.get("address_fingerprint"), rec.get("company_status"), rec.get("company_category"),
             rec.get("incorporation_date")),
        )

    def _company_from_index(self, conn: Any, number: str) -> None:
        """Create the company from the light index so a PSC event never leaves a nameless stub."""
        row = conn.execute("SELECT * FROM company_index WHERE company_number = ?", (number,)).fetchone()
        if row is None:
            return  # unknown to the index too: ingest_psc_record creates a stub
        rec = {
            "company_number": number,
            "company_name": row["company_name"],
            "company_status": row["company_status"],
            "company_category": row["company_category"],
            "incorporation_date": row["incorporation_date"],
            "reg_address_postcode": row["postcode"],
            "address_fingerprint": row["address_fingerprint"] or compute_address_fingerprint(row["postcode"]),
            "name_fingerprint": row["name_fingerprint"] or normalize_name(row["company_name"], is_company=True),
        }
        upsert_company_record(conn, self.db, rec, self._source_id(conn))

    def _source_id(self, conn: Any) -> str:
        return self.db.register_data_source(
            source_name="Companies House Streaming API",
            source_type="ch_stream",
            source_version=datetime.now(UTC).strftime("%Y-%m-%d"),
            source_url=STREAM_BASE,
            conn=conn,
        )

    def _load_timepoint(self, stream: str) -> int | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT last_seq_num FROM streaming_checkpoints WHERE stream_type = ?", (stream,)
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()

    def _save_timepoint(self, stream: str, timepoint: int | None, published_at: str | None = None) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO streaming_checkpoints (stream_type, last_seq_num, last_event_at, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(stream_type) DO UPDATE SET
                    last_seq_num = excluded.last_seq_num,
                    last_event_at = COALESCE(excluded.last_event_at, streaming_checkpoints.last_event_at),
                    updated_at = excluded.updated_at
                """,
                (stream, timepoint, published_at),
            )
            conn.commit()
        finally:
            conn.close()

    async def _rescore_loop(self) -> None:
        """Re-run FT3 scoring at most every 15 minutes while events keep changing the database."""
        while True:
            await asyncio.sleep(60)
            if self._dirty_since and time.monotonic() - self._dirty_since >= _RESCORE_EVERY_S:
                self._dirty_since = None
                await asyncio.to_thread(RiskScorer(self.db).run_all_detections)


def _is_recent(incorporated: str | None, years: int) -> bool:
    if not incorporated:
        return False
    try:
        since = date.today().replace(year=date.today().year - int(years))
        return date.fromisoformat(incorporated[:10]) >= since
    except ValueError:
        return False


def _add_member(conn: Any, number: str, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO subset_members (company_number, reasons) VALUES (?, ?)
        ON CONFLICT(company_number) DO UPDATE SET reasons =
            CASE WHEN ',' || subset_members.reasons || ',' LIKE '%,' || excluded.reasons || ',%'
                 THEN subset_members.reasons ELSE subset_members.reasons || ',' || excluded.reasons END
        """,
        (number, reason),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
