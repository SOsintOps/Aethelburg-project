"""
FollowTheMoney (FtM v3.x) Ontology Engine for Aethelburg.

Ensures 100% compatibility between Aethelburg's relational/graph database and the
FollowTheMoney schema used by OCCRP Aleph, OpenSanctions, and Quaesitor.

Every node and relationship in Aethelburg maps to a canonical FollowTheMoney entity:
  - Company         -> Company (extends Organization, LegalEntity, Thing, Asset)
  - Person          -> Person (extends LegalEntity, Thing)
  - Corporate PSC   -> LegalEntity / Company
  - Address         -> Address (extends Thing)
  - PSC Ownership   -> Ownership (edge: owner -> asset, extends Interest, Interval)
  - Directorship    -> Directorship (edge: director -> organization, extends Interest, Interval)
  - Sanction        -> Sanction (extends Interval, Thing; entity -> sanctioned target)
  - PEP Mandate     -> Occupancy (edge: holder -> post) + Person (topics=['role.pep'])
  - ICIJ Relationship -> Directorship / Ownership / Representation / Associate / UnknownLink
  - Manual Link     -> UnknownLink / Associate / Control / Ownership / Directorship
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

try:
    from followthemoney.util import make_entity_id as _ftm_make_id
except ImportError:
    _ftm_make_id = None

SCHEMA_PATH = Path(__file__).parent / "ftm_schema.json"

# ISO-2 mapping for common UK & offshore jurisdiction names
JURISDICTION_TO_ISO2: dict[str, str] = {
    "united kingdom": "gb",
    "uk": "gb",
    "great britain": "gb",
    "england": "gb",
    "england and wales": "gb",
    "england & wales": "gb",
    "wales": "gb",
    "scotland": "gb",
    "northern ireland": "gb",
    "british virgin islands": "vg",
    "bvi": "vg",
    "cayman islands": "ky",
    "cayman": "ky",
    "panama": "pa",
    "bahamas": "bs",
    "bermuda": "bm",
    "jersey": "je",
    "guernsey": "gg",
    "isle of man": "im",
    "gibraltar": "gi",
    "seychelles": "sc",
    "belize": "bz",
    "cyprus": "cy",
    "malta": "mt",
    "luxembourg": "lu",
    "liechtenstein": "li",
    "switzerland": "ch",
    "hong kong": "hk",
    "singapore": "sg",
    "united arab emirates": "ae",
    "uae": "ae",
    "dubai": "ae",
    "mauritius": "mu",
    "samoa": "ws",
    "marshall islands": "mh",
    "curacao": "cw",
    "anguilla": "ai",
    "turks and caicos islands": "tc",
    "niue": "nu",
    "cook islands": "ck",
    "vanuatu": "vu",
    "st kitts and nevis": "kn",
    "saint kitts and nevis": "kn",
    "delaware": "us",
    "united states": "us",
    "usa": "us",
    "russia": "ru",
    "russian federation": "ru",
    "belarus": "by",
    "iran": "ir",
    "china": "cn",
    "people's republic of china": "cn",
}

OFFSHORE_JURISDICTION_CODES: set[str] = {
    "vg", "ky", "pa", "bs", "bm", "je", "gg", "im", "gi", "sc", "bz",
    "cy", "mt", "lu", "li", "hk", "sg", "ae", "mu", "ws", "mh", "cw",
    "ai", "tc", "nu", "ck", "vu", "kn", "aw", "ky", "bvi", "pma", "bah",
    "cym", "sey", "jey", "ggy", "imn", "gib", "blz", "mlt", "cyp", "samoa",
}


@lru_cache(maxsize=1)
def load_ftm_schema() -> dict[str, dict[str, Any]]:
    """Load the official FollowTheMoney schema definition."""
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=256)
def get_ancestors(schema_name: str) -> tuple[str, ...]:
    """Return all ancestor schemas in inheritance order."""
    schemas = load_ftm_schema()
    seen: list[str] = []

    def _walk(name: str) -> None:
        spec = schemas.get(name) or {}
        for parent in spec.get("extends") or []:
            if parent not in seen and parent in schemas:
                seen.append(parent)
                _walk(parent)

    _walk(schema_name)
    return tuple(seen)


@lru_cache(maxsize=256)
def get_all_properties(schema_name: str) -> dict[str, dict[str, Any]]:
    """Return all valid FtM properties for a schema, including inherited properties."""
    schemas = load_ftm_schema()
    if schema_name not in schemas:
        raise ValueError(f"Unknown FollowTheMoney schema: {schema_name}")
    props: dict[str, dict[str, Any]] = {}
    for ancestor in reversed(get_ancestors(schema_name)):
        props.update(schemas[ancestor].get("properties") or {})
    props.update(schemas[schema_name].get("properties") or {})
    return props


def is_edge_schema(schema_name: str) -> bool:
    schemas = load_ftm_schema()
    spec = schemas.get(schema_name) or {}
    return bool(spec.get("edge"))


def get_edge_spec(schema_name: str) -> dict[str, Any] | None:
    schemas = load_ftm_schema()
    spec = schemas.get(schema_name) or {}
    return spec.get("edge")


def make_ftm_id(schema_name: str, *parts: Any, key_prefix: str = "aethelburg") -> str:
    """
    Generate a deterministic FollowTheMoney entity ID (40-char SHA-1 hex or prefixed slug).
    Compatible with followthemoney.util.make_entity_id and Quaesitor's ftm_ids table.
    """
    clean_parts = [str(p).strip() for p in parts if p is not None and str(p).strip()]
    if not clean_parts:
        clean_parts = ["anonymous"]
    if _ftm_make_id is not None:
        eid = _ftm_make_id(*clean_parts, key_prefix=f"{key_prefix}:{schema_name}")
        if eid:
            return eid
    digest = hashlib.sha1()
    digest.update(f"{key_prefix}:{schema_name}:".encode("utf-8"))
    digest.update("|".join(clean_parts).encode("utf-8"))
    return digest.hexdigest()


def normalize_country_code(raw: str | None) -> str:
    """Convert a country/jurisdiction string to lowercase ISO-2 or FtM country code."""
    if not raw:
        return ""
    s = str(raw).strip().lower()
    if not s:
        return ""
    if s in JURISDICTION_TO_ISO2:
        return JURISDICTION_TO_ISO2[s]
    if len(s) == 2 and s.isalpha():
        return s
    if len(s) == 3 and s.isalpha():
        # Common ISO-3 to ISO-2
        iso3_map = {
            "gbr": "gb", "usa": "us", "rus": "ru", "chn": "cn", "che": "ch",
            "cym": "ky", "vgb": "vg", "bvi": "vg", "pan": "pa", "pma": "pa",
            "bhs": "bs", "bah": "bs", "bmu": "bm", "jey": "je", "ggy": "gg",
            "imn": "im", "gib": "gi", "syc": "sc", "sey": "sc", "cyp": "cy",
            "mlt": "mt", "lux": "lu", "lie": "li", "hkg": "hk", "sgp": "sg",
            "are": "ae", "mus": "mu", "wsm": "ws", "sam": "ws", "mhl": "mh",
            "blz": "bz", "blr": "by", "irn": "ir", "AFG": "af", "afg": "af",
        }
        return iso3_map.get(s, s[:2])
    for k, v in JURISDICTION_TO_ISO2.items():
        if k in s:
            return v
    return s[:10]


def is_offshore_jurisdiction(raw: str | None) -> bool:
    if not raw:
        return False
    s = str(raw).strip().lower()
    code = normalize_country_code(s)
    return code in OFFSHORE_JURISDICTION_CODES or s in OFFSHORE_JURISDICTION_CODES


def compute_caption(schema_name: str, properties: dict[str, list[str]]) -> str:
    """Compute human-readable caption according to FollowTheMoney schema rules."""
    schemas = load_ftm_schema()
    spec = schemas.get(schema_name) or {}
    caption_keys = list(spec.get("caption") or [])
    if spec.get("edge"):
        caption_keys.extend(spec["edge"].get("caption") or [])
    caption_keys.extend(["name", "full", "title", "role", "summary", "registrationNumber"])
    for key in caption_keys:
        vals = properties.get(key)
        if vals and str(vals[0]).strip():
            return str(vals[0]).strip()
    return schema_name


def _clean_prop_values(values: Any) -> list[str]:
    """Ensure an FtM property value is a deduplicated list of non-empty strings."""
    if values is None:
        return []
    if isinstance(values, (str, int, float, bool)):
        if isinstance(values, bool):
            return []
        s = str(values).strip()
        return [s] if s else []
    out: list[str] = []
    for item in values:
        if item is None or isinstance(item, bool):
            continue
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
    return out


def build_ftm_entity(
    schema_name: str | None = None,
    properties: dict[str, Any] | None = None,
    *,
    schema: str | None = None,
    entity_id: str | None = None,
    datasets: list[str] | None = None,
    referents: list[str] | None = None,
    first_seen: str | None = None,
    last_seen: str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """
    Construct and validate a canonical FollowTheMoney entity dictionary.
    All unknown properties (not in schema_name or its ancestors) are moved into `notes`
    unless `strict=True` (which raises ValueError), just like Quaesitor's FtM exporter.
    """
    resolved_schema = schema_name or schema
    if not resolved_schema:
        raise ValueError("schema_name or schema is required")
    schema_name = resolved_schema
    properties = properties or {}
    allowed = get_all_properties(schema_name)
    cleaned_props: dict[str, list[str]] = {}
    extra_notes: list[str] = []

    for key, raw_val in properties.items():
        vals = _clean_prop_values(raw_val)
        if not vals:
            continue
        if key in allowed:
            existing = cleaned_props.setdefault(key, [])
            for v in vals:
                if v not in existing:
                    existing.append(v)
        elif strict:
            raise ValueError(f"Property '{key}' is not defined on FtM schema '{schema_name}'")
        else:
            extra_notes.append(f"{key}: {'; '.join(vals)}")

    if extra_notes and "notes" in allowed:
        notes_list = cleaned_props.setdefault("notes", [])
        for n in extra_notes:
            if n not in notes_list:
                notes_list.append(n)

    caption = compute_caption(schema_name, cleaned_props)
    eid = entity_id or make_ftm_id(schema_name, caption, json.dumps(cleaned_props, sort_keys=True))

    entity: dict[str, Any] = {
        "id": eid,
        "schema": schema_name,
        "caption": caption,
        "properties": cleaned_props,
        "datasets": datasets or ["aethelburg"],
        "referents": referents or [],
    }
    if first_seen:
        entity["first_seen"] = first_seen
    if last_seen:
        entity["last_seen"] = last_seen

    edge_spec = get_edge_spec(schema_name)
    if edge_spec:
        src_prop = edge_spec["source"]
        tgt_prop = edge_spec["target"]
        src_vals = cleaned_props.get(src_prop) or []
        tgt_vals = cleaned_props.get(tgt_prop) or []
        entity["_edge"] = {
            "source_prop": src_prop,
            "target_prop": tgt_prop,
            "source_id": src_vals[0] if src_vals else None,
            "target_id": tgt_vals[0] if tgt_vals else None,
            "label": edge_spec.get("label") or schema_name,
            "directed": bool(edge_spec.get("directed", True)),
        }
    return entity


def validate_ftm_entity(entity: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that an entity dict conforms to the official FollowTheMoney schema."""
    errors: list[str] = []
    if not isinstance(entity, dict):
        return False, ["Entity is not a dict"]
    eid = entity.get("id")
    if not eid or not isinstance(eid, str):
        errors.append("Missing or invalid 'id'")
    sc = entity.get("schema")
    schemas = load_ftm_schema()
    if not sc or sc not in schemas:
        errors.append(f"Unknown FtM schema: {sc!r}")
        return False, errors
    props = entity.get("properties")
    if not isinstance(props, dict):
        errors.append("Missing or invalid 'properties' dict")
        return False, errors

    allowed = get_all_properties(sc)
    for k, v in props.items():
        if k not in allowed:
            errors.append(f"Property '{k}' not valid for schema '{sc}'")
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errors.append(f"Property '{k}' must be a list[str]")

    edge_spec = get_edge_spec(sc)
    if edge_spec:
        for req_prop in (edge_spec["source"], edge_spec["target"]):
            if not props.get(req_prop):
                errors.append(f"Edge schema '{sc}' requires endpoint property '{req_prop}'")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Domain Converters: Aethelburg Relational Rows -> FollowTheMoney Entities
