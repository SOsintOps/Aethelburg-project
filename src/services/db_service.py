"""Database service — Relational + FollowTheMoney (FtM v3.x) storage & query engine.

Supports:
  - Local SQLite backend (`dati/aethelburg.sqlite`) out-of-the-box without Docker
  - PostgreSQL + PostGIS + Apache AGE backend when configured
  - Full FollowTheMoney (`ftm_entities`) canonical store, JSONL import/export, and cross-table sync
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config.database import get_sqlite_connection
from src.core.ftm import (
    address_to_ftm,
    company_to_ftm,
    directorship_to_ftm,
    icij_entity_to_ftm,
    icij_officer_to_ftm,
    icij_relationship_to_ftm,
    legal_entity_to_ftm,
    person_to_ftm,
    psc_to_ftm_ownership,
    sanction_to_ftm,
    validate_ftm_entity,
)
from src.core.logging import get_logger
from src.core.normalizer import (
    compute_address_fingerprint,
    extract_uk_company_numbers,
    normalize_name,
    normalize_postcode,
    phonetic_key,
)

log = get_logger(__name__)


SQLITE_SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS data_sources (
    id              TEXT PRIMARY KEY,
    source_name     TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    source_version  TEXT,
    source_url      TEXT,
    collected_at    TEXT NOT NULL DEFAULT (datetime('now')),
    file_hash       TEXT,
    record_count    INTEGER,
    notes           TEXT,
    UNIQUE (source_name, source_version)
);

CREATE TABLE IF NOT EXISTS ftm_entities (
    id              TEXT PRIMARY KEY,
    schema          TEXT NOT NULL,
    caption         TEXT NOT NULL,
    properties      TEXT NOT NULL DEFAULT '{}',
    datasets        TEXT NOT NULL DEFAULT '[]',
    referents       TEXT NOT NULL DEFAULT '[]',
    target          INTEGER NOT NULL DEFAULT 0,
    first_seen      TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen       TEXT NOT NULL DEFAULT (datetime('now')),
    last_change     TEXT NOT NULL DEFAULT (datetime('now')),
    source_id       TEXT REFERENCES data_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_ftm_entities_schema ON ftm_entities(schema);
CREATE INDEX IF NOT EXISTS idx_ftm_entities_caption ON ftm_entities(caption);
CREATE INDEX IF NOT EXISTS idx_ftm_entities_target ON ftm_entities(target);

CREATE TABLE IF NOT EXISTS geo_postcode_centroids (
    postcode        TEXT PRIMARY KEY,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    admin_district  TEXT,
    admin_county    TEXT,
    admin_ward      TEXT,
    nuts_level1     TEXT,
    country_code    TEXT,
    precision       TEXT,  -- postcode (ONSPD) | district | area (built-in approximation)
    source_id       TEXT REFERENCES data_sources(id)
);

CREATE TABLE IF NOT EXISTS addresses (
    id                  TEXT PRIMARY KEY,
    ftm_id              TEXT UNIQUE NOT NULL,
    ftm_schema          TEXT NOT NULL DEFAULT 'Address',
    full_address        TEXT NOT NULL,
    street              TEXT,
    city                TEXT,
    county              TEXT,
    postcode            TEXT,
    country             TEXT,
    country_code        TEXT,
    address_fingerprint TEXT UNIQUE,
    lat                 REAL,
    lon                 REAL,
    company_count       INTEGER NOT NULL DEFAULT 0,
    source_id           TEXT REFERENCES data_sources(id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_addresses_postcode ON addresses(postcode);
CREATE INDEX IF NOT EXISTS idx_addresses_fp ON addresses(address_fingerprint);

CREATE TABLE IF NOT EXISTS companies (
    company_number              TEXT PRIMARY KEY,
    company_name                TEXT NOT NULL,
    ftm_id                      TEXT,
    ftm_schema                  TEXT NOT NULL DEFAULT 'Company',
    reg_address_care_of         TEXT,
    reg_address_po_box          TEXT,
    reg_address_line1           TEXT,
    reg_address_line2           TEXT,
    reg_address_post_town       TEXT,
    reg_address_county          TEXT,
    reg_address_country         TEXT,
    reg_address_postcode        TEXT,
    company_category            TEXT,
    company_status              TEXT,
    country_of_origin           TEXT,
    dissolution_date            TEXT,
    incorporation_date          TEXT,
    accounts_account_ref_day    INTEGER,
    accounts_account_ref_month  INTEGER,
    accounts_account_category   TEXT,
    accounts_account_date       TEXT,
    accounts_next_due_date      TEXT,
    accounts_last_made_up_date  TEXT,
    returns_next_due_date       TEXT,
    returns_last_made_up_date   TEXT,
    mortgages_num_charges       INTEGER DEFAULT 0,
    mortgages_num_outstanding   INTEGER DEFAULT 0,
    mortgages_num_part_satisfied INTEGER DEFAULT 0,
    mortgages_num_satisfied     INTEGER DEFAULT 0,
    sic_text_1                  TEXT,
    sic_text_2                  TEXT,
    sic_text_3                  TEXT,
    sic_text_4                  TEXT,
    sic_code_1                  TEXT,
    sic_code_2                  TEXT,
    sic_code_3                  TEXT,
    sic_code_4                  TEXT,
    lp_num_gen_partners         INTEGER,
    lp_num_lim_partners         INTEGER,
    ch_uri                      TEXT,
    prev_name_1_date            TEXT,
    prev_name_1                 TEXT,
    prev_name_2_date            TEXT,
    prev_name_2                 TEXT,
    prev_name_3_date            TEXT,
    prev_name_3                 TEXT,
    prev_name_4_date            TEXT,
    prev_name_4                 TEXT,
    prev_name_5_date            TEXT,
    prev_name_5                 TEXT,
    prev_name_6_date            TEXT,
    prev_name_6                 TEXT,
    prev_name_7_date            TEXT,
    prev_name_7                 TEXT,
    prev_name_8_date            TEXT,
    prev_name_8                 TEXT,
    prev_name_9_date            TEXT,
    prev_name_9                 TEXT,
    prev_name_10_date           TEXT,
    prev_name_10                TEXT,
    conf_stmt_next_due_date     TEXT,
    conf_stmt_last_made_up_date TEXT,
    address_fingerprint         TEXT,
    name_fingerprint            TEXT,
    risk_score                  REAL DEFAULT 0.0,
    ft3_techniques              TEXT DEFAULT '[]',
    officers_fetched_at         TEXT,
    is_flagged                  INTEGER DEFAULT 0,
    source_id                   TEXT REFERENCES data_sources(id),
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(company_name);
CREATE INDEX IF NOT EXISTS idx_companies_fingerprint ON companies(name_fingerprint);
CREATE INDEX IF NOT EXISTS idx_companies_postcode ON companies(reg_address_postcode);
CREATE INDEX IF NOT EXISTS idx_companies_addr_fp ON companies(address_fingerprint);
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(company_status);
CREATE INDEX IF NOT EXISTS idx_companies_risk ON companies(risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_companies_sic1 ON companies(sic_code_1);
CREATE INDEX IF NOT EXISTS idx_companies_ftm_id ON companies(ftm_id);

CREATE TABLE IF NOT EXISTS persons (
    id                      TEXT PRIMARY KEY,
    ftm_id                  TEXT,
    ftm_schema              TEXT NOT NULL DEFAULT 'Person',
    name                    TEXT NOT NULL,
    name_fingerprint        TEXT,
    forename                TEXT,
    surname                 TEXT,
    title                   TEXT,
    nationality             TEXT,
    country_of_residence    TEXT,
    dob_month               INTEGER,
    dob_year                INTEGER,
    is_pep                  INTEGER DEFAULT 0,
    pep_source              TEXT,
    source_id               TEXT REFERENCES data_sources(id),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_persons_fingerprint ON persons(name_fingerprint);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);
CREATE INDEX IF NOT EXISTS idx_persons_ftm_id ON persons(ftm_id);

CREATE TABLE IF NOT EXISTS legal_entities (
    id                      TEXT PRIMARY KEY,
    ftm_id                  TEXT,
    ftm_schema              TEXT NOT NULL DEFAULT 'LegalEntity',
    name                    TEXT NOT NULL,
    name_fingerprint        TEXT,
    jurisdiction            TEXT,
    company_number_foreign  TEXT,
    entity_type             TEXT,
    is_offshore             INTEGER DEFAULT 0,
    source_id               TEXT REFERENCES data_sources(id),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_legal_entities_fingerprint ON legal_entities(name_fingerprint);
CREATE INDEX IF NOT EXISTS idx_legal_entities_jurisdiction ON legal_entities(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_legal_entities_ftm_id ON legal_entities(ftm_id);

CREATE TABLE IF NOT EXISTS psc_ownerships (
    id                  TEXT PRIMARY KEY,
    ftm_id              TEXT,
    ftm_schema          TEXT NOT NULL DEFAULT 'Ownership',
    company_number      TEXT NOT NULL REFERENCES companies(company_number),
    person_id           TEXT REFERENCES persons(id),
    legal_entity_id     TEXT REFERENCES legal_entities(id),
    nature_of_control   TEXT DEFAULT '[]',
    notified_on         TEXT,
    ceased_on           TEXT,
    is_ceased           INTEGER DEFAULT 0,
    is_super_secure     INTEGER DEFAULT 0,
    source_id           TEXT REFERENCES data_sources(id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT chk_psc_owner CHECK (
        (person_id IS NOT NULL AND legal_entity_id IS NULL) OR
        (person_id IS NULL AND legal_entity_id IS NOT NULL) OR
        (is_super_secure = 1)
    )
);
CREATE INDEX IF NOT EXISTS idx_psc_company ON psc_ownerships(company_number);
CREATE INDEX IF NOT EXISTS idx_psc_person ON psc_ownerships(person_id);
CREATE INDEX IF NOT EXISTS idx_psc_legal ON psc_ownerships(legal_entity_id);

CREATE TABLE IF NOT EXISTS directorships (
    id                      TEXT PRIMARY KEY,
    ftm_id                  TEXT,
    ftm_schema              TEXT NOT NULL DEFAULT 'Directorship',
    company_number          TEXT NOT NULL REFERENCES companies(company_number),
    person_id               TEXT REFERENCES persons(id),
    officer_role            TEXT,
    appointed_on            TEXT,
    resigned_on             TEXT,
    is_active               INTEGER DEFAULT 1,
    occupation              TEXT,
    nationality             TEXT,
    country_of_residence    TEXT,
    api_person_id           TEXT,
    source_id               TEXT REFERENCES data_sources(id),
    fetched_via             TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dir_company ON directorships(company_number);
CREATE INDEX IF NOT EXISTS idx_dir_person ON directorships(person_id);

CREATE TABLE IF NOT EXISTS officers_fetch_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_number  TEXT NOT NULL REFERENCES companies(company_number),
    priority        INTEGER DEFAULT 5,
    status          TEXT DEFAULT 'pending',
    enqueued_at     TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    completed_at    TEXT,
    error_msg       TEXT,
    UNIQUE (company_number, status)
);

CREATE TABLE IF NOT EXISTS streaming_checkpoints (
    stream_type     TEXT PRIMARY KEY,
    last_event_id   TEXT,
    last_seq_num    INTEGER,
    last_event_at   TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Light index of the whole UK register (search + subset selection); full detail lives in `companies`
CREATE TABLE IF NOT EXISTS company_index (
    company_number      TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    name_fingerprint    TEXT,
    postcode            TEXT,
    address_fingerprint TEXT,
    company_status      TEXT,
    company_category    TEXT,
    incorporation_date  TEXT,
    source_version      TEXT
);
CREATE INDEX IF NOT EXISTS idx_company_index_name ON company_index(company_name);
CREATE INDEX IF NOT EXISTS idx_company_index_name_fp ON company_index(name_fingerprint);
CREATE INDEX IF NOT EXISTS idx_company_index_address ON company_index(address_fingerprint);
CREATE INDEX IF NOT EXISTS idx_company_index_incorporated ON company_index(incorporation_date);

-- Companies selected for full import, with the criteria that selected them
CREATE TABLE IF NOT EXISTS subset_members (
    company_number  TEXT PRIMARY KEY,
    reasons         TEXT NOT NULL,
    selected_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Bulk import runs: progress, resume point and outcome
CREATE TABLE IF NOT EXISTS ingest_runs (
    id              TEXT PRIMARY KEY,
    task            TEXT NOT NULL,
    source          TEXT,
    source_version  TEXT,
    file            TEXT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    rows_read       INTEGER NOT NULL DEFAULT 0,
    rows_written    INTEGER NOT NULL DEFAULT 0,
    last_row        INTEGER NOT NULL DEFAULT 0,
    message         TEXT,
    heartbeat_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_task ON ingest_runs(task, source_version, status);

CREATE TABLE IF NOT EXISTS sanctions (
    id                      TEXT PRIMARY KEY,
    ftm_id                  TEXT,
    ftm_schema              TEXT NOT NULL DEFAULT 'Sanction',
    subject_ftm_id          TEXT,
    name                    TEXT NOT NULL,
    name_fingerprint        TEXT,
    aliases                 TEXT DEFAULT '[]',
    entity_type             TEXT,
    topics                  TEXT DEFAULT '[]',
    countries               TEXT DEFAULT '[]',
    registration_numbers    TEXT DEFAULT '[]',
    list_name               TEXT,
    listed_on               TEXT,
    source                  TEXT,
    opensanctions_id        TEXT,
    raw_properties          TEXT DEFAULT '{}',
    source_id               TEXT REFERENCES data_sources(id),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sanctions_fingerprint ON sanctions(name_fingerprint);
CREATE INDEX IF NOT EXISTS idx_sanctions_name ON sanctions(name);
CREATE INDEX IF NOT EXISTS idx_sanctions_opensanctions_id ON sanctions(opensanctions_id);

CREATE TABLE IF NOT EXISTS pep_persons (
    id              TEXT PRIMARY KEY,
    ftm_id          TEXT,
    ftm_schema      TEXT NOT NULL DEFAULT 'Person',
    name            TEXT NOT NULL,
    name_fingerprint TEXT,
    country         TEXT,
    party           TEXT,
    legislature     TEXT,
    mandate_start   TEXT,
    mandate_end     TEXT,
    is_current      INTEGER DEFAULT 0,
    pep_source      TEXT NOT NULL,
    external_id     TEXT,
    source_id       TEXT REFERENCES data_sources(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pep_fingerprint ON pep_persons(name_fingerprint);

CREATE TABLE IF NOT EXISTS name_variants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    variant_text    TEXT NOT NULL,
    fingerprint     TEXT,
    ftm_id          TEXT,
    variant_type    TEXT,
    source_id       TEXT REFERENCES data_sources(id),
    UNIQUE (entity_id, entity_type, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_name_variants_fingerprint ON name_variants(fingerprint);
CREATE INDEX IF NOT EXISTS idx_name_variants_entity ON name_variants(entity_id, entity_type);

CREATE TABLE IF NOT EXISTS icij_entities (
    node_id                     TEXT PRIMARY KEY,
    ftm_id                      TEXT,
    ftm_schema                  TEXT NOT NULL DEFAULT 'Company',
    name                        TEXT,
    name_fingerprint            TEXT,
    original_name               TEXT,
    former_name                 TEXT,
    jurisdiction                TEXT,
    jurisdiction_description    TEXT,
    company_type                TEXT,
    address                     TEXT,
    internal_id                 TEXT,
    incorporation_date          TEXT,
    inactivation_date           TEXT,
    struck_off_date             TEXT,
    status                      TEXT,
    source_id_list              TEXT,
    valid_until                 TEXT,
    note                        TEXT,
    source_id                   TEXT REFERENCES data_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_icij_entities_fp ON icij_entities(name_fingerprint);

CREATE TABLE IF NOT EXISTS icij_officers (
    node_id         TEXT PRIMARY KEY,
    ftm_id          TEXT,
    ftm_schema      TEXT NOT NULL DEFAULT 'LegalEntity',
    name            TEXT,
    name_fingerprint TEXT,
    icij_id         TEXT,
    valid_until     TEXT,
    country_codes   TEXT,
    countries       TEXT,
    source_id_list  TEXT,
    source_id       TEXT REFERENCES data_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_icij_officers_fp ON icij_officers(name_fingerprint);

CREATE TABLE IF NOT EXISTS icij_intermediaries (
    node_id         TEXT PRIMARY KEY,
    ftm_id          TEXT,
    ftm_schema      TEXT NOT NULL DEFAULT 'LegalEntity',
    name            TEXT,
    name_fingerprint TEXT,
    status          TEXT,
    internal_id     TEXT,
    address         TEXT,
    countries       TEXT,
    country_codes   TEXT,
    source_id_list  TEXT,
    valid_until     TEXT,
    note            TEXT,
    source_id       TEXT REFERENCES data_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_icij_intermediaries_fp ON icij_intermediaries(name_fingerprint);

CREATE TABLE IF NOT EXISTS icij_addresses (
    node_id             TEXT PRIMARY KEY,
    ftm_id              TEXT,
    ftm_schema          TEXT NOT NULL DEFAULT 'Address',
    address             TEXT,
    name                TEXT,
    countries           TEXT,
    country_codes       TEXT,
    address_fingerprint TEXT,
    source_id_list      TEXT,
    valid_until         TEXT,
    note                TEXT,
    source_id           TEXT REFERENCES data_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_icij_addresses_fp ON icij_addresses(address_fingerprint);

CREATE TABLE IF NOT EXISTS icij_others (
    node_id                     TEXT PRIMARY KEY,
    ftm_id                      TEXT,
    ftm_schema                  TEXT NOT NULL DEFAULT 'LegalEntity',
    name                        TEXT,
    name_fingerprint            TEXT,
    type                        TEXT,
    incorporation_date          TEXT,
    struck_off_date             TEXT,
    closed_date                 TEXT,
    jurisdiction                TEXT,
    jurisdiction_description    TEXT,
    countries                   TEXT,
    country_codes               TEXT,
    source_id_list              TEXT,
    valid_until                 TEXT,
    note                        TEXT,
    source_id                   TEXT REFERENCES data_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_icij_others_fp ON icij_others(name_fingerprint);

CREATE TABLE IF NOT EXISTS icij_relationships (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ftm_id          TEXT,
    ftm_schema      TEXT NOT NULL DEFAULT 'UnknownLink',
    node_id_start   TEXT NOT NULL,
    node_id_end     TEXT NOT NULL,
    rel_type        TEXT,
    link            TEXT,
    status          TEXT,
    start_date      TEXT,
    end_date        TEXT,
    source_id_list  TEXT,
    source_id       TEXT REFERENCES data_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_icij_rel_start ON icij_relationships(node_id_start);
CREATE INDEX IF NOT EXISTS idx_icij_rel_end ON icij_relationships(node_id_end);

CREATE TABLE IF NOT EXISTS risk_flags (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_number      TEXT NOT NULL REFERENCES companies(company_number),
    ft3_technique       TEXT NOT NULL,
    priority            TEXT NOT NULL,
    score_contribution  REAL NOT NULL DEFAULT 0.0,
    evidence            TEXT NOT NULL DEFAULT '{}',
    source_ids          TEXT DEFAULT '[]',
    detected_at         TEXT NOT NULL DEFAULT (datetime('now')),
    is_active           INTEGER NOT NULL DEFAULT 1,
    UNIQUE (company_number, ft3_technique)
);
CREATE INDEX IF NOT EXISTS idx_risk_company ON risk_flags(company_number);
CREATE INDEX IF NOT EXISTS idx_risk_technique ON risk_flags(ft3_technique);

CREATE TABLE IF NOT EXISTS entity_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
    source          TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_entity ON entity_events(entity_type, entity_id);

-- Change history: one row per field that differed when an update overwrote a company
CREATE TABLE IF NOT EXISTS company_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_number  TEXT NOT NULL,
    change_type     TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    effective_date  TEXT,
    observed_at     TEXT NOT NULL,
    source_id       TEXT
);
CREATE INDEX IF NOT EXISTS idx_changes_company ON company_changes(company_number, observed_at);
CREATE INDEX IF NOT EXISTS idx_changes_observed ON company_changes(observed_at);

-- Companies House filing history; downloaded_path is set once the PDF is in <data folder>/documents
CREATE TABLE IF NOT EXISTS filings (
    transaction_id          TEXT PRIMARY KEY,
    company_number          TEXT NOT NULL,
    date                    TEXT,
    category                TEXT,
    type                    TEXT,
    description             TEXT,
    description_values      TEXT,
    pages                   INTEGER,
    paper_filed             INTEGER NOT NULL DEFAULT 0,
    document_metadata_url   TEXT,
    downloaded_path         TEXT,
    fetched_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_filings_company ON filings(company_number, date);

-- Casework tables (prefix casework_ in SQLite for single-file portability)
CREATE TABLE IF NOT EXISTS casework_investigations (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT,
    hypothesis      TEXT,
    classification  TEXT DEFAULT 'CONFIDENTIAL',
    status          TEXT NOT NULL DEFAULT 'open',
    priority        TEXT DEFAULT 'medium',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at       TEXT
);

CREATE TABLE IF NOT EXISTS casework_investigation_entities (
    id                  TEXT PRIMARY KEY,
    investigation_id    TEXT NOT NULL REFERENCES casework_investigations(id) ON DELETE CASCADE,
    entity_type         TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    role_in_case        TEXT DEFAULT 'subject',
    relevance_note      TEXT,
    added_at            TEXT NOT NULL DEFAULT (datetime('now')),
    notes               TEXT,
    UNIQUE (investigation_id, entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS casework_annotations (
    id                  TEXT PRIMARY KEY,
    investigation_id    TEXT NOT NULL REFERENCES casework_investigations(id) ON DELETE CASCADE,
    entity_type         TEXT,
    entity_id           TEXT,
    annotation_text     TEXT NOT NULL,
    annotation_type     TEXT DEFAULT 'note',
    confidence          TEXT DEFAULT 'moderate',
    source_grade        TEXT DEFAULT 'B2',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS casework_manual_links (
    id                  TEXT PRIMARY KEY,
    investigation_id    TEXT REFERENCES casework_investigations(id) ON DELETE SET NULL,
    from_entity_type    TEXT NOT NULL,
    from_entity_id      TEXT NOT NULL,
    to_entity_type      TEXT NOT NULL,
    to_entity_id        TEXT NOT NULL,
    link_type           TEXT,
    confidence          REAL DEFAULT 1.0,
    confidence_level    TEXT DEFAULT 'moderate',
    source_grade        TEXT DEFAULT 'C3',
    evidence            TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS casework_visual_snapshots (
    id                  TEXT PRIMARY KEY,
    investigation_id    TEXT NOT NULL REFERENCES casework_investigations(id) ON DELETE CASCADE,
    title               TEXT,
    view_type           TEXT DEFAULT 'graph',
    snapshot_png_b64    TEXT,
    graph_json          TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS casework_saved_queries (
    id                  TEXT PRIMARY KEY,
    investigation_id    TEXT REFERENCES casework_investigations(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    query_type          TEXT NOT NULL,
    query_text          TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS casework_investigation_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id    TEXT NOT NULL REFERENCES casework_investigations(id) ON DELETE CASCADE,
    event_type          TEXT NOT NULL,
    description         TEXT,
    metadata            TEXT DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS casework_generated_reports (
    id                  TEXT PRIMARY KEY,
    investigation_id    TEXT REFERENCES casework_investigations(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    format              TEXT NOT NULL,
    file_path           TEXT,
    file_size_bytes     INTEGER,
    sha256_hash         TEXT,
    generated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    generation_params   TEXT DEFAULT '{}'
);
"""


