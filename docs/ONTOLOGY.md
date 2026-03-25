# Ontology — Aethelburg
**Ontology version**: 1.0.0
**Date**: 2026-03-26
**Compatible with**: FollowTheMoney schema 3.x, Apache AGE 1.5+

This document describes the conceptual data model (ontology) of Aethelburg: the entities represented, the relationships between them, the risk taxonomy, and the investigative casework schema.

---

## Design Principles

- **FtM as foundation**: FollowTheMoney (OCCRP/OpenSanctions, MIT) defines the common entity vocabulary. Every entity in Aethelburg can be mapped to an FtM schema type.
- **Data/investigation separation**: PostgreSQL schema `public` for source data (immutable), schema `casework` for investigative annotations (mutable).
- **Auditability**: every risk flag has a documented FT3 technique ID; every piece of data has a traceable `source_id` FK.
- **Multi-script normalisation**: `fingerprints.generate()` produces canonical representations for names in any script (CJK, Cyrillic, Arabic, Latin).

---

## Layer 1 — FollowTheMoney Entity Model

**FtM schema version**: 3.x
**Python library**: `followthemoney>=3.5`
**Schema reference**: https://www.opensanctions.org/reference/

### Main entity types

| FtM Schema Type | Use in Aethelburg | Main PostgreSQL table |
|-----------------|-------------------|-----------------------|
| `Company` | UK registered companies (Companies House) | `companies` |
| `Person` | Natural persons (directors, individual PSCs, PEPs) | `persons` |
| `LegalEntity` | Corporate PSCs, foreign entities, funds, trusts | `legal_entities` |
| `Organization` | Legal bodies without full legal personality | `organizations` |
| `Address` | Registered addresses (with geocoding) | `addresses` |
| `Ownership` | PSC shareholdings (persons → company) | `psc_ownerships` |
| `Directorship` | Directorial appointments (persons → company) | `directorships` |
| `Sanction` | Sanctioned entities (OpenSanctions, OFSI) | `sanctions` |
| `Identification` | Identity documents (passport, etc.) | `identifications` |

### Standard FtM properties (relevant selection)

| FtM Property | Type | Notes |
|--------------|------|-------|
| `name` | string | Primary name — always present |
| `alias` | string[] | Alternative names, spelling variants |
| `country` | country[] | ISO 3166-1 alpha-2 |
| `jurisdiction` | country | Legal jurisdiction |
| `incorporationDate` | date | Incorporation date |
| `dissolutionDate` | date | Dissolution date (if applicable) |
| `registrationNumber` | string | `company_number` for UK companies |
| `leiCode` | string | Legal Entity Identifier (if available) |
| `status` | string | Active / Dissolved / Liquidation / ... |
| `topics` | string[] | Semantic tags: `sanction`, `pep`, `shell`, `offshore` |

### Aethelburg custom properties (FtM extensions)

| Property | Type | Non-standard FtM? | Notes |
|----------|------|-------------------|-------|
| `addressFingerprint` | string | Yes | `postcode\|house_number\|keyword` for shared address detection |
| `riskScore` | float | Yes | Composite score 0–100 (calculated, not imported) |
| `ft3Techniques` | string[] | Yes | Array of activated FT3 technique IDs |
| `dataSourceId` | uuid | Yes | FK on `data_sources` for provenance |

### FtM extensions: make_id and fingerprinting

```python
from followthemoney.util import make_id
from fingerprints import generate as fp

# Stable canonical ID for cross-source deduplication
entity_id = make_id("Company", "GB", "12345678")

# Name fingerprint for multi-script matching
canonical = fp("江澤民")  # → "jiang zemin"
```

---

## Layer 2 — Apache AGE Graph

Apache AGE extends PostgreSQL with a property-graph (Cypher queries).
**AGE version**: 1.5+
**Graph name**: `aethelburg`

### Nodes (7 types)

#### `Company`
```
(c:Company {
    company_number: string,   -- CH primary key, immutable
    name: string,
    fingerprint: string,      -- fingerprints.generate(name)
    status: string,           -- Active | Dissolved | Liquidation | ...
    incorporation_date: date,
    dissolution_date: date,
    company_type: string,
    sic_codes: string[],
    postcode: string,
    address_fingerprint: string,
    risk_score: float,
    ft3_techniques: string[]
})
```

#### `Person`
```
(p:Person {
    id: uuid,
    name: string,
    fingerprint: string,      -- fingerprints.generate(name)
    nationality: string,      -- ISO 3166-1 alpha-2
    country_of_residence: string,
    dob_month: int,           -- month+year only for privacy (CH does not provide day)
    dob_year: int,
    is_pep: boolean,          -- Politically Exposed Person
    pep_source: string        -- 'opensanctions' | 'everypolitician' | null
})
```

