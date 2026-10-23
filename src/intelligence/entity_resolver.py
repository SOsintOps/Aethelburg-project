"""Cross-dataset Entity Resolution engine (ADR-017).

Links UK Companies House (`companies`, `persons`, `legal_entities`) with:
  - UK FCDO / OFSI `sanctions`: exact UK CRN (`A1`), exact company `name_fingerprint` (`B2`); people by
    `name_fingerprint` checked against the published date of birth (`A2` when month/year agree, `B2`
    moderate when only the years can be compared, dropped when they differ, `B3` low confidence when
    either side has no date); a former controller is kept, marked with `controller_ceased_on`
  - ICIJ Offshore Leaks (`icij_entities`, `icij_officers`; officers have no date of birth: `C3` low)
  - Updates `ftm_entities.referents` to preserve canonical FollowTheMoney cross-dataset links
"""
from __future__ import annotations

import json
from typing import Any

from src.core.logging import get_logger
from src.services.db_service import DatabaseService, _parse_json_field

log = get_logger(__name__)


def compare_birth_dates(birth_dates: list[dict[str, Any]], year: Any, month: Any) -> str:
    """Compare a Companies House month/year with the dates a sanctions list publishes.

    `match` when month and year agree, `year_only` when the years agree but one side has no month,
    `conflict` when the year or the month differs, `unknown` when either side has no date at all.
    """
    if not year or not birth_dates:
        return "unknown"
    outcome = "conflict"
    for d in birth_dates:
        if d.get("year") != int(year):
            continue
        if d.get("month") is None or not month:
            outcome = "year_only"
        elif d["month"] == int(month):
            return "match"
    return outcome


# grade, confidence and match type for each outcome of the date comparison
_PSC_SANCTION_GRADES = {
    "match": ("A2", "high", "psc_name_and_dob"),
    "year_only": ("B2", "moderate", "psc_name_and_birth_year"),
    "unknown": ("B3", "low", "psc_name_only"),
}
_OUTCOME_RANK = {"match": 0, "year_only": 1, "unknown": 2}


