# Changelog — Aethelburg

Tutte le modifiche rilevanti al progetto vengono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
Il versionamento segue [Semantic Versioning](https://semver.org/lang/it/).

---

## [Non rilasciato] — Prossima release: v0.1.0

### Aggiunto
- Struttura progetto iniziale con documentazione completa
- README, FAQ, LEGAL, ARCHITECTURE, DATA_SOURCES, SETUP, DESIGN_INTELLIGENCE, ONTOLOGY
- Analisi architetturale completa (swarm di 5 agenti specializzati)
- Piano di implementazione in 6 fasi (Phase 0 → Phase 5)
- Architecture Decision Records (ADR-001 — ADR-018)
- Design sistema di geo-intelligence con ONSPD, PostGIS clustering, hotspot analysis
- Design sistema di link analysis con Apache AGE, cytoscape.js, pattern strutturali FT3
- Design sistema di reportistica con case management e export multi-formato
- Ontologia multi-layer v1.0.0: FtM entity model, AGE schema (7 nodi, 6 edge), FT3 taxonomy (11 pattern), casework (8 tabelle), data provenance
- Name normalization engine: `fingerprints` library per nomi multi-script (CJK, Cirillico, Arabo)
- Schema `name_variants` con fingerprint index per entity resolution O(log n)
- Fonte PEP: EveryPolitician supplementare a OpenSanctions (politici storici, 233 paesi)

### Decisioni architetturali (ADR)
- **ADR-001**: pgvector come default, RuVector opzionale oltre 10M vettori
- **ADR-002**: binary quantization pgvector (HNSW 30GB → 4GB con perdita recall <5%)
- **ADR-003**: Import sequenziale obbligatorio (Sanctions → ICIJ → Companies → PSC)
- **ADR-004**: COPY FROM STDIN per Companies House (no pandas, RAM <1GB vs >8GB)
- **ADR-005**: Staging table pattern per bulk load con rollback pulito
- **ADR-006**: UK Sanctions matching via nome (`business_registration_number` sempre vuoto)
- **ADR-007**: FtM su PostgreSQL via JSONB partial index (no EAV puro)
- **ADR-008**: GNN prematuro senza officers bulk e labeled data (rinviato a Phase 4+)
- **ADR-009**: ServiceRegistry singleton con Qt Signal per degradazione graceful
- **ADR-010**: Docker port binding esplicito su 127.0.0.1 (non 0.0.0.0)
- **ADR-011**: ONSPD come fonte primaria geocoding (95% copertura day 1 vs ~5% Nominatim)
- **ADR-012**: Case management in schema PostgreSQL separato `casework`
- **ADR-013**: PDF generation via WeasyPrint con fallback QWebEngineView Qt
- **ADR-014**: Export formati definitivi: PDF, FtM JSON, XLSX, GEXF, GraphML, GeoJSON, KML
- **ADR-015**: `address_fingerprint` column per shared address detection (no libpostal)
- **ADR-016**: Soglie FT3 per pattern detection (circular FT3-SC-005 e sanctions FT3-SC-015 = CRITICI)
- **ADR-017**: `fingerprints` library (MIT, OpenSanctions) come unico motore name normalization multi-script
- **ADR-018**: EveryPolitician come fonte PEP storica supplementare a OpenSanctions

---

## Formato versioni

### Versionamento software (MAJOR.MINOR.PATCH)

| Tipo | Quando |
|------|--------|
| **MAJOR** | Cambiamenti incompatibili con versioni precedenti (schema breaking, API break) |
| **MINOR** | Nuove funzionalità retrocompatibili |
| **PATCH** | Bugfix retrocompatibili |

### Versionamento ontologia (indipendente dal software)

L'ontologia versiona separatamente — vedi `docs/ONTOLOGY.md`.

| Tipo | Quando |
|------|--------|
| **MAJOR** | Rimozione nodo/edge AGE, cambio tipo proprietà FtM, rimozione pattern FT3 |
| **MINOR** | Nuovo nodo/edge, nuovo pattern FT3, nuova proprietà FtM |
| **PATCH** | Correzioni documentazione, aggiornamento soglie FT3 |

**Versione ontologia corrente**: `1.0.0`

### Versionamento schema database (Alembic)

Le migrazioni Alembic tracciano il versioning dello schema PostgreSQL indipendentemente.
Ogni migrazione ha un ID univoco e un messaggio descrittivo.

| Migration ID | Versione | Descrizione |
|-------------|----------|-------------|
| `0001` | _(da creare in Phase 0)_ | Schema completo iniziale |

### Versionamento dati

Le fonti dati vengono tracciate nella tabella `data_sources` (PostgreSQL) con:
- `source_version`: data snapshot o versione file
- `file_hash`: SHA-256 del file sorgente
- `collected_at`: timestamp di import

---

## Roadmap versioni pianificate

| Versione | Fase | Contenuto principale |
|----------|------|----------------------|
| `v0.1.0` | Phase 0 | Infrastruttura Docker, schema DB, configurazione base |
| `v0.2.0` | Phase 1 | ETL Companies House + PSC + OpenSanctions |
| `v0.3.0` | Phase 2 | Risk scoring, pattern detection FT3, shell company flags |
| `v0.4.0` | Phase 3 | UI PySide6: search, company detail, basic map |
| `v0.5.0` | Phase 4 | Geo-intelligence, link analysis, network graph |
| `v1.0.0` | Phase 5 | Case management, reporting, export completo, packaging |
