"""Core modules: service registry, logging, FollowTheMoney ontology engine, name/address normalization."""
from src.core.ftm import (
    build_ftm_entity,
    company_to_ftm,
    dump_ftm_jsonl,
    iter_ftm_entities,
    load_ftm_schema,
    make_ftm_id,
    validate_ftm_entity,
)
from src.core.logging import setup_logging
from src.core.normalizer import (
    compute_address_fingerprint,
    extract_uk_company_numbers,
    jaro_winkler_similarity,
    match_names,
    normalize_name,
    normalize_postcode,
    phonetic_key,
)
from src.core.service_registry import ServiceRegistry

__all__ = [
    "ServiceRegistry",
    "setup_logging",
    "load_ftm_schema",
    "make_ftm_id",
    "build_ftm_entity",
    "validate_ftm_entity",
    "company_to_ftm",
    "dump_ftm_jsonl",
    "iter_ftm_entities",
    "normalize_name",
    "normalize_postcode",
    "compute_address_fingerprint",
    "phonetic_key",
    "jaro_winkler_similarity",
    "match_names",
    "extract_uk_company_numbers",
]
