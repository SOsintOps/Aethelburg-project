"""Graph analysis service — Multi-hop network builder, centrality metrics & Link Analysis JSON.

Implements Link Analysis best practices from:
  - UNODC *Criminal Intelligence: Manual for Analysts* (2011, Chapters 4 & 6, pp. 25-48):
    - 4x4 Source/Information evaluation (`A1`, `A2`, `B2`, `C3`)
    - Confirmed links (`A1`/`A2`/`B1`/`B2` -> solid lines) vs Suspected/Inferred links (`C3` -> dashed lines)
    - Step 3-5 Association Matrix coding (`→` ownership, `+` officer/control, `●` confirmed, `○` suspected)
    - Step 5 Link counts (`degree`) and Company Tree tiers (`hierarchy_level`)
  - Malcolm Sparrow (1991) *The Application of Network Analysis to Criminal Intelligence*:
    - Degree, Betweenness (bridge/broker detection), and PageRank centrality
  - Peter Klerks (2001) *The Network Paradigm*:
    - Multi-view support (Organic Force, Hierarchical Levels, Concentric Ego-Rings, Circular, Matrix)
  - OCCRP FollowTheMoney (`FtM v3.x`) & IBM i2 / Anacapa visual conventions
"""
from __future__ import annotations

import re
from typing import Any

import networkx as nx

from src.core.ftm import make_ftm_id
from src.core.logging import get_logger
from src.services.db_service import DatabaseService, _parse_json_field

log = get_logger(__name__)

_JURISDICTION_ISO_MAP = {
    "united kingdom": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "british": "GB",
    "uk": "GB",
    "british virgin islands": "VG",
    "bvi": "VG",
    "cayman islands": "KY",
    "panama": "PA",
    "seychelles": "SC",
    "cyprus": "CY",
    "jersey": "JE",
    "guernsey": "GG",
    "isle of man": "IM",
    "bahamas": "BS",
    "belize": "BZ",
    "malta": "MT",
    "luxembourg": "LU",
    "switzerland": "CH",
    "russia": "RU",
    "russian": "RU",
    "united arab emirates": "AE",
    "hong kong": "HK",
    "singapore": "SG",
    "delaware": "US",
    "usa": "US",
}


def _infer_iso2(text: str | None, default: str = "GB") -> str:
    if not text:
        return default
    t = str(text).strip().lower()
    if len(t) == 2 and t.isalpha():
        return t.upper()
    for k, v in _JURISDICTION_ISO_MAP.items():
        if k in t:
            return v
    return default


def _extract_share_pct(role_text: str) -> int:
    """Extract numeric ownership percentage weight from CH nature-of-control string."""
    if "75-to-100" in role_text or "75 to 100" in role_text:
        return 88
    if "50-to-75" in role_text or "50 to 75" in role_text:
        return 62
    if "25-to-50" in role_text or "25 to 50" in role_text:
        return 38
    m = re.search(r"(\d{2,3})\s*%", role_text)
    if m:
        return min(100, int(m.group(1)))
    return 50


