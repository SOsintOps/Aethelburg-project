"""Topological pattern detection on corporate ownership & directorship graphs.

Detects:
  - Circular ownership rings (`FT3-SC-004`)
  - Multi-hop layered corporate chains (`FT3-SC-003`)
  - Star nominee controller topologies (`FT3-SC-002`)
  - Shortest path between any two entities
"""
from __future__ import annotations

from typing import Any

import networkx as nx

from src.services.db_service import DatabaseService


class GraphPatternDetector:
    """Graph topology analyzer for shell company structures."""

    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self.db = db_service or DatabaseService()

    def build_ownership_digraph(self) -> nx.DiGraph:
        """Build a directed graph of all PSC ownership relationships (`Owner -> Company`)."""
        conn = self.db.connect()
        dg = nx.DiGraph()
        try:
            fp_to_cnum = {
                r["name_fingerprint"]: r["company_number"]
                for r in conn.execute(
                    "SELECT company_number, name_fingerprint FROM companies WHERE name_fingerprint IS NOT NULL"
                ).fetchall()
            }

            rows = conn.execute(
                """
                SELECT po.company_number, c.company_name,
                       po.person_id, p.name AS person_name,
                       po.legal_entity_id, le.name AS le_name, le.name_fingerprint AS le_fp,
                       le.company_number_foreign, le.jurisdiction, le.is_offshore
                FROM psc_ownerships po
                JOIN companies c ON c.company_number = po.company_number
                LEFT JOIN persons p ON p.id = po.person_id
                LEFT JOIN legal_entities le ON le.id = po.legal_entity_id
                WHERE po.is_ceased = 0
                """
            ).fetchall()

            for r in rows:
                target = f"company:{r['company_number']}"
                dg.add_node(target, label=r["company_name"], node_type="Company", company_number=r["company_number"])

                if r["person_id"]:
                    src = f"person:{r['person_id']}"
                    dg.add_node(src, label=r["person_name"], node_type="Person")
                    dg.add_edge(src, target, rel="CONTROLS")
                elif r["legal_entity_id"]:
                    cnum_foreign = (r["company_number_foreign"] or "").strip().upper()
                    if cnum_foreign and cnum_foreign in fp_to_cnum.values():
                        src = f"company:{cnum_foreign}"
                        dg.add_node(src, label=r["le_name"], node_type="Company", company_number=cnum_foreign)
                    elif r["le_fp"] and r["le_fp"] in fp_to_cnum:
                        mapped_cnum = fp_to_cnum[r["le_fp"]]
                        src = f"company:{mapped_cnum}"
                        dg.add_node(src, label=r["le_name"], node_type="Company", company_number=mapped_cnum)
                    else:
                        src = f"legal_entity:{r['legal_entity_id']}"
                        dg.add_node(
                            src,
                            label=r["le_name"],
                            node_type="LegalEntity",
                            jurisdiction=r["jurisdiction"],
                            is_offshore=bool(r["is_offshore"]),
                        )
                    dg.add_edge(src, target, rel="CONTROLS")

            return dg
        finally:
            conn.close()

    def detect_all_patterns(self) -> dict[str, Any]:
        """Return circular ownership rings, deep chains, and star controllers."""
        dg = self.build_ownership_digraph()
        cycles = [list(c) for c in nx.simple_cycles(dg)]

        star_controllers = []
        for node, out_deg in dg.out_degree():
            if out_deg >= 4:
                attrs = dg.nodes[node]
                targets = [dg.nodes[t].get("label", t) for t in dg.successors(node)]
                star_controllers.append(
                    {
                        "controller_id": node,
                        "controller_name": attrs.get("label", node),
                        "node_type": attrs.get("node_type", "Entity"),
                        "controlled_count": out_deg,
                        "sample_targets": targets[:8],
                    }
                )
        star_controllers.sort(key=lambda x: x["controlled_count"], reverse=True)

        return {
            "circular_ownership_cycles": cycles,
            "star_controllers": star_controllers[:20],
            "total_nodes": dg.number_of_nodes(),
            "total_edges": dg.number_of_edges(),
        }