# ---------------------------------------------------------------------------


def address_to_ftm(
    *,
    postcode: str | None = None,
    line1: str | None = None,
    line2: str | None = None,
    post_town: str | None = None,
    street: str | None = None,
    street2: str | None = None,
    city: str | None = None,
    county: str | None = None,
    country: str | None = None,
    po_box: str | None = None,
    care_of: str | None = None,
    address_fingerprint: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    dataset: str = "companies_house",
) -> dict[str, Any] | None:
    """Convert an address record into a FollowTheMoney `Address` entity."""
    line1 = line1 or street
    line2 = line2 or street2
    post_town = post_town or city
    parts = [p for p in (care_of, po_box, line1, line2, post_town, county, postcode, country) if p and str(p).strip()]
    if not parts:
        return None
    full = ", ".join(str(p).strip() for p in parts)
    fp_key = address_fingerprint or full.upper()
    aid = make_ftm_id("Address", fp_key)
    cc = normalize_country_code(country or "gb")
    props: dict[str, Any] = {
        "full": [full],
        "street": [line1] if line1 else [],
        "street2": [line2] if line2 else [],
        "city": [post_town] if post_town else [],
        "region": [county] if county else [],
        "postalCode": [postcode] if postcode else [],
        "postOfficeBox": [po_box] if po_box else [],
        "country": [cc] if cc else ["gb"],
        "remarks": [f"c/o {care_of}"] if care_of else [],
    }
    if lat is not None and lon is not None:
        props["latitude"] = [f"{float(lat):.6f}"]
        props["longitude"] = [f"{float(lon):.6f}"]
    return build_ftm_entity("Address", props, entity_id=aid, datasets=[dataset])


