"""Batch computation of name & address fingerprints and `name_variants` (ADR-015 / ADR-017)."""
from __future__ import annotations

from src.core.logging import get_logger
from src.core.normalizer import compute_address_fingerprint, normalize_name, phonetic_key
from src.services.db_service import DatabaseService

log = get_logger(__name__)


def compute_all_fingerprints(db_service: DatabaseService | None = None) -> dict[str, int]:
    """Recompute missing `name_fingerprint`, `address_fingerprint`, and phonetic `name_variants`."""
    db = db_service or DatabaseService()
    conn = db.connect()
    updated = {"companies": 0, "persons": 0, "legal_entities": 0, "phonetic_variants": 0}

    try:
        comp_rows = conn.execute(
            """
            SELECT company_number, company_name, reg_address_postcode,
                   reg_address_line1, reg_address_line2, reg_address_post_town, ftm_id
            FROM companies
            WHERE name_fingerprint IS NULL OR address_fingerprint IS NULL
            """
        ).fetchall()
        for r in comp_rows:
            nfp = normalize_name(r["company_name"])
            afp = compute_address_fingerprint(
                r["reg_address_postcode"],
                r["reg_address_line1"],
                r["reg_address_line2"],
                r["reg_address_post_town"],
            )
            conn.execute(
                "UPDATE companies SET name_fingerprint = ?, address_fingerprint = ? WHERE company_number = ?",
                (nfp, afp, r["company_number"]),
            )
            updated["companies"] += 1

        person_rows = conn.execute(
            "SELECT id, name, ftm_id FROM persons WHERE name_fingerprint IS NULL"
        ).fetchall()
        for r in person_rows:
            nfp = normalize_name(r["name"])
            conn.execute("UPDATE persons SET name_fingerprint = ? WHERE id = ?", (nfp, r["id"]))
            updated["persons"] += 1

        # Add phonetic variants for persons & companies
        for r in conn.execute("SELECT id, name, name_fingerprint, ftm_id FROM persons LIMIT 5000").fetchall():
            pk = phonetic_key(r["name"])
            if pk:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO name_variants
                        (entity_id, entity_type, variant_text, fingerprint, ftm_id, variant_type)
                    VALUES (?, 'person', ?, ?, ?, 'phonetic_key')
                    """,
                    (r["id"], r["name"], pk, r["ftm_id"]),
                )
                updated["phonetic_variants"] += 1

        conn.commit()
        return updated
    finally:
        conn.close()
