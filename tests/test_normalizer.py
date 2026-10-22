"""Unit tests for multi-script name normalization, address fingerprinting, and BRN extraction."""
from __future__ import annotations

from src.core.normalizer import (
    compute_address_fingerprint,
    extract_uk_company_numbers,
    jaro_winkler_similarity,
    match_names,
    normalize_name,
    normalize_postcode,
    phonetic_key,
    transliterate_to_ascii,
)


def test_multi_script_transliteration():
    # Cyrillic
    cyr = transliterate_to_ascii("Морозов Виктор")
    assert "morozov" in cyr.lower()
    # Greek
    grk = transliterate_to_ascii("Αλέξανδρος")
    assert len(grk) >= 5
    # Arabic
    ara = transliterate_to_ascii("محمد")
    assert len(ara) >= 2


def test_corporate_name_normalization():
    n1 = normalize_name("AETHELBURG MERIDIAN HOLDINGS LIMITED", is_company=True)
    n2 = normalize_name("Meridian Holdings, Aethelburg Ltd.", is_company=True)
    assert n1 == n2


def test_uk_postcode_and_address_fingerprint():
    assert normalize_postcode("wc2h9jq") == "WC2H 9JQ"
    assert normalize_postcode("EC2N  4BQ") == "EC2N 4BQ"

    fp1 = compute_address_fingerprint("WC2H 9JQ", "71-75 Shelton Street", "Covent Garden, London")
    fp2 = compute_address_fingerprint("wc2h9jq", "71-75 SHELTON ST.", "LONDON")
    assert fp1 == fp2
    assert fp1.startswith("WC2H 9JQ|71|SHELTON")


def test_uk_company_registration_number_extraction():
    raw = "UK Company No: 6527449; OC425116; OE019729; SC123456"
    extracted = extract_uk_company_numbers(raw)
    assert "06527449" in extracted
    assert "OC425116" in extracted
    assert "OE019729" in extracted
    assert "SC123456" in extracted


def test_jaro_winkler_and_phonetic_matching():
    sim = jaro_winkler_similarity("Viktor Morozov", "Victor Morozov")
    assert sim > 0.90
    assert phonetic_key("Smith") == phonetic_key("Smyth")
    score, method = match_names("SOLARIS PACIFIC ASSETS CORP", "Solaris Pacific Assets Limited", is_company=True)
    assert score == 1.0
    assert method == "fingerprint_exact"