def company_to_ftm(row: dict[str, Any], *, address_ftm_id: str | None = None) -> dict[str, Any]:
    """Convert a Companies House `companies` row into a FollowTheMoney `Company` entity."""
    company_number = str(row.get("company_number") or "").strip()
    cid = row.get("ftm_id") or make_ftm_id("Company", "gb", company_number)

    prev_names = [
        row.get(f"prev_name_{i}")
        for i in range(1, 11)
        if row.get(f"prev_name_{i}")
    ]
    sic_texts = [
        row.get(f"sic_text_{i}")
        for i in range(1, 5)
        if row.get(f"sic_text_{i}")
    ]
    addr_parts = [
        row.get("reg_address_line1"),
        row.get("reg_address_line2"),
        row.get("reg_address_post_town"),
        row.get("reg_address_county"),
        row.get("reg_address_postcode"),
    ]
    full_addr = ", ".join(str(p).strip() for p in addr_parts if p and str(p).strip())

    topics: list[str] = ["corp.public"] if "plc" in str(row.get("company_category") or "").lower() else []
    if row.get("is_flagged"):
        topics.append("poi")

    ft3_list = row.get("ft3_techniques") or []
    if isinstance(ft3_list, str):
        try:
            ft3_list = json.loads(ft3_list)
        except Exception:
            ft3_list = [ft3_list]

    notes: list[str] = []
    if row.get("risk_score") is not None and float(row.get("risk_score") or 0) > 0:
        notes.append(f"Aethelburg risk_score={float(row['risk_score']):.1f}/100")
    if ft3_list:
        notes.append(f"FT3 techniques: {', '.join(str(x) for x in ft3_list)}")
    if row.get("accounts_account_category"):
        notes.append(f"Accounts category: {row['accounts_account_category']}")

    props: dict[str, Any] = {
        "name": [row.get("company_name") or company_number],
        "registrationNumber": [company_number],
        "jurisdiction": [normalize_country_code(row.get("country_of_origin") or "gb") or "gb"],
        "country": [normalize_country_code(row.get("reg_address_country") or "gb") or "gb"],
        "legalForm": [row.get("company_category")],
        "status": [row.get("company_status")],
        "incorporationDate": [str(row["incorporation_date"])] if row.get("incorporation_date") else [],
        "dissolutionDate": [str(row["dissolution_date"])] if row.get("dissolution_date") else [],
        "previousName": prev_names,
        "sector": sic_texts,
        "address": [full_addr] if full_addr else [],
        "addressEntity": [address_ftm_id] if address_ftm_id else [],
        "sourceUrl": [
            row.get("ch_uri")
            or f"https://find-and-update.company-information.service.gov.uk/company/{company_number}"
        ],
        "topics": topics,
        "notes": notes,
    }
    return build_ftm_entity("Company", props, entity_id=cid, datasets=["companies_house"])


