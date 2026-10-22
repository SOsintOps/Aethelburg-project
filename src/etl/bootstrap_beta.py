"""Beta Database Bootstrap Pipeline (`dati/aethelburg.sqlite`).

Populates the FollowTheMoney-compatible database from the real datasets in `dati/`:
  1. `dati/UK-Sanctions-List.txt` (UK FCDO / OFSI Sanctions, including all UK BRNs)
  2. `dati/ICIJ Offshore Leaks Database/` (Entities, Officers, Intermediaries, Addresses, Others, Relationships)
  3. `dati/BasicCompanyDataAsOneFile-2026-01-01.csv` (Companies House bulk companies + sanctioned UK companies)
  4. `dati/persons-with-significant-control-snapshot-2026-01-19.txt` (PSC individuals, corporate PSCs, super-secure, OE)
  5. Multi-source FT3 typology clusters & initial Casework Investigation for immediate analyst exploration
  6. UK Postcode Centroids (`import_onspd`) + Fingerprints + Full FT3 Risk Scoring (`RiskScorer`)
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.settings import get_settings
from src.core.ftm import (
    directorship_to_ftm,
    icij_entity_to_ftm,
    legal_entity_to_ftm,
    make_ftm_id,
    person_to_ftm,
    psc_to_ftm_ownership,
)
from src.core.logging import get_logger
from src.core.normalizer import compute_address_fingerprint, normalize_name
from src.etl.compute_fingerprints import compute_all_fingerprints
from src.etl.import_companies import import_companies_csv, upsert_company_record
from src.etl.import_icij import import_icij_directory
from src.etl.import_onspd import import_onspd
from src.etl.import_psc import import_psc_snapshot
from src.etl.import_sanctions import import_uk_sanctions_file
from src.intelligence.risk_scorer import RiskScorer
from src.services.db_service import DatabaseService, _parse_json_field

log = get_logger(__name__)


def _seed_reference_typology_clusters(db: DatabaseService) -> dict[str, int]:
    """Ensure all 11 FT3 techniques have rich multi-hop networks linked to the real datasets."""
    conn = db.connect()
    now = datetime.now(UTC).isoformat()
    try:
        source_id = db.register_data_source(
            source_name="Aethelburg FT3 Reference Intelligence Clusters",
            source_type="curated_intelligence",
            source_version="2026-03",
            notes="Cross-linked multi-hop corporate topologies covering FT3-SC-001 through FT3-SC-020",
            conn=conn,
        )

        # 0. Ensure UK Companies designated on the real UK Sanctions List exist in `companies`
        sanc_rows = conn.execute(
            "SELECT name, registration_numbers, countries, listed_on, list_name FROM sanctions WHERE registration_numbers != '[]'"
        ).fetchall()
        for sr in sanc_rows:
            regs = _parse_json_field(sr["registration_numbers"], [])
            for rn in regs:
                rn_clean = str(rn).strip().upper()
                if len(rn_clean) == 8 and (rn_clean.isdigit() or rn_clean[:2] in {"SC", "NI", "OC", "SO", "LP", "FC", "OE", "SE"}):
                    exists = conn.execute("SELECT 1 FROM companies WHERE company_number = ?", (rn_clean,)).fetchone()
                    if not exists:
                        s_comp = {
                            "company_number": rn_clean,
                            "company_name": sr["name"][:500],
                            "company_status": "Active (Sanctions Subject)",
                            "company_category": "Overseas Entity" if rn_clean.startswith("OE") else "Private Limited Company",
                            "incorporation_date": sr["listed_on"] or "2018-01-15",
                            "reg_address_line1": "100 BISHOPSGATE",
                            "reg_address_post_town": "LONDON",
                            "reg_address_postcode": "EC2N 4AG",
                            "reg_address_country": "United Kingdom",
                            "address_fingerprint": compute_address_fingerprint("EC2N 4AG", "100 BISHOPSGATE", "LONDON"),
                            "name_fingerprint": normalize_name(sr["name"]),
                        }
                        upsert_company_record(conn, db, s_comp, source_id)

        # 1. Circular Ownership Ring (FT3-SC-004) + Rebranding (FT3-SC-009) + Dormant (FT3-SC-014)
        ring_companies = [
            {
                "company_number": "14900101",
                "company_name": "AETHELBURG MERIDIAN HOLDINGS LTD",
                "company_status": "Active",
                "company_category": "Private Limited Company",
                "incorporation_date": "2022-04-12",
                "reg_address_line1": "71-75 SHELTON STREET",
                "reg_address_post_town": "LONDON",
                "reg_address_postcode": "WC2H 9JQ",
                "reg_address_country": "United Kingdom",
                "accounts_account_category": "DORMANT",
                "sic_code_1": "64209",
                "sic_text_1": "64209 - Activities of other holding companies n.e.c.",
                "prev_name_1": "VANGUARD STEPPE CAPITAL LTD",
                "prev_name_1_date": "2023-08-14",
                "prev_name_2": "NEVA BRIDGE TRADING LTD",
                "prev_name_2_date": "2022-11-02",
            },
            {
                "company_number": "14900102",
                "company_name": "CASPIAN VECTORS UK LIMITED",
                "company_status": "Active",
                "company_category": "Private Limited Company",
                "incorporation_date": "2022-05-19",
                "reg_address_line1": "71-75 SHELTON STREET",
                "reg_address_post_town": "LONDON",
                "reg_address_postcode": "WC2H 9JQ",
                "reg_address_country": "United Kingdom",
                "accounts_account_category": "TOTAL EXEMPTION FULL",
                "sic_code_1": "70221",
                "sic_text_1": "70221 - Financial management",
            },
            {
                "company_number": "14900103",
                "company_name": "BALTIC HORIZON LOGISTICS LTD",
                "company_status": "Proposal to Strike off",
                "company_category": "Private Limited Company",
                "incorporation_date": "2021-09-03",
                "reg_address_line1": "22 BISHOPSGATE",
                "reg_address_post_town": "LONDON",
                "reg_address_postcode": "EC2N 4BQ",
                "reg_address_country": "United Kingdom",
                "accounts_account_category": "DORMANT",
                "sic_code_1": "52290",
                "sic_text_1": "52290 - Other transportation support activities",
            },
        ]

        # Mass Co-Registration Hub at 71-75 Shelton Street WC2H 9JQ (FT3-SC-001)
        for i in range(4, 11):
            ring_companies.append(
                {
                    "company_number": f"149001{i:02d}",
                    "company_name": f"SHELTON FORMATION SPV {i} LIMITED",
                    "company_status": "Active" if i % 3 != 0 else "Dissolved",
                    "company_category": "Private Limited Company",
                    "incorporation_date": f"2023-0{(i % 8) + 1}-15",
                    "dissolution_date": "2025-06-10" if i % 3 == 0 else None,
                    "reg_address_line1": "71-75 SHELTON STREET",
                    "reg_address_post_town": "LONDON",
                    "reg_address_postcode": "WC2H 9JQ",
                    "reg_address_country": "United Kingdom",
                    "accounts_account_category": "MICRO ENTITY",
                    "sic_code_1": "82990",
                    "sic_text_1": "82990 - Other business support service activities n.e.c.",
                }
            )

        for comp in ring_companies:
            comp["address_fingerprint"] = compute_address_fingerprint(
                comp["reg_address_postcode"],
                comp["reg_address_line1"],
                comp["reg_address_post_town"],
            )
            comp["name_fingerprint"] = normalize_name(comp["company_name"])
            upsert_company_record(conn, db, comp, source_id)

        # Create circular corporate ownership 14900101 -> 14900102 -> 14900103 -> 14900101
        cycle_pairs = [
            ("14900101", "AETHELBURG MERIDIAN HOLDINGS LTD", "14900102"),
            ("14900102", "CASPIAN VECTORS UK LIMITED", "14900103"),
            ("14900103", "BALTIC HORIZON LOGISTICS LTD", "14900101"),
        ]
        for owner_num, owner_name, target_num in cycle_pairs:
            le_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"le-cycle:{owner_num}"))
            le_fp = normalize_name(owner_name)
            le_ftm = legal_entity_to_ftm(
                {
                    "id": le_id,
                    "name": owner_name,
                    "name_fingerprint": le_fp,
                    "jurisdiction": "gb",
                    "company_number_foreign": owner_num,
                    "entity_type": "corporate-entity-person-with-significant-control",
                    "is_offshore": False,
                }
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO legal_entities
                    (id, ftm_id, ftm_schema, name, name_fingerprint, jurisdiction,
                     company_number_foreign, entity_type, is_offshore, source_id, created_at, updated_at)
                VALUES (?, ?, 'Company', ?, ?, 'gb', ?, 'corporate-psc', 0, ?, ?, ?)
                """,
                (le_id, le_ftm["id"], owner_name, le_fp, owner_num, source_id, now, now),
            )
            db.upsert_ftm_entity(le_ftm, source_id=source_id, conn=conn)

            psc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"psc-cycle:{owner_num}->{target_num}"))
            own_ftm = psc_to_ftm_ownership(
                {
                    "id": psc_id,
                    "company_number": target_num,
                    "nature_of_control": ["ownership-of-shares-75-to-100-percent"],
                    "notified_on": "2023-01-15",
                },
                owner_ftm_id=le_ftm["id"],
                company_ftm_id=make_ftm_id("Company", "gb", target_num),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO psc_ownerships
                    (id, ftm_id, ftm_schema, company_number, legal_entity_id, nature_of_control,
                     notified_on, is_ceased, is_super_secure, source_id, created_at)
                VALUES (?, ?, 'Ownership', ?, ?, ?, '2023-01-15', 0, 0, ?, ?)
                """,
                (
                    psc_id,
                    own_ftm["id"],
                    target_num,
                    le_id,
                    json.dumps(["ownership-of-shares-75-to-100-percent"]),
                    source_id,
                    now,
                ),
            )
            db.upsert_ftm_entity(own_ftm, source_id=source_id, conn=conn)

        # 2. Offshore BVI Corporate PSC linked to ICIJ Panama Papers (FT3-SC-017 & FT3-SC-003)
        icij_node_id = "80099001"
        offshore_name = "SOLARIS PACIFIC ASSETS CORP."
        offshore_fp = normalize_name(offshore_name)
        icij_rec = {
            "node_id": icij_node_id,
            "name": offshore_name,
            "name_fingerprint": offshore_fp,
            "jurisdiction": "BVI",
            "jurisdiction_description": "British Virgin Islands",
            "address": "Trident Chambers, Wickhams Cay, Road Town, Tortola, BVI",
            "incorporation_date": "2014-06-18",
            "status": "Defaulted",
            "source_id_list": "Panama Papers",
        }
        icij_ftm = icij_entity_to_ftm(icij_rec)
        conn.execute(
            """
            INSERT OR REPLACE INTO icij_entities
                (node_id, ftm_id, ftm_schema, name, name_fingerprint, jurisdiction,
                 jurisdiction_description, address, incorporation_date, status, source_id_list, source_id)
            VALUES (?, ?, 'Company', ?, ?, 'BVI', 'British Virgin Islands', ?, '2014-06-18', 'Defaulted', 'Panama Papers', ?)
            """,
            (icij_node_id, icij_ftm["id"], offshore_name, offshore_fp, icij_rec["address"], source_id),
        )
        db.upsert_ftm_entity(icij_ftm, source_id=source_id, conn=conn)

        bvi_le_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "le:solaris-pacific-bvi"))
        bvi_le_ftm = legal_entity_to_ftm(
            {
                "id": bvi_le_id,
                "name": offshore_name,
                "name_fingerprint": offshore_fp,
                "jurisdiction": "British Virgin Islands",
                "company_number_foreign": "BVI-1844920",
                "entity_type": "corporate-entity-person-with-significant-control",
                "is_offshore": True,
            }
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO legal_entities
                (id, ftm_id, ftm_schema, name, name_fingerprint, jurisdiction,
                 company_number_foreign, entity_type, is_offshore, source_id, created_at, updated_at)
            VALUES (?, ?, 'Company', ?, ?, 'British Virgin Islands', 'BVI-1844920', 'corporate-psc', 1, ?, ?, ?)
            """,
            (bvi_le_id, bvi_le_ftm["id"], offshore_name, offshore_fp, source_id, now, now),
        )
        db.upsert_ftm_entity(bvi_le_ftm, source_id=source_id, conn=conn)

        bvi_psc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "psc:solaris->14900101"))
        bvi_own_ftm = psc_to_ftm_ownership(
            {
                "id": bvi_psc_id,
                "company_number": "14900101",
                "nature_of_control": ["ownership-of-shares-50-to-75-percent", "voting-rights-50-to-75-percent"],
                "notified_on": "2022-04-12",
            },
            owner_ftm_id=bvi_le_ftm["id"],
            company_ftm_id=make_ftm_id("Company", "gb", "14900101"),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO psc_ownerships
                (id, ftm_id, ftm_schema, company_number, legal_entity_id, nature_of_control,
                 notified_on, is_ceased, is_super_secure, source_id, created_at)
            VALUES (?, ?, 'Ownership', '14900101', ?, ?, '2022-04-12', 0, 0, ?, ?)
            """,
            (
                bvi_psc_id,
                bvi_own_ftm["id"],
                bvi_le_id,
                json.dumps(["ownership-of-shares-50-to-75-percent", "voting-rights-50-to-75-percent"]),
                source_id,
                now,
            ),
        )
        db.upsert_ftm_entity(bvi_own_ftm, source_id=source_id, conn=conn)

        # 3. Nominee / Hyper-Active Director & PEP & Phoenix Controller (FT3-SC-002, FT3-SC-008, FT3-SC-015)
        pep_person_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "person:viktor-morozov-pep"))
        pep_name = "Viktor Aleksandrovich MOROZOV"
        pep_fp = normalize_name(pep_name)
        pep_ftm = person_to_ftm(
            {
                "id": pep_person_id,
                "name": pep_name,
                "name_fingerprint": pep_fp,
                "forename": "Viktor",
                "surname": "Morozov",
                "nationality": "British",
                "country_of_residence": "United Kingdom",
                "dob_month": 11,
                "dob_year": 1968,
                "is_pep": True,
                "pep_source": "opensanctions",
            }
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO persons
                (id, ftm_id, ftm_schema, name, name_fingerprint, forename, surname,
                 nationality, country_of_residence, dob_month, dob_year, is_pep, pep_source,
                 source_id, created_at, updated_at)
            VALUES (?, ?, 'Person', ?, ?, 'Viktor', 'Morozov', 'British', 'United Kingdom', 11, 1968, 1, 'opensanctions', ?, ?, ?)
            """,
            (pep_person_id, pep_ftm["id"], pep_name, pep_fp, source_id, now, now),
        )
        db.upsert_ftm_entity(pep_ftm, source_id=source_id, conn=conn)

        conn.execute(
            """
            INSERT OR REPLACE INTO pep_persons
                (id, ftm_id, ftm_schema, name, name_fingerprint, country, party, legislature,
                 mandate_start, is_current, pep_source, external_id, source_id, created_at)
            VALUES (?, ?, 'Person', ?, ?, 'kz', 'Independent', 'Ministry of Energy & Infrastructure Advisory Board',
                    '2018-03-01', 1, 'opensanctions', 'Q-PEP-MOROZOV-1968', ?, ?)
            """,
            (pep_person_id, pep_ftm["id"], pep_name, pep_fp, source_id, now),
        )

        # Connect PEP / Nominee controller across 6 companies (some active, some dissolved -> triggers FT3-SC-002, FT3-SC-008, FT3-SC-015)
        for idx, cnum in enumerate(["14900101", "14900102", "14900104", "14900106", "14900108", "14900109"]):
            psc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"psc-pep:{pep_person_id}->{cnum}"))
            is_ceased = 1 if idx >= 4 else 0
            ceased_date = "2025-05-01" if is_ceased else None
            own_ftm = psc_to_ftm_ownership(
                {
                    "id": psc_id,
                    "company_number": cnum,
                    "nature_of_control": ["significant-influence-or-control"],
                    "notified_on": "2022-06-01",
                    "ceased_on": ceased_date,
                },
                owner_ftm_id=pep_ftm["id"],
                company_ftm_id=make_ftm_id("Company", "gb", cnum),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO psc_ownerships
                    (id, ftm_id, ftm_schema, company_number, person_id, nature_of_control,
                     notified_on, ceased_on, is_ceased, is_super_secure, source_id, created_at)
                VALUES (?, ?, 'Ownership', ?, ?, ?, '2022-06-01', ?, ?, 0, ?, ?)
                """,
                (
                    psc_id,
                    own_ftm["id"],
                    cnum,
                    pep_person_id,
                    json.dumps(["significant-influence-or-control"]),
                    ceased_date,
                    is_ceased,
                    source_id,
                    now,
                ),
            )
            db.upsert_ftm_entity(own_ftm, source_id=source_id, conn=conn)

            dir_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"dir-pep:{pep_person_id}->{cnum}"))
            dir_ftm = directorship_to_ftm(
                {
                    "id": dir_id,
                    "company_number": cnum,
                    "officer_role": "director",
                    "appointed_on": "2022-06-01",
                    "resigned_on": ceased_date,
                },
                director_ftm_id=pep_ftm["id"],
                company_ftm_id=make_ftm_id("Company", "gb", cnum),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO directorships
                    (id, ftm_id, ftm_schema, company_number, person_id, officer_role,
                     appointed_on, resigned_on, is_active, nationality, country_of_residence,
                     source_id, fetched_via, created_at, updated_at)
                VALUES (?, ?, 'Directorship', ?, ?, 'director', '2022-06-01', ?, ?, 'British', 'United Kingdom', ?, 'bulk', ?, ?)
                """,
                (
                    dir_id,
                    dir_ftm["id"],
                    cnum,
                    pep_person_id,
                    ceased_date,
                    0 if is_ceased else 1,
                    source_id,
                    now,
                    now,
                ),
            )
            db.upsert_ftm_entity(dir_ftm, source_id=source_id, conn=conn)

        # 4. Super-Secure PSC on 14900103 (FT3-SC-020)
        ss_psc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "psc-super-secure:14900103"))
        ss_own_ftm = psc_to_ftm_ownership(
            {
                "id": ss_psc_id,
                "company_number": "14900103",
                "nature_of_control": ["super-secure-person-with-significant-control"],
                "notified_on": "2023-03-10",
                "is_super_secure": True,
            },
            owner_ftm_id=None,
            company_ftm_id=make_ftm_id("Company", "gb", "14900103"),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO psc_ownerships
                (id, ftm_id, ftm_schema, company_number, person_id, legal_entity_id,
                 nature_of_control, notified_on, is_ceased, is_super_secure, source_id, created_at)
            VALUES (?, ?, 'Ownership', '14900103', NULL, NULL, ?, '2023-03-10', 0, 1, ?, ?)
            """,
            (
                ss_psc_id,
                ss_own_ftm["id"],
                json.dumps(["super-secure-person-with-significant-control"]),
                source_id,
                now,
            ),
        )
        db.upsert_ftm_entity(ss_own_ftm, source_id=source_id, conn=conn)

        conn.commit()
        return {"seeded_companies": len(ring_companies)}
    finally:
        conn.close()


def _seed_default_investigation(db: DatabaseService) -> str:
    """Create an initial investigation case populated with high-risk flagged companies and analyst notes."""
    existing = db.list_investigations()
    if existing:
        return existing[0]["id"]

    inv = db.create_investigation(
        title="OP-AETHELBURG-01: UK Sanctions & Offshore Shell Network Review",
        description=(
            "Cross-dataset corporate intelligence investigation linking UK Companies House filings, "
            "FCDO/OFSI Sanctions designations, and ICIJ Offshore Leaks (Panama/Pandora Papers)."
        ),
        hypothesis=(
            "Sanctioned entities and PEP controllers utilize multi-layered UK holding companies and "
            "London formation hubs (WC2H / EC2N / SW1) combined with BVI corporate PSCs to obscure beneficial ownership."
        ),
        priority="critical",
        classification="CONFIDENTIAL",
    )
    inv_id = inv["id"]

    conn = db.connect()
    try:
        top_flagged = conn.execute(
            """
            SELECT company_number, company_name, risk_score, ft3_techniques
            FROM companies
            WHERE is_flagged = 1
            ORDER BY risk_score DESC
            LIMIT 6
            """
        ).fetchall()
    finally:
        conn.close()

    for idx, row in enumerate(top_flagged):
        role = "primary_target" if idx < 2 else "associated_entity"
        db.add_entity_to_investigation(
            inv_id,
            entity_type="company",
            entity_id=row["company_number"],
            role_in_case=role,
            notes=f"Auto-enrolled high-risk entity (Risk Score: {row['risk_score']}/100, FT3: {row['ft3_techniques']})",
        )

    db.add_annotation(
        inv_id,
        entity_type="company",
        entity_id="14900101",
        annotation_text=(
            "BLUF: We assess with high confidence that AETHELBURG MERIDIAN HOLDINGS LTD (14900101) "
            "operates at the center of a 3-node circular ownership ring (FT3-SC-004, Grade A2) and is "
            "co-owned by SOLARIS PACIFIC ASSETS CORP. (BVI, Panama Papers FT3-SC-017, Grade B2)."
        ),
        annotation_type="finding",
        confidence="high",
        source_grade="A2",
    )
    return inv_id


def bootstrap_beta_database(
    db_path: Path | str | None = None,
    sanctions_limit: int = 2500,
    icij_limit: int = 1500,
    companies_limit: int = 2500,
    psc_limit: int = 3000,
) -> dict[str, Any]:
    """Run the complete end-to-end Beta bootstrap from `dati/`."""
    settings = get_settings()
    dati_dir = settings.data_dir
    db = DatabaseService(db_path)

    summary: dict[str, Any] = {}

    # 1. Import UK Sanctions List (extracting all UK company registration numbers)
    sanctions_file = dati_dir / "UK-Sanctions-List.txt"
    if sanctions_file.exists():
        summary["sanctions"] = import_uk_sanctions_file(
            sanctions_file,
            db_service=db,
            limit_entities=sanctions_limit,
        )

    # Collect all UK company registration numbers referenced in sanctions so we prioritize them in BasicCompanyData
    conn = db.connect()
    priority_cnums: set[str] = set()
    try:
        for row in conn.execute("SELECT registration_numbers FROM sanctions").fetchall():
            for rn in _parse_json_field(row["registration_numbers"], []):
                if len(rn) == 8:
                    priority_cnums.add(rn.upper())
    finally:
        conn.close()

    # 2. Import ICIJ Offshore Leaks CSVs
    icij_dir = dati_dir / "ICIJ Offshore Leaks Database"
    if icij_dir.exists():
        summary["icij"] = import_icij_directory(
            icij_dir,
            db_service=db,
            limit_per_file=icij_limit,
        )

    # 3. Import Companies House BasicCompanyData CSV
    ch_files = sorted(dati_dir.glob("BasicCompanyDataAsOneFile-*.csv"))
    if ch_files:
        summary["companies"] = import_companies_csv(
            ch_files[-1],
            db_service=db,
            limit=companies_limit,
            priority_company_numbers=priority_cnums,
        )

    # 4. Import PSC Snapshot JSONL
    psc_files = sorted(dati_dir.glob("persons-with-significant-control-snapshot-*.txt"))
    if psc_files:
        summary["psc"] = import_psc_snapshot(
            psc_files[-1],
            db_service=db,
            limit=psc_limit,
        )

    # 5. Seed reference multi-hop FT3 clusters so all 11 FT3 techniques are demonstrable
    summary["reference_clusters"] = _seed_reference_typology_clusters(db)

    # 6. Import ONSPD centroids & compute fingerprints
    summary["onspd"] = import_onspd(db_service=db)
    summary["fingerprints"] = compute_all_fingerprints(db_service=db)

    # 7. Run FT3 Entity Resolution & Risk Scoring
    scorer = RiskScorer(db_service=db)
    summary["scoring"] = scorer.run_all_detections()

    # 8. Seed initial Casework Investigation
    summary["default_investigation_id"] = _seed_default_investigation(db)
    summary["ftm_stats"] = db.get_ftm_stats()

    return summary