def _parse_json_field(val: Any, default: Any) -> Any:
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return default
        try:
            return json.loads(val)
        except Exception:
            return default
    return default


class DatabaseService:
    """High-level database & FollowTheMoney (FtM v3.x) service."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        return get_sqlite_connection(self.db_path)

    def ensure_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(SQLITE_SCHEMA_DDL)
            self._migrate_sqlite(conn)
            conn.execute(
                """
                INSERT OR IGNORE INTO streaming_checkpoints (stream_type)
                VALUES ('officers'), ('psc'), ('company_profile')
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _migrate_sqlite(conn: sqlite3.Connection) -> None:
        """Bring databases created by older versions up to the current schema (idempotent)."""
        run_cols = {r["name"] for r in conn.execute("PRAGMA table_info(ingest_runs)")}
        if run_cols and "heartbeat_at" not in run_cols:
            conn.execute("ALTER TABLE ingest_runs ADD COLUMN heartbeat_at TEXT")
        geo_cols = {r["name"] for r in conn.execute("PRAGMA table_info(geo_postcode_centroids)")}
        if "precision" not in geo_cols:
            conn.execute("ALTER TABLE geo_postcode_centroids ADD COLUMN precision TEXT")
            # Rows written before 0.3.0 carry a random offset around an area centroid:
            # drop them so positions are re-resolved with an explicit precision.
            conn.execute("DELETE FROM geo_postcode_centroids")

    # ------------------------------------------------------------------ #
    # DATA SOURCES & PROVENANCE                                          #
    # ------------------------------------------------------------------ #

    def register_data_source(
        self,
        source_name: str,
        source_type: str,
        source_version: str = "2026-01",
        source_url: str | None = None,
        file_hash: str | None = None,
        record_count: int | None = None,
        notes: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        own_conn = conn is None
        c = conn or self.connect()
        try:
            row = c.execute(
                "SELECT id FROM data_sources WHERE source_name = ? AND source_version = ?",
                (source_name, source_version),
            ).fetchone()
            if row:
                source_id = str(row["id"])
                if record_count is not None:
                    c.execute(
                        "UPDATE data_sources SET record_count = ?, collected_at = datetime('now') WHERE id = ?",
                        (record_count, source_id),
                    )
            else:
                source_id = str(uuid.uuid4())
                c.execute(
                    """
                    INSERT INTO data_sources
                        (id, source_name, source_type, source_version, source_url, file_hash, record_count, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        source_name,
                        source_type,
                        source_version,
                        source_url,
                        file_hash,
                        record_count,
                        notes,
                    ),
                )
            if own_conn:
                c.commit()
            return source_id
        finally:
            if own_conn:
                c.close()

    # ------------------------------------------------------------------ #
    # FOLLOW THE MONEY (FtM v3.x) CANONICAL STORE                        #
    # ------------------------------------------------------------------ #

    def upsert_ftm_entity(
        self,
        entity: dict[str, Any],
        source_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        """Upsert a FollowTheMoney entity into `ftm_entities`, merging properties and datasets."""
        valid, errors = validate_ftm_entity(entity)
        if not valid:
            log.warning("ftm_validation_warning", id=entity.get("id"), errors=errors)

        own_conn = conn is None
        c = conn or self.connect()
        try:
            entity_id = str(entity["id"])
            schema_name = str(entity["schema"])
            caption = str(entity.get("caption") or schema_name)[:500]
            new_props = entity.get("properties") or {}
            new_datasets = list(entity.get("datasets") or [])
            new_referents = list(entity.get("referents") or [])
            target = 1 if entity.get("target") else 0
            now_iso = datetime.now(timezone.utc).isoformat()

            existing = c.execute(
                "SELECT properties, datasets, referents, target FROM ftm_entities WHERE id = ?",
                (entity_id,),
            ).fetchone()

            if existing:
                merged_props = _parse_json_field(existing["properties"], {})
                for prop, values in new_props.items():
                    cur_vals = merged_props.get(prop, [])
                    for v in values:
                        if v not in cur_vals:
                            cur_vals.append(v)
                    if cur_vals:
                        merged_props[prop] = cur_vals

                merged_datasets = _parse_json_field(existing["datasets"], [])
                for ds in new_datasets:
                    if ds not in merged_datasets:
                        merged_datasets.append(ds)

                merged_referents = _parse_json_field(existing["referents"], [])
                for ref in new_referents:
                    if ref not in merged_referents:
                        merged_referents.append(ref)

                merged_target = 1 if (existing["target"] or target) else 0

                c.execute(
                    """
                    UPDATE ftm_entities
                    SET caption = ?,
                        properties = ?,
                        datasets = ?,
                        referents = ?,
                        target = ?,
                        last_seen = ?,
                        last_change = ?
                    WHERE id = ?
                    """,
                    (
                        caption,
                        json.dumps(merged_props, ensure_ascii=False),
                        json.dumps(merged_datasets, ensure_ascii=False),
                        json.dumps(merged_referents, ensure_ascii=False),
                        merged_target,
                        now_iso,
                        now_iso,
                        entity_id,
                    ),
                )
            else:
                c.execute(
                    """
                    INSERT INTO ftm_entities
                        (id, schema, caption, properties, datasets, referents, target, first_seen, last_seen, last_change, source_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        schema_name,
                        caption,
                        json.dumps(new_props, ensure_ascii=False),
                        json.dumps(new_datasets, ensure_ascii=False),
                        json.dumps(new_referents, ensure_ascii=False),
                        target,
                        entity.get("first_seen", now_iso),
                        entity.get("last_seen", now_iso),
                        entity.get("last_change", now_iso),
                        source_id,
                    ),
                )
            if own_conn:
                c.commit()
            return entity_id
        finally:
            if own_conn:
                c.close()

    def get_ftm_entity(self, ftm_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ftm_entities WHERE id = ?",
                (ftm_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_ftm_dict(row)
        finally:
            conn.close()

    def _row_to_ftm_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "schema": row["schema"],
            "caption": row["caption"],
            "properties": _parse_json_field(row["properties"], {}),
            "datasets": _parse_json_field(row["datasets"], []),
            "referents": _parse_json_field(row["referents"], []),
            "target": bool(row["target"]),
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "last_change": row["last_change"],
        }

    def iter_ftm_entities(
        self,
        schema: str | None = None,
        dataset: str | None = None,
        target_only: bool = False,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        conn = self.connect()
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if schema:
                clauses.append("schema = ?")
                params.append(schema)
            if dataset:
                clauses.append("datasets LIKE ?")
                params.append(f'%"{dataset}"%')
            if target_only:
                clauses.append("target = 1")
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            limit_sql = f"LIMIT {int(limit)}" if limit else ""
            cursor = conn.execute(
                f"SELECT * FROM ftm_entities {where_sql} ORDER BY target DESC, last_change DESC {limit_sql}",
                params,
            )
            for row in cursor:
                yield self._row_to_ftm_dict(row)
        finally:
            conn.close()

    def export_ftm_jsonl(
        self,
        output_path: Path | str,
        schema: str | None = None,
        dataset: str | None = None,
        target_only: bool = False,
        limit: int | None = None,
    ) -> int:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with out.open("w", encoding="utf-8") as fh:
            for entity in self.iter_ftm_entities(
                schema=schema,
                dataset=dataset,
                target_only=target_only,
                limit=limit,
            ):
                fh.write(json.dumps(entity, ensure_ascii=False) + "\n")
                count += 1
        return count

    def import_ftm_jsonl(self, input_path: Path | str, dataset_override: str | None = None) -> int:
        inp = Path(input_path)
        conn = self.connect()
        count = 0
        try:
            source_id = self.register_data_source(
                source_name=dataset_override or inp.stem,
                source_type="ftm_jsonl",
                source_version=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                source_url=str(inp),
                conn=conn,
            )
            with inp.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    entity = json.loads(line)
                    if dataset_override:
                        ds = list(entity.get("datasets") or [])
                        if dataset_override not in ds:
                            ds.append(dataset_override)
                        entity["datasets"] = ds
                    self.upsert_ftm_entity(entity, source_id=source_id, conn=conn)
                    count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def get_ftm_stats(self) -> dict[str, Any]:
        conn = self.connect()
        try:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM ftm_entities").fetchone()["cnt"]
            targets = conn.execute("SELECT COUNT(*) AS cnt FROM ftm_entities WHERE target = 1").fetchone()["cnt"]
            by_schema = {
                row["schema"]: row["cnt"]
                for row in conn.execute(
                    "SELECT schema, COUNT(*) AS cnt FROM ftm_entities GROUP BY schema ORDER BY cnt DESC"
                ).fetchall()
            }
            return {
                "total_entities": total,
                "target_entities": targets,
                "by_schema": by_schema,
                "ontology_version": "FollowTheMoney v3.x",
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # DASHBOARD & SEARCH                                                 #
    # ------------------------------------------------------------------ #

    def get_dashboard_stats(self) -> dict[str, Any]:
        conn = self.connect()
        try:
            companies_cnt = conn.execute("SELECT COUNT(*) AS c FROM companies").fetchone()["c"]
            flagged_cnt = conn.execute("SELECT COUNT(*) AS c FROM companies WHERE is_flagged = 1").fetchone()["c"]
            persons_cnt = conn.execute("SELECT COUNT(*) AS c FROM persons").fetchone()["c"]
            legal_cnt = conn.execute("SELECT COUNT(*) AS c FROM legal_entities").fetchone()["c"]
            psc_cnt = conn.execute("SELECT COUNT(*) AS c FROM psc_ownerships").fetchone()["c"]
            dir_cnt = conn.execute("SELECT COUNT(*) AS c FROM directorships").fetchone()["c"]
            sanctions_cnt = conn.execute("SELECT COUNT(*) AS c FROM sanctions").fetchone()["c"]
            icij_ent_cnt = conn.execute("SELECT COUNT(*) AS c FROM icij_entities").fetchone()["c"]
            icij_off_cnt = conn.execute("SELECT COUNT(*) AS c FROM icij_officers").fetchone()["c"]
            icij_rel_cnt = conn.execute("SELECT COUNT(*) AS c FROM icij_relationships").fetchone()["c"]
            flags_cnt = conn.execute("SELECT COUNT(*) AS c FROM risk_flags WHERE is_active = 1").fetchone()["c"]
            ftm_cnt = conn.execute("SELECT COUNT(*) AS c FROM ftm_entities").fetchone()["c"]
            cases_cnt = conn.execute("SELECT COUNT(*) AS c FROM casework_investigations").fetchone()["c"]

            ft3_breakdown = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT ft3_technique, priority, COUNT(*) AS count, ROUND(AVG(score_contribution), 1) AS avg_score
                    FROM risk_flags
                    WHERE is_active = 1
                    GROUP BY ft3_technique, priority
                    ORDER BY count DESC
                    """
                ).fetchall()
            ]

            top_flagged = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT company_number, company_name, company_status, reg_address_post_town,
                           reg_address_postcode, risk_score, ft3_techniques, ftm_id
                    FROM companies
                    WHERE is_flagged = 1
                    ORDER BY risk_score DESC, company_name ASC
                    LIMIT 15
                    """
                ).fetchall()
            ]
            for item in top_flagged:
                item["ft3_techniques"] = _parse_json_field(item.get("ft3_techniques"), [])

            sources = [
                dict(row)
                for row in conn.execute(
                    "SELECT source_name, source_type, source_version, record_count, collected_at FROM data_sources ORDER BY collected_at DESC"
                ).fetchall()
            ]

            return {
                "counts": {
                    "companies": companies_cnt,
                    "flagged_companies": flagged_cnt,
                    "persons": persons_cnt,
                    "legal_entities": legal_cnt,
                    "psc_ownerships": psc_cnt,
                    "directorships": dir_cnt,
                    "sanctions": sanctions_cnt,
                    "icij_entities": icij_ent_cnt,
                    "icij_officers": icij_off_cnt,
                    "icij_relationships": icij_rel_cnt,
                    "risk_flags": flags_cnt,
                    "ftm_entities": ftm_cnt,
                    "investigations": cases_cnt,
                },
                "ft3_breakdown": ft3_breakdown,
                "top_flagged": top_flagged,
                "data_sources": sources,
                "ftm": self.get_ftm_stats(),
            }
        finally:
            conn.close()

    def search_companies(
        self,
        query: str = "",
        status: str | None = None,
        min_risk: float = 0.0,
        ft3_technique: str | None = None,
        flagged_only: bool = False,
        postcode: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            clauses: list[str] = []
            params: list[Any] = []

            q = (query or "").strip()
            if q:
                fp = normalize_name(q) or q.lower()
                clauses.append(
                    "(company_number LIKE ? OR company_name LIKE ? OR name_fingerprint LIKE ? OR reg_address_postcode LIKE ? OR reg_address_line1 LIKE ?)"
                )
                params.extend([f"%{q.upper()}%", f"%{q}%", f"%{fp}%", f"%{q.upper()}%", f"%{q}%"])

            if status:
                clauses.append("company_status LIKE ?")
                params.append(f"%{status}%")

            if min_risk > 0:
                clauses.append("risk_score >= ?")
                params.append(float(min_risk))

            if flagged_only:
                clauses.append("is_flagged = 1")

            if ft3_technique:
                clauses.append("ft3_techniques LIKE ?")
                params.append(f'%"{ft3_technique}"%')

            if postcode:
                norm_pc = normalize_postcode(postcode) or postcode.upper().strip()
                clauses.append("reg_address_postcode LIKE ?")
                params.append(f"{norm_pc}%")

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM companies {where_sql}",
                params,
            ).fetchone()["cnt"]

            rows = conn.execute(
                f"""
                SELECT c.company_number, c.company_name, c.ftm_id, c.ftm_schema,
                       c.company_status, c.company_category, c.incorporation_date, c.dissolution_date,
                       c.reg_address_line1, c.reg_address_post_town, c.reg_address_postcode,
                       c.address_fingerprint, c.sic_code_1, c.sic_text_1,
                       c.risk_score, c.ft3_techniques, c.is_flagged,
                       g.lat, g.lon
                FROM companies c
                LEFT JOIN geo_postcode_centroids g ON g.postcode = c.reg_address_postcode
                {where_sql.replace('company_', 'c.company_').replace('name_fingerprint', 'c.name_fingerprint').replace('reg_address_', 'c.reg_address_').replace('risk_score', 'c.risk_score').replace('is_flagged', 'c.is_flagged').replace('ft3_techniques', 'c.ft3_techniques')}
                ORDER BY c.risk_score DESC, c.is_flagged DESC, c.company_name ASC
                LIMIT ? OFFSET ?
                """,
                [*params, int(limit), int(offset)],
            ).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                d["ft3_techniques"] = _parse_json_field(d.get("ft3_techniques"), [])
                d["is_flagged"] = bool(d.get("is_flagged"))
                results.append(d)

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": results,
            }
        finally:
            conn.close()

    def get_company_dossier(self, company_number: str) -> dict[str, Any] | None:
        """Return full multi-source intelligence dossier for a UK company."""
        from src.intelligence.ft3_mapper import get_technique_metadata

        conn = self.connect()
        try:
            comp_row = conn.execute(
                """
                SELECT c.*, g.lat, g.lon, g.admin_district
                FROM companies c
                LEFT JOIN geo_postcode_centroids g ON g.postcode = c.reg_address_postcode
                WHERE c.company_number = ?
                """,
                (company_number.strip().upper(),),
            ).fetchone()
            if not comp_row:
                return None

            company = dict(comp_row)
            company["ft3_techniques"] = _parse_json_field(company.get("ft3_techniques"), [])
            company["is_flagged"] = bool(company.get("is_flagged"))

            # FtM canonical representation
            ftm_entity = None
            if company.get("ftm_id"):
                ftm_row = conn.execute(
                    "SELECT * FROM ftm_entities WHERE id = ?",
                    (company["ftm_id"],),
                ).fetchone()
                if ftm_row:
                    ftm_entity = self._row_to_ftm_dict(ftm_row)
            if not ftm_entity:
                ftm_entity = company_to_ftm(company)

            # PSC Ownerships
            psc_rows = conn.execute(
                """
                SELECT po.*,
                       p.name AS person_name, p.nationality AS person_nationality,
                       p.country_of_residence AS person_residence,
                       p.dob_month, p.dob_year, p.is_pep, p.ftm_id AS person_ftm_id,
                       le.name AS legal_entity_name, le.jurisdiction AS legal_entity_jurisdiction,
                       le.entity_type AS legal_entity_type, le.is_offshore, le.ftm_id AS legal_entity_ftm_id
                FROM psc_ownerships po
                LEFT JOIN persons p ON p.id = po.person_id
                LEFT JOIN legal_entities le ON le.id = po.legal_entity_id
                WHERE po.company_number = ?
                ORDER BY po.is_ceased ASC, po.notified_on DESC
                """,
                (company["company_number"],),
            ).fetchall()
            pscs = []
            for r in psc_rows:
                item = dict(r)
                item["nature_of_control"] = _parse_json_field(item.get("nature_of_control"), [])
                item["is_ceased"] = bool(item.get("is_ceased"))
                item["is_super_secure"] = bool(item.get("is_super_secure"))
                pscs.append(item)

            # Directorships
            dir_rows = conn.execute(
                """
                SELECT d.*, p.name AS person_name, p.dob_month, p.dob_year, p.is_pep, p.ftm_id AS person_ftm_id,
                       (SELECT COUNT(DISTINCT d2.company_number) FROM directorships d2 WHERE d2.person_id = d.person_id) AS total_appointments
                FROM directorships d
                LEFT JOIN persons p ON p.id = d.person_id
                WHERE d.company_number = ?
                ORDER BY d.is_active DESC, d.appointed_on DESC
                """,
                (company["company_number"],),
            ).fetchall()
            directorships = [dict(r) for r in dir_rows]

            # Risk Flags with FT3 metadata
            flag_rows = conn.execute(
                """
                SELECT * FROM risk_flags
                WHERE company_number = ? AND is_active = 1
                ORDER BY score_contribution DESC
                """,
                (company["company_number"],),
            ).fetchall()
            risk_flags = []
            for r in flag_rows:
                f = dict(r)
                f["evidence"] = _parse_json_field(f.get("evidence"), {})
                f["source_ids"] = _parse_json_field(f.get("source_ids"), [])
                meta = get_technique_metadata(f["ft3_technique"])
                f["technique_name"] = meta["name"]
                f["tactic"] = meta["tactic"]
                f["description"] = meta["description"]
                f["innocent_explanations"] = meta["innocent_explanations"]
                f["unodc_grade"] = meta["default_grade"]
                risk_flags.append(f)

            # Co-located companies at same address fingerprint or postcode
            colocated = []
            if company.get("address_fingerprint"):
                colocated = [
                    dict(r)
                    for r in conn.execute(
                        """
                        SELECT company_number, company_name, company_status, incorporation_date, risk_score, is_flagged
                        FROM companies
                        WHERE address_fingerprint = ? AND company_number != ?
                        ORDER BY risk_score DESC
                        LIMIT 25
                        """,
                        (company["address_fingerprint"], company["company_number"]),
                    ).fetchall()
                ]
            colocated_count = (
                conn.execute(
                    "SELECT COUNT(*) AS c FROM companies WHERE address_fingerprint = ?",
                    (company["address_fingerprint"],),
                ).fetchone()["c"]
                if company.get("address_fingerprint")
                else 1
            )

            # Direct sanction matches (by company_number in registration_numbers or name_fingerprint)
            sanction_matches = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, ftm_id, name, entity_type, list_name, listed_on, countries, registration_numbers, opensanctions_id
                    FROM sanctions
                    WHERE registration_numbers LIKE ?
                       OR (name_fingerprint IS NOT NULL AND name_fingerprint != '' AND name_fingerprint = ?)
                    LIMIT 20
                    """,
                    (f'%"{company["company_number"]}"%', company.get("name_fingerprint") or "__none__"),
                ).fetchall()
            ]
            for sm in sanction_matches:
                sm["countries"] = _parse_json_field(sm.get("countries"), [])
                sm["registration_numbers"] = _parse_json_field(sm.get("registration_numbers"), [])

            # ICIJ Offshore matches (by company name_fingerprint or PSC legal_entity / officer fingerprints)
            fingerprints_to_check = {company.get("name_fingerprint")}
            for psc in pscs:
                if psc.get("person_name"):
                    fingerprints_to_check.add(normalize_name(psc["person_name"]))
                if psc.get("legal_entity_name"):
                    fingerprints_to_check.add(normalize_name(psc["legal_entity_name"]))
            for d in directorships:
                if d.get("person_name"):
                    fingerprints_to_check.add(normalize_name(d["person_name"]))
            fingerprints_to_check.discard(None)
            fingerprints_to_check.discard("")

            icij_matches: list[dict[str, Any]] = []
            if fingerprints_to_check:
                placeholders = ",".join("?" for _ in fingerprints_to_check)
                fp_list = list(fingerprints_to_check)
                icij_ent = conn.execute(
                    f"""
                    SELECT node_id, ftm_id, 'Offshore Entity' AS match_category, name, jurisdiction,
                           jurisdiction_description, incorporation_date, status, source_id_list
                    FROM icij_entities
                    WHERE name_fingerprint IN ({placeholders})
                    LIMIT 15
                    """,
                    fp_list,
                ).fetchall()
                icij_off = conn.execute(
                    f"""
                    SELECT node_id, ftm_id, 'Offshore Officer' AS match_category, name, country_codes AS jurisdiction,
                           countries AS jurisdiction_description, '' AS incorporation_date, '' AS status, source_id_list
                    FROM icij_officers
                    WHERE name_fingerprint IN ({placeholders})
                    LIMIT 15
                    """,
                    fp_list,
                ).fetchall()
                icij_matches = [dict(r) for r in [*icij_ent, *icij_off]]

            # Timeline construction
            timeline: list[dict[str, Any]] = []
            if company.get("incorporation_date"):
                timeline.append(
                    {
                        "date": company["incorporation_date"],
                        "event_type": "INCORPORATION",
                        "title": f"Incorporated as {company['company_name']}",
                        "source": "Companies House (A1)",
                        "severity": "info",
                    }
                )
            for idx in range(1, 11):
                p_date = company.get(f"prev_name_{idx}_date")
                p_name = company.get(f"prev_name_{idx}")
                if p_date and p_name:
                    timeline.append(
                        {
                            "date": p_date,
                            "event_type": "NAME_CHANGE",
                            "title": f"Previous name ceased: {p_name}",
                            "source": "Companies House (A1)",
                            "severity": "warning",
                        }
                    )
            for psc in pscs:
                owner_label = psc.get("person_name") or psc.get("legal_entity_name") or "Super-Secure PSC"
                if psc.get("notified_on"):
                    timeline.append(
                        {
                            "date": psc["notified_on"],
                            "event_type": "PSC_NOTIFIED",
                            "title": f"PSC notified: {owner_label}",
                            "source": "CH PSC Register (B2)",
                            "severity": "info",
                        }
                    )
                if psc.get("ceased_on"):
                    timeline.append(
                        {
                            "date": psc["ceased_on"],
                            "event_type": "PSC_CEASED",
                            "title": f"PSC ceased: {owner_label}",
                            "source": "CH PSC Register (B2)",
                            "severity": "warning",
                        }
                    )
            for d in directorships:
                if d.get("appointed_on"):
                    timeline.append(
                        {
                            "date": d["appointed_on"],
                            "event_type": "OFFICER_APPOINTED",
                            "title": f"Officer appointed: {d.get('person_name')} ({d.get('officer_role')})",
                            "source": "CH Officers (B2)",
                            "severity": "info",
                        }
                    )
                if d.get("resigned_on"):
                    timeline.append(
                        {
                            "date": d["resigned_on"],
                            "event_type": "OFFICER_RESIGNED",
                            "title": f"Officer resigned: {d.get('person_name')} ({d.get('officer_role')})",
                            "source": "CH Officers (B2)",
                            "severity": "warning",
                        }
                    )
            for sm in sanction_matches:
                if sm.get("listed_on"):
                    timeline.append(
                        {
                            "date": sm["listed_on"],
                            "event_type": "SANCTION_DESIGNATION",
                            "title": f"Designated on {sm.get('list_name')}: {sm.get('name')}",
                            "source": "UK FCDO / OFSI (A1)",
                            "severity": "critical",
                        }
                    )
            if company.get("dissolution_date"):
                timeline.append(
                    {
                        "date": company["dissolution_date"],
                        "event_type": "DISSOLUTION",
                        "title": "Company dissolved",
                        "source": "Companies House (A1)",
                        "severity": "critical",
                    }
                )
            # Observed changes; names, appointments and PSC already appear above with the registry's dates
            from src.etl.company_changes import COMPANY_FIELDS, list_changes  # src.etl imports this module

            changes = list_changes(conn, company_number=company["company_number"], limit=500)
            for ch in changes:
                if ch["change_type"] not in COMPANY_FIELDS or ch["change_type"] == "NAME_CHANGED":
                    continue
                timeline.append(
                    {
                        "date": ch["effective_date"] or ch["observed_at"][:10],
                        "event_type": ch["change_type"],
                        "title": f"{ch['old_value'] or '—'} → {ch['new_value'] or '—'}",
                        "source": f"Observed {ch['observed_at'][:10]} ({ch['source'] or 'update'})",
                        "severity": "warning" if ch["change_type"] in ("ADDRESS_CHANGED", "STATUS_CHANGED") else "info",
                    }
                )
            for f in conn.execute(
                "SELECT date, category, type, description FROM filings WHERE company_number = ?",
                (company["company_number"],),
            ):
                if f["date"]:
                    timeline.append(
                        {
                            "date": f["date"],
                            "event_type": "FILING",
                            "title": f"{f['type'] or ''} {(f['description'] or '').replace('-', ' ')}".strip(),
                            "source": f"CH filing history ({f['category'] or 'other'})",
                            "severity": "info",
                        }
                    )
            timeline.sort(key=lambda x: str(x.get("date") or ""), reverse=True)

            # Casework annotations for this company
            annotations = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT a.*, i.title AS investigation_title
                    FROM casework_annotations a
                    LEFT JOIN casework_investigations i ON i.id = a.investigation_id
                    WHERE a.entity_type = 'company' AND a.entity_id = ?
                    ORDER BY a.created_at DESC
                    """,
                    (company["company_number"],),
                ).fetchall()
            ]

            return {
                "company": company,
                "ftm_entity": ftm_entity,
                "psc_ownerships": pscs,
                "directorships": directorships,
                "risk_flags": risk_flags,
                "colocated_companies": colocated,
                "colocated_total": colocated_count,
                "sanction_matches": sanction_matches,
                "icij_matches": icij_matches,
                "timeline": timeline,
                "changes": changes,
                "annotations": annotations,
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # CASEWORK MANAGEMENT                                                #
    # ------------------------------------------------------------------ #

    def list_investigations(self) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                """
                SELECT i.*,
                       (SELECT COUNT(*) FROM casework_investigation_entities ie WHERE ie.investigation_id = i.id) AS entity_count,
                       (SELECT COUNT(*) FROM casework_annotations a WHERE a.investigation_id = i.id) AS annotation_count,
                       (SELECT COUNT(*) FROM casework_generated_reports r WHERE r.investigation_id = i.id) AS report_count
                FROM casework_investigations i
                ORDER BY i.updated_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_investigation(
        self,
        title: str,
        description: str = "",
        hypothesis: str = "",
        priority: str = "high",
        classification: str = "CONFIDENTIAL",
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            inv_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO casework_investigations
                    (id, title, description, hypothesis, classification, status, priority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (inv_id, title, description, hypothesis, classification, priority, now, now),
            )
            conn.execute(
                """
                INSERT INTO casework_investigation_events
                    (investigation_id, event_type, description, created_at)
                VALUES (?, 'CASE_OPENED', ?, ?)
                """,
                (inv_id, f"Investigation '{title}' opened with classification {classification}", now),
            )
            conn.commit()
            return self.get_investigation(inv_id) or {"id": inv_id, "title": title}
        finally:
            conn.close()

    def get_investigation(self, investigation_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            inv_row = conn.execute(
                "SELECT * FROM casework_investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if not inv_row:
                return None
            inv = dict(inv_row)

            entities = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT ie.*, c.company_name, c.risk_score, c.company_status, c.ftm_id
                    FROM casework_investigation_entities ie
                    LEFT JOIN companies c ON ie.entity_type = 'company' AND c.company_number = ie.entity_id
                    WHERE ie.investigation_id = ?
                    ORDER BY ie.added_at DESC
                    """,
                    (investigation_id,),
                ).fetchall()
            ]
            annotations = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM casework_annotations WHERE investigation_id = ? ORDER BY created_at DESC",
                    (investigation_id,),
                ).fetchall()
            ]
            links = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM casework_manual_links WHERE investigation_id = ? ORDER BY created_at DESC",
                    (investigation_id,),
                ).fetchall()
            ]
            events = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM casework_investigation_events WHERE investigation_id = ? ORDER BY created_at DESC",
                    (investigation_id,),
                ).fetchall()
            ]
            reports = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM casework_generated_reports WHERE investigation_id = ? ORDER BY generated_at DESC",
                    (investigation_id,),
                ).fetchall()
            ]
            inv["entities"] = entities
            inv["annotations"] = annotations
            inv["manual_links"] = links
            inv["events"] = events
            inv["reports"] = reports
            return inv
        finally:
            conn.close()

    def add_entity_to_investigation(
        self,
        investigation_id: str,
        entity_type: str,
        entity_id: str,
        role_in_case: str = "subject",
        notes: str = "",
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            rec_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO casework_investigation_entities
                    (id, investigation_id, entity_type, entity_id, role_in_case, relevance_note, added_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rec_id, investigation_id, entity_type, entity_id, role_in_case, notes, now, notes),
            )
            conn.execute(
                """
                INSERT INTO casework_investigation_events
                    (investigation_id, event_type, description, created_at)
                VALUES (?, 'ENTITY_ADDED', ?, ?)
                """,
                (investigation_id, f"Added {entity_type} {entity_id} as {role_in_case}", now),
            )
            conn.execute(
                "UPDATE casework_investigations SET updated_at = ? WHERE id = ?",
                (now, investigation_id),
            )
            conn.commit()
            return {"id": rec_id, "investigation_id": investigation_id, "entity_type": entity_type, "entity_id": entity_id}
        finally:
            conn.close()

    def add_annotation(
        self,
        investigation_id: str,
        annotation_text: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        annotation_type: str = "finding",
        confidence: str = "high",
        source_grade: str = "A1",
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            ann_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO casework_annotations
                    (id, investigation_id, entity_type, entity_id, annotation_text, annotation_type, confidence, source_grade, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ann_id,
                    investigation_id,
                    entity_type,
                    entity_id,
                    annotation_text,
                    annotation_type,
                    confidence,
                    source_grade,
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE casework_investigations SET updated_at = ? WHERE id = ?",
                (now, investigation_id),
            )
            conn.commit()
            return {
                "id": ann_id,
                "investigation_id": investigation_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "annotation_text": annotation_text,
                "annotation_type": annotation_type,
                "confidence": confidence,
                "source_grade": source_grade,
                "created_at": now,
            }
        finally:
            conn.close()
