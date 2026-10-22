"""Map Companies House REST/Streaming `company-profile` resources onto the bulk-CSV record shape.

The FT3 rules (`src/intelligence/risk_scorer.py`) match the wording of the bulk product
(`Active`, `Active - Proposal to Strike off`, `DORMANT`), so API enums are translated to it.
"""
from __future__ import annotations

from typing import Any

from src.core.normalizer import compute_address_fingerprint, normalize_name, normalize_postcode

# API `company_status` -> bulk `CompanyStatus`
_STATUS = {
    "active": "Active",
    "dissolved": "Dissolved",
    "liquidation": "Liquidation",
    "receivership": "Receivership",
    "administration": "In Administration",
    "voluntary-arrangement": "Voluntary Arrangement",
    "converted-closed": "Converted/Closed",
    "insolvency-proceedings": "Insolvency Proceedings",
    "registered": "Registered",
    "removed": "Removed",
    "closed": "Closed",
    "open": "Open",
}

# API `type` -> bulk `CompanyCategory` (unknown types keep the API value)
_CATEGORY = {
    "ltd": "Private Limited Company",
    "plc": "Public Limited Company",
    "old-public-company": "Old Public Company",
    "private-unlimited": "Private Unlimited Company",
    "private-unlimited-nsc": "Private Unlimited Company",
    "private-limited-guarant-nsc": "PRI/LTD BY GUAR/NSC (Private, limited by guarantee, no share capital)",
    "private-limited-guarant-nsc-limited-exemption": (
        "PRI/LBG/NSC (Private, Limited by guarantee, no share capital, use of 'Limited' exemption)"
    ),
    "llp": "Limited Liability Partnership",
    "limited-partnership": "Limited Partnership",
    "charitable-incorporated-organisation": "Charitable Incorporated Organisation",
    "scottish-charitable-incorporated-organisation": "Scottish Charitable Incorporated Organisation",
    "community-interest-company": "Community Interest Company",
    "registered-overseas-entity": "Overseas Entity",
    "royal-charter": "Royal Charter Company",
    "registered-society-non-jurisdictional": "Registered Society",
    "other": "Other company type",
}


def map_company_status(status: str | None, detail: str | None = None) -> str | None:
    if not status:
        return None
    mapped = _STATUS.get(status, status)
    if detail == "active-proposal-to-strike-off":
        return "Active - Proposal to Strike off"
    return mapped


def map_accounts_category(api_type: str | None) -> str | None:
    """`micro-entity` -> `MICRO ENTITY`, `dormant` -> `DORMANT` (bulk wording)."""
    return api_type.replace("-", " ").upper() if api_type else None


def profile_to_record(profile: dict[str, Any]) -> dict[str, Any] | None:
    """Translate a `company-profile` resource into the record accepted by `upsert_company_record`.

    Fields the API does not provide (SIC descriptions, mortgage counts) are left as None so an
    update keeps the values already loaded from the bulk product.
    """
    number = (profile.get("company_number") or "").strip().upper()
    name = (profile.get("company_name") or "").strip()
    if not number or not name:
        return None

    addr = profile.get("registered_office_address") or {}
    postcode = normalize_postcode(addr.get("postal_code")) or addr.get("postal_code") or None
    line1 = " ".join(x for x in (addr.get("premises"), addr.get("address_line_1")) if x) or None
    line2 = addr.get("address_line_2")
    town = addr.get("locality")

    accounts = profile.get("accounts") or {}
    ref_date = accounts.get("accounting_reference_date") or {}
    last_accounts = accounts.get("last_accounts") or {}
    conf = profile.get("confirmation_statement") or {}
    sic_codes = profile.get("sic_codes") or []

    rec: dict[str, Any] = {
        "company_number": number[:8],
        "company_name": name[:500],
        "reg_address_care_of": addr.get("care_of"),
        "reg_address_po_box": addr.get("po_box"),
        "reg_address_line1": line1,
        "reg_address_line2": line2,
        "reg_address_post_town": town,
        "reg_address_county": addr.get("region"),
        "reg_address_country": addr.get("country"),
        "reg_address_postcode": postcode,
        "company_category": _CATEGORY.get(profile.get("type") or "", profile.get("type")),
        "company_status": map_company_status(profile.get("company_status"), profile.get("company_status_detail")),
        "dissolution_date": profile.get("date_of_cessation"),
        "incorporation_date": profile.get("date_of_creation"),
        "accounts_account_ref_day": _int(ref_date.get("day")),
        "accounts_account_ref_month": _int(ref_date.get("month")),
        "accounts_account_category": map_accounts_category(last_accounts.get("type")),
        "accounts_next_due_date": accounts.get("next_due"),
        "accounts_last_made_up_date": last_accounts.get("made_up_to"),
        "conf_stmt_next_due_date": conf.get("next_due"),
        "conf_stmt_last_made_up_date": conf.get("last_made_up_to"),
        "ch_uri": f"http://business.data.gov.uk/id/company/{number}",
        "address_fingerprint": compute_address_fingerprint(postcode, line1, line2, town),
        "name_fingerprint": normalize_name(name),
    }
    for idx, code in enumerate(sic_codes[:4], start=1):
        rec[f"sic_code_{idx}"] = code
    for idx, prev in enumerate((profile.get("previous_company_names") or [])[:10], start=1):
        rec[f"prev_name_{idx}"] = prev.get("name")
        rec[f"prev_name_{idx}_date"] = prev.get("ceased_on")
    return rec


def _int(val: Any) -> int | None:
    try:
        return int(val) if val not in (None, "") else None
    except (TypeError, ValueError):
        return None
