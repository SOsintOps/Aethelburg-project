# Changelog — Aethelburg

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- `python -m src.main import-onspd PATH` imports exact postcode centroids from an ONS Postcode Directory CSV.
- Map markers carry a `location_precision` (`postcode`, `district`, `area`); approximate positions are drawn as dashed rings with an explanation in the popup and in the legend.

### Fixed
- **Wrong cities on the map**: the postcode-area fallback kept every letter of the outward code, so `W1A`, `W1N` and `W1R` (London) were placed in Warrington, Wigan and Worcester; `SE10` was truncated to `SE1`. The area is now the leading letters only, and only a trailing sub-district letter is dropped (`EC1V` → `EC1`).
- **Invented positions**: the built-in fallback no longer adds a random offset around the area centre; existing approximate centroids are cleared on first start and re-resolved with their precision.
- **ONSPD overwritten**: syncing company postcodes replaced exact ONSPD centroids with approximate ones; approximate rows now never overwrite a `postcode`-precision row.
- **Broken FollowTheMoney links**: ownerships and directorships referenced companies and people with ids built from lower-case schema names (`company`, `person`), while the entities themselves were stored under `Company`/`Person` ids, so 99.7% of the links in an export pointed at nothing. Ids are now consistent; a fresh bootstrap leaves only links to ICIJ nodes outside the import limits unresolved. Re-run `bootstrap` (or re-import) to rebuild existing databases.
- **Duplicated PSC controllers**: the lookup of an existing person or legal entity used a different id from the one stored, so every PSC statement created a new controller. Controllers are now reused.
- **Re-imports wiped analysis results**: companies were written with `INSERT OR REPLACE`, which deletes the row, so updating a company lost its risk score, FT3 techniques, flag and officer-fetch date. Companies are now upserted on registry fields only, and the per-address company count no longer grows on every re-import.
- **Map tiles blocked**: the UI sent no `Referer` (`<meta name="referrer" content="no-referrer">`), so OpenStreetMap served its "Access blocked" tile for every request. The page now uses `strict-origin-when-cross-origin` and the Leaflet tile layer sets the same `referrerPolicy`.

---

## [0.2.0-beta.1] — 2026-10-22

### Added
- **FollowTheMoney (`FtM v3.x`) Full Database & Ontology Compatibility**:
  - Added canonical `ftm_entities` table (JSONB + GIN indexes on PostgreSQL; JSON + indexed columns on SQLite) and `addresses` (`Address`) table, plus `ftm_id` and `ftm_schema` columns across all domain tables (`companies`, `persons`, `legal_entities`, `psc_ownerships`, `directorships`, `sanctions`, `pep_persons`, `icij_*`).
  - Added [`src/core/ftm.py`](src/core/ftm.py) and official [`src/core/ftm_schema.json`](src/core/ftm_schema.json) (synchronized with sibling project `Quaesitor`) supporting full validation, inheritance resolution (`Thing` → `LegalEntity` → `Organization` → `Company`, `Interval` → `Ownership` / `Directorship` / `Representation` / `Sanction`), and `.ftm.json` JSONL import/export.
- **Complete ETL Pipeline (`src/etl/`) for Real Datasets in `dati/`**:
  - `import_sanctions.py`: right-anchored parser for `UK-Sanctions-List.txt` handling unquoted semicolons in `Statement of Reasons` (`len(row) > 58`), consolidating records by `Unique ID` and extracting UK company registration numbers (`row[-11]`).
  - `import_icij.py`: imports all 6 ICIJ Offshore Leaks CSVs (`nodes-entities`, `nodes-officers`, `nodes-intermediaries`, `nodes-addresses`, `nodes-others`, `relationships`).
  - `import_companies.py`: streams `BasicCompanyDataAsOneFile` CSV (stripping leading spaces from headers), extracts SIC codes, and computes ADR-015 address fingerprints.
  - `import_psc.py`: handles all 6 PSC `kind` types (including `super-secure-person-with-significant-control` and Overseas Entities `OE...`) and auto-creates historical/dissolved company stubs to preserve phoenix company networks (`FT3-SC-015`).
  - `bootstrap_beta.py`: fast Beta bootstrap populating `dati/aethelburg.sqlite` with 19,200+ canonical FtM entities from `dati/`.
