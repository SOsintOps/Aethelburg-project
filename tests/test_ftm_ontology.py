"""Unit & integration tests for FollowTheMoney (FtM v3.x) ontology compatibility."""
from __future__ import annotations

import json
from pathlib import Path

from src.core.ftm import (
    address_to_ftm,
    build_ftm_entity,
    company_to_ftm,
    directorship_to_ftm,
    get_all_properties,
    get_ancestors,
    icij_entity_to_ftm,
    icij_officer_to_ftm,
    icij_relationship_to_ftm,
    legal_entity_to_ftm,
    load_ftm_schema,
    make_ftm_id,
    person_to_ftm,
    psc_to_ftm_ownership,
    sanction_to_ftm,
    validate_ftm_entity,
)


def test_ftm_schema_loaded_and_inheritance():
    schemas = load_ftm_schema()
    assert "Company" in schemas
    assert "Person" in schemas
    assert "Ownership" in schemas
    assert "Directorship" in schemas
    assert "Sanction" in schemas
    assert "Address" in schemas

    ancestors = get_ancestors("Company")
    assert "Organization" in ancestors
    assert "LegalEntity" in ancestors
    assert "Thing" in ancestors

    props = get_all_properties("Company")
    for expected in ("name", "registrationNumber", "jurisdiction", "incorporationDate", "dissolutionDate", "addressEntity"):
        assert expected in props


def test_build_and_validate_ftm_company():
    comp = company_to_ftm(
        {
            "company_number": "14900101",
            "company_name": "AETHELBURG MERIDIAN HOLDINGS LTD",
            "company_status": "Active",
            "company_category": "Private Limited Company",
            "incorporation_date": "2022-04-12",
            "reg_address_line1": "71-75 SHELTON STREET",
            "reg_address_post_town": "LONDON",
            "reg_address_postcode": "WC2H 9JQ",
            "reg_address_country": "United Kingdom",
            "sic_text_1": "64209 - Holding companies",
            "risk_score": 88.0,
            "ft3_techniques": ["FT3-SC-004", "FT3-SC-017"],
            "is_flagged": True,
        }
    )
    ok, errors = validate_ftm_entity(comp)
    assert ok, f"Validation failed: {errors}"
    assert comp["schema"] == "Company"
    assert comp["properties"]["registrationNumber"] == ["14900101"]
    assert comp["properties"]["jurisdiction"] == ["gb"]


def test_ftm_ownership_and_directorship_edges():
    person = person_to_ftm(
        {
            "name": "Viktor Aleksandrovich MOROZOV",
            "forename": "Viktor",
            "surname": "Morozov",
            "nationality": "British",
            "dob_month": 11,
            "dob_year": 1968,
            "is_pep": True,
        }
    )
    ok_p, errs_p = validate_ftm_entity(person)
    assert ok_p, errs_p
    assert "role.pep" in person["properties"].get("topics", [])

    comp_id = make_ftm_id("Company", "gb", "14900101")
    ownership = psc_to_ftm_ownership(
        {
            "company_number": "14900101",
            "nature_of_control": ["ownership-of-shares-75-to-100-percent"],
            "notified_on": "2022-04-12",
        },
        owner_ftm_id=person["id"],
        company_ftm_id=comp_id,
    )
    ok_o, errs_o = validate_ftm_entity(ownership)
    assert ok_o, errs_o
    assert ownership["schema"] == "Ownership"
    assert ownership["properties"]["owner"] == [person["id"]]
    assert ownership["properties"]["asset"] == [comp_id]

    directorship = directorship_to_ftm(
        {
            "company_number": "14900101",
            "officer_role": "director",
            "appointed_on": "2022-04-12",
        },
        director_ftm_id=person["id"],
        company_ftm_id=comp_id,
    )
    ok_d, errs_d = validate_ftm_entity(directorship)
    assert ok_d, errs_d
    assert directorship["schema"] == "Directorship"


def test_ftm_sanction_and_icij_converters():
    subj_ftm, sanc_ftm = sanction_to_ftm(
        {
            "name": "IMPERIAL SHIPPING UK LTD",
            "aliases": ["IMPERIAL MARITIME LTD"],
            "entity_type": "Company",
            "countries": ["United Kingdom", "Russia"],
            "registration_numbers": ["06527449"],
            "list_name": "UK Sanctions List",
            "listed_on": "2024-02-22",
            "opensanctions_id": "RUS2099",
        }
    )
    assert validate_ftm_entity(subj_ftm)[0]
    assert validate_ftm_entity(sanc_ftm)[0]
    assert sanc_ftm["properties"]["entity"] == [subj_ftm["id"]]
    assert subj_ftm["properties"]["registrationNumber"] == ["06527449"]

    icij_ent = icij_entity_to_ftm(
        {
            "node_id": "80099001",
            "name": "SOLARIS PACIFIC ASSETS CORP.",
            "jurisdiction": "BVI",
            "source_id_list": "Panama Papers",
        }
    )
    assert validate_ftm_entity(icij_ent)[0]
    assert "corp.offshore" in icij_ent["properties"].get("topics", [])
