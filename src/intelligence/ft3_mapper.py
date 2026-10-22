"""FT3 ( Stripe Financial Threat Taxonomy ) Shell Company Mapper & UNODC 4x4 Grading Engine.

Implements ADR-016 and `docs/DESIGN_INTELLIGENCE.md`:
  - All 11 FT3 shell-company techniques (`FT3-SC-001` through `FT3-SC-020`)
  - Priority tiers (`CRITICAL`, `HIGH`, `MEDIUM`) and base risk score weights
  - Mandatory innocent explanations (ICD 203 Analytic Standard — Alternatives)
  - UNODC 4x4 Evaluation System (`A1`–`X4`) and Confidence Levels (`high`, `moderate`, `low`)
"""
from __future__ import annotations

from typing import Any

UNODC_SOURCE_RELIABILITY: dict[str, str] = {
    "A": "Always reliable — Official statutory registry or sovereign sanctions list (Companies House, UK FCDO/OFSI)",
    "B": "Mostly reliable — Self-reported statutory filings or verified investigative journalism consortium (CH PSC, ICIJ)",
    "C": "Sometimes reliable — Unverified third-party aggregator or fuzzy cross-dataset match without secondary ID",
    "X": "Untested — Newly ingested or uncorroborated manual intelligence",
}

UNODC_INFO_CREDIBILITY: dict[str, str] = {
    "1": "Confirmed — Corroborated by independent authoritative sources or exact statutory registration number",
    "2": "Probably true — Logical, consistent with known corporate filings, corroborated by exact name + DOB/postcode",
    "3": "Possibly true — Plausible phonetic/fuzzy match or indirect topological connection; requires analyst verification",
    "4": "Doubtful — Contradicted by other filings or anomalous date sequence",
}

CONFIDENCE_LEVELS: dict[str, str] = {
    "high": "High confidence — Based on high-quality official records (A1/B1) and corroborating multi-source evidence.",
    "moderate": "Moderate confidence — Credible sources and plausible indicators (B2/C2), but alternative innocent explanations remain possible.",
    "low": "Low confidence — Fragmentary or fuzzy-matched data (C3/X3); treat as an investigative lead rather than a confirmed finding.",
}

