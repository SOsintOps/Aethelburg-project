"""ETL Importer for ONS Postcode Directory (ONSPD) centroids (`geo_postcode_centroids`).

Supports:
  - Importing an external ONSPD CSV file if provided (`pcds`, `lat`, `long`, `oslaua`, `cty`, `osward`, `rgn`, `ctry`)
  - Approximate built-in centroids (with `precision`) for company postcodes ONSPD does not cover
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from src.core.logging import get_logger
from src.core.normalizer import normalize_postcode
from src.services.db_service import DatabaseService
from src.services.geo_service import PRECISION_POSTCODE, GeoService

log = get_logger(__name__)

_INSERT_ONSPD_SQL = f"""
    INSERT OR REPLACE INTO geo_postcode_centroids
        (postcode, lat, lon, admin_district, admin_county, admin_ward, nuts_level1, country_code, source_id, precision)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{PRECISION_POSTCODE}')
"""


_GEOGRAPHY_COLUMNS = {
    # ONSPD renames these every release with the boundary year (lad26cd, cty26cd, ...);
    # older releases used oslaua/cty/osward/rgn/ctry
    "district": ("lad", "oslaua"),
    "county": ("cty",),
    "ward": ("wd", "osward"),
    "region": ("rgn",),
    "country": ("ctry",),
}


def _geography_columns(fieldnames: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, prefixes in _GEOGRAPHY_COLUMNS.items():
        candidates = [
            f for f in fieldnames
            if any(re.fullmatch(rf"{p}(\d{{2}}cd)?", f) for p in prefixes)
        ]
        found[key] = max(candidates) if candidates else ""
    return found


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
                col = _geography_columns(reader.fieldnames or [])
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
                            row.get(col["district"]) or None,
                            row.get(col["county"]) or None,
                            row.get(col["ward"]) or None,
                            row.get(col["region"]) or None,
                            (row.get(col["country"]) or "E")[:1],
                            source_id,
                        )
                    )
                    imported += 1
                    if len(batch) >= 2000:
                        conn.executemany(_INSERT_ONSPD_SQL, batch)
                        batch.clear()
                if batch:
                    conn.executemany(_INSERT_ONSPD_SQL, batch)

        # Company postcodes missing from ONSPD fall back to built-in outward/area centroids
        synced = geo.sync_company_postcodes(conn=conn)
        conn.commit()
        return {"onspd_postcodes": imported, "company_postcodes_resolved": synced}
    finally:
        conn.close()
