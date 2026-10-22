"""ETL Importer for Companies House PSC Snapshot (`dati/persons-with-significant-control-snapshot-*.txt`).

Handles all 6 PSC `data.kind` types:
  - `individual-person-with-significant-control`
  - `individual-beneficial-owner` (Register of Overseas Entities `OE...`)
  - `corporate-entity-person-with-significant-control`
  - `corporate-entity-beneficial-owner`
  - `legal-person-person-with-significant-control`
  - `super-secure-person-with-significant-control` (`person_id = NULL, legal_entity_id = NULL, is_super_secure = 1`)

Crucially, if `company_number` is not yet in `companies` (e.g. dissolved company or Overseas Entity),
auto-inserts a stub `companies` row (`Dissolved / Historical (from PSC)` or `Overseas Entity`)
to prevent foreign-key failures and preserve historical phoenix company networks (`FT3-SC-015`).
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.ftm import (
    company_to_ftm,
    directorship_to_ftm,
    legal_entity_to_ftm,
    make_ftm_id,
    person_to_ftm,
    psc_to_ftm_ownership,
)
from src.core.logging import get_logger
from src.core.normalizer import compute_address_fingerprint, normalize_name, normalize_postcode
from src.etl.company_changes import add_change
from src.services.db_service import DatabaseService

log = get_logger(__name__)

OFFSHORE_KEYWORDS = {
    "british virgin islands",
    "bvi",
    "cayman",
    "cayman islands",
    "panama",
    "seychelles",
    "belize",
    "bahamas",
    "bermuda",
    "jersey",
    "guernsey",
    "isle of man",
    "liechtenstein",
    "marshall islands",
    "curacao",
    "mauritius",
    "gibraltar",
    "cyprus",
    "malta",
    "delaware",
    "luxembourg",
}


def _is_offshore_jurisdiction(jur: str | None) -> bool:
    if not jur:
        return False
    low = jur.lower().strip()
    return any(kw in low for kw in OFFSHORE_KEYWORDS)


def ingest_psc_record(
    conn: Any,
    db: DatabaseService,
    comp_num: str,
    data: dict[str, Any],
    source_id: str | None,
    now: str,
    existing_companies: set[str],
    counts: dict[str, int],
) -> None:
    """Write one PSC statement (bulk snapshot `data` or API item) and its FtM entities.

    Ids are deterministic, so ingesting the same statement twice updates instead of duplicating.
    A stub company is created when the company is not in the database yet.
    """
    kind = (data.get("kind") or "").strip()
    notified_on = data.get("notified_on")
    ceased_on = data.get("ceased_on")
    is_ceased = 1 if (ceased_on or data.get("ceased")) else 0
    natures = data.get("natures_of_control") or []
    addr = data.get("address") or {}
    postcode = normalize_postcode(addr.get("postal_code")) or addr.get("postal_code")

    # Ensure company exists (auto-create historical/dissolved or Overseas Entity stub if missing)
    if comp_num not in existing_companies:
        is_oe = comp_num.startswith("OE")
        stub_status = "Overseas Entity (ROE)" if is_oe else "Dissolved"
        stub_name = f"HISTORICAL UK ENTITY {comp_num}" if not is_oe else f"OVERSEAS ENTITY {comp_num}"
        stub_dissolution = ceased_on if not is_oe else None
        addr_fp = compute_address_fingerprint(
            postcode,
            addr.get("address_line_1") or addr.get("premises"),
            addr.get("locality"),
        )
        stub_rec = {
            "company_number": comp_num,
            "company_name": stub_name,
            "company_status": stub_status,
            "company_category": "Overseas Entity" if is_oe else "Private Limited Company (Historical)",
            "incorporation_date": notified_on,
            "dissolution_date": stub_dissolution,
            "reg_address_line1": addr.get("address_line_1") or addr.get("premises"),
            "reg_address_post_town": addr.get("locality"),
            "reg_address_postcode": postcode,
            "reg_address_country": addr.get("country") or "United Kingdom",
            "address_fingerprint": addr_fp,
            "name_fingerprint": normalize_name(stub_name),
        }
        comp_ftm = company_to_ftm(stub_rec)
        conn.execute(
            """
            INSERT OR IGNORE INTO companies
                (company_number, company_name, ftm_id, ftm_schema, company_status, company_category,
                 incorporation_date, dissolution_date, reg_address_line1, reg_address_post_town,
                 reg_address_postcode, reg_address_country, address_fingerprint, name_fingerprint,
                 source_id, created_at, updated_at)
            VALUES (?, ?, ?, 'Company', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comp_num,
                stub_name,
                comp_ftm["id"],
                stub_status,
                stub_rec["company_category"],
                notified_on,
                stub_dissolution,
                stub_rec["reg_address_line1"],
                stub_rec["reg_address_post_town"],
                postcode,
                stub_rec["reg_address_country"],
                addr_fp,
                stub_rec["name_fingerprint"],
                source_id,
                now,
                now,
            ),
        )
        db.upsert_ftm_entity(comp_ftm, source_id=source_id, conn=conn)
        existing_companies.add(comp_num)
        counts["stub_companies"] += 1
        counts["ftm_entities"] += 1

    company_ftm_id = make_ftm_id("Company", "gb", comp_num)
    etag_or_link = (data.get("links") or {}).get("self") or data.get("etag") or f"{comp_num}:{counts['psc_ownerships']}"
    psc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"psc:{comp_num}:{etag_or_link}"))

    person_id: str | None = None
    legal_entity_id: str | None = None
    owner_ftm_id: str | None = None
    is_super_secure = 0

    if "super-secure" in kind:
        is_super_secure = 1
    elif "corporate-entity" in kind or "legal-person" in kind:
        raw_name = (data.get("name") or f"Corporate Controller ({comp_num})").strip()
        fp = normalize_name(raw_name)
        ident = data.get("identification") or {}
        jur = ident.get("country_registered") or ident.get("legal_authority") or addr.get("country")
        reg_no = ident.get("registration_number")
        is_off = 1 if _is_offshore_jurisdiction(jur) else 0

        le_ftm_id = make_ftm_id("legal_entity", fp or raw_name, jur or "", reg_no or "")
        owner_ftm_id = le_ftm_id
        existing_le = conn.execute(
            "SELECT id FROM legal_entities WHERE ftm_id = ?",
            (le_ftm_id,),
        ).fetchone()
        if existing_le:
            legal_entity_id = existing_le["id"]
        else:
            legal_entity_id = str(uuid.uuid4())
            le_rec = {
                "id": legal_entity_id,
                "name": raw_name,
                "name_fingerprint": fp,
                "jurisdiction": jur,
                "company_number_foreign": reg_no,
                "entity_type": kind,
                "is_offshore": bool(is_off),
                "ftm_id": le_ftm_id,
            }
            le_ftm = legal_entity_to_ftm(le_rec)
            conn.execute(
                """
                INSERT INTO legal_entities
                    (id, ftm_id, ftm_schema, name, name_fingerprint, jurisdiction,
                     company_number_foreign, entity_type, is_offshore, source_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    legal_entity_id,
                    le_ftm["id"],
                    le_ftm["schema"],
                    raw_name,
                    fp,
                    jur,
                    reg_no,
                    kind[:50],
                    is_off,
                    source_id,
                    now,
                    now,
                ),
            )
            db.upsert_ftm_entity(le_ftm, source_id=source_id, conn=conn)
            counts["legal_entities"] += 1
            counts["ftm_entities"] += 1
    else:
        # Individual PSC / Beneficial Owner
        name_elems = data.get("name_elements") or {}
        forename = name_elems.get("forename")
        surname = name_elems.get("surname")
        title = name_elems.get("title")
        raw_name = (
            data.get("name")
            or " ".join(x for x in [title, forename, surname] if x)
            or f"Individual PSC ({comp_num})"
        ).strip()
        fp = normalize_name(raw_name, is_company=False)
        dob = data.get("date_of_birth") or {}
        dob_month = dob.get("month")
        dob_year = dob.get("year")
        nationality = data.get("nationality")
        residence = data.get("country_of_residence")

        p_ftm_id = make_ftm_id("Person", fp or raw_name, str(dob_year or ""), str(dob_month or ""))
        owner_ftm_id = p_ftm_id
        existing_p = conn.execute(
            "SELECT id FROM persons WHERE ftm_id = ?",
            (p_ftm_id,),
        ).fetchone()
        if existing_p:
            person_id = existing_p["id"]
        else:
            person_id = str(uuid.uuid4())
            p_rec = {
                "id": person_id,
                "name": raw_name,
                "name_fingerprint": fp,
                "forename": forename,
                "surname": surname,
                "title": title,
                "nationality": nationality,
                "country_of_residence": residence,
                "dob_month": dob_month,
                "dob_year": dob_year,
                "ftm_id": p_ftm_id,
            }
            p_ftm = person_to_ftm(p_rec)
            conn.execute(
                """
                INSERT INTO persons
                    (id, ftm_id, ftm_schema, name, name_fingerprint, forename, surname, title,
                     nationality, country_of_residence, dob_month, dob_year, source_id, created_at, updated_at)
                VALUES (?, ?, 'Person', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_id,
                    p_ftm["id"],
                    raw_name,
                    fp,
                    forename,
                    surname,
                    title,
                    nationality,
                    residence,
                    dob_month,
                    dob_year,
                    source_id,
                    now,
                    now,
                ),
            )
            db.upsert_ftm_entity(p_ftm, source_id=source_id, conn=conn)
            counts["persons"] += 1
            counts["ftm_entities"] += 1

        # Also record active control / directorship appointment
        dir_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"dir-psc:{comp_num}:{person_id}"))
        dir_ftm = directorship_to_ftm(
            {
                "id": dir_id,
                "company_number": comp_num,
                "officer_role": "director / psc-controller",
                "appointed_on": notified_on,
                "resigned_on": ceased_on,
            },
            director_ftm_id=p_ftm_id,
            company_ftm_id=company_ftm_id,
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO directorships
                (id, ftm_id, ftm_schema, company_number, person_id, officer_role,
                 appointed_on, resigned_on, is_active, nationality, country_of_residence,
                 source_id, fetched_via, created_at, updated_at)
            VALUES (?, ?, 'Directorship', ?, ?, 'director', ?, ?, ?, ?, ?, ?, 'bulk', ?, ?)
            """,
            (
                dir_id,
                dir_ftm["id"],
                comp_num,
                person_id,
                notified_on,
                ceased_on,
                0 if is_ceased else 1,
                nationality,
                residence,
                source_id,
                now,
                now,
            ),
        )
        db.upsert_ftm_entity(dir_ftm, source_id=source_id, conn=conn)
        counts["directorships"] += 1

    own_ftm = psc_to_ftm_ownership(
        {
            "id": psc_id,
            "company_number": comp_num,
            "nature_of_control": natures,
            "notified_on": notified_on,
            "ceased_on": ceased_on,
            "is_super_secure": bool(is_super_secure),
        },
        owner_ftm_id=owner_ftm_id,
        company_ftm_id=company_ftm_id,
    )

    _record_psc_change(conn, comp_num, psc_id, owner_label(data, comp_num), ceased_on, source_id, now)
    # created_at is kept from the first time the statement was seen (the change history relies on it)
    conn.execute(
        """
        INSERT INTO psc_ownerships
            (id, ftm_id, ftm_schema, company_number, person_id, legal_entity_id,
             nature_of_control, notified_on, ceased_on, is_ceased, is_super_secure,
             source_id, created_at)
        VALUES (?, ?, 'Ownership', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            ftm_id = excluded.ftm_id,
            company_number = excluded.company_number,
            person_id = excluded.person_id,
            legal_entity_id = excluded.legal_entity_id,
            nature_of_control = excluded.nature_of_control,
            notified_on = excluded.notified_on,
            ceased_on = excluded.ceased_on,
            is_ceased = excluded.is_ceased,
            is_super_secure = excluded.is_super_secure,
            source_id = excluded.source_id
        """,
        (
            psc_id,
            own_ftm["id"],
            comp_num,
            person_id,
            legal_entity_id,
            json.dumps(natures, ensure_ascii=False),
            notified_on,
            ceased_on,
            is_ceased,
            is_super_secure,
            source_id,
            now,
        ),
    )
    db.upsert_ftm_entity(own_ftm, source_id=source_id, conn=conn)
    counts["psc_ownerships"] += 1
    counts["ftm_entities"] += 1


def owner_label(data: dict[str, Any], comp_num: str) -> str:
    kind = data.get("kind") or ""
    if "super-secure" in kind:
        return "Super-secure PSC"
    return (data.get("name") or f"PSC of {comp_num}").strip()


def _record_psc_change(
    conn: Any, comp_num: str, psc_id: str, label: str, ceased_on: str | None, source_id: str | None, now: str
) -> None:
    """PSC added after the company's first load, or a statement that has just ceased."""
    prior = conn.execute("SELECT ceased_on FROM psc_ownerships WHERE id = ?", (psc_id,)).fetchone()
    if prior is None:
        seen_before = conn.execute(
            "SELECT 1 FROM psc_ownerships WHERE company_number = ? AND created_at < ? LIMIT 1",
            (comp_num, now),
        ).fetchone()
        if seen_before:
            add_change(conn, comp_num, "PSC_ADDED", None, label, source_id, now)
    elif ceased_on and not prior["ceased_on"]:
        add_change(conn, comp_num, "PSC_CEASED", label, None, source_id, now, ceased_on)


def import_psc_snapshot(
    jsonl_path: Path | str,
    db_service: DatabaseService | None = None,
    limit: int | None = None,
    only_existing_companies: bool = False,
) -> dict[str, int]:
    """Stream PSC JSONL snapshot into `persons`, `legal_entities`, `psc_ownerships`, `directorships`, and `ftm_entities`."""
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"PSC snapshot file not found: {path}")

    db = db_service or DatabaseService()
    conn = db.connect()
    counts = {
        "psc_ownerships": 0,
        "persons": 0,
        "legal_entities": 0,
        "stub_companies": 0,
        "directorships": 0,
        "ftm_entities": 0,
    }
    now = datetime.now(UTC).isoformat()

    try:
        source_id = db.register_data_source(
            source_name="Companies House PSC Snapshot",
            source_type="ch_psc_jsonl",
            source_version="2026-01-19",
            source_url=str(path),
            notes="Persons with Significant Control & Overseas Entity Beneficial Owners",
            conn=conn,
        )

        existing_companies = {
            r["company_number"]
            for r in conn.execute("SELECT company_number FROM companies").fetchall()
        }

        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if limit is not None and counts["psc_ownerships"] >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                comp_num = (obj.get("company_number") or "").strip().upper()[:8]
                data = obj.get("data") or {}
                if not comp_num or not data:
                    continue

                if only_existing_companies and comp_num not in existing_companies:
                    continue

                ingest_psc_record(conn, db, comp_num, data, source_id, now, existing_companies, counts)

        conn.commit()
        log.info("psc_import_complete", **counts)
        return counts
    finally:
        conn.close()
