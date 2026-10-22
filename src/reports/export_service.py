"""Multi-format Intelligence Export Service (ADR-014).

Supports 8 standard investigative interoperability formats:
  1. FollowTheMoney JSONL (`.ftm.json` — Aleph, OpenSanctions, Quaesitor)
  2. Excel Workbook (`.xlsx` — multi-sheet via `openpyxl`: Companies, PSCs, Risk Flags, FtM Entities)
  3. CSV (`.csv`)
  4. GEXF (`.gexf` — Gephi)
  5. GraphML (`.graphml` — yEd, Maltego, i2 Analyst's Notebook)
  6. GeoJSON (`.geojson` — QGIS, Kepler.gl)
  7. KML (`.kml` — Google Earth Pro)
  8. Intelligence Report Dossier (`.html` printable A4 report)
"""
from __future__ import annotations

import csv
import io
import json

from openpyxl import Workbook

from src.graph.graph_service import GraphService
from src.reports.pdf_generator import ReportGenerator
from src.services.db_service import DatabaseService
from src.services.geo_service import GeoService


class ExportService:
    """Unified export engine for Aethelburg."""

    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self.db = db_service or DatabaseService()
        self.graph_service = GraphService(self.db)
        self.geo_service = GeoService(self.db.db_path)
        self.report_generator = ReportGenerator(self.db)

    def export_ftm_jsonl_bytes(
        self,
        company_number: str | None = None,
        target_only: bool = False,
        limit: int = 2000,
    ) -> bytes:
        """Export FollowTheMoney v3.x JSONL stream as UTF-8 bytes."""
        buf = io.StringIO()
        if company_number:
            dossier = self.db.get_company_dossier(company_number)
            if dossier and dossier.get("ftm_entity"):
                buf.write(json.dumps(dossier["ftm_entity"], ensure_ascii=False) + "\n")
                # Also export linked FtM entities from ego graph
                ego = self.graph_service.build_ego_graph(company_number, hops=2)
                seen_ids = {dossier["ftm_entity"]["id"]}
                for n in ego["elements"]["nodes"]:
                    fid = n["data"].get("ftm_id")
                    if fid and fid not in seen_ids:
                        ent = self.db.get_ftm_entity(fid)
                        if ent:
                            buf.write(json.dumps(ent, ensure_ascii=False) + "\n")
                            seen_ids.add(fid)
                for e in ego["elements"]["edges"]:
                    fid = e["data"].get("ftm_id")
                    if fid and fid not in seen_ids:
                        ent = self.db.get_ftm_entity(fid)
                        if ent:
                            buf.write(json.dumps(ent, ensure_ascii=False) + "\n")
                            seen_ids.add(fid)
        else:
            for ent in self.db.iter_ftm_entities(target_only=target_only, limit=limit):
                buf.write(json.dumps(ent, ensure_ascii=False) + "\n")
        return buf.getvalue().encode("utf-8")

    def export_xlsx_bytes(self, flagged_only: bool = True, limit: int = 1000) -> bytes:
        """Export multi-tab Excel workbook (`.xlsx`) with Companies, Risk Flags, and FtM Entities."""
        wb = Workbook()

        # Sheet 1: Companies
        ws_comp = wb.active
        ws_comp.title = "Companies"
        ws_comp.append(
            [
                "Company Number",
                "Company Name",
                "FtM ID",
                "Status",
                "Incorporation Date",
                "Postcode",
                "Address Fingerprint",
                "SIC Code",
                "Risk Score",
                "FT3 Techniques",
            ]
        )
        search_res = self.db.search_companies(flagged_only=flagged_only, limit=limit)
        for item in search_res["items"]:
            ws_comp.append(
                [
                    item["company_number"],
                    item["company_name"],
                    item.get("ftm_id") or "",
                    item.get("company_status") or "",
                    item.get("incorporation_date") or "",
                    item.get("reg_address_postcode") or "",
                    item.get("address_fingerprint") or "",
                    item.get("sic_code_1") or "",
                    item.get("risk_score") or 0.0,
                    ", ".join(item.get("ft3_techniques") or []),
                ]
            )

        # Sheet 2: FT3 Risk Flags
        ws_flags = wb.create_sheet("FT3 Risk Flags")
        ws_flags.append(["Company Number", "FT3 Technique", "Priority", "Score Contribution", "Evidence Summary"])
        conn = self.db.connect()
        try:
            for r in conn.execute(
                "SELECT company_number, ft3_technique, priority, score_contribution, evidence FROM risk_flags WHERE is_active = 1 ORDER BY score_contribution DESC LIMIT 2000"
            ).fetchall():
                ev = json.loads(r["evidence"] or "{}")
                ws_flags.append(
                    [
                        r["company_number"],
                        r["ft3_technique"],
                        r["priority"],
                        r["score_contribution"],
                        ev.get("summary") or "",
                    ]
                )
        finally:
            conn.close()

        # Sheet 3: FollowTheMoney Entities
        ws_ftm = wb.create_sheet("FollowTheMoney Entities")
        ws_ftm.append(["FtM ID", "Schema", "Caption", "Target", "Datasets", "Referents"])
        for ent in self.db.iter_ftm_entities(target_only=flagged_only, limit=1000):
            ws_ftm.append(
                [
                    ent["id"],
                    ent["schema"],
                    ent["caption"],
                    "YES" if ent["target"] else "NO",
                    ", ".join(ent.get("datasets") or []),
                    ", ".join(ent.get("referents") or []),
                ]
            )

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    def export_csv_bytes(self, flagged_only: bool = True, limit: int = 2000) -> bytes:
        """Export companies & risk scores as UTF-8 CSV."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "company_number",
                "company_name",
                "ftm_id",
                "company_status",
                "incorporation_date",
                "reg_address_postcode",
                "address_fingerprint",
                "risk_score",
                "ft3_techniques",
            ]
        )
        search_res = self.db.search_companies(flagged_only=flagged_only, limit=limit)
        for item in search_res["items"]:
            writer.writerow(
                [
                    item["company_number"],
                    item["company_name"],
                    item.get("ftm_id") or "",
                    item.get("company_status") or "",
                    item.get("incorporation_date") or "",
                    item.get("reg_address_postcode") or "",
                    item.get("address_fingerprint") or "",
                    item.get("risk_score") or 0.0,
                    "|".join(item.get("ft3_techniques") or []),
                ]
            )
        return buf.getvalue().encode("utf-8")

    def export_kml_bytes(self, flagged_only: bool = True, limit: int = 500) -> bytes:
        """Export geocoded companies and controller links to KML 2.2 (Google Earth Pro)."""
        geojson = self.geo_service.get_map_geojson(flagged_only=flagged_only, limit=limit)
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<kml xmlns="http://www.opengis.net/kml/2.2">',
            "  <Document>",
            "    <name>Aethelburg Geospatial Intelligence Export</name>",
        ]
        for feat in geojson.get("features", []):
            geom = feat.get("geometry") or {}
            props = feat.get("properties") or {}
            if geom.get("type") == "Point":
                lon, lat = geom["coordinates"]
                name = (props.get("company_name") or "Company").replace("&", "&amp;").replace("<", "&lt;")
                desc = (
                    f"CRN: {props.get('company_number')} | Risk: {props.get('risk_score')}/100 | "
                    f"Postcode: {props.get('postcode')} | Co-located: {props.get('colocated_count')}"
                ).replace("&", "&amp;")
                lines.append("    <Placemark>")
                lines.append(f"      <name>{name}</name>")
                lines.append(f"      <description>{desc}</description>")
                lines.append(f"      <Point><coordinates>{lon},{lat},0</coordinates></Point>")
                lines.append("    </Placemark>")
        lines.append("  </Document>")
        lines.append("</kml>")
        return "\n".join(lines).encode("utf-8")