- **FT3 Intelligence Engine (`src/intelligence/`), Graph (`src/graph/`) & 10-Section Reports (`src/reports/`)**:
  - Implemented all 11 FT3 shell-company techniques (`FT3-SC-001` through `FT3-SC-020`) with UNODC 4×4 source/information grades (`A1`–`X4`), ICD 203 confidence levels (`high`, `moderate`, `low`), and mandatory innocent explanations.
  - Implemented multi-hop NetworkX + Cytoscape graph analysis, cycle detection, and 8 export formats (`.ftm.json`, `.xlsx`, `.csv`, `.gexf`, `.graphml`, `.dot`, `.geojson`, `.kml`) plus 10-section HTML/PDF intelligence dossiers with BLUF and SHA-256 verification.
- **Interactive 3-Panel Web & Desktop UI (`src/ui/`) & Graphic Assets (`assets/`)**:
  - Generated vector [`assets/logo.svg`](assets/logo.svg), high-resolution `1024x1024` RGBA [`assets/logo.png`](assets/logo.png), [`assets/logo-dark.png`](assets/logo-dark.png), Windows multi-size [`assets/icon.ico`](assets/icon.ico), and bundled local `Inter` (`woff2`) web fonts.
  - Built 3-panel UI (Search & FT3 Filters | Network Graph, UK Coordinate Map & Hubs, Timeline & FT3 Matrix, FtM Ontology Inspector, Casework | Entity Dossier) with Light/Dark mode and `start.ps1` / `src/main.py` CLI.

---

## [0.1.1] — 2026-10-13

### Documentation
- **Changed:** intelligence vocabulary aligned with the [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes): confidence is `high`, `moderate` or `low`; "confirmed" applies only to links graded A1, A2, B1 or B2 (UNODC 4 x 4), not as a confidence level. `DESIGN_INTELLIGENCE.md` (manual links) and `ONTOLOGY.md` (`SANCTIONED` edge, which no longer uses "probable"/"possible") updated, with a note on how the implemented `FLOAT` confidence of `casework.manual_links` maps to the three levels.
- **Changed:** report section 2 is the **Bottom line**, not an executive summary, as in `REPORT_WRITING.md`; ICD 203 and the UNODC manual linked at first mention.
- **Fixed:** licences verified at source: OpenSanctions is CC BY-NC 4.0 (not CC BY-NC-SA); the ICIJ Offshore Leaks database is under the Open Database License with contents under CC BY-SA 3.0 (not CC BY-NC). `DATA_SOURCES.md`, `LEGAL.md`, README and FAQ corrected.
- **Fixed:** the OFSI Consolidated List closed on 28 January 2026; the FCDO UK Sanctions List is the only UK source. `DATA_SOURCES.md`, `SETUP.md` and FAQ updated.
- **Docs:** FAQ restructured with a table of contents; related projects now include Codex Machinae, Acta Diurna, Il Conclave and Claudii Exploratores.

---

## [0.1.0] — Phase 0 baseline

### Added
- Initial project structure with complete documentation
- README, FAQ, LEGAL, ARCHITECTURE, DATA_SOURCES, SETUP, DESIGN_INTELLIGENCE, ONTOLOGY
- Complete architectural analysis (swarm of 5 specialised agents)
- 6-phase implementation plan (Phase 0 → Phase 5)
- Architecture Decision Records (ADR-001 — ADR-018)
- Geo-intelligence system design with ONSPD, PostGIS clustering, hotspot analysis
- Link analysis system design with Apache AGE, cytoscape.js, FT3 structural patterns
- Reporting system design with case management and multi-format export
- Multi-layer ontology v1.0.0: FtM entity model, AGE schema (7 nodes, 6 edges), FT3 taxonomy (11 patterns), casework (8 tables), data provenance
- Name normalisation engine: `fingerprints` library for multi-script names (CJK, Cyrillic, Arabic)
- `name_variants` schema with fingerprint index for O(log n) entity resolution
- PEP source: EveryPolitician supplementary to OpenSanctions (historical politicians, 233 countries)