#### `CorporatePSC`
```
(cp:CorporatePSC {
    id: uuid,
    name: string,
    fingerprint: string,
    jurisdiction: string,     -- ISO country code
    company_number_foreign: string,  -- foreign registration number (if known)
    is_offshore: boolean      -- jurisdiction on offshore list
})
```

#### `Address`
```
(a:Address {
    fingerprint: string,      -- postcode|house_number|keyword (logical PRIMARY KEY)
    full_address: string,
    postcode: string,
    lat: float,               -- from ONSPD or Nominatim
    lon: float,
    geocoding_source: string  -- 'onspd' | 'nominatim' | 'manual'
})
```

#### `JurisdictionEntity`
```
(je:JurisdictionEntity {
    id: uuid,
    name: string,
    fingerprint: string,
    jurisdiction: string,
    entity_type: string       -- 'trust' | 'foundation' | 'nominee' | ...
})
```

#### `IcijOfficer`
```
(io:IcijOfficer {
    node_id: string,          -- ICIJ node_id (not stable across releases)
    name: string,
    fingerprint: string,
    source_id: string,        -- 'Panama Papers' | 'Pandora Papers' | ...
    valid_until: string       -- ICIJ release version for stability tracking
})
```

#### `SanctionedEntity`
```
(se:SanctionedEntity {
    id: uuid,
    name: string,
    fingerprint: string,
    source: string,           -- 'opensanctions' | 'ofsi'
    list_date: date,
    topics: string[]          -- 'sanction' | 'pep' | 'debarment' | ...
})
```

### Edges (6 types)

#### `CONTROLS`
PSC → company relationship. Both natural persons and corporate PSCs.
```
(person|corporate_psc)-[:CONTROLS {
    nature_of_control: string[],  -- ownership-of-shares-25-to-50-percent, etc.
    notified_on: date,
    ceased_on: date,              -- null if active
    is_ceased: boolean
}]->(company)
```

#### `SHARES_ADDRESS`
Two or more companies registered at the same physical address.
```
(company1)-[:SHARES_ADDRESS {
    address_fingerprint: string,
    companies_at_address: int     -- total count of companies at that address
}]->(company2)
```

#### `OFFSHORE_LINK`
Probabilistic link between a CH entity and an ICIJ officer/entity.
```
(person|company)-[:OFFSHORE_LINK {
    match_score: float,           -- 0.0–1.0
    match_method: string,         -- 'fingerprint_exact' | 'jaro_winkler' | 'phonetic'
    icij_source: string,          -- 'Panama Papers' | ...
    evidence: jsonb
}]->(icij_officer)
```

#### `SANCTIONED`
Link between a local entity and a sanctioned record.
```
(person|company)-[:SANCTIONED {
    list_name: string,            -- 'UK FCDO' | 'OFAC' | 'EU' | ...
    match_score: float,
    match_method: string,         -- 'fingerprint_exact' | 'fuzzy' | 'phonetic'
    confidence: string            -- 'confirmed' | 'probable' | 'possible'
}]->(sanctioned_entity)
```

#### `ICIJ_OFFICER_OF`
Role of an ICIJ officer in an offshore entity.
```
(icij_officer)-[:ICIJ_OFFICER_OF {
    role: string,                 -- 'director' | 'shareholder' | 'beneficiary' | ...
    start_date: date,
    end_date: date
}]->(jurisdiction_entity)
```

#### `SAME_PERSON_AS`
Deduplication: two `Person` nodes are the same real individual.
```
(person1)-[:SAME_PERSON_AS {
    confidence: float,            -- 0.0–1.0
    evidence: jsonb,              -- criteria that generated the match
    verified_by: string           -- 'auto' | 'manual'
}]->(person2)
```

---

## Layer 3 — Risk Taxonomy (FT3 Framework)

**Framework**: Stripe FT3 (github.com/stripe/ft3)
**Usage**: every risk flag has a documented FT3 technique ID — the system is fully auditable.

### Implemented patterns

| FT3 ID | Name | Priority | Description | Activation threshold |
|--------|------|----------|-------------|----------------------|
| `FT3-SC-001` | Star PSC | HIGH | One person controls N companies (ownership hub) | N >= 5 companies |
| `FT3-ML-003` | Ownership chain | MEDIUM | Ownership chain A→B→C→... (layering) | Depth >= 3 |
| `FT3-SC-005` | Circular ownership | **CRITICAL** | Ownership loop A→B→C→A | Any loop |
| `FT3-SC-008` | Island / No UBO | HIGH | Company with no identifiable Ultimate Beneficial Owner | UBO not found |
| `FT3-SC-009` | Bridge entity | MEDIUM | Entity connecting two otherwise separate clusters | Bridge centrality > threshold |
| `FT3-SC-012` | Shared address | MEDIUM | N companies at the same physical address | N >= 10 |
| `FT3-ML-007` | Offshore PSC | HIGH | PSC in an offshore jurisdiction | Offshore jurisdiction list |
| `FT3-SC-015` | Sanctions match | **CRITICAL** | Director or PSC present on a sanctions list | Match score >= 0.75 |
| `FT3-SC-016` | PEP connection | HIGH | Director or PSC is a PEP (OpenSanctions + EveryPolitician) | Confirmed match |
| `FT3-ML-009` | Rapid incorporation | MEDIUM | Company incorporated and dissolved in < 12 months | Duration < 365 days |
| `FT3-SC-020` | Dormant with assets | MEDIUM | Dormant company with active mortgages | Dormant + mortgages > 0 |