def person_to_ftm(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a `persons` row into a FollowTheMoney `Person` entity."""
    pid = row.get("ftm_id") or make_ftm_id(
        "Person",
        row.get("name_fingerprint") or row.get("name"),
        row.get("dob_year") or "",
        row.get("dob_month") or "",
    )
    birth_date: list[str] = []
    if row.get("dob_year") and row.get("dob_month"):
        birth_date.append(f"{int(row['dob_year']):04d}-{int(row['dob_month']):02d}")
    elif row.get("dob_year"):
        birth_date.append(f"{int(row['dob_year']):04d}")

    topics: list[str] = []
    if row.get("is_pep"):
        topics.append("role.pep")

    props: dict[str, Any] = {
        "name": [row.get("name")],
        "firstName": [row.get("forename")] if row.get("forename") else [],
        "lastName": [row.get("surname")] if row.get("surname") else [],
        "title": [row.get("title")] if row.get("title") else [],
        "birthDate": birth_date,
        "nationality": [normalize_country_code(row.get("nationality"))] if row.get("nationality") else [],
        "country": [normalize_country_code(row.get("country_of_residence"))] if row.get("country_of_residence") else [],
        "topics": topics,
    }
    return build_ftm_entity("Person", props, entity_id=pid, datasets=["companies_house_psc"])


def legal_entity_to_ftm(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a `legal_entities` row into a FollowTheMoney `LegalEntity` or `Company` entity."""
    etype = str(row.get("entity_type") or "")
    schema_name = "Company" if "corporate" in etype or row.get("company_number_foreign") else "LegalEntity"
    lid = row.get("ftm_id") or make_ftm_id(
        schema_name,
        row.get("name_fingerprint") or row.get("name"),
        row.get("jurisdiction") or "",
        row.get("company_number_foreign") or "",
    )
    topics: list[str] = []
    if row.get("is_offshore") or is_offshore_jurisdiction(row.get("jurisdiction")):
        topics.append("corp.offshore")

    props: dict[str, Any] = {
        "name": [row.get("name")],
        "jurisdiction": [normalize_country_code(row.get("jurisdiction"))] if row.get("jurisdiction") else [],
        "registrationNumber": [row.get("company_number_foreign")] if row.get("company_number_foreign") else [],
        "legalForm": [row.get("entity_type")] if row.get("entity_type") else [],
        "topics": topics,
    }
    return build_ftm_entity(schema_name, props, entity_id=lid, datasets=["companies_house_psc"])


def psc_to_ftm_ownership(
    row: dict[str, Any],
    *,
    owner_ftm_id: str | None,
    company_ftm_id: str,
) -> dict[str, Any]:
    """Convert a `psc_ownerships` row into a FollowTheMoney `Ownership` edge."""
    effective_owner_id = owner_ftm_id or make_ftm_id("LegalEntity", "super_secure_psc", company_ftm_id)
    natures = row.get("nature_of_control") or []
    if isinstance(natures, str):
        try:
            natures = json.loads(natures)
        except Exception:
            natures = [natures]

    pct: list[str] = []
    for n in natures:
        s = str(n)
        if "75-to-100" in s:
            pct.append("75-100%")
        elif "50-to-75" in s:
            pct.append("50-75%")
        elif "25-to-50" in s:
            pct.append("25-50%")

    oid = row.get("ftm_id") or make_ftm_id("Ownership", effective_owner_id, company_ftm_id, row.get("notified_on") or "")
    props: dict[str, Any] = {
        "owner": [effective_owner_id],
        "asset": [company_ftm_id],
        "role": [str(n) for n in natures] or ["person-with-significant-control"],
        "percentage": pct,
        "startDate": [str(row["notified_on"])] if row.get("notified_on") else [],
        "endDate": [str(row["ceased_on"])] if row.get("ceased_on") else [],
        "status": ["ceased" if row.get("is_ceased") else "active"],
    }
    return build_ftm_entity("Ownership", props, entity_id=oid, datasets=["companies_house_psc"])


def directorship_to_ftm(
    row: dict[str, Any],
    *,
    director_ftm_id: str,
    company_ftm_id: str,
) -> dict[str, Any]:
    """Convert a `directorships` row into a FollowTheMoney `Directorship` edge."""
    did = row.get("ftm_id") or make_ftm_id(
        "Directorship",
        director_ftm_id,
        company_ftm_id,
        row.get("officer_role") or "director",
        row.get("appointed_on") or "",
    )
    props: dict[str, Any] = {
        "director": [director_ftm_id],
        "organization": [company_ftm_id],
        "role": [row.get("officer_role") or "director"],
        "startDate": [str(row["appointed_on"])] if row.get("appointed_on") else [],
        "endDate": [str(row["resigned_on"])] if row.get("resigned_on") else [],
        "status": ["active" if row.get("is_active", True) else "resigned"],
    }
    return build_ftm_entity("Directorship", props, entity_id=did, datasets=["companies_house_officers"])


def sanction_to_ftm(row: dict[str, Any], *, target_ftm_id: str | None = None) -> list[dict[str, Any]]:
    """
    Convert a `sanctions` row into FollowTheMoney entities:
      1. The sanctioned subject (`Person`, `Company`, or `LegalEntity`)
      2. The `Sanction` entity pointing to `entity = subject_id`
    """
    etype = str(row.get("entity_type") or "LegalEntity").strip()
    if etype.lower() in ("individual", "person"):
        subject_schema = "Person"
    elif etype.lower() in ("entity", "company", "organization"):
        subject_schema = "Company"
    else:
        subject_schema = "LegalEntity"

    ext_id = row.get("opensanctions_id") or row.get("unique_id") or row.get("name")
    subj_id = target_ftm_id or row.get("ftm_id") or make_ftm_id(subject_schema, "sanction_subject", ext_id)
    sanc_id = make_ftm_id("Sanction", ext_id, row.get("list_name") or "UK Sanctions List")

    aliases = row.get("aliases") or []
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except Exception:
            aliases = [aliases]

    reg_nums = row.get("registration_numbers") or []
    if isinstance(reg_nums, str):
        try:
            reg_nums = json.loads(reg_nums)
        except Exception:
            reg_nums = [reg_nums]

    countries = row.get("countries") or []
    if isinstance(countries, str):
        try:
            countries = json.loads(countries)
        except Exception:
            countries = [countries]
    norm_countries = [normalize_country_code(c) for c in countries if normalize_country_code(c)]

    subj_props: dict[str, Any] = {
        "name": [row.get("name")],
        "alias": aliases,
        "country": norm_countries,
        "topics": ["sanction"],
    }
    if subject_schema in ("Company", "LegalEntity") and reg_nums:
        subj_props["registrationNumber"] = reg_nums

    subject_ent = build_ftm_entity(subject_schema, subj_props, entity_id=subj_id, datasets=["uk_sanctions"])

    raw_props = row.get("raw_properties") or {}
    if isinstance(raw_props, str):
        try:
            raw_props = json.loads(raw_props)
        except Exception:
            raw_props = {}

    sanc_props: dict[str, Any] = {
        "entity": [subj_id],
        "authority": [row.get("list_name") or "UK FCDO / OFSI"],
        "authorityId": [ext_id] if ext_id else [],
        "program": [raw_props.get("regime_name")] if raw_props.get("regime_name") else [],
        "reason": [raw_props.get("statement_of_reasons")] if raw_props.get("statement_of_reasons") else [],
        "provisions": [raw_props.get("sanctions_imposed")] if raw_props.get("sanctions_imposed") else [],
        "listingDate": [str(row["listed_on"])] if row.get("listed_on") else [],
        "country": norm_countries,
    }
    sanc_ent = build_ftm_entity("Sanction", sanc_props, entity_id=sanc_id, datasets=["uk_sanctions"])
    return [subject_ent, sanc_ent]


def icij_entity_to_ftm(row: dict[str, Any]) -> dict[str, Any]:
    """Convert an `icij_entities` row into a FollowTheMoney `Company` entity."""
    node_id = str(row.get("node_id") or "")
    fid = row.get("ftm_id") or make_ftm_id("Company", "icij_entity", node_id)
    jur = normalize_country_code(row.get("jurisdiction") or row.get("jurisdiction_description"))
    props: dict[str, Any] = {
        "name": [row.get("name") or f"ICIJ Entity {node_id}"],
        "alias": [x for x in (row.get("original_name"), row.get("former_name")) if x],
        "jurisdiction": [jur] if jur else [],
        "registrationNumber": [row.get("ibc_ruc") or row.get("internal_id")] if (row.get("ibc_ruc") or row.get("internal_id")) else [],
        "incorporationDate": [str(row["incorporation_date"])] if row.get("incorporation_date") else [],
        "dissolutionDate": [str(row["inactivation_date"] or row.get("struck_off_date"))] if (row.get("inactivation_date") or row.get("struck_off_date")) else [],
        "status": [row.get("status")] if row.get("status") else [],
        "address": [row.get("address")] if row.get("address") else [],
        "publisher": [row.get("source_id_list")] if row.get("source_id_list") else ["ICIJ Offshore Leaks"],
        "topics": ["corp.offshore"],
        "notes": [row.get("note")] if row.get("note") else [],
    }
    return build_ftm_entity("Company", props, entity_id=fid, datasets=["icij_offshore_leaks"])


def icij_officer_to_ftm(row: dict[str, Any]) -> dict[str, Any]:
    """Convert an `icij_officers` or `icij_intermediaries` row into a FollowTheMoney `LegalEntity` / `Person`."""
    node_id = str(row.get("node_id") or "")
    name = str(row.get("name") or f"ICIJ Officer {node_id}")
    is_corp = bool(re.search(r"\b(ltd|limited|inc|corp|sa|s\.a\.|llc|trust|foundation|b\.v\.|ag|gmbh)\b", name, re.I))
    sc = "Company" if is_corp else "Person"
    fid = row.get("ftm_id") or make_ftm_id(sc, "icij_officer", node_id)
    cc_raw = str(row.get("country_codes") or "")
    countries = [normalize_country_code(c) for c in cc_raw.split(";") if normalize_country_code(c)]
    props: dict[str, Any] = {
        "name": [name],
        "country": countries,
        "publisher": [row.get("source_id_list")] if row.get("source_id_list") else ["ICIJ Offshore Leaks"],
        "notes": [row.get("note")] if row.get("note") else [],
    }
    return build_ftm_entity(sc, props, entity_id=fid, datasets=["icij_offshore_leaks"])


def icij_relationship_to_ftm(
    row: dict[str, Any],
    *,
    start_ftm_id: str,
    end_ftm_id: str,
) -> dict[str, Any]:
    """Convert an `icij_relationships` row into a typed FollowTheMoney edge entity."""
    rel_type = str(row.get("rel_type") or "").lower()
    link_label = str(row.get("link") or rel_type or "linked to")
    if "shareholder" in link_label.lower() or "beneficial owner" in link_label.lower() or "owner" in link_label.lower():
        sc = "Ownership"
        props: dict[str, Any] = {"owner": [start_ftm_id], "asset": [end_ftm_id], "role": [link_label]}
    elif "director" in link_label.lower() or "officer_of" in rel_type:
        sc = "Directorship"
        props = {"director": [start_ftm_id], "organization": [end_ftm_id], "role": [link_label]}
    elif "intermediary" in rel_type:
        sc = "Representation"
        props = {"agent": [start_ftm_id], "client": [end_ftm_id], "role": [link_label]}
    elif "same_" in rel_type:
        sc = "Associate"
        props = {"person": [start_ftm_id], "associate": [end_ftm_id], "relationship": [link_label]}
    else:
        sc = "UnknownLink"
        props = {"subject": [start_ftm_id], "object": [end_ftm_id], "role": [link_label]}

    if row.get("start_date"):
        props["startDate"] = [str(row["start_date"])]
    if row.get("end_date"):
        props["endDate"] = [str(row["end_date"])]
    if row.get("status"):
        props["status"] = [str(row["status"])]

    rid = make_ftm_id(sc, "icij_rel", start_ftm_id, end_ftm_id, link_label)
    return build_ftm_entity(sc, props, entity_id=rid, datasets=["icij_offshore_leaks"])


def dump_ftm_jsonl(entities: list[dict[str, Any]]) -> str:
    """Serialize FollowTheMoney entities as newline-delimited JSON (Aleph / OpenSanctions / Quaesitor format)."""
    lines: list[str] = []
    for ent in entities:
        clean = {k: v for k, v in ent.items() if not k.startswith("_")}
        lines.append(json.dumps(clean, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def iter_ftm_entities(blob_or_text: bytes | str) -> Iterator[dict[str, Any]]:
    """
    Parse FollowTheMoney entities from JSONL, a JSON array, or an Aleph export dict.
    Compatible with Quaesitor's ftm.py format.
    """
    text = blob_or_text.decode("utf-8-sig", errors="replace") if isinstance(blob_or_text, bytes) else str(blob_or_text)
    stripped = text.strip()
    if not stripped:
        return
    schemas = load_ftm_schema()

    if stripped.startswith("[") or (stripped.startswith("{") and "\n" not in stripped):
        try:
            parsed = json.loads(stripped)
            items = parsed.get("entities") or parsed.get("results") or [parsed] if isinstance(parsed, dict) else parsed
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("schema") in schemas and isinstance(item.get("properties"), dict):
                        yield build_ftm_entity(
                            item["schema"],
                            item["properties"],
                            entity_id=item.get("id"),
                            datasets=item.get("datasets"),
                            referents=item.get("referents"),
                        )
                return
        except json.JSONDecodeError:
            pass

    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("schema") in schemas and isinstance(item.get("properties"), dict):
            yield build_ftm_entity(
                item["schema"],
                item["properties"],
                entity_id=item.get("id"),
                datasets=item.get("datasets"),
                referents=item.get("referents"),
            )