FT3_TECHNIQUES: dict[str, dict[str, Any]] = {
    # CRITICAL Priority
    "FT3-SC-007": {
        "code": "FT3-SC-007",
        "name": "Sanctioned Entity Connection",
        "tactic": "TA05 — Sanctions Evasion & Illicit Finance",
        "priority": "CRITICAL",
        "base_score": 45.0,
        "default_grade": "A1",
        "default_confidence": "high",
        "description": (
            "The UK company, its Person with Significant Control (PSC), or an active officer matches "
            "a designated subject on the UK FCDO / OFSI Sanctions List or OpenSanctions."
        ),
        "innocent_explanations": [
            "Homonymy on common corporate or personal names where no secondary identifier (CRN or DOB) was published on the sanctions notice.",
            "Historical pre-designation commercial relationship terminated prior to the statutory sanctions date.",
            "Company operating under a specific OFSI humanitarian or wind-down licence.",
        ],
    },
    "FT3-SC-017": {
        "code": "FT3-SC-017",
        "name": "Cross-Dataset Offshore Entity",
        "tactic": "TA03 — Obfuscation & Layering",
        "priority": "CRITICAL",
        "base_score": 38.0,
        "default_grade": "B2",
        "default_confidence": "high",
        "description": (
            "The UK company, its corporate PSC, or its beneficial owner matches an offshore entity or officer "
            "in the ICIJ Offshore Leaks Database (Panama Papers, Pandora Papers, Paradise Papers, Bahamas Leaks)."
        ),
        "innocent_explanations": [
            "Legitimate cross-border holding structure for international joint ventures, shipping, or intellectual property management.",
            "Regulated private equity or real estate investment fund domiciled in a Crown Dependency (Jersey, Guernsey, Isle of Man) with full tax transparency.",
        ],
    },
    "FT3-SC-004": {
        "code": "FT3-SC-004",
        "name": "Circular Ownership Structure",
        "tactic": "TA03 — Obfuscation & Layering",
        "priority": "CRITICAL",
        "base_score": 40.0,
        "default_grade": "A2",
        "default_confidence": "high",
        "description": (
            "Directed ownership cycle detected (Company A -> Company B -> ... -> Company A), obscuring "
            "the ultimate natural person beneficial owner."
        ),
        "innocent_explanations": [
            "Transitional corporate restructuring or demerger where historical PSC notifications have not yet been marked as ceased.",
            "Cross-shareholding between employee benefit trusts and operating subsidiaries.",
        ],
    },
    # HIGH Priority
    "FT3-SC-001": {
        "code": "FT3-SC-001",
        "name": "Mass Co-Registration Hub",
        "tactic": "TA09 — Identity & Registration Abuse",
        "priority": "HIGH",
        "base_score": 24.0,
        "default_grade": "A1",
        "default_confidence": "high",
        "description": (
            "Registered office address shares an identical ADR-015 address fingerprint with a high density "
            "of other companies (virtual office, Trust or Company Service Provider / formation agent)."
        ),
        "innocent_explanations": [
            "Legitimate use of a chartered accountancy firm, corporate secretarial provider, or virtual office by SMEs and startups to protect residential privacy.",
            "Multi-SPV real estate or renewable energy developer registering project subsidiaries at head office.",
        ],
    },
    "FT3-SC-002": {
        "code": "FT3-SC-002",
        "name": "Nominee / Hyper-Active Director",
        "tactic": "TA03 — Obfuscation & Layering",
        "priority": "HIGH",
        "base_score": 25.0,
        "default_grade": "B2",
        "default_confidence": "moderate",
        "description": (
            "Controlled or directed by an individual holding concurrent appointments across numerous distinct "
            "companies, indicative of professional nominee directorship services."
        ),
        "innocent_explanations": [
            "In-house general counsel or group finance director appointed across all operating subsidiaries of a single corporate conglomerate.",
            "Court-appointed insolvency practitioner or liquidator managing multiple wind-downs.",
        ],
    },
    "FT3-SC-003": {
        "code": "FT3-SC-003",
        "name": "Layered Corporate Ownership Chain",
        "tactic": "TA03 — Obfuscation & Layering",
        "priority": "HIGH",
        "base_score": 26.0,
        "default_grade": "B2",
        "default_confidence": "moderate",
        "description": (
            "Multi-hop corporate ownership chain (>= 2 corporate layers or foreign corporate PSC in an offshore/secrecy jurisdiction) "
            "separating the UK entity from natural person beneficial owners."
        ),
        "innocent_explanations": [
            "Standard acquisition financing stack (TopCo -> MidCo -> BidCo -> OpCo) required by institutional senior and mezzanine lenders.",
            "Multinational subsidiary reporting up to a listed foreign parent company.",
        ],
    },
    "FT3-SC-008": {
        "code": "FT3-SC-008",
        "name": "Politically Exposed Person (PEP) Link",
        "tactic": "TA07 — Corrupt Proceeds & Kleptocracy",
        "priority": "HIGH",
        "base_score": 30.0,
        "default_grade": "B2",
        "default_confidence": "moderate",
        "description": (
            "An active or former PSC or director is flagged as a Politically Exposed Person (PEP) or close associate."
        ),
        "innocent_explanations": [
            "Declared, lawful private shareholding or non-executive board role compliant with parliamentary register of interests.",
            "Domestic UK civic or municipal appointment with low corruption exposure.",
        ],
    },
    "FT3-SC-015": {
        "code": "FT3-SC-015",
        "name": "Phoenix Company Pattern",
        "tactic": "TA09 — Identity & Registration Abuse",
        "priority": "HIGH",
        "base_score": 28.0,
        "default_grade": "B2",
        "default_confidence": "moderate",
        "description": (
            "Controller or director is linked to multiple dissolved or liquidated companies sharing similar "
            "registered office addresses or SIC business sectors."
        ),
        "innocent_explanations": [
            "Serial entrepreneur or venture builder closing unsuccessful early-stage projects with no unpaid creditors.",
            "Planned wind-down of single-project construction or film production SPVs upon project completion.",
        ],
    },
    # MEDIUM Priority
    "FT3-SC-009": {
        "code": "FT3-SC-009",
        "name": "Rapid Director / PSC Turnover",
        "tactic": "TA03 — Obfuscation & Layering",
        "priority": "MEDIUM",
        "base_score": 16.0,
        "default_grade": "B2",
        "default_confidence": "moderate",
        "description": (
            "Multiple PSC or officer appointments and cessations within a short timeframe, or frequent corporate name changes (>= 2)."
        ),
        "innocent_explanations": [
            "Purchase of a pre-incorporated 'off-the-shelf' company from a formation agent followed by immediate transfer to the end client.",
            "Management buyout (MBO) or venture capital round resulting in board reconstitution and rebranding.",
        ],
    },
    "FT3-SC-014": {
        "code": "FT3-SC-014",
        "name": "Dormant / Overdue Filing Anomaly",
        "tactic": "TA09 — Identity & Registration Abuse",
        "priority": "MEDIUM",
        "base_score": 14.0,
        "default_grade": "A1",
        "default_confidence": "high",
        "description": (
            "Company exhibits dormant accounts combined with complex corporate/offshore PSC links, or active proposal to strike off / overdue accounts."
        ),
        "innocent_explanations": [
            "Name-protection dormant company maintained solely to safeguard a registered trademark.",
            "Pre-trading startup awaiting regulatory authorization or initial seed funding.",
        ],
    },
    "FT3-SC-020": {
        "code": "FT3-SC-020",
        "name": "Opaque / Unverified Beneficial Control",
        "tactic": "TA03 — Obfuscation & Layering",
        "priority": "MEDIUM",
        "base_score": 18.0,
        "default_grade": "A1",
        "default_confidence": "high",
        "description": (
            "Beneficial ownership is restricted under Section 790ZG (Super-Secure PSC), Overseas Entity exemption, "
            "or controlled exclusively by foreign legal persons without identified natural persons."
        ),
        "innocent_explanations": [
            "Statutory Section 790ZG protection granted by Companies House to individuals at serious risk of violence or intimidation (e.g. defence, animal testing, or judicial figures).",
        ],
    },
}


def get_technique_metadata(code: str) -> dict[str, Any]:
    """Return full FT3 technique metadata for a given code."""
    return FT3_TECHNIQUES.get(
        code,
        {
            "code": code,
            "name": code,
            "tactic": "TA03 — Obfuscation & Layering",
            "priority": "MEDIUM",
            "base_score": 15.0,
            "default_grade": "B2",
            "default_confidence": "moderate",
            "description": f"FT3 shell company indicator {code}.",
            "innocent_explanations": [
                "Standard commercial structure; requires contextual analyst review."
            ],
        },
    )


def list_all_techniques() -> list[dict[str, Any]]:
    """Return all FT3 techniques ordered by priority and score weight."""
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return sorted(
        FT3_TECHNIQUES.values(),
        key=lambda t: (priority_order.get(t["priority"], 9), -t["base_score"], t["code"]),
    )