### Documentation (2026-10-13)
- `docs/REPORT_WRITING.md`: how to write the investigation report: the risk score is an anomaly indicator and not a judgement, how to grade the register, PSC, sanctions, ICIJ and name-match sources (UNODC 4 x 4), the ten report sections with the bottom line first, personal data. It applies the [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes), the method shared by the SOsintOps tools.
- FAQ: risk score versus judgement, how to write up an investigation, related SOsintOps projects; README: documentation index and related projects.
- Fixed: the FAQ gave the old ICIJ import script (`scripts/import_icij.py`); it is `python -m src.etl.import_icij`. FT3 is Stripe's *Fraud Tools, Tactics, and Techniques* framework, now linked.

### Architectural decisions (ADR)
- **ADR-001**: pgvector as default, RuVector optional beyond 10M vectors
- **ADR-002**: pgvector binary quantization (HNSW 30GB → 4GB with <5% recall loss)
- **ADR-003**: Mandatory sequential import (Sanctions → ICIJ → Companies → PSC)
- **ADR-004**: COPY FROM STDIN for Companies House (no pandas, RAM <1GB vs >8GB)
- **ADR-005**: Staging table pattern for bulk load with clean rollback
- **ADR-006**: UK Sanctions matching by name (`business_registration_number` always empty)
- **ADR-007**: FtM on PostgreSQL via JSONB partial index (no pure EAV)
- **ADR-008**: GNN premature without bulk officers and labelled data (deferred to Phase 4+)
- **ADR-009**: ServiceRegistry singleton with Qt Signal for graceful degradation
- **ADR-010**: Docker port binding explicitly on 127.0.0.1 (not 0.0.0.0)
- **ADR-011**: ONSPD as primary geocoding source (95% day-1 coverage vs ~5% Nominatim)
- **ADR-012**: Case management in separate PostgreSQL schema `casework`
- **ADR-013**: PDF generation via WeasyPrint with QWebEngineView Qt fallback
- **ADR-014**: Definitive export formats: PDF, FtM JSON, XLSX, GEXF, GraphML, GeoJSON, KML
- **ADR-015**: `address_fingerprint` column for shared address detection (no libpostal)
- **ADR-016**: FT3 thresholds for pattern detection (circular FT3-SC-005 and sanctions FT3-SC-015 = CRITICAL)
- **ADR-017**: `fingerprints` library (MIT, OpenSanctions) as the sole multi-script name normalisation engine
- **ADR-018**: EveryPolitician as supplementary historical PEP source alongside OpenSanctions

---

## Version format

### Software versioning (MAJOR.MINOR.PATCH)

| Type | When |
|------|------|
| **MAJOR** | Backwards-incompatible changes (breaking schema, API break) |
| **MINOR** | New backwards-compatible features |
| **PATCH** | Backwards-compatible bug fixes |

### Ontology versioning (independent from software)

The ontology versions separately — see `docs/ONTOLOGY.md`.

| Type | When |
|------|------|
| **MAJOR** | Removal of AGE node/edge, change of FtM property type, removal of FT3 pattern |
| **MINOR** | New node/edge, new FT3 pattern, new FtM property |
| **PATCH** | Documentation corrections, FT3 threshold updates |

**Current ontology version**: `1.0.0`

### Database schema versioning (Alembic)

Alembic migrations track PostgreSQL schema versioning independently.
Each migration has a unique ID and a descriptive message.

| Migration ID | Version | Description |
|-------------|---------|-------------|
| `0001` | _(to be created in Phase 0)_ | Full initial schema |

### Data versioning

Data sources are tracked in the `data_sources` table (PostgreSQL) with:
- `source_version`: snapshot date or file version
- `file_hash`: SHA-256 of the source file
- `collected_at`: import timestamp

---

## Planned version roadmap

| Version | Phase | Main contents |
|---------|-------|---------------|
| `v0.1.0` | Phase 0 | Docker infrastructure, DB schema, base configuration |
| `v0.2.0` | Phase 1 | ETL Companies House + PSC + OpenSanctions |
| `v0.3.0` | Phase 2 | Risk scoring, FT3 pattern detection, shell company flags |
| `v0.4.0` | Phase 3 | PySide6 UI: search, company detail, basic map |
| `v0.5.0` | Phase 4 | Geo-intelligence, link analysis, network graph |
| `v1.0.0` | Phase 5 | Case management, reporting, full export, packaging |
