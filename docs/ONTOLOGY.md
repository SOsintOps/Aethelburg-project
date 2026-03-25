# Ontologia — Aethelburg
**Versione ontologia**: 1.0.0
**Data**: 2026-03-26
**Compatibile con**: FollowTheMoney schema 3.x, Apache AGE 1.5+

Questo documento descrive il modello dati concettuale (ontologia) di Aethelburg: le entità rappresentate, le relazioni tra di esse, la tassonomia dei rischi e lo schema di casework investigativo.

---

## Principi di design

- **FtM come base**: FollowTheMoney (OCCRP/OpenSanctions, MIT) definisce il vocabolario comune delle entità. Ogni entità in Aethelburg è mappabile a un FtM schema type.
- **Separazione dati/investigazione**: schema PostgreSQL `public` per dati sorgente (immutabili), schema `casework` per annotazioni investigative (mutabili).
- **Auditabilità**: ogni risk flag ha un FT3 technique ID documentato; ogni dato ha un `source_id` FK tracciabile.
- **Normalizzazione multi-script**: `fingerprints.generate()` produce rappresentazioni canoniche per nomi in qualunque scrittura (CJK, Cirillico, Arabo, Latino).

---

## Layer 1 — FollowTheMoney Entity Model

**Versione FtM schema**: 3.x
**Libreria Python**: `followthemoney>=3.5`
**Schema reference**: https://www.opensanctions.org/reference/

### Tipi di entità principali

| FtM Schema Type | Uso in Aethelburg | Tabella PostgreSQL principale |
|-----------------|-------------------|-------------------------------|
| `Company` | Aziende registrate UK (Companies House) | `companies` |
| `Person` | Persone fisiche (directors, PSC individuali, PEP) | `persons` |
| `LegalEntity` | PSC corporate, entità straniere, fondi, trusts | `legal_entities` |
| `Organization` | Enti legali senza personalità giuridica completa | `organizations` |
| `Address` | Indirizzi registrati (con geocoding) | `addresses` |
| `Ownership` | Partecipazioni azionarie PSC (persons → company) | `psc_ownerships` |
| `Directorship` | Incarichi direttoriali (persons → company) | `directorships` |
| `Sanction` | Entità sanzionate (OpenSanctions, OFSI) | `sanctions` |
| `Identification` | Documenti identificativi (passaporto, ecc.) | `identifications` |

### Proprietà FtM standard (selezione rilevante)

| Proprietà FtM | Tipo | Note |
|---------------|------|------|
| `name` | string | Nome principale — sempre presente |
| `alias` | string[] | Nomi alternativi, varianti ortografiche |
| `country` | country[] | ISO 3166-1 alpha-2 |
| `jurisdiction` | country | Giurisdizione legale |
| `incorporationDate` | date | Data costituzione |
| `dissolutionDate` | date | Data scioglimento (se applicabile) |
| `registrationNumber` | string | `company_number` per aziende UK |
| `leiCode` | string | Legal Entity Identifier (se disponibile) |
| `status` | string | Active / Dissolved / Liquidation / ... |
| `topics` | string[] | Tag semantici: `sanction`, `pep`, `shell`, `offshore` |

### Proprietà custom Aethelburg (estensioni FtM)

| Proprietà | Tipo | FtM non standard? | Note |
|-----------|------|-------------------|------|
| `addressFingerprint` | string | Sì | `postcode\|house_number\|keyword` per shared address detection |
| `riskScore` | float | Sì | Score composito 0–100 (calcolato, non importato) |
| `ft3Techniques` | string[] | Sì | Array FT3 technique IDs attivati |
| `dataSourceId` | uuid | Sì | FK su `data_sources` per provenance |

### Estensioni FtM: make_id e fingerprinting

```python
from followthemoney.util import make_id
from fingerprints import generate as fp

# ID canonico stabile per deduplication cross-source
entity_id = make_id("Company", "GB", "12345678")

# Fingerprint nome per matching multi-script
canonical = fp("江澤民")  # → "jiang zemin"
```

---

## Layer 2 — Grafo Apache AGE

Apache AGE estende PostgreSQL con un grafo property-graph (Cypher queries).
**Versione AGE**: 1.5+
**Grafo nome**: `aethelburg`

### Nodi (7 tipi)

#### `Company`
```
(c:Company {
    company_number: string,   -- chiave primaria CH, immutabile
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
    dob_month: int,           -- solo mese+anno per privacy (CH non fornisce giorno)
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
    company_number_foreign: string,  -- numero registrazione estero (se noto)
    is_offshore: boolean      -- jurisdiction in lista offshore
})
```

