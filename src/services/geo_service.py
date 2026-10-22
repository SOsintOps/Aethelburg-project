"""Geo-intelligence service — UK Postcode Centroids (ONSPD), DBSCAN Clustering & GeoJSON/KML.

Implements ADR-011:
  - Instant postcode centroid resolution via `geo_postcode_centroids` + built-in UK outward/area centroid table
  - DBSCAN spatial clustering of high-risk shell company formations
  - Co-registration hotspot detection (50+ companies at a single address / postcode)
  - Director/PSC cross-company geographic connection lines
"""
from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Any

from config.database import get_sqlite_connection
from src.core.logging import get_logger
from src.core.normalizer import normalize_postcode

log = get_logger(__name__)

# Built-in UK Postcode Area & Key District Centroids (WGS84 lat, lon, district, country)
UK_POSTCODE_CENTROIDS: dict[str, tuple[float, float, str, str]] = {
    # Central London & Financial Districts
    "EC1": (51.5245, -0.0989, "Islington / City of London", "E"),
    "EC1A": (51.5185, -0.0972, "City of London", "E"),
    "EC1M": (51.5215, -0.1018, "Islington", "E"),
    "EC1N": (51.5202, -0.1088, "Camden / City of London", "E"),
    "EC1R": (51.5256, -0.1066, "Islington", "E"),
    "EC1V": (51.5269, -0.0914, "Islington / Hackney", "E"),
    "EC2": (51.5180, -0.0836, "City of London", "E"),
    "EC2A": (51.5228, -0.0818, "Hackney / Islington", "E"),
    "EC2M": (51.5175, -0.0825, "City of London", "E"),
    "EC2N": (51.5149, -0.0847, "City of London", "E"),
    "EC2R": (51.5146, -0.0888, "City of London", "E"),
    "EC2V": (51.5152, -0.0928, "City of London", "E"),
    "EC2Y": (51.5192, -0.0938, "City of London", "E"),
    "EC3": (51.5122, -0.0816, "City of London", "E"),
    "EC3A": (51.5136, -0.0792, "City of London", "E"),
    "EC3M": (51.5116, -0.0822, "City of London", "E"),
    "EC3N": (51.5105, -0.0762, "City of London", "E"),
    "EC3R": (51.5098, -0.0836, "City of London", "E"),
    "EC3V": (51.5125, -0.0858, "City of London", "E"),
    "EC4": (51.5129, -0.0998, "City of London", "E"),
    "EC4A": (51.5142, -0.1085, "City of London", "E"),
    "EC4M": (51.5135, -0.0975, "City of London", "E"),
    "EC4N": (51.5118, -0.0905, "City of London", "E"),
    "EC4R": (51.5102, -0.0892, "City of London", "E"),
    "EC4V": (51.5119, -0.0992, "City of London", "E"),
    "EC4Y": (51.5125, -0.1065, "City of London", "E"),
    "WC1": (51.5225, -0.1235, "Camden", "E"),
    "WC1A": (51.5178, -0.1248, "Camden", "E"),
    "WC1B": (51.5198, -0.1282, "Camden", "E"),
    "WC1E": (51.5222, -0.1332, "Camden", "E"),
    "WC1H": (51.5265, -0.1255, "Camden", "E"),
    "WC1N": (51.5228, -0.1195, "Camden", "E"),
    "WC1R": (51.5188, -0.1152, "Camden", "E"),
    "WC1V": (51.5178, -0.1175, "Camden", "E"),
    "WC1X": (51.5262, -0.1145, "Islington / Camden", "E"),
    "WC2": (51.5135, -0.1218, "Westminster / Camden", "E"),
    "WC2A": (51.5155, -0.1142, "Camden / Westminster", "E"),
    "WC2B": (51.5152, -0.1202, "Camden / Westminster", "E"),
    "WC2E": (51.5122, -0.1235, "Westminster", "E"),
    "WC2H": (51.5138, -0.1285, "Westminster / Camden", "E"),
    "WC2N": (51.5088, -0.1255, "Westminster", "E"),
    "WC2R": (51.5112, -0.1175, "Westminster", "E"),
    # Westminster, Mayfair, Soho, Canary Wharf, Hackney (Major formation agent hubs)
    "W1": (51.5145, -0.1445, "Westminster (Mayfair / Soho)", "E"),
    "W1B": (51.5132, -0.1408, "Westminster", "E"),
    "W1C": (51.5145, -0.1492, "Westminster", "E"),
    "W1D": (51.5138, -0.1328, "Westminster (Soho)", "E"),
    "W1F": (51.5138, -0.1368, "Westminster (Soho)", "E"),
    "W1G": (51.5188, -0.1462, "Westminster (Harley St)", "E"),
    "W1H": (51.5175, -0.1618, "Westminster (Marylebone)", "E"),
    "W1J": (51.5078, -0.1468, "Westminster (Mayfair)", "E"),
    "W1K": (51.5108, -0.1512, "Westminster (Mayfair)", "E"),
    "W1S": (51.5115, -0.1422, "Westminster (Mayfair)", "E"),
    "W1T": (51.5205, -0.1368, "Camden / Fitzrovia", "E"),
    "W1U": (51.5192, -0.1528, "Westminster (Marylebone)", "E"),
    "W1W": (51.5198, -0.1415, "Westminster (Fitzrovia)", "E"),
    "SW1": (51.4985, -0.1415, "Westminster (Belgravia / Victoria)", "E"),
    "SW1A": (51.5035, -0.1318, "Westminster (Whitehall / St James's)", "E"),
    "SW1E": (51.4982, -0.1375, "Westminster (Victoria)", "E"),
    "SW1H": (51.4992, -0.1332, "Westminster", "E"),
    "SW1P": (51.4935, -0.1312, "Westminster (Millbank)", "E"),
    "SW1V": (51.4888, -0.1412, "Westminster (Pimlico)", "E"),
    "SW1W": (51.4928, -0.1518, "Westminster (Belgravia)", "E"),
    "SW1X": (51.4988, -0.1562, "Westminster (Knightsbridge)", "E"),
    "SW1Y": (51.5075, -0.1342, "Westminster (St James's)", "E"),
    "E1": (51.5175, -0.0595, "Tower Hamlets", "E"),
    "E14": (51.5045, -0.0195, "Tower Hamlets (Canary Wharf)", "E"),
    "N1": (51.5365, -0.0955, "Islington / Hackney", "E"),
    "N1C": (51.5352, -0.1255, "Camden (King's Cross)", "E"),
    "NW1": (51.5345, -0.1425, "Camden", "E"),
    "SE1": (51.5015, -0.0915, "Southwark", "E"),
    # Greater London & Regional UK Postcode Areas
    "E": (51.5380, -0.0320, "East London", "E"),
    "EC": (51.5155, -0.0910, "City of London", "E"),
    "N": (51.5820, -0.1050, "North London", "E"),
    "NW": (51.5590, -0.2010, "North West London", "E"),
    "SE": (51.4650, -0.0450, "South East London", "E"),
    "SW": (51.4520, -0.1680, "South West London", "E"),
    "W": (51.5120, -0.2250, "West London", "E"),
    "WC": (51.5165, -0.1215, "Central London", "E"),
    "AB": (57.1497, -2.0943, "Aberdeen", "S"),
    "AL": (51.7520, -0.3360, "St Albans", "E"),
    "B": (52.4862, -1.8904, "Birmingham", "E"),
    "BA": (51.3758, -2.3599, "Bath", "E"),
    "BB": (53.7486, -2.4875, "Blackburn", "E"),
    "BD": (53.7960, -1.7594, "Bradford", "E"),
    "BH": (50.7192, -1.8808, "Bournemouth", "E"),
    "BL": (53.5769, -2.4282, "Bolton", "E"),
    "BN": (50.8225, -0.1372, "Brighton", "E"),
    "BR": (51.4060, 0.0152, "Bromley", "E"),
    "BS": (51.4545, -2.5879, "Bristol", "E"),
    "BT": (54.5973, -5.9301, "Belfast", "N"),
    "CA": (54.8925, -2.9329, "Carlisle", "E"),
    "CB": (52.2053, 0.1218, "Cambridge", "E"),
    "CF": (51.4816, -3.1791, "Cardiff", "W"),
    "CH": (53.1930, -2.8931, "Chester", "E"),
    "CM": (51.7356, 0.4685, "Chelmsford", "E"),
    "CO": (51.8959, 0.8919, "Colchester", "E"),
    "CR": (51.3762, -0.0982, "Croydon", "E"),
    "CT": (51.2802, 1.0789, "Canterbury", "E"),
    "CV": (52.4068, -1.5197, "Coventry", "E"),
    "CW": (53.0980, -2.4400, "Crewe", "E"),
    "DA": (51.4462, 0.2186, "Dartford", "E"),
    "DD": (56.4620, -2.9707, "Dundee", "S"),
    "DE": (52.9225, -1.4746, "Derby", "E"),
    "DG": (55.0709, -3.6051, "Dumfries", "S"),
    "DH": (54.7753, -1.5849, "Durham", "E"),
    "DL": (54.5270, -1.5526, "Darlington", "E"),
    "DN": (53.5228, -1.1285, "Doncaster", "E"),
    "DT": (50.7155, -2.4367, "Dorchester", "E"),
    "DY": (52.5120, -2.0810, "Dudley", "E"),
    "EH": (55.9533, -3.1883, "Edinburgh", "S"),
    "EN": (51.6523, -0.0808, "Enfield", "E"),
    "EX": (50.7184, -3.5339, "Exeter", "E"),
    "FK": (56.0019, -3.7839, "Falkirk", "S"),
    "FY": (53.8175, -3.0357, "Blackpool", "E"),
    "G": (55.8642, -4.2518, "Glasgow", "S"),
    "GL": (51.8642, -2.2382, "Gloucester", "E"),
    "GU": (51.2362, -0.5704, "Guildford", "E"),
    "GY": (49.4554, -2.5369, "Guernsey", "J"),
    "HA": (51.5795, -0.3340, "Harrow", "E"),
    "HD": (53.6458, -1.7850, "Huddersfield", "E"),
    "HG": (53.9921, -1.5418, "Harrogate", "E"),
    "HP": (51.7550, -0.7500, "Hemel Hempstead", "E"),
    "HR": (52.0564, -2.7160, "Hereford", "E"),
    "HS": (58.2090, -6.3860, "Outer Hebrides", "S"),
    "HU": (53.7457, -0.3367, "Hull", "E"),
    "HX": (53.7248, -1.8596, "Halifax", "E"),
    "IG": (51.5590, 0.0741, "Ilford", "E"),
    "IM": (54.1500, -4.4819, "Isle of Man", "M"),
    "IP": (52.0567, 1.1482, "Ipswich", "E"),
    "IV": (57.4778, -4.2247, "Inverness", "S"),
    "JE": (49.1869, -2.1066, "Jersey", "J"),
    "KA": (55.6111, -4.4958, "Kilmarnock", "S"),
    "KT": (51.4085, -0.3064, "Kingston upon Thames", "E"),
    "KW": (58.4409, -3.0928, "Kirkwall", "S"),
    "KY": (56.1107, -3.1674, "Kirkcaldy", "S"),
    "L": (53.4084, -2.9916, "Liverpool", "E"),
    "LA": (54.0466, -2.8007, "Lancaster", "E"),
    "LD": (52.2405, -3.3788, "Llandrindod Wells", "W"),
    "LE": (52.6369, -1.1398, "Leicester", "E"),
    "LL": (53.2274, -4.1293, "Llandudno", "W"),
    "LN": (53.2307, -0.5406, "Lincoln", "E"),
    "LS": (53.8008, -1.5491, "Leeds", "E"),
    "LU": (51.8787, -0.4200, "Luton", "E"),
    "M": (53.4808, -2.2426, "Manchester", "E"),
    "ME": (51.3888, 0.5262, "Medway / Maidstone", "E"),
    "MK": (52.0406, -0.7594, "Milton Keynes", "E"),
    "ML": (55.7897, -3.9911, "Motherwell", "S"),
    "NE": (54.9783, -1.6178, "Newcastle upon Tyne", "E"),
    "NG": (52.9548, -1.1581, "Nottingham", "E"),
    "NN": (52.2405, -0.9027, "Northampton", "E"),
    "NP": (51.5842, -2.9977, "Newport", "W"),
    "NR": (52.6309, 1.2974, "Norwich", "E"),
    "OL": (53.5409, -2.1114, "Oldham", "E"),
    "OX": (51.7520, -1.2577, "Oxford", "E"),
    "PA": (55.8456, -4.4239, "Paisley", "S"),
    "PE": (52.5695, -0.2405, "Peterborough", "E"),
    "PH": (56.3950, -3.4308, "Perth", "S"),
    "PL": (50.3755, -4.1427, "Plymouth", "E"),
    "PO": (50.8198, -1.0880, "Portsmouth", "E"),
    "PR": (53.7632, -2.7031, "Preston", "E"),
    "RG": (51.4543, -0.9781, "Reading", "E"),
    "RH": (51.2365, -0.1972, "Redhill", "E"),
    "RM": (51.5762, 0.1802, "Romford", "E"),
    "S": (53.3811, -1.4701, "Sheffield", "E"),
    "SA": (51.6214, -3.9436, "Swansea", "W"),
    "SG": (51.9022, -0.2016, "Stevenage", "E"),
    "SK": (53.4083, -2.1494, "Stockport", "E"),
    "SL": (51.5105, -0.5950, "Slough", "E"),
    "SM": (51.3618, -0.1945, "Sutton", "E"),
    "SN": (51.5558, -1.7797, "Swindon", "E"),
    "SO": (50.9097, -1.4044, "Southampton", "E"),
    "SP": (51.0688, -1.7945, "Salisbury", "E"),
    "SR": (54.9069, -1.3838, "Sunderland", "E"),
    "SS": (51.5459, 0.7077, "Southend-on-Sea", "E"),
    "ST": (53.0027, -2.1794, "Stoke-on-Trent", "E"),
    "SY": (52.7073, -2.7553, "Shrewsbury", "E"),
    "TA": (51.0149, -3.1029, "Taunton", "E"),
    "TD": (55.6039, -2.7717, "Galashiels", "S"),
    "TF": (52.6766, -2.4469, "Telford", "E"),
    "TN": (51.1324, 0.2637, "Tonbridge", "E"),
    "TQ": (50.4619, -3.5253, "Torquay", "E"),
    "TR": (50.2632, -5.0510, "Truro", "E"),
    "TS": (54.5742, -1.2350, "Cleveland / Middlesbrough", "E"),
    "TW": (51.4490, -0.3370, "Twickenham", "E"),
    "UB": (51.5310, -0.4480, "Southall / Uxbridge", "E"),
    "WA": (53.3900, -2.5970, "Warrington", "E"),
    "WD": (51.6565, -0.3903, "Watford", "E"),
    "WF": (53.6833, -1.4977, "Wakefield", "E"),
    "WN": (53.5451, -2.6325, "Wigan", "E"),
    "WR": (52.1936, -2.2216, "Worcester", "E"),
    "WS": (52.5862, -1.9829, "Walsall", "E"),
    "WV": (52.5870, -2.1288, "Wolverhampton", "E"),
    "YO": (53.9591, -1.0815, "York", "E"),
    "ZE": (60.1530, -1.1493, "Lerwick / Shetland", "S"),
}