### Risk flags storage

```sql
CREATE TABLE risk_flags (
    id              BIGSERIAL PRIMARY KEY,
    company_number  VARCHAR(8) NOT NULL REFERENCES companies(company_number),
    ft3_technique   VARCHAR(20) NOT NULL,   -- 'FT3-SC-001' etc.
    score_contribution FLOAT NOT NULL,      -- contribution to the composite risk_score
    priority        VARCHAR(10) NOT NULL,   -- 'CRITICAL' | 'HIGH' | 'MEDIUM'
    evidence        JSONB NOT NULL,         -- structured evidence of the pattern
    source_ids      UUID[] NOT NULL,        -- provenance: from which sources
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT true
);
```

---

## Layer 4 — Casework Schema

Separate PostgreSQL schema `casework`. User investigative data, separated from source data.

### Tables

| Table | Purpose |
|-------|---------|
| `investigations` | Investigative case files |
| `investigation_entities` | Entities included in a case file |
| `annotations` | Text notes on entities or relationships |
| `manual_links` | Connections added manually by the investigator |
| `visual_snapshots` | PNG snapshots of the Cytoscape graph |
| `saved_queries` | Saved queries for reuse |
| `investigation_events` | Log of all actions (audit trail) |
| `generated_reports` | Generated PDF/JSON reports |

### Investigation lifecycle

```
OPEN → IN_PROGRESS → PENDING_REVIEW → CLOSED
                   ↘ ARCHIVED
```

---

## Layer 5 — Data Provenance

Every piece of data in Aethelburg has traceable provenance.

```sql
-- Every data table has this FK
source_id UUID REFERENCES data_sources(id)

-- data_sources
CREATE TABLE data_sources (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name  VARCHAR(100) NOT NULL,   -- 'companies_house_bulk' | 'opensanctions' | ...
    source_type  VARCHAR(50) NOT NULL,    -- 'bulk_download' | 'api' | 'manual' | 'streaming'
    source_version VARCHAR(50),          -- data snapshot, file version
    source_url   TEXT,
    collected_at TIMESTAMPTZ NOT NULL,
    file_hash    VARCHAR(64)             -- SHA-256 of the source file
);
```

---

## Ontology Versioning

| Version | Date | Changes |
|---------|------|---------|
| `1.0.0` | 2026-03-26 | Initial version: FtM layer, AGE schema (7 nodes, 6 edges), FT3 patterns (11), casework (8 tables), provenance |

### Versioning policy

- **MAJOR**: breaking changes (removal of node/edge, property type change, removal of FT3 pattern)
- **MINOR**: non-breaking additions (new node, new edge, new FT3 pattern, new property)
- **PATCH**: corrections (typo fix, FT3 threshold update, documentation)

The ontology versions **independently** from the software (application version) and from schema migrations (Alembic version).

### Cross-layer compatibility

| Component | Version | Notes |
|-----------|---------|-------|
| FtM schema | 3.x | Compatible with OpenSanctions export |
| Apache AGE | 1.5+ | Cypher query subset |
| Alembic migration | 0001 | First migration — full schema |
| FT3 framework | current commit | github.com/stripe/ft3 |
| fingerprints | >=0.5 | Name normalisation |
| followthemoney | >=3.5 | Entity model + make_id |

---

## Glossary

| Term | Definition |
|------|------------|
| **PSC** | Person with Significant Control — entity that controls >=25% of a company |
| **UBO** | Ultimate Beneficial Owner — the natural person at the top of the control chain |
| **PEP** | Politically Exposed Person — politician or senior public official at high AML risk |
| **FtM** | FollowTheMoney — OCCRP entity model (MIT licence) |
| **FT3** | Fraud Threat Taxonomy — Stripe framework for classifying fraudulent techniques |
| **AGE** | Apache Graph Extension — PostgreSQL extension for property-graph |
| **ONSPD** | ONS Postcode Directory — geographic centroids for UK postcodes |
| **OFSI** | Office of Financial Sanctions Implementation — UK sanctions authority |
| **address fingerprint** | String `postcode\|house_number\|keyword` to identify a physical address without libpostal |
| **offshore jurisdiction** | Jurisdiction with low corporate transparency (BVI, Cayman, Panama, etc.) |