#### `Address`
```
(a:Address {
    fingerprint: string,      -- postcode|house_number|keyword (PRIMARY KEY logica)
    full_address: string,
    postcode: string,
    lat: float,               -- da ONSPD o Nominatim
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
    node_id: string,          -- ICIJ node_id (non stabile cross-release)
    name: string,
    fingerprint: string,
    source_id: string,        -- 'Panama Papers' | 'Pandora Papers' | ...
    valid_until: string       -- ICIJ release version per tracking stabilità
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

### Edge (6 tipi)

#### `CONTROLS`
Relazione PSC → azienda. Sia persone fisiche che corporate PSC.
```
(person|corporate_psc)-[:CONTROLS {
    nature_of_control: string[],  -- ownership-of-shares-25-to-50-percent, ecc.
    notified_on: date,
    ceased_on: date,              -- null se attivo
    is_ceased: boolean
}]->(company)
```

#### `SHARES_ADDRESS`
Due o più aziende registrate allo stesso indirizzo fisico.
```
(company1)-[:SHARES_ADDRESS {
    address_fingerprint: string,
    companies_at_address: int     -- conteggio totale aziende a quell'indirizzo
}]->(company2)
```

#### `OFFSHORE_LINK`
Link probabilistico tra entità CH e officer/entity ICIJ.
```
(person|company)-[:OFFSHORE_LINK {
    match_score: float,           -- 0.0–1.0
    match_method: string,         -- 'fingerprint_exact' | 'jaro_winkler' | 'phonetic'
    icij_source: string,          -- 'Panama Papers' | ...
    evidence: jsonb
}]->(icij_officer)
```

#### `SANCTIONED`
Link tra entità locale e record sanzionato.
```
(person|company)-[:SANCTIONED {
    list_name: string,            -- 'UK FCDO' | 'OFAC' | 'EU' | ...
    match_score: float,
    match_method: string,         -- 'fingerprint_exact' | 'fuzzy' | 'phonetic'
    confidence: string            -- 'confirmed' | 'probable' | 'possible'
}]->(sanctioned_entity)
```

#### `ICIJ_OFFICER_OF`
Ruolo di un officer ICIJ in un'entità offshore.
```
(icij_officer)-[:ICIJ_OFFICER_OF {
    role: string,                 -- 'director' | 'shareholder' | 'beneficiary' | ...
    start_date: date,
    end_date: date
}]->(jurisdiction_entity)
```

#### `SAME_PERSON_AS`
Deduplication: due nodi `Person` sono la stessa persona reale.
```
(person1)-[:SAME_PERSON_AS {
    confidence: float,            -- 0.0–1.0
    evidence: jsonb,              -- criteri che hanno generato il match
    verified_by: string           -- 'auto' | 'manual'
}]->(person2)
```

---

## Layer 3 — Risk Taxonomy (FT3 Framework)

**Framework**: Stripe FT3 (github.com/stripe/ft3)
**Uso**: ogni risk flag ha un FT3 technique ID documentato — il sistema è completamente auditabile.

### Pattern implementati

| FT3 ID | Nome | Priorità | Descrizione | Soglia attivazione |
|--------|------|----------|-------------|-------------------|
| `FT3-SC-001` | Star PSC | ALTA | Una persona controlla N aziende (hub di ownership) | N >= 5 aziende |
| `FT3-ML-003` | Ownership chain | MEDIA | Catena di ownership A→B→C→... (layering) | Profondità >= 3 |
| `FT3-SC-005` | Circular ownership | **CRITICA** | Loop di ownership A→B→C→A | Qualsiasi loop |
| `FT3-SC-008` | Island / No UBO | ALTA | Azienda senza Ultimate Beneficial Owner identificabile | UBO non trovato |
| `FT3-SC-009` | Bridge entity | MEDIA | Entità che connette due cluster altrimenti separati | Bridge centrality > soglia |
| `FT3-SC-012` | Shared address | MEDIA | N aziende allo stesso indirizzo fisico | N >= 10 |
| `FT3-ML-007` | Offshore PSC | ALTA | PSC in giurisdizione offshore | Lista jurisdiction offshore |
| `FT3-SC-015` | Sanctions match | **CRITICA** | Director o PSC presente in lista sanzioni | Score match >= 0.75 |
| `FT3-SC-016` | PEP connection | ALTA | Director o PSC è PEP (OpenSanctions + EveryPolitician) | Match confermato |
| `FT3-ML-009` | Rapid incorporation | MEDIA | Azienda costituita e sciolta in < 12 mesi | Durata < 365 giorni |
| `FT3-SC-020` | Dormant with assets | MEDIA | Azienda dormant con ipoteche attive | Dormant + mortgages > 0 |

### Storage risk flags

```sql
CREATE TABLE risk_flags (
    id              BIGSERIAL PRIMARY KEY,
    company_number  VARCHAR(8) NOT NULL REFERENCES companies(company_number),
    ft3_technique   VARCHAR(20) NOT NULL,   -- 'FT3-SC-001' ecc.
    score_contribution FLOAT NOT NULL,      -- contributo al risk_score composito
    priority        VARCHAR(10) NOT NULL,   -- 'CRITICAL' | 'HIGH' | 'MEDIUM'
    evidence        JSONB NOT NULL,         -- prova strutturata del pattern
    source_ids      UUID[] NOT NULL,        -- provenance: da quali sorgenti
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT true
);
```

---

## Layer 4 — Casework Schema

Schema PostgreSQL separato `casework`. Dati investigativi dell'utente, separati dai dati sorgente.

### Tabelle

| Tabella | Scopo |
|---------|-------|
| `investigations` | Fascicoli investigativi |
| `investigation_entities` | Entità incluse in un fascicolo |
| `annotations` | Note testuali su entità o relazioni |
| `manual_links` | Connessioni aggiunte manualmente dall'investigatore |
| `visual_snapshots` | Snapshot PNG del grafo cytoscape |
| `saved_queries` | Query salvate per riuso |
| `investigation_events` | Log di tutte le azioni (audit trail) |
| `generated_reports` | Report PDF/JSON generati |

### Investigation lifecycle

```
OPEN → IN_PROGRESS → PENDING_REVIEW → CLOSED
                   ↘ ARCHIVED