PRECISION_POSTCODE = "postcode"  # exact ONSPD centroid of the full postcode
PRECISION_DISTRICT = "district"  # centroid of the outward code (e.g. EC1V, SW1A)
PRECISION_AREA = "area"  # centroid of the postcode area (e.g. B = Birmingham)

_AREA_RE = re.compile(r"[A-Z]+")


def resolve_postcode_location(postcode: str | None) -> tuple[float, float, str, str, str] | None:
    """Resolve a UK postcode from the built-in table to `(lat, lon, district, country_code, precision)`.

    The built-in table only knows outward codes and postcode areas, so the result is never
    more precise than `district`. Exact positions come from ONSPD (`geo_postcode_centroids`).
    """
    norm = normalize_postcode(postcode)
    if not norm or " " not in norm:
        return None
    outward = norm.split(" ")[0]

    # 1. Exact outward code (e.g. EC1V, W1J, SW1A)
    match = UK_POSTCODE_CENTROIDS.get(outward)
    precision = PRECISION_DISTRICT

    # 2. Sub-district letter dropped (EC1V -> EC1); never truncate digits (SE10 is not SE1)
    if not match and len(outward) >= 3 and outward[-1].isalpha():
        match = UK_POSTCODE_CENTROIDS.get(outward[:-1])

    # 3. Postcode area = leading letters only (W1A -> W, not WA = Warrington)
    if not match:
        area = _AREA_RE.match(outward)
        if area:
            match = UK_POSTCODE_CENTROIDS.get(area.group(0))
            precision = PRECISION_AREA

    if not match:
        return None
    lat, lon, district, country = match
    return (lat, lon, district, country, precision)


