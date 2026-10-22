"""Graph exporter — GEXF (Gephi), GraphML (yEd/Maltego/i2), Cytoscape JSON, DOT, and FtM JSONL."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import networkx as nx


def cytoscape_to_networkx(cyto_payload: dict[str, Any]) -> nx.DiGraph:
    """Convert a Cytoscape.js graph payload (`elements.nodes`, `elements.edges`) into a clean NetworkX DiGraph."""
    g = nx.DiGraph()
    elements = cyto_payload.get("elements") or {}
    for n in elements.get("nodes", []):
        data = dict(n.get("data") or {})
        nid = str(data.pop("id"))
        clean_attrs = {
            k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
            for k, v in data.items()
            if v is not None
        }
        g.add_node(nid, **clean_attrs)
    for e in elements.get("edges", []):
        data = dict(e.get("data") or {})
        u = str(data.pop("source"))
        v = str(data.pop("target"))
        clean_attrs = {
            k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
            for k, v in data.items()
            if v is not None
        }
        g.add_edge(u, v, **clean_attrs)
    return g


def export_graph_gexf(cyto_payload: dict[str, Any], output_path: Path | str | None = None) -> str:
    """Export graph to GEXF 1.2 XML string (compatible with Gephi)."""
    g = cytoscape_to_networkx(cyto_payload)
    buf = io.BytesIO()
    nx.write_gexf(g, buf, encoding="utf-8")
    xml_text = buf.getvalue().decode("utf-8")
    if output_path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(xml_text, encoding="utf-8")
    return xml_text


def export_graph_graphml(cyto_payload: dict[str, Any], output_path: Path | str | None = None) -> str:
    """Export graph to GraphML XML string (compatible with yEd, Maltego, i2 Analyst's Notebook)."""
    g = cytoscape_to_networkx(cyto_payload)
    buf = io.BytesIO()
    nx.write_graphml(g, buf, encoding="utf-8")
    xml_text = buf.getvalue().decode("utf-8")
    if output_path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(xml_text, encoding="utf-8")
    return xml_text


def export_graph_dot(cyto_payload: dict[str, Any]) -> str:
    """Export graph to Graphviz DOT format."""
    g = cytoscape_to_networkx(cyto_payload)
    lines = ["digraph Aethelburg {"]
    lines.append('  rankdir=LR; node [shape=box, style="rounded,filled", fontname="Inter"];')
    for nid, attrs in g.nodes(data=True):
        label = str(attrs.get("short_label") or attrs.get("label") or nid).replace('"', '\\"')
        ntype = attrs.get("node_type", "Company")
        fill = "#fee2e2" if attrs.get("is_flagged") else "#e0f2fe"
        if ntype == "Sanction":
            fill = "#fecaca"
        elif ntype == "OffshoreEntity":
            fill = "#fef3c7"
        lines.append(f'  "{nid}" [label="{label}\\n({ntype})", fillcolor="{fill}"];')
    for u, v, attrs in g.edges(data=True):
        elabel = str(attrs.get("label") or attrs.get("edge_type") or "").replace('"', '\\"')
        lines.append(f'  "{u}" -> "{v}" [label="{elabel}"];')
    lines.append("}")
    return "\n".join(lines)
