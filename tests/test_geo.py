"""Postcode geocoding: built-in fallback precision and ONSPD precedence."""
from __future__ import annotations

from src.services.db_service import DatabaseService
from src.services.geo_service import (
    PRECISION_AREA,
    PRECISION_DISTRICT,
    PRECISION_POSTCODE,
    GeoService,
    resolve_postcode_location,
)


def test_area_prefix_uses_leading_letters():
    # W1A/W1N/W1R used to resolve to WA (Warrington), WN (Wigan), WR (Worcester)
    for pc in ("W1A 2HU", "W1N 1HB", "W1R 9RE"):
        lat, lon, _, _, _ = resolve_postcode_location(pc)
        assert 51.4 < lat < 51.6 and -0.3 < lon < 0.0, pc


def test_sub_district_letter_dropped_but_digits_kept():
    lat, lon, district, _, precision = resolve_postcode_location("EC1V 2NX")
    assert precision == PRECISION_DISTRICT and "Islington" in district
    # SE10 (Greenwich) must not be truncated to SE1 (Southwark)
    *_, se10_district, _, se10_precision = resolve_postcode_location("SE10 9NN")
    assert se10_precision == PRECISION_AREA and se10_district != "Southwark"


def test_unresolvable_postcodes():
    assert resolve_postcode_location("") is None
    assert resolve_postcode_location("10022") is None
    # E1W (Wapping) is a sub-district of E1 and used to be unresolved
    assert resolve_postcode_location("E1W 1DD")[4] == PRECISION_DISTRICT


def test_no_random_offset():
    assert resolve_postcode_location("B1 1AA")[:2] == resolve_postcode_location("B2 4QA")[:2]


def test_sync_never_overwrites_onspd(tmp_path):
    db = DatabaseService(tmp_path / "geo.sqlite")
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO companies (company_number, company_name, reg_address_postcode) VALUES (?, ?, ?)",
            ("00000001", "EXACT LTD", "W1A 2HU"),
        )
        conn.execute(
            "INSERT INTO companies (company_number, company_name, reg_address_postcode) VALUES (?, ?, ?)",
            ("00000002", "APPROX LTD", "B1 1AA"),
        )
        conn.execute(
            "INSERT INTO geo_postcode_centroids (postcode, lat, lon, precision) VALUES ('W1A 2HU', 51.5186, -0.1437, ?)",
            (PRECISION_POSTCODE,),
        )
        conn.commit()

        GeoService(db.db_path).sync_company_postcodes(conn=conn)
        conn.commit()

        rows = {r["postcode"]: dict(r) for r in conn.execute("SELECT * FROM geo_postcode_centroids")}
        assert rows["W1A 2HU"]["lat"] == 51.5186 and rows["W1A 2HU"]["precision"] == PRECISION_POSTCODE
        assert rows["B1 1AA"]["precision"] == PRECISION_AREA
    finally:
        conn.close()

    features = GeoService(db.db_path).get_map_geojson()["features"]
    by_crn = {f["properties"]["company_number"]: f["properties"] for f in features}
    assert by_crn["00000001"]["location_precision"] == PRECISION_POSTCODE
    assert by_crn["00000002"]["location_precision"] == PRECISION_AREA