def resolve_postcode_coords(postcode: str | None) -> tuple[float, float, str, str] | None:
    """Resolve a UK postcode to `(lat, lon, admin_district, country_code)` from the built-in table."""
    loc = resolve_postcode_location(postcode)
    return loc[:4] if loc else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in kilometers between two WGS84 points."""
    r = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


class GeoService:
    """Geospatial intelligence service for Aethelburg."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None

    def connect(self) -> sqlite3.Connection:
        return get_sqlite_connection(self.db_path)

    def sync_company_postcodes(self, conn: sqlite3.Connection | None = None) -> int:
        """Populate `geo_postcode_centroids` for all distinct postcodes present in `companies`."""
        own_conn = conn is None
        c = conn or self.connect()
        try:
            rows = c.execute(
                """
                SELECT DISTINCT reg_address_postcode
                FROM companies
                WHERE reg_address_postcode IS NOT NULL AND reg_address_postcode != ''
                """
            ).fetchall()
            inserted = 0
            batch: list[tuple[Any, ...]] = []
            for r in rows:
                pc = r["reg_address_postcode"]
                resolved = resolve_postcode_location(pc)
                if resolved:
                    batch.append((pc, *resolved))
            if batch:
                # Approximate rows never overwrite an exact ONSPD centroid
                c.executemany(
                    """
                    INSERT INTO geo_postcode_centroids
                        (postcode, lat, lon, admin_district, country_code, precision)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(postcode) DO UPDATE SET
                        lat = excluded.lat,
                        lon = excluded.lon,
                        admin_district = excluded.admin_district,
                        country_code = excluded.country_code,
                        precision = excluded.precision
                    WHERE geo_postcode_centroids.precision IS NULL
                       OR geo_postcode_centroids.precision != 'postcode'
                    """,
                    batch,
                )
                inserted = len(batch)
            if own_conn:
                c.commit()
            return inserted
        finally:
            if own_conn:
                c.close()

    def get_address_hotspots(self, min_companies: int = 3, limit: int = 100) -> list[dict[str, Any]]:
        """Return co-registration address hotspots with coordinates and risk metrics."""
        conn = self.connect()
        try:
            rows = conn.execute(
                """
                SELECT c.address_fingerprint,
                       MAX(c.reg_address_line1) AS sample_address,
                       MAX(c.reg_address_post_town) AS post_town,
                       MAX(c.reg_address_postcode) AS postcode,
                       COUNT(*) AS company_count,
                       SUM(CASE WHEN c.is_flagged = 1 THEN 1 ELSE 0 END) AS flagged_count,
                       ROUND(AVG(c.risk_score), 1) AS avg_risk_score,
                       ROUND(MAX(c.risk_score), 1) AS max_risk_score,
                       g.lat, g.lon, g.admin_district, g.precision
                FROM companies c
                LEFT JOIN geo_postcode_centroids g ON g.postcode = c.reg_address_postcode
                WHERE c.address_fingerprint IS NOT NULL AND c.address_fingerprint != ''
                GROUP BY c.address_fingerprint
                HAVING COUNT(*) >= ?
                ORDER BY company_count DESC, max_risk_score DESC
                LIMIT ?
                """,
                (int(min_companies), int(limit)),
            ).fetchall()
            hotspots = []
            for r in rows:
                d = dict(r)
                if d.get("lat") is None and d.get("postcode"):
                    resolved = resolve_postcode_location(d["postcode"])
                    if resolved:
                        d["lat"], d["lon"], d["admin_district"], _, d["precision"] = resolved
                hotspots.append(d)
            return hotspots
        finally:
            conn.close()

    def get_map_geojson(
        self,
        flagged_only: bool = False,
        min_risk: float = 0.0,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Build a GeoJSON FeatureCollection of companies, address hotspots, and director connection lines."""
        conn = self.connect()
        try:
            clauses = ["c.reg_address_postcode IS NOT NULL AND c.reg_address_postcode != ''"]
            params: list[Any] = []
            if flagged_only:
                clauses.append("c.is_flagged = 1")
            if min_risk > 0:
                clauses.append("c.risk_score >= ?")
                params.append(float(min_risk))
            where_sql = " AND ".join(clauses)

            rows = conn.execute(
                f"""
                SELECT c.company_number, c.company_name, c.company_status,
                       c.reg_address_line1, c.reg_address_post_town, c.reg_address_postcode,
                       c.address_fingerprint, c.risk_score, c.ft3_techniques, c.is_flagged,
                       g.lat, g.lon, g.admin_district, g.precision,
                       (SELECT COUNT(*) FROM companies c2 WHERE c2.address_fingerprint = c.address_fingerprint) AS colocated_count
                FROM companies c
                LEFT JOIN geo_postcode_centroids g ON g.postcode = c.reg_address_postcode
                WHERE {where_sql}
                ORDER BY c.risk_score DESC, c.is_flagged DESC
                LIMIT ?
                """,
                [*params, int(limit)],
            ).fetchall()

            features: list[dict[str, Any]] = []
            company_coords: dict[str, tuple[float, float, str]] = {}

            for r in rows:
                lat, lon, precision = r["lat"], r["lon"], r["precision"]
                if lat is None or lon is None:
                    resolved = resolve_postcode_location(r["reg_address_postcode"])
                    if resolved:
                        lat, lon, precision = resolved[0], resolved[1], resolved[4]
                if lat is None or lon is None:
                    continue

                company_coords[r["company_number"]] = (float(lat), float(lon), r["company_name"])
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(lon), float(lat)],
                        },
                        "properties": {
                            "feature_type": "company",
                            "company_number": r["company_number"],
                            "company_name": r["company_name"],
                            "company_status": r["company_status"],
                            "address": f"{r['reg_address_line1'] or ''}, {r['reg_address_post_town'] or ''} {r['reg_address_postcode'] or ''}".strip(
                                ", "
                            ),
                            "postcode": r["reg_address_postcode"],
                            "district": r["admin_district"] or r["reg_address_post_town"],
                            "location_precision": precision or PRECISION_AREA,
                            "risk_score": round(float(r["risk_score"] or 0.0), 1),
                            "is_flagged": bool(r["is_flagged"]),
                            "colocated_count": int(r["colocated_count"] or 1),
                            "ft3_techniques": r["ft3_techniques"],
                        },
                    }
                )

            # Add cross-company PSC / Director geographic links between loaded companies
            if len(company_coords) >= 2:
                comp_nums = list(company_coords.keys())
                placeholders = ",".join("?" for _ in comp_nums[:200])
                shared_links = conn.execute(
                    f"""
                    SELECT po1.company_number AS c1, po2.company_number AS c2, p.name AS controller_name
                    FROM psc_ownerships po1
                    JOIN psc_ownerships po2 ON po1.person_id = po2.person_id AND po1.company_number < po2.company_number
                    JOIN persons p ON p.id = po1.person_id
                    WHERE po1.company_number IN ({placeholders})
                      AND po2.company_number IN ({placeholders})
                    LIMIT 100
                    """,
                    [*comp_nums[:200], *comp_nums[:200]],
                ).fetchall()
                for link in shared_links:
                    c1, c2 = link["c1"], link["c2"]
                    if c1 in company_coords and c2 in company_coords:
                        lat1, lon1, name1 = company_coords[c1]
                        lat2, lon2, name2 = company_coords[c2]
                        if (lat1, lon1) != (lat2, lon2):
                            features.append(
                                {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "LineString",
                                        "coordinates": [[lon1, lat1], [lon2, lat2]],
                                    },
                                    "properties": {
                                        "feature_type": "controller_link",
                                        "from_company": c1,
                                        "from_name": name1,
                                        "to_company": c2,
                                        "to_name": name2,
                                        "controller_name": link["controller_name"],
                                        "distance_km": round(haversine_km(lat1, lon1, lat2, lon2), 2),
                                    },
                                }
                            )

            return {
                "type": "FeatureCollection",
                "features": features,
            }
        finally:
            conn.close()
