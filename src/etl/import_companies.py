"""ETL Importer for Companies House BasicCompanyData CSV (`dati/BasicCompanyDataAsOneFile-*.csv`).

Features:
  - Strips leading spaces from CH CSV headers (e.g. `" CompanyNumber"` -> `"CompanyNumber"`)
  - Extracts 5-digit SIC codes (`sic_code_1..4`) from `SICCode.SicText_1..4`
  - Computes `name_fingerprint` and ADR-015 `address_fingerprint` (`postcode|house_no|keyword`)
  - Populates `companies`, `addresses`, `name_variants`, `geo_postcode_centroids`, and `ftm_entities` (`Company` + `Address`)
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.ftm import address_to_ftm, company_to_ftm
from src.core.logging import get_logger
from src.core.normalizer import compute_address_fingerprint, normalize_name, normalize_postcode
from src.services.db_service import DatabaseService
from src.services.geo_service import resolve_postcode_coords

log = get_logger(__name__)

_SIC_CODE_RE = re.compile(r"^(\d{4,5})\b")


# Registry fields written by bulk imports and API refreshes. Analysis fields (risk_score,
# ft3_techniques, is_flagged, officers_fetched_at, ...) are never touched by an update.
_COMPANY_REGISTRY_COLUMNS: tuple[str, ...] = (
    "company_number",
    "company_name",
    "ftm_id",
    "reg_address_care_of",
    "reg_address_po_box",
    "reg_address_line1",
    "reg_address_line2",
    "reg_address_post_town",
    "reg_address_county",
    "reg_address_country",
    "reg_address_postcode",
    "company_category",
    "company_status",
    "country_of_origin",
    "dissolution_date",
    "incorporation_date",
    "accounts_account_ref_day",
    "accounts_account_ref_month",
    "accounts_account_category",
    "accounts_next_due_date",
    "accounts_last_made_up_date",
    "returns_next_due_date",
    "returns_last_made_up_date",
    "mortgages_num_charges",
    "mortgages_num_outstanding",
    "mortgages_num_part_satisfied",
    "mortgages_num_satisfied",
    "sic_text_1",
    "sic_text_2",
    "sic_text_3",
    "sic_text_4",
    "sic_code_1",
    "sic_code_2",
    "sic_code_3",
    "sic_code_4",
    "lp_num_gen_partners",
    "lp_num_lim_partners",
    "ch_uri",
    *(f"prev_name_{i}{suffix}" for i in range(1, 11) for suffix in ("_date", "")),
    "conf_stmt_next_due_date",
    "conf_stmt_last_made_up_date",
    "address_fingerprint",
    "name_fingerprint",
    "source_id",
)

_UPSERT_COMPANY_SQL = (
    f"INSERT INTO companies ({', '.join(_COMPANY_REGISTRY_COLUMNS)}, ftm_schema, created_at, updated_at) "
    f"VALUES ({', '.join('?' for _ in _COMPANY_REGISTRY_COLUMNS)}, 'Company', ?, ?) "
    "ON CONFLICT(company_number) DO UPDATE SET "
    + ", ".join(f"{c} = excluded.{c}" for c in _COMPANY_REGISTRY_COLUMNS if c != "company_number")
    + ", updated_at = excluded.updated_at"
)


def _parse_ch_date(val: str | None) -> str | None:
    if not val:
        return None
    v = val.strip()
    if not v:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return v[:10]


def _parse_int(val: str | None, default: int | None = None) -> int | None:
    if not val:
        return default
    v = val.strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _extract_sic_code(sic_text: str | None) -> str | None:
    if not sic_text:
        return None
    m = _SIC_CODE_RE.match(sic_text.strip())
    return m.group(1) if m else None


def parse_ch_company_row(raw_row: dict[str, str]) -> dict[str, Any] | None:
    """Normalize a raw DictReader row from `BasicCompanyDataAsOneFile` into a clean Company dict."""
    row = {(k.strip() if k else ""): (v.strip() if v else "") for k, v in raw_row.items() if k}
    comp_num = row.get("CompanyNumber", "").upper()
    comp_name = row.get("CompanyName", "")
    if not comp_num or not comp_name:
        return None

    postcode = normalize_postcode(row.get("RegAddress.PostCode")) or row.get("RegAddress.PostCode") or None
    line1 = row.get("RegAddress.AddressLine1") or None
    line2 = row.get("RegAddress.AddressLine2") or None
    post_town = row.get("RegAddress.PostTown") or None
    county = row.get("RegAddress.County") or None
    country = row.get("RegAddress.Country") or None

    addr_fp = compute_address_fingerprint(postcode, line1, line2, post_town)
    name_fp = normalize_name(comp_name)

    sic1 = row.get("SICCode.SicText_1") or None
    sic2 = row.get("SICCode.SicText_2") or None
    sic3 = row.get("SICCode.SicText_3") or None
    sic4 = row.get("SICCode.SicText_4") or None

    record: dict[str, Any] = {
        "company_number": comp_num[:8],
        "company_name": comp_name[:500],
        "reg_address_care_of": row.get("RegAddress.CareOf") or None,
        "reg_address_po_box": row.get("RegAddress.POBox") or None,
        "reg_address_line1": line1,
        "reg_address_line2": line2,
        "reg_address_post_town": post_town,
        "reg_address_county": county,
        "reg_address_country": country,
        "reg_address_postcode": postcode,
        "company_category": row.get("CompanyCategory") or None,
        "company_status": row.get("CompanyStatus") or None,
        "country_of_origin": row.get("CountryOfOrigin") or None,
        "dissolution_date": _parse_ch_date(row.get("DissolutionDate")),
        "incorporation_date": _parse_ch_date(row.get("IncorporationDate")),
        "accounts_account_ref_day": _parse_int(row.get("Accounts.AccountRefDay")),
        "accounts_account_ref_month": _parse_int(row.get("Accounts.AccountRefMonth")),
        "accounts_account_category": row.get("Accounts.AccountCategory") or None,
        "accounts_next_due_date": _parse_ch_date(row.get("Accounts.NextDueDate")),
        "accounts_last_made_up_date": _parse_ch_date(row.get("Accounts.LastMadeUpDate")),
        "returns_next_due_date": _parse_ch_date(row.get("Returns.NextDueDate")),
        "returns_last_made_up_date": _parse_ch_date(row.get("Returns.LastMadeUpDate")),
        "mortgages_num_charges": _parse_int(row.get("Mortgages.NumMortCharges"), 0),
        "mortgages_num_outstanding": _parse_int(row.get("Mortgages.NumMortOutstanding"), 0),
        "mortgages_num_part_satisfied": _parse_int(row.get("Mortgages.NumMortPartSatisfied"), 0),
        "mortgages_num_satisfied": _parse_int(row.get("Mortgages.NumMortSatisfied"), 0),
        "sic_text_1": sic1,
        "sic_text_2": sic2,
        "sic_text_3": sic3,
        "sic_text_4": sic4,
        "sic_code_1": _extract_sic_code(sic1),
        "sic_code_2": _extract_sic_code(sic2),
        "sic_code_3": _extract_sic_code(sic3),
        "sic_code_4": _extract_sic_code(sic4),
        "lp_num_gen_partners": _parse_int(row.get("LimitedPartnerships.NumGenPartners")),
        "lp_num_lim_partners": _parse_int(row.get("LimitedPartnerships.NumLimPartners")),
        "ch_uri": row.get("URI") or None,
        "conf_stmt_next_due_date": _parse_ch_date(row.get("ConfirmationStmtNextDueDate")),
        "conf_stmt_last_made_up_date": _parse_ch_date(row.get("ConfirmationStmtLastMadeUpDate")),
        "address_fingerprint": addr_fp,
        "name_fingerprint": name_fp,
    }

    for idx in range(1, 11):
        record[f"prev_name_{idx}_date"] = _parse_ch_date(row.get(f"PreviousName_{idx}.CONDate"))
        record[f"prev_name_{idx}"] = row.get(f"PreviousName_{idx}.CompanyName") or None

    return record


def upsert_company_record(
    conn: Any,
    db: DatabaseService,
    rec: dict[str, Any],
    source_id: str,
) -> tuple[str, str | None]:
    """Insert or update a company record and its FtM `Company` + `Address` entities.

    `rec` may be partial (e.g. an API profile): fields that are None keep the stored value.
    """
    now = datetime.now(timezone.utc).isoformat()
    previous = conn.execute(
        "SELECT * FROM companies WHERE company_number = ?",
        (rec["company_number"],),
    ).fetchone()
    if previous is not None:
        stored = {c: previous[c] for c in _COMPANY_REGISTRY_COLUMNS}
        rec = {**stored, **{k: v for k, v in rec.items() if v is not None}}
    else:
        rec = {
            "mortgages_num_charges": 0,
            "mortgages_num_outstanding": 0,
            "mortgages_num_part_satisfied": 0,
            "mortgages_num_satisfied": 0,
            **{k: v for k, v in rec.items() if v is not None},
        }

    addr_ftm = address_to_ftm(
        street=rec.get("reg_address_line1"),
        street2=rec.get("reg_address_line2"),
        city=rec.get("reg_address_post_town"),
        county=rec.get("reg_address_county"),
        postcode=rec.get("reg_address_postcode"),
        country=rec.get("reg_address_country") or "United Kingdom",
        address_fingerprint=rec.get("address_fingerprint"),
    )
    addr_ftm_id = addr_ftm["id"] if addr_ftm else None
    if addr_ftm:
        db.upsert_ftm_entity(addr_ftm, source_id=source_id, conn=conn)
        coords = resolve_postcode_coords(rec.get("reg_address_postcode"))
        lat, lon = (coords[0], coords[1]) if coords else (None, None)
        conn.execute(
            """
            INSERT OR IGNORE INTO addresses
                (id, ftm_id, ftm_schema, full_address, street, city, county, postcode, country, country_code, address_fingerprint, lat, lon, company_count, source_id, created_at)
            VALUES (?, ?, 'Address', ?, ?, ?, ?, ?, ?, 'gb', ?, ?, ?, 0, ?, ?)
            """,
            (
                addr_ftm["id"],
                addr_ftm["id"],
                addr_ftm["caption"],
                rec.get("reg_address_line1"),
                rec.get("reg_address_post_town"),
                rec.get("reg_address_county"),
                rec.get("reg_address_postcode"),
                rec.get("reg_address_country") or "United Kingdom",
                rec.get("address_fingerprint"),
                lat,
                lon,
                source_id,
                now,
            ),
        )
        if previous is None or previous["address_fingerprint"] != rec.get("address_fingerprint"):
            conn.execute(
                "UPDATE addresses SET company_count = company_count + 1 WHERE id = ?",
                (addr_ftm["id"],),
            )

    comp_ftm = company_to_ftm(rec, address_ftm_id=addr_ftm_id)
    db.upsert_ftm_entity(comp_ftm, source_id=source_id, conn=conn)

    values = {**rec, "ftm_id": comp_ftm["id"], "source_id": source_id}
    conn.execute(
        _UPSERT_COMPANY_SQL,
        [*(values.get(c) for c in _COMPANY_REGISTRY_COLUMNS), now, now],
    )

    if rec.get("name_fingerprint"):
        conn.execute(
            """
            INSERT OR IGNORE INTO name_variants
                (entity_id, entity_type, variant_text, fingerprint, ftm_id, variant_type, source_id)
            VALUES (?, 'company', ?, ?, ?, 'original', ?)
            """,
            (
                rec["company_number"],
                rec["company_name"],
                rec["name_fingerprint"],
                comp_ftm["id"],
                source_id,
            ),
        )

    return comp_ftm["id"], addr_ftm_id


def import_companies_csv(
    csv_path: Path | str,
    db_service: DatabaseService | None = None,
    limit: int | None = None,
    priority_company_numbers: set[str] | None = None,
) -> dict[str, int]:
    """Import Companies House `BasicCompanyDataAsOneFile` CSV into the database."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Companies CSV not found: {path}")

    db = db_service or DatabaseService()
    conn = db.connect()
    priority_set = {c.strip().upper() for c in (priority_company_numbers or set()) if c}
    imported = 0

    try:
        source_id = db.register_data_source(
            source_name="Companies House BasicCompanyData",
            source_type="ch_bulk_csv",
            source_version="2026-01-01",
            source_url=str(path),
            notes="UK Companies House Free Company Data Product",
            conn=conn,
        )

        with path.open("r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row_idx, raw_row in enumerate(reader):
                comp_num = (raw_row.get(" CompanyNumber") or raw_row.get("CompanyNumber") or "").strip().upper()
                is_priority = comp_num in priority_set

                if limit is not None and imported >= limit and not is_priority:
                    if not priority_set or row_idx >= limit * 10:
                        break
                    continue

                rec = parse_ch_company_row(raw_row)
                if not rec:
                    continue

                upsert_company_record(conn, db, rec, source_id)
                imported += 1
                if is_priority:
                    priority_set.discard(comp_num)

        conn.commit()
        log.info("companies_import_complete", imported=imported)
        return {"companies": imported}
    finally:
        conn.close()
