"""ETL Importer for ICIJ Offshore Leaks Database (`dati/ICIJ Offshore Leaks Database/`).

Imports all 6 official ICIJ CSV files:
  - `nodes-entities.csv` -> `icij_entities` + FtM `Company`
  - `nodes-officers.csv` -> `icij_officers` + FtM `LegalEntity`
  - `nodes-intermediaries.csv` -> `icij_intermediaries` + FtM `LegalEntity`
  - `nodes-addresses.csv` -> `icij_addresses` + FtM `Address`
  - `nodes-others.csv` -> `icij_others` + FtM `LegalEntity`
  - `relationships.csv` -> `icij_relationships` + FtM interval links (`Directorship`, `Ownership`, `Representation`, `UnknownLink`)
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.ftm import (
    build_ftm_entity,
    icij_entity_to_ftm,
    icij_officer_to_ftm,
    icij_relationship_to_ftm,
    make_ftm_id,
)
from src.core.logging import get_logger
from src.core.normalizer import compute_address_fingerprint, normalize_name
from src.services.db_service import DatabaseService

log = get_logger(__name__)


def _parse_icij_date(val: str | None) -> str | None:
    if not val:
        return None
    v = val.strip()
    if not v:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return v[:10] if len(v) >= 4 else None


def import_icij_directory(
    icij_dir: Path | str,
    db_service: DatabaseService | None = None,
    limit_per_file: int | None = None,
) -> dict[str, int]:
    """Import ICIJ Offshore Leaks CSVs into relational tables and `ftm_entities`."""
    base_dir = Path(icij_dir)
    if not base_dir.exists():
        raise FileNotFoundError(f"ICIJ directory not found: {base_dir}")

    db = db_service or DatabaseService()
    conn = db.connect()
    counts = {
        "entities": 0,
        "officers": 0,
        "intermediaries": 0,
        "addresses": 0,
        "others": 0,
        "relationships": 0,
        "ftm_entities": 0,
    }
    node_ftm_map: dict[str, str] = {}

    try:
        source_id = db.register_data_source(
            source_name="ICIJ Offshore Leaks Database",
            source_type="icij_csv",
            source_version="2024-11",
            source_url=str(base_dir),
            notes="Panama Papers, Paradise Papers, Pandora Papers, Bahamas Leaks, Offshore Leaks",
            conn=conn,
        )

        # 1. nodes-entities.csv
        entities_file = base_dir / "nodes-entities.csv"
        if entities_file.exists():
            with entities_file.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    if limit_per_file and idx >= limit_per_file:
                        break
                    node_id = (row.get("node_id") or "").strip()
                    if not node_id:
                        continue
                    name = (row.get("name") or "").strip()
                    fp = normalize_name(name)
                    rec = {
                        "node_id": node_id,
                        "name": name,
                        "name_fingerprint": fp,
                        "original_name": (row.get("original_name") or "").strip() or None,
                        "former_name": (row.get("former_name") or "").strip() or None,
                        "jurisdiction": (row.get("jurisdiction") or "").strip() or None,
                        "jurisdiction_description": (row.get("jurisdiction_description") or "").strip() or None,
                        "company_type": (row.get("company_type") or "").strip() or None,
                        "address": (row.get("address") or "").strip() or None,
                        "internal_id": (row.get("internal_id") or "").strip() or None,
                        "incorporation_date": _parse_icij_date(row.get("incorporation_date")),
                        "inactivation_date": _parse_icij_date(row.get("inactivation_date")),
                        "struck_off_date": _parse_icij_date(row.get("struck_off_date")),
                        "status": (row.get("status") or "").strip() or None,
                        "source_id_list": (row.get("sourceID") or "").strip() or None,
                        "valid_until": (row.get("valid_until") or "").strip() or None,
                        "note": (row.get("note") or "").strip() or None,
                    }
                    ftm_ent = icij_entity_to_ftm(rec)
                    node_ftm_map[node_id] = ftm_ent["id"]
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO icij_entities
                            (node_id, ftm_id, ftm_schema, name, name_fingerprint, original_name, former_name,
                             jurisdiction, jurisdiction_description, company_type, address, internal_id,
                             incorporation_date, inactivation_date, struck_off_date, status,
                             source_id_list, valid_until, note, source_id)
                        VALUES (?, ?, 'Company', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            ftm_ent["id"],
                            rec["name"],
                            rec["name_fingerprint"],
                            rec["original_name"],
                            rec["former_name"],
                            rec["jurisdiction"],
                            rec["jurisdiction_description"],
                            rec["company_type"],
                            rec["address"],
                            rec["internal_id"],
                            rec["incorporation_date"],
                            rec["inactivation_date"],
                            rec["struck_off_date"],
                            rec["status"],
                            rec["source_id_list"],
                            rec["valid_until"],
                            rec["note"],
                            source_id,
                        ),
                    )
                    db.upsert_ftm_entity(ftm_ent, source_id=source_id, conn=conn)
                    counts["entities"] += 1
                    counts["ftm_entities"] += 1

        # 2. nodes-officers.csv
        officers_file = base_dir / "nodes-officers.csv"
        if officers_file.exists():
            with officers_file.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    if limit_per_file and idx >= limit_per_file:
                        break
                    node_id = (row.get("node_id") or "").strip()
                    if not node_id:
                        continue
                    name = (row.get("name") or "").strip()
                    fp = normalize_name(name)
                    rec = {
                        "node_id": node_id,
                        "name": name,
                        "name_fingerprint": fp,
                        "icij_id": (row.get("icij_id") or "").strip() or None,
                        "valid_until": (row.get("valid_until") or "").strip() or None,
                        "country_codes": (row.get("country_codes") or "").strip() or None,
                        "countries": (row.get("countries") or "").strip() or None,
                        "source_id_list": (row.get("sourceID") or "").strip() or None,
                    }
                    ftm_ent = icij_officer_to_ftm(rec)
                    node_ftm_map[node_id] = ftm_ent["id"]
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO icij_officers
                            (node_id, ftm_id, ftm_schema, name, name_fingerprint, icij_id, valid_until,
                             country_codes, countries, source_id_list, source_id)
                        VALUES (?, ?, 'LegalEntity', ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            ftm_ent["id"],
                            rec["name"],
                            rec["name_fingerprint"],
                            rec["icij_id"],
                            rec["valid_until"],
                            rec["country_codes"],
                            rec["countries"],
                            rec["source_id_list"],
                            source_id,
                        ),
                    )
                    db.upsert_ftm_entity(ftm_ent, source_id=source_id, conn=conn)
                    counts["officers"] += 1
                    counts["ftm_entities"] += 1

        # 3. nodes-intermediaries.csv
        inter_file = base_dir / "nodes-intermediaries.csv"
        if inter_file.exists():
            with inter_file.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    if limit_per_file and idx >= limit_per_file:
                        break
                    node_id = (row.get("node_id") or "").strip()
                    if not node_id:
                        continue
                    name = (row.get("name") or "").strip()
                    fp = normalize_name(name)
                    ftm_id = make_ftm_id("icij", "intermediary", node_id)
                    node_ftm_map[node_id] = ftm_id
                    ftm_ent = build_ftm_entity(
                        schema="LegalEntity",
                        entity_id=ftm_id,
                        properties={
                            "name": [name],
                            "country": [
                                c.strip()
                                for c in (row.get("country_codes") or "").split(";")
                                if c.strip()
                            ],
                            "address": [row.get("address")],
                            "status": [row.get("status")],
                            "publisher": [row.get("sourceID") or "ICIJ Offshore Leaks"],
                        },
                        datasets=["icij_offshore_leaks"],
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO icij_intermediaries
                            (node_id, ftm_id, ftm_schema, name, name_fingerprint, status, internal_id,
                             address, countries, country_codes, source_id_list, valid_until, note, source_id)
                        VALUES (?, ?, 'LegalEntity', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            ftm_id,
                            name,
                            fp,
                            row.get("status"),
                            row.get("internal_id"),
                            row.get("address"),
                            row.get("countries"),
                            row.get("country_codes"),
                            row.get("sourceID"),
                            row.get("valid_until"),
                            row.get("note"),
                            source_id,
                        ),
                    )
                    db.upsert_ftm_entity(ftm_ent, source_id=source_id, conn=conn)
                    counts["intermediaries"] += 1
                    counts["ftm_entities"] += 1

        # 4. nodes-addresses.csv
        addr_file = base_dir / "nodes-addresses.csv"
        if addr_file.exists():
            with addr_file.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    if limit_per_file and idx >= limit_per_file:
                        break
                    node_id = (row.get("node_id") or "").strip()
                    if not node_id:
                        continue
                    addr_text = (row.get("address") or row.get("name") or "").strip()
                    addr_fp = compute_address_fingerprint(None, addr_text, row.get("countries"))
                    ftm_id = make_ftm_id("icij", "address", node_id)
                    node_ftm_map[node_id] = ftm_id
                    ftm_ent = build_ftm_entity(
                        schema="Address",
                        entity_id=ftm_id,
                        properties={
                            "full": [addr_text],
                            "country": [
                                c.strip()
                                for c in (row.get("country_codes") or "").split(";")
                                if c.strip()
                            ],
                        },
                        datasets=["icij_offshore_leaks"],
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO icij_addresses
                            (node_id, ftm_id, ftm_schema, address, name, countries, country_codes,
                             address_fingerprint, source_id_list, valid_until, note, source_id)
                        VALUES (?, ?, 'Address', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            ftm_id,
                            addr_text,
                            row.get("name"),
                            row.get("countries"),
                            row.get("country_codes"),
                            addr_fp,
                            row.get("sourceID"),
                            row.get("valid_until"),
                            row.get("note"),
                            source_id,
                        ),
                    )
                    db.upsert_ftm_entity(ftm_ent, source_id=source_id, conn=conn)
                    counts["addresses"] += 1
                    counts["ftm_entities"] += 1

        # 5. nodes-others.csv
        others_file = base_dir / "nodes-others.csv"
        if others_file.exists():
            with others_file.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    if limit_per_file and idx >= limit_per_file:
                        break
                    node_id = (row.get("node_id") or "").strip()
                    if not node_id:
                        continue
                    name = (row.get("name") or "").strip()
                    fp = normalize_name(name)
                    ftm_id = make_ftm_id("icij", "other", node_id)
                    node_ftm_map[node_id] = ftm_id
                    ftm_ent = build_ftm_entity(
                        schema="LegalEntity",
                        entity_id=ftm_id,
                        properties={
                            "name": [name],
                            "jurisdiction": [row.get("jurisdiction")],
                            "incorporationDate": [_parse_icij_date(row.get("incorporation_date"))],
                            "dissolutionDate": [_parse_icij_date(row.get("struck_off_date") or row.get("closed_date"))],
                        },
                        datasets=["icij_offshore_leaks"],
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO icij_others
                            (node_id, ftm_id, ftm_schema, name, name_fingerprint, type,
                             incorporation_date, struck_off_date, closed_date, jurisdiction,
                             jurisdiction_description, countries, country_codes, source_id_list,
                             valid_until, note, source_id)
                        VALUES (?, ?, 'LegalEntity', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            ftm_id,
                            name,
                            fp,
                            row.get("type"),
                            _parse_icij_date(row.get("incorporation_date")),
                            _parse_icij_date(row.get("struck_off_date")),
                            _parse_icij_date(row.get("closed_date")),
                            row.get("jurisdiction"),
                            row.get("jurisdiction_description"),
                            row.get("countries"),
                            row.get("country_codes"),
                            row.get("sourceID"),
                            row.get("valid_until"),
                            row.get("note"),
                            source_id,
                        ),
                    )
                    db.upsert_ftm_entity(ftm_ent, source_id=source_id, conn=conn)
                    counts["others"] += 1
                    counts["ftm_entities"] += 1

        # 6. relationships.csv
        rel_file = base_dir / "relationships.csv"
        if rel_file.exists():
            rel_limit = (limit_per_file * 2) if limit_per_file else None
            with rel_file.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if rel_limit and counts["relationships"] >= rel_limit:
                        break
                    start_id = (row.get("node_id_start") or "").strip()
                    end_id = (row.get("node_id_end") or "").strip()
                    if not start_id or not end_id:
                        continue
                    if limit_per_file and (start_id not in node_ftm_map and end_id not in node_ftm_map):
                        continue

                    start_ftm = node_ftm_map.get(start_id) or make_ftm_id("icij", "node", start_id)
                    end_ftm = node_ftm_map.get(end_id) or make_ftm_id("icij", "node", end_id)
                    rel_dict = {
                        "node_id_start": start_id,
                        "node_id_end": end_id,
                        "rel_type": (row.get("rel_type") or "").strip() or None,
                        "link": (row.get("link") or "").strip() or None,
                        "status": (row.get("status") or "").strip() or None,
                        "start_date": _parse_icij_date(row.get("start_date")),
                        "end_date": _parse_icij_date(row.get("end_date")),
                        "source_id_list": (row.get("sourceID") or "").strip() or None,
                    }
                    ftm_rel = icij_relationship_to_ftm(rel_dict, start_ftm_id=start_ftm, end_ftm_id=end_ftm)
                    conn.execute(
                        """
                        INSERT INTO icij_relationships
                            (ftm_id, ftm_schema, node_id_start, node_id_end, rel_type, link,
                             status, start_date, end_date, source_id_list, source_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ftm_rel["id"],
                            ftm_rel["schema"],
                            start_id,
                            end_id,
                            rel_dict["rel_type"],
                            rel_dict["link"],
                            rel_dict["status"],
                            rel_dict["start_date"],
                            rel_dict["end_date"],
                            rel_dict["source_id_list"],
                            source_id,
                        ),
                    )
                    db.upsert_ftm_entity(ftm_rel, source_id=source_id, conn=conn)
                    counts["relationships"] += 1
                    counts["ftm_entities"] += 1

        conn.commit()
        log.info("icij_import_complete", **counts)
        return counts
    finally:
        conn.close()
