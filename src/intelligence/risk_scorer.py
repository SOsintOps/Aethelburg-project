"""FT3 Shell Company Detection & Risk Scoring Engine (ADR-016).

Evaluates all 11 FT3 techniques (`FT3-SC-001` through `FT3-SC-020`):
  - Populates `risk_flags` with structured JSON evidence, UNODC 4x4 grades, and confidence levels
  - Computes composite `risk_score` (0.0 - 100.0) and `ft3_techniques` on `companies`
  - Sets `ftm_entities.target = 1` for flagged high-risk entities
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import networkx as nx

from src.core.logging import get_logger
from src.intelligence.entity_resolver import EntityResolver
from src.intelligence.ft3_mapper import FT3_TECHNIQUES, get_technique_metadata
from src.services.db_service import DatabaseService

log = get_logger(__name__)


class RiskScorer:
    """Comprehensive FT3 pattern detector and risk scorer."""

    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self.db = db_service or DatabaseService()
        self.resolver = EntityResolver(self.db)

    def run_all_detections(
        self,
        mass_address_threshold: int = 5,
        nominee_director_threshold: int = 4,
    ) -> dict[str, Any]:
        """Run all 11 FT3 detection rules, persist `risk_flags`, and recompute company `risk_score`."""
        resolved = self.resolver.resolve_all()
        conn = self.db.connect()
        now = datetime.now(UTC).isoformat()
        detected_counts: dict[str, int] = {code: 0 for code in FT3_TECHNIQUES}

        try:
            # Reset active flags before full recomputation
            conn.execute("DELETE FROM risk_flags")

            def _upsert_flag(
                company_number: str,
                code: str,
                evidence: dict[str, Any],
                score_override: float | None = None,
            ) -> None:
                meta = get_technique_metadata(code)
                score = float(score_override if score_override is not None else meta["base_score"])
                evidence_with_grading = {
                    "unodc_grade": evidence.get("unodc_grade", meta["default_grade"]),
                    "confidence": evidence.get("confidence", meta["default_confidence"]),
                    "tactic": meta["tactic"],
                    "technique_name": meta["name"],
                    **evidence,
                }
                conn.execute(
                    """
                    INSERT OR REPLACE INTO risk_flags
                        (company_number, ft3_technique, priority, score_contribution, evidence, detected_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        company_number,
                        code,
                        meta["priority"],
                        score,
                        json.dumps(evidence_with_grading, ensure_ascii=False),
                        now,
                    ),
                )
                detected_counts[code] = detected_counts.get(code, 0) + 1

            # ------------------------------------------------------------------ #
            # 1. FT3-SC-007: Sanctioned Entity Connection (CRITICAL)             #
            # ------------------------------------------------------------------ #
            sanc_by_comp: dict[str, list[dict[str, Any]]] = {}
            for m in resolved["sanction_matches"]:
                sanc_by_comp.setdefault(m["company_number"], []).append(m)
            for comp_num, matches in sanc_by_comp.items():
                best_grade = "A1" if any(m.get("unodc_grade") == "A1" for m in matches) else "B2"
                _upsert_flag(
                    comp_num,
                    "FT3-SC-007",
                    {
                        "unodc_grade": best_grade,
                        "confidence": "high",
                        "match_count": len(matches),
                        "sanctions": matches[:5],
                        "summary": f"Matched {len(matches)} UK FCDO/OFSI sanctions designation(s): {matches[0]['sanction_name']} ({matches[0]['opensanctions_id']})",
                    },
                    score_override=48.0 if best_grade == "A1" else 42.0,
                )

            # ------------------------------------------------------------------ #
            # 2. FT3-SC-017: Cross-Dataset Offshore Entity (CRITICAL)            #
            # ------------------------------------------------------------------ #
            icij_by_comp: dict[str, list[dict[str, Any]]] = {}
            for m in resolved["icij_matches"]:
                icij_by_comp.setdefault(m["company_number"], []).append(m)
            for comp_num, matches in icij_by_comp.items():
                _upsert_flag(
                    comp_num,
                    "FT3-SC-017",
                    {
                        "unodc_grade": "B2",
                        "confidence": "high",
                        "match_count": len(matches),
                        "offshore_matches": matches[:5],
                        "summary": f"Linked to {len(matches)} ICIJ Offshore Leaks record(s): {matches[0]['icij_name']} ({matches[0].get('dataset') or 'Offshore Leaks'})",
                    },
                )

            # ------------------------------------------------------------------ #
            # 3. FT3-SC-004: Circular Ownership Structure (CRITICAL)             #
            # ------------------------------------------------------------------ #
            corp_edges = conn.execute(
                """
                SELECT po.company_number AS target_comp,
                       c_target.name_fingerprint AS target_fp,
                       le.name_fingerprint AS owner_fp,
                       le.company_number_foreign AS owner_reg,
                       le.name AS owner_name
                FROM psc_ownerships po
                JOIN companies c_target ON c_target.company_number = po.company_number
                JOIN legal_entities le ON le.id = po.legal_entity_id
                WHERE po.is_ceased = 0
                """
            ).fetchall()

            fp_to_comp: dict[str, str] = {}
            for r in conn.execute(
                "SELECT company_number, name_fingerprint FROM companies WHERE name_fingerprint IS NOT NULL"
            ).fetchall():
                fp_to_comp[r["name_fingerprint"]] = r["company_number"]

            dg = nx.DiGraph()
            for edge in corp_edges:
                target_c = edge["target_comp"]
                owner_c = None
                if edge["owner_reg"] and edge["owner_reg"].strip().upper() in fp_to_comp.values():
                    owner_c = edge["owner_reg"].strip().upper()
                elif edge["owner_fp"] and edge["owner_fp"] in fp_to_comp:
                    owner_c = fp_to_comp[edge["owner_fp"]]
                if owner_c:
                    dg.add_edge(owner_c, target_c, owner_name=edge["owner_name"])

            for cycle in nx.simple_cycles(dg):
                if len(cycle) >= 1:
                    cycle_chain = " -> ".join([*cycle, cycle[0]])
                    for comp_num in cycle:
                        _upsert_flag(
                            comp_num,
                            "FT3-SC-004",
                            {
                                "unodc_grade": "A2",
                                "confidence": "high",
                                "cycle_length": len(cycle),
                                "cycle_nodes": cycle,
                                "summary": f"Circular corporate ownership cycle detected ({len(cycle)} hops): {cycle_chain}",
                            },
                        )

            # ------------------------------------------------------------------ #
            # 4. FT3-SC-001: Mass Co-Registration Hub (HIGH)                     #
            # ------------------------------------------------------------------ #
            hub_rows = conn.execute(
                """
                SELECT address_fingerprint, COUNT(*) AS cnt,
                       MAX(reg_address_line1) AS line1,
                       MAX(reg_address_postcode) AS postcode
                FROM companies
                WHERE address_fingerprint IS NOT NULL AND address_fingerprint != ''
                GROUP BY address_fingerprint
                HAVING COUNT(*) >= ?
                """,
                (int(mass_address_threshold),),
            ).fetchall()

            for hub in hub_rows:
                afp = hub["address_fingerprint"]
                cnt = int(hub["cnt"])
                dynamic_score = min(34.0, 20.0 + (cnt / 5.0))
                comp_rows = conn.execute(
                    "SELECT company_number FROM companies WHERE address_fingerprint = ?",
                    (afp,),
                ).fetchall()
                for cr in comp_rows:
                    _upsert_flag(
                        cr["company_number"],
                        "FT3-SC-001",
                        {
                            "unodc_grade": "A1",
                            "confidence": "high",
                            "address_fingerprint": afp,
                            "colocated_companies_count": cnt,
                            "address": f"{hub['line1'] or ''}, {hub['postcode'] or ''}".strip(", "),
                            "summary": f"Co-registered at formation hub with {cnt} companies ({hub['line1'] or ''}, {hub['postcode'] or ''})",
                        },
                        score_override=round(dynamic_score, 1),
                    )

            # ------------------------------------------------------------------ #
            # 5. FT3-SC-002: Nominee / Hyper-Active Director or Controller (HIGH)#
            # ------------------------------------------------------------------ #
            nominee_rows = conn.execute(
                """
                SELECT p.id AS person_id, p.name AS person_name, p.nationality,
                       COUNT(DISTINCT po.company_number) AS company_count
                FROM psc_ownerships po
                JOIN persons p ON p.id = po.person_id
                GROUP BY p.id
                HAVING COUNT(DISTINCT po.company_number) >= ?
                """,
                (int(nominee_director_threshold),),
            ).fetchall()

            for nom in nominee_rows:
                p_id = nom["person_id"]
                cnt = int(nom["company_count"])
                c_rows = conn.execute(
                    "SELECT DISTINCT company_number FROM psc_ownerships WHERE person_id = ?",
                    (p_id,),
                ).fetchall()
                for cr in c_rows:
                    _upsert_flag(
                        cr["company_number"],
                        "FT3-SC-002",
                        {
                            "unodc_grade": "B2",
                            "confidence": "moderate",
                            "person_id": p_id,
                            "person_name": nom["person_name"],
                            "appointment_count": cnt,
                            "summary": f"Controlled/directed by hyper-active individual '{nom['person_name']}' across {cnt} companies",
                        },
                        score_override=min(32.0, 22.0 + cnt),
                    )

            # ------------------------------------------------------------------ #
            # 6. FT3-SC-003: Layered Corporate / Offshore Ownership Chain (HIGH) #
            # ------------------------------------------------------------------ #
            layered_rows = conn.execute(
                """
                SELECT po.company_number, le.name AS corporate_owner, le.jurisdiction,
                       le.is_offshore, le.company_number_foreign
                FROM psc_ownerships po
                JOIN legal_entities le ON le.id = po.legal_entity_id
                WHERE le.is_offshore = 1
                   OR po.company_number IN (
                       SELECT company_number FROM psc_ownerships WHERE legal_entity_id IS NOT NULL
                   )
                """
            ).fetchall()
            for lr in layered_rows:
                cnum = lr["company_number"]
                is_off = bool(lr["is_offshore"])
                in_chain = dg.in_degree(cnum) > 0 and dg.out_degree(cnum) > 0 if cnum in dg else False
                if is_off or in_chain:
                    _upsert_flag(
                        cnum,
                        "FT3-SC-003",
                        {
                            "unodc_grade": "B2",
                            "confidence": "moderate",
                            "corporate_owner": lr["corporate_owner"],
                            "jurisdiction": lr["jurisdiction"] or "Foreign / Multi-Layer",
                            "is_offshore": is_off,
                            "summary": (
                                f"Controlled by corporate legal entity '{lr['corporate_owner']}' "
                                f"({lr['jurisdiction'] or 'Corporate Layer'})"
                            ),
                        },
                    )

            # ------------------------------------------------------------------ #
            # 7. FT3-SC-008: Politically Exposed Person (PEP) Link (HIGH)        #
            # ------------------------------------------------------------------ #
            for pm in resolved["pep_matches"]:
                _upsert_flag(
                    pm["company_number"],
                    "FT3-SC-008",
                    {
                        "unodc_grade": "B2",
                        "confidence": "moderate",
                        "person_name": pm["person_name"],
                        "party": pm.get("party"),
                        "legislature": pm.get("legislature"),
                        "country": pm.get("country"),
                        "summary": f"Controlled by Politically Exposed Person (PEP): {pm['person_name']} ({pm.get('legislature') or pm.get('pep_source') or 'PEP Register'})",
                    },
                )

            # ------------------------------------------------------------------ #
            # 8. FT3-SC-015: Phoenix Company Pattern (HIGH)                      #
            # ------------------------------------------------------------------ #
            phoenix_controllers = conn.execute(
                """
                SELECT po.person_id, p.name AS person_name,
                       SUM(CASE WHEN c.company_status LIKE '%Dissolved%' OR c.company_status LIKE '%Liquidation%' OR po.is_ceased = 1 THEN 1 ELSE 0 END) AS dissolved_count,
                       SUM(CASE WHEN c.company_status = 'Active' THEN 1 ELSE 0 END) AS active_count,
                       GROUP_CONCAT(c.company_number, ', ') AS company_list
                FROM psc_ownerships po
                JOIN companies c ON c.company_number = po.company_number
                JOIN persons p ON p.id = po.person_id
                GROUP BY po.person_id
                HAVING dissolved_count >= 2 AND active_count >= 1
                """
            ).fetchall()
            for ph in phoenix_controllers:
                c_rows = conn.execute(
                    "SELECT company_number FROM psc_ownerships WHERE person_id = ?",
                    (ph["person_id"],),
                ).fetchall()
                for cr in c_rows:
                    _upsert_flag(
                        cr["company_number"],
                        "FT3-SC-015",
                        {
                            "unodc_grade": "B2",
                            "confidence": "moderate",
                            "controller_name": ph["person_name"],
                            "dissolved_companies_count": ph["dissolved_count"],
                            "active_companies_count": ph["active_count"],
                            "related_companies": ph["company_list"],
                            "summary": (
                                f"Phoenix pattern: controller '{ph['person_name']}' linked to "
                                f"{ph['dissolved_count']} dissolved/liquidated entities and {ph['active_count']} active successor(s)"
                            ),
                        },
                    )

            # ------------------------------------------------------------------ #
            # 9. FT3-SC-009: Rapid Director / PSC Turnover or Rebranding (MEDIUM)#
            # ------------------------------------------------------------------ #
            rebrand_rows = conn.execute(
                """
                SELECT company_number, company_name, prev_name_1, prev_name_2, prev_name_3
                FROM companies
                WHERE prev_name_2 IS NOT NULL AND prev_name_2 != ''
                """
            ).fetchall()
            for rb in rebrand_rows:
                prevs = [rb["prev_name_1"], rb["prev_name_2"], rb["prev_name_3"]]
                prevs_clean = [p for p in prevs if p]
                _upsert_flag(
                    rb["company_number"],
                    "FT3-SC-009",
                    {
                        "unodc_grade": "A1",
                        "confidence": "high",
                        "previous_names": prevs_clean,
                        "summary": f"Multiple corporate identity changes ({len(prevs_clean)} prior names, e.g. '{prevs_clean[0]}')",
                    },
                )

            psc_churn_rows = conn.execute(
                """
                SELECT company_number,
                       COUNT(*) AS total_pscs,
                       SUM(CASE WHEN is_ceased = 1 THEN 1 ELSE 0 END) AS ceased_pscs
                FROM psc_ownerships
                GROUP BY company_number
                HAVING total_pscs >= 3 AND ceased_pscs >= 2
                """
            ).fetchall()
            for ch in psc_churn_rows:
                _upsert_flag(
                    ch["company_number"],
                    "FT3-SC-009",
                    {
                        "unodc_grade": "B2",
                        "confidence": "moderate",
                        "total_pscs": ch["total_pscs"],
                        "ceased_pscs": ch["ceased_pscs"],
                        "summary": f"High beneficial ownership churn: {ch['ceased_pscs']} ceased PSCs out of {ch['total_pscs']} notifications",
                    },
                )

            # ------------------------------------------------------------------ #
            # 10. FT3-SC-014: Dormant / Strike-Off Filing Anomaly (MEDIUM)       #
            # ------------------------------------------------------------------ #
            dormant_rows = conn.execute(
                """
                SELECT c.company_number, c.company_name, c.accounts_account_category, c.company_status
                FROM companies c
                WHERE (c.accounts_account_category LIKE '%DORMANT%' AND EXISTS (
                           SELECT 1 FROM psc_ownerships po WHERE po.company_number = c.company_number AND po.legal_entity_id IS NOT NULL
                       ))
                   OR c.company_status LIKE '%Proposal to Strike off%'
                   OR c.company_status LIKE '%Liquidation%'
                """
            ).fetchall()
            for dr in dormant_rows:
                _upsert_flag(
                    dr["company_number"],
                    "FT3-SC-014",
                    {
                        "unodc_grade": "A1",
                        "confidence": "high",
                        "accounts_category": dr["accounts_account_category"],
                        "company_status": dr["company_status"],
                        "summary": f"Filing/status anomaly: status='{dr['company_status']}', accounts='{dr['accounts_account_category'] or 'N/A'}'",
                    },
                )

            # ------------------------------------------------------------------ #
            # 11. FT3-SC-020: Opaque / Super-Secure Beneficial Control (MEDIUM)  #
            # ------------------------------------------------------------------ #
            opaque_rows = conn.execute(
                """
                SELECT DISTINCT po.company_number, po.is_super_secure, c.company_status
                FROM psc_ownerships po
                JOIN companies c ON c.company_number = po.company_number
                WHERE po.is_super_secure = 1
                   OR po.company_number LIKE 'OE%'
                """
            ).fetchall()
            for opq in opaque_rows:
                is_ss = bool(opq["is_super_secure"])
                _upsert_flag(
                    opq["company_number"],
                    "FT3-SC-020",
                    {
                        "unodc_grade": "A1",
                        "confidence": "high",
                        "is_super_secure": is_ss,
                        "summary": (
                            "Beneficial owner identity restricted under Companies Act s.790ZG (Super-Secure PSC)"
                            if is_ss
                            else "Overseas Entity registered on ROE with foreign beneficial ownership structure"
                        ),
                    },
                )

            # ------------------------------------------------------------------ #
            # AGGREGATE RISK SCORES ON `companies` & SYNC `ftm_entities.target`  #
            # ------------------------------------------------------------------ #
            conn.execute("UPDATE companies SET risk_score = 0.0, ft3_techniques = '[]', is_flagged = 0")

            agg_rows = conn.execute(
                """
                SELECT company_number,
                       MIN(100.0, ROUND(SUM(score_contribution), 1)) AS total_score,
                       GROUP_CONCAT(ft3_technique, ',') AS tech_csv
                FROM risk_flags
                WHERE is_active = 1
                GROUP BY company_number
                """
            ).fetchall()

            flagged_companies = 0
            for ar in agg_rows:
                techs = sorted(set((ar["tech_csv"] or "").split(",")))
                score = float(ar["total_score"] or 0.0)
                conn.execute(
                    """
                    UPDATE companies
                    SET risk_score = ?,
                        ft3_techniques = ?,
                        is_flagged = 1,
                        updated_at = ?
                    WHERE company_number = ?
                    """,
                    (score, json.dumps(techs), now, ar["company_number"]),
                )
                flagged_companies += 1

            # Mark flagged companies as target=1 in ftm_entities
            conn.execute(
                """
                UPDATE ftm_entities
                SET target = 1
                WHERE id IN (SELECT ftm_id FROM companies WHERE is_flagged = 1 AND ftm_id IS NOT NULL)
                """
            )

            conn.commit()
            log.info(
                "risk_scoring_complete",
                flagged_companies=flagged_companies,
                techniques=detected_counts,
            )
            return {
                "flagged_companies": flagged_companies,
                "techniques_detected": detected_counts,
                "resolution_summary": {
                    "sanction_matches": len(resolved["sanction_matches"]),
                    "icij_matches": len(resolved["icij_matches"]),
                    "pep_matches": len(resolved["pep_matches"]),
                },
            }
        finally:
            conn.close()