class GraphService:
    """Multi-hop corporate intelligence graph builder and UNODC link-analysis engine."""

    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self.db = db_service or DatabaseService()

    def build_ego_graph(
        self,
        company_number: str,
        hops: int = 2,
        max_colocated: int = 8,
    ) -> dict[str, Any]:
        """Build a multi-hop NetworkX + Link Analysis graph centered on `company_number`."""
        conn = self.db.connect()
        g = nx.DiGraph()
        visited_companies: set[str] = set()
        root_cnum = company_number.strip().upper()
        frontier_companies: set[str] = {root_cnum}

        try:
            fp_to_cnum = {
                r["name_fingerprint"]: r["company_number"]
                for r in conn.execute(
                    "SELECT company_number, name_fingerprint FROM companies WHERE name_fingerprint IS NOT NULL"
                ).fetchall()
            }

            for hop in range(max(1, min(hops, 3))):
                next_frontier: set[str] = set()
                for cnum in list(frontier_companies):
                    if cnum in visited_companies:
                        continue
                    visited_companies.add(cnum)

                    comp = conn.execute(
                        "SELECT * FROM companies WHERE company_number = ?",
                        (cnum,),
                    ).fetchone()
                    if not comp:
                        continue

                    comp_node_id = f"company:{cnum}"
                    ft3_list = _parse_json_field(comp["ft3_techniques"], [])
                    is_root = cnum == root_cnum
                    g.add_node(
                        comp_node_id,
                        id=comp_node_id,
                        label=f"{comp['company_name']}\n({cnum})",
                        short_label=comp["company_name"][:30],
                        node_type="Company",
                        pole_category="Organization",
                        unodc_shape="rectangle",
                        ftm_schema="Company",
                        ftm_id=comp["ftm_id"] or make_ftm_id("Company", "gb", cnum),
                        company_number=cnum,
                        status=comp["company_status"] or "Active",
                        risk_score=float(comp["risk_score"] or 0.0),
                        is_flagged=bool(comp["is_flagged"]),
                        is_root=is_root,
                        hop_distance=0 if is_root else hop + 1,
                        hierarchy_level=2,
                        unodc_grade="A1",
                        country_code="GB",
                        ft3_techniques=ft3_list,
                        postcode=comp["reg_address_postcode"] or "",
                    )

                    # 1. Address node + co-located companies
                    if comp["address_fingerprint"]:
                        afp = comp["address_fingerprint"]
                        addr_node_id = f"address:{afp}"
                        coloc_cnt = conn.execute(
                            "SELECT COUNT(*) AS c FROM companies WHERE address_fingerprint = ?",
                            (afp,),
                        ).fetchone()["c"]
                        addr_label = f"{comp['reg_address_line1'] or ''}, {comp['reg_address_postcode'] or ''}".strip(", ")
                        g.add_node(
                            addr_node_id,
                            id=addr_node_id,
                            label=f"{addr_label}\n[{coloc_cnt} cos]",
                            short_label=comp["reg_address_postcode"] or addr_label[:24],
                            node_type="Address",
                            pole_category="Location",
                            unodc_shape="diamond",
                            ftm_schema="Address",
                            ftm_id=make_ftm_id("Address", afp),
                            colocated_count=int(coloc_cnt),
                            hop_distance=hop + 1,
                            hierarchy_level=4,
                            unodc_grade="A2",
                            country_code="GB",
                            risk_score=min(100.0, float(coloc_cnt * 4)),
                        )
                        g.add_edge(
                            comp_node_id,
                            addr_node_id,
                            id=f"edge:reg:{cnum}:{afp}",
                            label="registered at [A1]",
                            ftm_verb="registered at",
                            edge_type="REGISTERED_AT",
                            ftm_schema="Address",
                            unodc_grade="A1",
                            confirmed=True,
                            matrix_code="●",
                            weight=1.6,
                        )

                        if hop == 0:
                            coloc_rows = conn.execute(
                                """
                                SELECT company_number, company_name, company_status, risk_score, is_flagged, ftm_id, ft3_techniques
                                FROM companies
                                WHERE address_fingerprint = ? AND company_number != ?
                                ORDER BY risk_score DESC
                                LIMIT ?
                                """,
                                (afp, cnum, int(max_colocated)),
                            ).fetchall()
                            for cr in coloc_rows:
                                cc_id = f"company:{cr['company_number']}"
                                if cc_id not in g:
                                    g.add_node(
                                        cc_id,
                                        id=cc_id,
                                        label=f"{cr['company_name']}\n({cr['company_number']})",
                                        short_label=cr["company_name"][:26],
                                        node_type="Company",
                                        pole_category="Organization",
                                        unodc_shape="rectangle",
                                        ftm_schema="Company",
                                        ftm_id=cr["ftm_id"] or make_ftm_id("Company", "gb", cr["company_number"]),
                                        company_number=cr["company_number"],
                                        status=cr["company_status"] or "Active",
                                        risk_score=float(cr["risk_score"] or 0.0),
                                        is_flagged=bool(cr["is_flagged"]),
                                        is_root=False,
                                        hop_distance=2,
                                        hierarchy_level=3,
                                        unodc_grade="A2",
                                        country_code="GB",
                                        ft3_techniques=_parse_json_field(cr["ft3_techniques"], []),
                                    )
                                g.add_edge(
                                    cc_id,
                                    addr_node_id,
                                    id=f"edge:reg:{cr['company_number']}:{afp}",
                                    label="co-located [C3]",
                                    ftm_verb="co-located at",
                                    edge_type="CO_LOCATED",
                                    ftm_schema="Address",
                                    unodc_grade="C3",
                                    confirmed=False,
                                    matrix_code="○",
                                    weight=1.4,
                                )

                    # 2. PSC Ownerships (Persons, Corporate PSCs, Super-Secure)
                    psc_rows = conn.execute(
                        """
                        SELECT po.*,
                               p.name AS person_name, p.nationality AS person_nat, p.is_pep, p.ftm_id AS p_ftm_id, p.name_fingerprint AS p_fp,
                               le.name AS le_name, le.jurisdiction AS le_jur, le.is_offshore, le.company_number_foreign,
                               le.ftm_id AS le_ftm_id, le.name_fingerprint AS le_fp
                        FROM psc_ownerships po
                        LEFT JOIN persons p ON p.id = po.person_id
                        LEFT JOIN legal_entities le ON le.id = po.legal_entity_id
                        WHERE po.company_number = ?
                        """,
                        (cnum,),
                    ).fetchall()

                    for po in psc_rows:
                        natures = _parse_json_field(po["nature_of_control"], [])
                        raw_nat = natures[0] if natures else "significant-control"
                        share_pct = _extract_share_pct(raw_nat)
                        role_short = (
                            raw_nat.replace("ownership-of-shares-", "owns ")
                            .replace("voting-rights-", "votes ")
                            .replace("-percent", "%")
                            .replace("-to-", "–")
                            .replace("right-to-appoint-and-remove-directors", "appoints directors")
                        )
                        is_ceased = bool(po["is_ceased"])

                        if po["is_super_secure"]:
                            ss_id = f"super_secure:{cnum}"
                            g.add_node(
                                ss_id,
                                id=ss_id,
                                label="Unknown / Restricted UBO\n(s.790ZG Super-Secure)",
                                short_label="Unknown UBO (s.790ZG)",
                                node_type="SuperSecurePSC",
                                pole_category="Person",
                                unodc_shape="circle_unknown",
                                ftm_schema="LegalEntity",
                                ftm_id=po["ftm_id"],
                                hop_distance=hop + 1,
                                hierarchy_level=0,
                                unodc_grade="B2",
                                country_code="GB",
                                risk_score=65.0,
                            )
                            g.add_edge(
                                ss_id,
                                comp_node_id,
                                id=f"edge:psc:{po['id']}",
                                label="restricted UBO [B2]",
                                ftm_verb="controls (s.790ZG)",
                                edge_type="CONTROLS",
                                ftm_schema="Ownership",
                                ftm_id=po["ftm_id"],
                                unodc_grade="B2",
                                confirmed=False,
                                matrix_code="-",
                                share_pct=75,
                                weight=2.2,
                            )
                        elif po["person_id"]:
                            pid = po["person_id"]
                            p_node_id = f"person:{pid}"
                            iso_nat = _infer_iso2(po["person_nat"], "GB")
                            g.add_node(
                                p_node_id,
                                id=p_node_id,
                                label=f"{po['person_name']}" + ("\n[PEP]" if po["is_pep"] else ""),
                                short_label=po["person_name"][:26],
                                node_type="Person",
                                pole_category="Person",
                                unodc_shape="circle",
                                ftm_schema="Person",
                                ftm_id=po["p_ftm_id"],
                                is_pep=bool(po["is_pep"]),
                                nationality=po["person_nat"] or "Unknown",
                                country_code=iso_nat,
                                hop_distance=hop + 1,
                                hierarchy_level=0,
                                unodc_grade="A2",
                                risk_score=80.0 if po["is_pep"] else 35.0,
                            )
                            edge_grade = "B3" if is_ceased else "A2"
                            g.add_edge(
                                p_node_id,
                                comp_node_id,
                                id=f"edge:psc:{po['id']}",
                                label=f"{role_short[:24]} [{edge_grade}]",
                                ftm_verb="owns" if "owns" in role_short else "directs",
                                edge_type="CONTROLS",
                                ftm_schema="Ownership",
                                ftm_id=po["ftm_id"],
                                is_ceased=is_ceased,
                                unodc_grade=edge_grade,
                                confirmed=not is_ceased,
                                matrix_code="→" if "owns" in role_short else "+",
                                share_pct=share_pct,
                                weight=2.6 if share_pct >= 75 else 2.0,
                            )

                            # Find other companies controlled by this person
                            other_c = conn.execute(
                                "SELECT DISTINCT company_number FROM psc_ownerships WHERE person_id = ? AND company_number != ? LIMIT 10",
                                (pid, cnum),
                            ).fetchall()
                            for oc in other_c:
                                next_frontier.add(oc["company_number"])

                        elif po["legal_entity_id"]:
                            leid = po["legal_entity_id"]
                            linked_uk_cnum = None
                            if po["company_number_foreign"] and po["company_number_foreign"].strip().upper() in fp_to_cnum.values():
                                linked_uk_cnum = po["company_number_foreign"].strip().upper()
                            elif po["le_fp"] and po["le_fp"] in fp_to_cnum:
                                linked_uk_cnum = fp_to_cnum[po["le_fp"]]

                            if linked_uk_cnum:
                                owner_node_id = f"company:{linked_uk_cnum}"
                                next_frontier.add(linked_uk_cnum)
                                if owner_node_id not in g:
                                    g.add_node(
                                        owner_node_id,
                                        id=owner_node_id,
                                        label=f"{po['le_name']}\n({linked_uk_cnum})",
                                        short_label=po["le_name"][:26],
                                        node_type="Company",
                                        pole_category="Organization",
                                        unodc_shape="rectangle",
                                        ftm_schema="Company",
                                        ftm_id=make_ftm_id("Company", "gb", linked_uk_cnum),
                                        company_number=linked_uk_cnum,
                                        hop_distance=hop + 1,
                                        hierarchy_level=1,
                                        unodc_grade="A1",
                                        country_code="GB",
                                        risk_score=60.0,
                                        is_flagged=True,
                                    )
                            else:
                                owner_node_id = f"legal_entity:{leid}"
                                iso_jur = _infer_iso2(po["le_jur"], "VG" if po["is_offshore"] else "GB")
                                g.add_node(
                                    owner_node_id,
                                    id=owner_node_id,
                                    label=f"{po['le_name']}\n[{po['le_jur'] or 'Corporate PSC'}]",
                                    short_label=po["le_name"][:26],
                                    node_type="OffshoreEntity" if po["is_offshore"] else "LegalEntity",
                                    pole_category="Organization",
                                    unodc_shape="rectangle",
                                    ftm_schema="Company" if po["is_offshore"] else "LegalEntity",
                                    ftm_id=po["le_ftm_id"],
                                    jurisdiction=po["le_jur"] or "",
                                    country_code=iso_jur,
                                    is_offshore=bool(po["is_offshore"]),
                                    hop_distance=hop + 1,
                                    hierarchy_level=1,
                                    unodc_grade="B2" if po["is_offshore"] else "A2",
                                    risk_score=75.0 if po["is_offshore"] else 40.0,
                                )

                            g.add_edge(
                                owner_node_id,
                                comp_node_id,
                                id=f"edge:psc:{po['id']}",
                                label=f"{role_short[:24]} [A2]",
                                ftm_verb="owns",
                                edge_type="CONTROLS",
                                ftm_schema="Ownership",
                                ftm_id=po["ftm_id"],
                                is_ceased=is_ceased,
                                unodc_grade="A2",
                                confirmed=not is_ceased,
                                matrix_code="→",
                                share_pct=share_pct,
                                weight=2.5,
                            )

                            # Check if this corporate PSC matches ICIJ Offshore Leaks
                            if po["le_fp"]:
                                icij_rows = conn.execute(
                                    "SELECT node_id, name, jurisdiction_description, source_id_list, ftm_id FROM icij_entities WHERE name_fingerprint = ? LIMIT 3",
                                    (po["le_fp"],),
                                ).fetchall()
                                for ir in icij_rows:
                                    icij_nid = f"icij:{ir['node_id']}"
                                    iso_icij = _infer_iso2(ir["jurisdiction_description"], "VG")
                                    g.add_node(
                                        icij_nid,
                                        id=icij_nid,
                                        label=f"{ir['name']}\n({ir['source_id_list']} — {ir['jurisdiction_description'] or 'Offshore'})",
                                        short_label=f"ICIJ: {ir['name'][:22]}",
                                        node_type="OffshoreEntity",
                                        pole_category="Organization",
                                        unodc_shape="rectangle",
                                        ftm_schema="Company",
                                        ftm_id=ir["ftm_id"],
                                        country_code=iso_icij,
                                        is_offshore=True,
                                        hop_distance=hop + 2,
                                        hierarchy_level=0,
                                        unodc_grade="B2",
                                        risk_score=90.0,
                                    )
                                    g.add_edge(
                                        icij_nid,
                                        owner_node_id,
                                        id=f"edge:icij:{leid}:{ir['node_id']}",
                                        label=f"leak match ({ir['source_id_list'] or 'ICIJ'}) [C3]",
                                        ftm_verb="offshore match",
                                        edge_type="OFFSHORE_MATCH",
                                        ftm_schema="UnknownLink",
                                        unodc_grade="C3",
                                        confirmed=False,
                                        matrix_code="○",
                                        weight=2.0,
                                    )

                    # 3. Direct Sanctions Matches
                    sanc_rows = conn.execute(
                        """
                        SELECT id, ftm_id, name, list_name, opensanctions_id
                        FROM sanctions
                        WHERE registration_numbers LIKE ?
                           OR (name_fingerprint IS NOT NULL AND name_fingerprint != '' AND name_fingerprint = ?)
                        LIMIT 5
                        """,
                        (f'%"{cnum}"%', comp["name_fingerprint"] or "__none__"),
                    ).fetchall()
                    for sr in sanc_rows:
                        s_nid = f"sanction:{sr['id']}"
                        g.add_node(
                            s_nid,
                            id=s_nid,
                            label=f"SANCTION: {sr['name']}\n({sr['opensanctions_id']} — {sr['list_name']})",
                            short_label=f"OFSI: {sr['opensanctions_id']}",
                            node_type="Sanction",
                            pole_category="Event",
                            unodc_shape="octagon",
                            ftm_schema="Sanction",
                            ftm_id=sr["ftm_id"],
                            country_code="GB",
                            is_sanctioned=True,
                            hop_distance=hop + 1,
                            hierarchy_level=0,
                            unodc_grade="A1",
                            risk_score=100.0,
                        )
                        g.add_edge(
                            s_nid,
                            comp_node_id,
                            id=f"edge:sanc:{cnum}:{sr['id']}",
                            label="designated on [A1]",
                            ftm_verb="designated on",
                            edge_type="SANCTIONED_AS",
                            ftm_schema="Sanction",
                            unodc_grade="A1",
                            confirmed=True,
                            matrix_code="●",
                            weight=3.0,
                        )

                frontier_companies = next_frontier - visited_companies

            return self._graph_to_payload(g, root_id=f"company:{root_cnum}")
        finally:
            conn.close()

    def build_overview_graph(self, limit_companies: int = 35) -> dict[str, Any]:
        """Build a global overview network of top flagged companies and their shared controllers/hubs."""
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT company_number
                FROM companies
                WHERE is_flagged = 1
                ORDER BY risk_score DESC
                LIMIT ?
                """,
                (int(limit_companies),),
            ).fetchall()
        finally:
            conn.close()

        merged = nx.DiGraph()
        for r in rows[:12]:
            sub = self.build_ego_graph(r["company_number"], hops=1, max_colocated=3)
            for n in sub["elements"]["nodes"]:
                nid = n["data"]["id"]
                if nid not in merged:
                    merged.add_node(nid, **n["data"])
                else:
                    # Preserve root flag only if explicitly root in overview
                    merged.nodes[nid]["is_root"] = False
            for e in sub["elements"]["edges"]:
                merged.add_edge(e["data"]["source"], e["data"]["target"], **e["data"])

        return self._graph_to_payload(merged, root_id=None)

    def _graph_to_payload(self, g: nx.DiGraph, root_id: str | None = None) -> dict[str, Any]:
        """Compute NetworkX SNA centrality metrics (Sparrow 1991) and UNODC link counts."""
        deg_centrality = nx.degree_centrality(g) if len(g) > 1 else {n: 1.0 for n in g.nodes}
        undirected = g.to_undirected()
        try:
            betweenness = nx.betweenness_centrality(undirected) if len(g) > 2 else {n: 0.0 for n in g.nodes}
        except Exception:
            betweenness = {n: 0.0 for n in g.nodes}
        try:
            pagerank = nx.pagerank(g) if len(g) > 1 else {n: 1.0 for n in g.nodes}
        except Exception:
            pagerank = deg_centrality

        nodes_out = []
        for nid, attrs in g.nodes(data=True):
            data = dict(attrs)
            data["id"] = nid
            data["degree"] = int(g.degree(nid))
            data["in_degree"] = int(g.in_degree(nid))
            data["out_degree"] = int(g.out_degree(nid))
            data["degree_centrality"] = round(float(deg_centrality.get(nid, 0.0)), 4)
            data["betweenness_centrality"] = round(float(betweenness.get(nid, 0.0)), 4)
            data["pagerank"] = round(float(pagerank.get(nid, 0.0)), 4)
            data["is_bridge"] = bool(betweenness.get(nid, 0.0) >= 0.12 and g.degree(nid) >= 2)
            nodes_out.append({"data": data})

        edges_out = []
        for u, v, attrs in g.edges(data=True):
            data = dict(attrs)
            data["source"] = u
            data["target"] = v
            if "id" not in data:
                data["id"] = f"edge:{u}->{v}"
            edges_out.append({"data": data})

        cycles = list(nx.simple_cycles(g))
        return {
            "root_id": root_id,
            "stats": {
                "node_count": g.number_of_nodes(),
                "edge_count": g.number_of_edges(),
                "cycle_count": len(cycles),
                "cycles": cycles[:10],
                "density": round(nx.density(g), 4) if g.number_of_nodes() > 1 else 0.0,
            },
            "elements": {
                "nodes": nodes_out,
                "edges": edges_out,
            },
        }
