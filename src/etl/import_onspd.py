"""ETL Importer for ONS Postcode Directory (ONSPD) centroids (`geo_postcode_centroids`).

Supports:
  - Importing an external ONSPD CSV file if provided (`pcds`, `lat`, `long`, `oslaua`, `cty`, `osward`, `rgn`, `ctry`)
  - Synchronizing built-in UK postcode centroids for all postcodes present in `companies`
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.core.logging import get_logger
from src.core.normalizer import normalize_postcode
from src.services.db_service import DatabaseService
from src.services.geo_service import GeoService, UK_POSTCODE_CENTROIDS

log = get_logger(__name__)


def import_onspd(
    csv_path: Path | str | None = None,
    db_service: DatabaseService | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Import ONSPD centroids or seed built-in UK postcode centroids."""
    db = db_service or DatabaseService()
    geo = GeoService(db.db_path)
    conn = db.connect()
    imported = 0

    try:
        source_id = db.register_data_source(
            source_name="ONS Postcode Directory (ONSPD)",
            source_type="onspd_centroids",
            source_version="2026-01",
            notes="UK WGS84 postcode centroids (Open Government Licence v3.0)",
            conn=conn,
        )

        if csv_path and Path(csv_path).exists():
            path = Path(csv_path)
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                batch = []
                for row in reader:
                    if limit and imported >= limit:
                        break
                    pc = normalize_postcode(row.get("pcds") or row.get("pcd") or row.get("postcode"))
                    lat_s = row.get("lat")
                    lon_s = row.get("long") or row.get("lon")
                    if not pc or not lat_s or not lon_s:
                        continue
                    try:
                        lat, lon = float(lat_s), float(lon_s)
                    except ValueError:
                        continue
                    if abs(lat) > 90 or abs(lon) > 180 or (lat == 0.0 and lon == 0.0):
                        continue
                    batch.append(
                        (
                            pc,
                            lat,
                            lon,
                            row.get("oslaua") or row.get("admin_district"),
                            row.get("cty") or row.get("admin_county"),
                            row.get("osward") or row.get("admin_ward"),
                            row.get("rgn") or row.get("nuts_level1"),
                            (row.get("ctry") or "E")[:1],
                            source_id,
                        )
                    )
                    imported += 1
                    if len(batch) >= 2000:
                        conn.executemany(
                            """
                            INSERT OR REPLACE INTO geo_postcode_centroids
                                (postcode, lat, lon, admin_district, admin_county, admin_ward, nuts_level1, country_code, source_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            batch,
                        )
                        batch.clear()
                if batch:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO geo_postcode_centroids
                            (postcode, lat, lon, admin_district, admin_county, admin_ward, nuts_level1, country_code, source_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )

        # Always seed outward/area centroids & resolve all company postcodes
        for outward, (lat, lon, district, ctry) in UK_POSTCODE_CENTROIDS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO geo_postcode_centroids
                    (postcode, lat, lon, admin_district, country_code, source_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (outward, lat, lon, district, ctry, source_id),
            )
            imported += 1

        synced = geo.sync_company_postcodes(conn=conn)
        conn.commit()
        return {"centroids": imported + synced}
    finally:
        conn.close()
