"""ETL Importer for UK FCDO / OFSI Sanctions (`dati/UK-Sanctions-List.txt`) and OpenSanctions FtM JSONL.

Handles the exact UK Sanctions List semicolon format:
  - Line 0: `Report Date: DD-Mon-YYYY`
  - Line 1: 58 semicolon-delimited headers
  - Lines 2+: Data rows where `Other Information` (col 20) and `UK Statement of Reasons` (col 21)
    can contain unquoted semicolons (`len(row) > 58`), solved via right-anchored indexing (`row[-36:]`).
  - Consolidates rows by `Unique ID` (e.g. `AFG0001`, `RUS1850`), merging primary name, aliases,
    addresses, countries, and extracted UK registration numbers (`Business registration number (s)` at `row[-11]`).
  - Populates `sanctions`, `name_variants`, and `ftm_entities` (FollowTheMoney v3.x `Sanction` + subject entity).
"""
from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.ftm import make_ftm_id, sanction_to_ftm
from src.core.logging import get_logger
from src.core.normalizer import extract_uk_company_numbers, normalize_name, phonetic_key
from src.services.db_service import DatabaseService

log = get_logger(__name__)


def _parse_uk_date(val: str | None) -> str | None:
    if not val:
        return None
    v = val.strip()
    if not v:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return v[:10]


def parse_uk_sanctions_row(row: list[str]) -> dict[str, Any] | None:
    """Parse a single row from `UK-Sanctions-List.txt` using right-anchored column indexing."""
    if len(row) < 50:
        return None

    last_updated = row[0].strip()
    unique_id = row[1].strip()
    if not unique_id or unique_id == "Unique ID":
        return None

    ofsi_group_id = row[2].strip()
    un_ref = row[3].strip()

    # Name fields: Name 6 (col 4), Name 1..5 (cols 5..9), Title (col 10), Script (col 11), Non-latin (col 12)
    name_parts = [row[5].strip(), row[6].strip(), row[7].strip(), row[8].strip(), row[9].strip(), row[4].strip()]
    full_name = " ".join(p for p in name_parts if p).strip()
    non_latin_name = row[12].strip()
    name_type = row[13].strip()  # 'Primary name' | 'Alias'
    alias_type = row[14].strip()
    regime_name = row[16].strip()
    entity_raw_type = row[17].strip()  # 'Individual' | 'Entity' | 'Ship'
    designation_source = row[18].strip()
    sanctions_imposed = row[19].strip()

    # Columns 22..57 are the last 36 columns (indices -36..-1)
    tail = row[-36:]
    # Middle columns between 20 and len(row)-36 are Other Info + Statement of Reasons
    middle = "; ".join(x.strip() for x in row[20 : len(row) - 36] if x.strip())

    # Tail mapping (length 36):
    # tail[0..5]   = Address 1..6 (cols 22..27)
    # tail[6]      = Post/Zip Code (col 28)
    # tail[7]      = Country (col 29)
    # tail[11]     = Date designated (col 33)
    # tail[12]     = D.O.B (col 34)
    # tail[14]     = Nationality(-ies) (col 36)
    # tail[24]     = Type of entity (col 46)
    # tail[25]     = Business registration number (s) (col 47 == row[-11])
    address_parts = [tail[i].strip() for i in range(6) if tail[i].strip()]
    postcode = tail[6].strip()
    country = tail[7].strip()
    date_designated = _parse_uk_date(tail[11])
    dob = tail[12].strip()
    nationality = tail[14].strip()
    type_of_entity = tail[24].strip()
    brn_raw = tail[25].strip()  # row[-11]

    if entity_raw_type.lower() == "individual":
        mapped_type = "Person"
    elif entity_raw_type.lower() == "ship":
        mapped_type = "Vessel"
    else:
        mapped_type = "Company"

    reg_nums = extract_uk_company_numbers(brn_raw)
    if brn_raw and not reg_nums:
        # Keep non-UK registration numbers too, stripped
        for token in brn_raw.replace(";", ",").split(","):
            tok = token.strip()
            if tok and tok not in reg_nums:
                reg_nums.append(tok)

    return {
        "unique_id": unique_id,
        "ofsi_group_id": ofsi_group_id,
        "un_ref": un_ref,
        "last_updated": _parse_uk_date(last_updated),
        "full_name": full_name or non_latin_name or unique_id,
        "non_latin_name": non_latin_name,
        "name_type": name_type,
        "alias_type": alias_type,
        "regime_name": regime_name,
        "entity_type": mapped_type,
        "designation_source": designation_source,
        "sanctions_imposed": sanctions_imposed,
        "statement_of_reasons": middle[:1500],
        "address": ", ".join([*address_parts, postcode, country]).strip(", "),
        "postcode": postcode,
        "country": country,
        "date_designated": date_designated,
        "dob": dob,
        "nationality": nationality,
        "type_of_entity": type_of_entity,
        "registration_numbers": reg_nums,
        "brn_raw": brn_raw,
    }