```

---

## Layer 5 — Data Provenance

Ogni dato in Aethelburg ha una provenienza tracciabile.

```sql
-- Ogni tabella dati ha questa FK
source_id UUID REFERENCES data_sources(id)

-- data_sources
CREATE TABLE data_sources (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name  VARCHAR(100) NOT NULL,   -- 'companies_house_bulk' | 'opensanctions' | ...
    source_type  VARCHAR(50) NOT NULL,    -- 'bulk_download' | 'api' | 'manual' | 'streaming'
    source_version VARCHAR(50),          -- data snapshot, versione file
    source_url   TEXT,
    collected_at TIMESTAMPTZ NOT NULL,
    file_hash    VARCHAR(64)             -- SHA-256 del file sorgente
);
```

---

## Versioning dell'ontologia

| Versione | Data | Cambiamenti |
|----------|------|-------------|
| `1.0.0` | 2026-03-26 | Versione iniziale: FtM layer, AGE schema (7 nodi, 6 edge), FT3 patterns (11), casework (8 tabelle), provenance |

### Politica di versioning

- **MAJOR**: cambiamenti breaking (rimozione nodo/edge, cambio tipo proprietà, rimozione FT3 pattern)
- **MINOR**: aggiunte non breaking (nuovo nodo, nuovo edge, nuovo FT3 pattern, nuova proprietà)
- **PATCH**: correzioni (fix typo, aggiornamento soglie FT3, documentazione)

L'ontologia versiona **indipendentemente** dal software (versione applicazione) e dalle migrazioni schema (versione Alembic).

### Compatibilità cross-layer

| Componente | Versione | Note |
|-----------|----------|------|
| FtM schema | 3.x | Compatibile con OpenSanctions export |
| Apache AGE | 1.5+ | Cypher query subset |
| Alembic migration | 0001 | Prima migrazione — schema completo |
| FT3 framework | commit attuale | github.com/stripe/ft3 |
| fingerprints | >=0.5 | Name normalization |
| followthemoney | >=3.5 | Entity model + make_id |

---

## Glossario

| Termine | Definizione |
|---------|-------------|
| **PSC** | Person with Significant Control — entità che controlla >=25% di un'azienda |
| **UBO** | Ultimate Beneficial Owner — la persona fisica al vertice della catena di controllo |
| **PEP** | Politically Exposed Person — politico o funzionario pubblico ad alto rischio AML |
| **FtM** | FollowTheMoney — modello entità OCCRP (MIT license) |
| **FT3** | Fraud Threat Taxonomy — framework Stripe per classificare tecniche fraudolente |
| **AGE** | Apache Graph Extension — estensione PostgreSQL per grafi property-graph |
| **ONSPD** | ONS Postcode Directory — centroidi geografici postcodes UK |
| **OFSI** | Office of Financial Sanctions Implementation — UK sanctions authority |
| **address fingerprint** | Stringa `postcode\|house_number\|keyword` per identificare indirizzo fisico senza libpostal |
| **offshore jurisdiction** | Giurisdizione con bassa trasparenza societaria (BVI, Cayman, Panama, ecc.) |