class EntityResolver:
    """Multi-tiered cross-dataset entity resolution."""

    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self.db = db_service or DatabaseService()

    def resolve_all(self) -> dict[str, Any]:
        """Run cross-dataset resolution and return all resolved links with UNODC 4x4 grades."""
        conn = self.db.connect()
        try:
            sanction_matches: list[dict[str, Any]] = []
            icij_matches: list[dict[str, Any]] = []
            pep_matches: list[dict[str, Any]] = []

            # 1. Exact UK Registration Number match in Sanctions (Grade A1, Confidence: high)
            sanc_with_reg = conn.execute(
                """
                SELECT id, ftm_id, subject_ftm_id, name, list_name, listed_on, registration_numbers, opensanctions_id
                FROM sanctions
                WHERE registration_numbers IS NOT NULL AND registration_numbers != '[]'
                """
            ).fetchall()

            reg_to_sanc: dict[str, list[dict[str, Any]]] = {}
            for s in sanc_with_reg:
                regs = _parse_json_field(s["registration_numbers"], [])
                for rn in regs:
                    rn_clean = str(rn).strip().upper()
                    if rn_clean:
                        reg_to_sanc.setdefault(rn_clean, []).append(dict(s))

            if reg_to_sanc:
                placeholders = ",".join("?" for _ in reg_to_sanc)
                matched_comps = conn.execute(
                    f"SELECT company_number, company_name, ftm_id FROM companies WHERE company_number IN ({placeholders})",
                    list(reg_to_sanc.keys()),
                ).fetchall()
                for c in matched_comps:
                    cnum = c["company_number"]
                    for s in reg_to_sanc.get(cnum, []):
                        sanction_matches.append(
                            {
                                "company_number": cnum,
                                "company_name": c["company_name"],
                                "sanction_id": s["id"],
                                "sanction_name": s["name"],
                                "opensanctions_id": s["opensanctions_id"],
                                "list_name": s["list_name"],
                                "listed_on": s["listed_on"],
                                "match_type": "exact_registration_number",
                                "unodc_grade": "A1",
                                "confidence": "high",
                            }
                        )
                        self._add_ftm_referent(conn, c["ftm_id"], s["subject_ftm_id"] or s["ftm_id"])

            # 2. Exact name_fingerprint match between Companies / PSCs and Sanctions (Grade B2)
            fp_matches = conn.execute(
                """
                SELECT c.company_number, c.company_name, c.ftm_id AS comp_ftm_id,
                       s.id AS sanction_id, s.name AS sanction_name, s.opensanctions_id,
                       s.list_name, s.listed_on, s.subject_ftm_id, s.ftm_id AS sanc_ftm_id
                FROM companies c
                JOIN sanctions s ON s.name_fingerprint = c.name_fingerprint AND s.entity_type != 'Person'
                WHERE c.name_fingerprint IS NOT NULL AND c.name_fingerprint != ''
                """
            ).fetchall()
            seen_pairs = {(m["company_number"], m["sanction_id"]) for m in sanction_matches}
            for row in fp_matches:
                pair = (row["company_number"], row["sanction_id"])
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    sanction_matches.append(
                        {
                            "company_number": row["company_number"],
                            "company_name": row["company_name"],
                            "sanction_id": row["sanction_id"],
                            "sanction_name": row["sanction_name"],
                            "opensanctions_id": row["opensanctions_id"],
                            "list_name": row["list_name"],
                            "listed_on": row["listed_on"],
                            "match_type": "company_name_fingerprint",
                            "unodc_grade": "B2",
                            "confidence": "high",
                        }
                    )
                    self._add_ftm_referent(conn, row["comp_ftm_id"], row["subject_ftm_id"] or row["sanc_ftm_id"])

            # PSC Person -> sanctioned Person: same name, then the date of birth decides
            psc_sanc_rows = conn.execute(
                """
                SELECT po.company_number, c.company_name, p.name AS controller_name, p.ftm_id AS person_ftm_id,
                       p.dob_year, p.dob_month, po.ceased_on,
                       s.id AS sanction_id, s.name AS sanction_name, s.opensanctions_id,
                       s.list_name, s.listed_on, s.subject_ftm_id, s.raw_properties
                FROM psc_ownerships po
                JOIN companies c ON c.company_number = po.company_number
                JOIN persons p ON p.id = po.person_id
                JOIN sanctions s ON s.name_fingerprint = p.name_fingerprint AND s.entity_type = 'Person'
                WHERE p.name_fingerprint IS NOT NULL AND p.name_fingerprint != ''
                """
            ).fetchall()
            best: dict[tuple[str, str], dict[str, Any]] = {}
            for row in psc_sanc_rows:
                pair = (row["company_number"], row["sanction_id"])
                if pair in seen_pairs:
                    continue
                birth_dates = _parse_json_field(row["raw_properties"], {}).get("birth_dates") or []
                outcome = compare_birth_dates(birth_dates, row["dob_year"], row["dob_month"])
                if outcome == "conflict":
                    continue  # same name, different person
                ceased_on = row["ceased_on"] or None
                # keep the best evidence for the pair: closest dates first, a current controller before a former one
                rank = (_OUTCOME_RANK[outcome], ceased_on is not None)
                if pair in best and best[pair]["_rank"] <= rank:
                    continue
                grade, confidence, match_type = _PSC_SANCTION_GRADES[outcome]
                best[pair] = {
                    "company_number": row["company_number"],
                    "company_name": row["company_name"],
                    "controller_name": row["controller_name"],
                    "controller_dob": f"{row['dob_month'] or '?'}/{row['dob_year']}" if row["dob_year"] else None,
                    "controller_ceased_on": ceased_on,
                    "sanction_id": row["sanction_id"],
                    "sanction_name": row["sanction_name"],
                    "opensanctions_id": row["opensanctions_id"],
                    "list_name": row["list_name"],
                    "listed_on": row["listed_on"],
                    "match_type": match_type,
                    "unodc_grade": grade,
                    "confidence": confidence,
                    "_ftm": (row["person_ftm_id"], row["subject_ftm_id"]),
                    "_rank": rank,
                }
            for match in best.values():
                match.pop("_rank")
                self._add_ftm_referent(conn, *match.pop("_ftm"))
                sanction_matches.append(match)

            # 3. Cross-Dataset ICIJ Offshore Matches (Companies, Corporate PSCs, Individual PSCs)
            comp_icij_rows = conn.execute(
                """
                SELECT c.company_number, c.company_name, c.ftm_id AS comp_ftm_id,
                       ie.node_id, ie.name AS icij_name, ie.jurisdiction_description,
                       ie.source_id_list, ie.ftm_id AS icij_ftm_id
                FROM companies c
                JOIN icij_entities ie ON ie.name_fingerprint = c.name_fingerprint
                WHERE c.name_fingerprint IS NOT NULL AND len_check.len_ok = 1
                """.replace(
                    "AND len_check.len_ok = 1",
                    "AND length(c.name_fingerprint) >= 4",
                )
            ).fetchall()
            for row in comp_icij_rows:
                icij_matches.append(
                    {
                        "company_number": row["company_number"],
                        "company_name": row["company_name"],
                        "node_id": row["node_id"],
                        "icij_name": row["icij_name"],
                        "jurisdiction": row["jurisdiction_description"],
                        "dataset": row["source_id_list"],
                        "match_role": "company_direct_match",
                        "unodc_grade": "B2",
                        "confidence": "high",
                    }
                )
                self._add_ftm_referent(conn, row["comp_ftm_id"], row["icij_ftm_id"])

            le_icij_rows = conn.execute(
                """
                SELECT po.company_number, c.company_name, le.name AS psc_entity_name, le.ftm_id AS le_ftm_id,
                       ie.node_id, ie.name AS icij_name, ie.jurisdiction_description,
                       ie.source_id_list, ie.ftm_id AS icij_ftm_id
                FROM psc_ownerships po
                JOIN companies c ON c.company_number = po.company_number
                JOIN legal_entities le ON le.id = po.legal_entity_id
                JOIN icij_entities ie ON ie.name_fingerprint = le.name_fingerprint
                WHERE le.name_fingerprint IS NOT NULL AND length(le.name_fingerprint) >= 4
                """
            ).fetchall()
            for row in le_icij_rows:
                icij_matches.append(
                    {
                        "company_number": row["company_number"],
                        "company_name": row["company_name"],
                        "psc_entity_name": row["psc_entity_name"],
                        "node_id": row["node_id"],
                        "icij_name": row["icij_name"],
                        "jurisdiction": row["jurisdiction_description"],
                        "dataset": row["source_id_list"],
                        "match_role": "corporate_psc_in_icij",
                        "unodc_grade": "B2",
                        "confidence": "high",
                    }
                )
                self._add_ftm_referent(conn, row["le_ftm_id"], row["icij_ftm_id"])

            p_icij_rows = conn.execute(
                """
                SELECT po.company_number, c.company_name, p.name AS person_name, p.ftm_id AS p_ftm_id,
                       io.node_id, io.name AS icij_name, io.countries AS jurisdiction_description,
                       io.source_id_list, io.ftm_id AS icij_ftm_id
                FROM psc_ownerships po
                JOIN companies c ON c.company_number = po.company_number
                JOIN persons p ON p.id = po.person_id
                JOIN icij_officers io ON io.name_fingerprint = p.name_fingerprint
                WHERE p.name_fingerprint IS NOT NULL AND length(p.name_fingerprint) >= 5
                """
            ).fetchall()
            for row in p_icij_rows:
                icij_matches.append(
                    {
                        "company_number": row["company_number"],
                        "company_name": row["company_name"],
                        "person_name": row["person_name"],
                        "node_id": row["node_id"],
                        "icij_name": row["icij_name"],
                        "jurisdiction": row["jurisdiction_description"],
                        "dataset": row["source_id_list"],
                        "match_role": "individual_psc_in_icij_officers",
                        "unodc_grade": "C3",  # name only: ICIJ publishes no date of birth
                        "confidence": "low",
                    }
                )
                self._add_ftm_referent(conn, row["p_ftm_id"], row["icij_ftm_id"])

            # 4. PEP Matches
            pep_rows = conn.execute(
                """
                SELECT po.company_number, c.company_name, p.id AS person_id, p.name AS person_name,
                       pp.party, pp.legislature, pp.country, pp.pep_source
                FROM psc_ownerships po
                JOIN companies c ON c.company_number = po.company_number
                JOIN persons p ON p.id = po.person_id
                LEFT JOIN pep_persons pp ON pp.name_fingerprint = p.name_fingerprint
                WHERE p.is_pep = 1 OR pp.id IS NOT NULL
                """
            ).fetchall()
            for row in pep_rows:
                if row["person_id"]:
                    conn.execute("UPDATE persons SET is_pep = 1 WHERE id = ?", (row["person_id"],))
                pep_matches.append(dict(row))

            conn.commit()
            return {
                "sanction_matches": sanction_matches,
                "icij_matches": icij_matches,
                "pep_matches": pep_matches,
            }
        finally:
            conn.close()

    def _add_ftm_referent(self, conn: Any, primary_ftm_id: str | None, referent_ftm_id: str | None) -> None:
        if not primary_ftm_id or not referent_ftm_id or primary_ftm_id == referent_ftm_id:
            return
        row = conn.execute(
            "SELECT referents FROM ftm_entities WHERE id = ?",
            (primary_ftm_id,),
        ).fetchone()
        if not row:
            return
        refs = _parse_json_field(row["referents"], [])
        if referent_ftm_id not in refs:
            refs.append(referent_ftm_id)
            conn.execute(
                "UPDATE ftm_entities SET referents = ? WHERE id = ?",
                (json.dumps(refs, ensure_ascii=False), primary_ftm_id),
            )