def import_uk_sanctions_file(
    file_path: Path | str,
    db_service: DatabaseService | None = None,
    limit_entities: int | None = None,
) -> dict[str, int]:
    """Import `UK-Sanctions-List.txt` into `sanctions`, `name_variants`, and `ftm_entities`."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Sanctions file not found: {path}")

    db = db_service or DatabaseService()
    grouped: dict[str, dict[str, Any]] = {}
    report_date = "2026-03-17"

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        first_line = fh.readline().strip()
        if first_line.startswith("Report Date:"):
            report_date = first_line.replace("Report Date:", "").strip()
        else:
            fh.seek(0)

        reader = csv.reader(fh, delimiter=";")
        # Skip header row
        next(reader, None)

        for row in reader:
            parsed = parse_uk_sanctions_row(row)
            if not parsed:
                continue
            uid = parsed["unique_id"]
            if uid not in grouped:
                if limit_entities and len(grouped) >= limit_entities:
                    # Still allow rows belonging to already-collected entities or entities with UK BRNs
                    has_uk_brn = any(
                        len(rn) == 8 and (rn.isdigit() or rn[:2].isalpha())
                        for rn in parsed["registration_numbers"]
                    )
                    if not has_uk_brn:
                        continue
                grouped[uid] = {
                    "unique_id": uid,
                    "ofsi_group_id": parsed["ofsi_group_id"],
                    "primary_name": parsed["full_name"],
                    "aliases": set(),
                    "entity_type": parsed["entity_type"],
                    "regime_name": parsed["regime_name"],
                    "date_designated": parsed["date_designated"],
                    "countries": set(),
                    "registration_numbers": set(),
                    "addresses": set(),
                    "statement_of_reasons": parsed["statement_of_reasons"],
                    "sanctions_imposed": parsed["sanctions_imposed"],
                }

            rec = grouped[uid]
            if parsed["name_type"].lower() == "primary name" and parsed["full_name"]:
                rec["primary_name"] = parsed["full_name"]
            elif parsed["full_name"] and parsed["full_name"] != rec["primary_name"]:
                rec["aliases"].add(parsed["full_name"])

            if parsed["non_latin_name"]:
                rec["aliases"].add(parsed["non_latin_name"])
            if parsed["country"]:
                rec["countries"].add(parsed["country"])
            if parsed["nationality"]:
                rec["countries"].add(parsed["nationality"])
            for rn in parsed["registration_numbers"]:
                rec["registration_numbers"].add(rn)
            if parsed["address"]:
                rec["addresses"].add(parsed["address"])

    conn = db.connect()
    try:
        source_id = db.register_data_source(
            source_name="UK Sanctions List (FCDO / OFSI)",
            source_type="sanctions_bulk",
            source_version=report_date,
            source_url=str(path),
            record_count=len(grouped),
            notes="Official UK Sanctions List consolidated by Unique ID",
            conn=conn,
        )

        now = datetime.now(timezone.utc).isoformat()
        sanctions_inserted = 0
        ftm_inserted = 0
        variants_inserted = 0

        for uid, rec in grouped.items():
            sanc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"uk-sanctions:{uid}"))
            primary_name = rec["primary_name"]
            fp = normalize_name(primary_name)
            aliases_list = sorted(rec["aliases"])
            countries_list = sorted(rec["countries"])
            reg_nums_list = sorted(rec["registration_numbers"])
            list_name = rec["regime_name"] or "UK FCDO Sanctions List"

            raw_props = {
                "unique_id": uid,
                "ofsi_group_id": rec["ofsi_group_id"],
                "regime": rec["regime_name"],
                "sanctions_imposed": rec["sanctions_imposed"],
                "reasons": rec["statement_of_reasons"][:600],
                "addresses": sorted(rec["addresses"])[:5],
                "registrationNumber": reg_nums_list,
            }

            sanc_dict = {
                "id": sanc_id,
                "name": primary_name,
                "aliases": aliases_list,
                "entity_type": rec["entity_type"],
                "topics": ["sanction"],
                "countries": countries_list,
                "registration_numbers": reg_nums_list,
                "list_name": list_name,
                "listed_on": rec["date_designated"],
                "source": "uk_ofsi",
                "opensanctions_id": uid,
                "raw_properties": raw_props,
            }
            subj_ftm, sanc_ftm = sanction_to_ftm(sanc_dict)

            conn.execute(
                """
                INSERT OR REPLACE INTO sanctions
                    (id, ftm_id, ftm_schema, subject_ftm_id, name, name_fingerprint, aliases,
                     entity_type, topics, countries, registration_numbers, list_name, listed_on,
                     source, opensanctions_id, raw_properties, source_id, created_at, updated_at)
                VALUES (?, ?, 'Sanction', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'uk_ofsi', ?, ?, ?, ?, ?)
                """,
                (
                    sanc_id,
                    sanc_ftm["id"],
                    subj_ftm["id"],
                    primary_name,
                    fp,
                    json.dumps(aliases_list, ensure_ascii=False),
                    rec["entity_type"],
                    json.dumps(["sanction"], ensure_ascii=False),
                    json.dumps(countries_list, ensure_ascii=False),
                    json.dumps(reg_nums_list, ensure_ascii=False),
                    list_name,
                    rec["date_designated"],
                    uid,
                    json.dumps(raw_props, ensure_ascii=False),
                    source_id,
                    now,
                    now,
                ),
            )
            sanctions_inserted += 1

            # Sync FtM entities
            db.upsert_ftm_entity(subj_ftm, source_id=source_id, conn=conn)
            db.upsert_ftm_entity(sanc_ftm, source_id=source_id, conn=conn)
            ftm_inserted += 2

            # Name variants (primary + up to 5 aliases)
            if fp:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO name_variants
                        (entity_id, entity_type, variant_text, fingerprint, ftm_id, variant_type, source_id)
                    VALUES (?, 'sanction', ?, ?, ?, 'original', ?)
                    """,
                    (sanc_id, primary_name, fp, subj_ftm["id"], source_id),
                )
                variants_inserted += 1
            for alias in aliases_list[:5]:
                afp = normalize_name(alias)
                if afp:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO name_variants
                            (entity_id, entity_type, variant_text, fingerprint, ftm_id, variant_type, source_id)
                        VALUES (?, 'sanction', ?, ?, ?, 'alias', ?)
                        """,
                        (sanc_id, alias[:500], afp, subj_ftm["id"], source_id),
                    )
                    variants_inserted += 1

        conn.commit()
        log.info(
            "sanctions_import_complete",
            sanctions=sanctions_inserted,
            ftm_entities=ftm_inserted,
            name_variants=variants_inserted,
        )
        return {
            "sanctions": sanctions_inserted,
            "ftm_entities": ftm_inserted,
            "name_variants": variants_inserted,
        }
    finally:
        conn.close()
