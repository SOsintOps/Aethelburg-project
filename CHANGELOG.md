# Changelog — Aethelburg

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased] — Next release: v0.1.0

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
