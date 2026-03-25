# Architecture — Aethelburg

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Desktop Application                      │
│                    PySide6 + QWebEngine                      │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────────┐  │
│  │ Search Panel│  │  Map Panel  │  │   Detail Panel     │  │
│  │  (Qt/HTML)  │  │ (Leaflet.js)│  │(cytoscape/Chart.js)│  │
│  └──────┬──────┘  └──────┬──────┘  └─────────┬──────────┘  │
│         └────────────────┼─────────────────────┘            │
│                    QWebChannel                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Service Layer (Python)                  │   │
│  │  ServiceRegistry · DBService · APIService · MLService│   │
│  │  GeoService · GraphService · ReportService           │   │
│  └──────────────────────┬──────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┼────────────────┐
          │               │                │
    ┌─────▼────┐   ┌──────▼─────┐  ┌──────▼──────┐
    │PostgreSQL│   │  RuVector  │  │  Nominatim  │
    │  :5432   │   │  (Docker)  │  │  (Docker)   │
    │+PostGIS  │   │   :8080    │  │   :7070     │
    │+pgvector │   │  (optional)│  │             │
    │+AGE      │   └────────────┘  └─────────────┘
    └──────────┘
```

---

## Application layer

### UI Layer (PySide6)
- **QMainWindow** with 3-panel layout (QSplitter): Search | Map | Detail
- **QWebEngineView** for rendering Leaflet.js and cytoscape.js
- **QWebChannel** for bidirectional Python ↔ JavaScript communication
- **QThreadPool** for async operations (DB queries, API calls, ML inference)
- **ServiceRegistry** singleton: checks service availability → publishes state via Qt Signal

### Service Layer
| Service | Responsibility | Offline fallback |
|---------|----------------|-----------------|
| `DBService` | PostgreSQL queries, SQLAlchemy ORM | — (required) |
| `GeoService` | Geocoding, PostGIS queries | ONSPD centroids (PostCode) |
| `GraphService` | Apache AGE Cypher, NetworkX | PostgreSQL recursive CTEs |
| `VectorService` | pgvector HNSW, embeddings | PostgreSQL FTS (tsvector) |
| `APIService` | CH API, OpenCorporates (cached) | Local cache only |
| `ReportService` | PDF generation, FtM/GEXF export | — |

### Intelligence Layer
- **RiskScorer**: computes a composite score 0–100 from deterministic flags
- **FT3Mapper**: maps each flag to an FT3 technique ID
- **EntityResolver**: cross-source deduplication via FtM `make_id()`
- **PatternDetector**: 8 SQL/ML patterns for shell company detection

---

## Database schema (overview)

```
entities            -- Core FtM table (Company, Person, Address...)
  ├── entity_events -- Versioning log for each update
  ├── risk_flags    -- Risk flags with ft3_technique_id
  └── annotations   -- Investigator notes

companies           -- CH fields extracted for fast querying
pscs                -- Relational PSCs extracted from JSONL
officers            -- Directors (populated from API on-demand)
sanctions_entries   -- UK Sanctions + OpenSanctions
icij_nodes          -- ICIJ Offshore Leaks entities
icij_relationships  -- ICIJ relationships (officer_of, registered_address, ...)

investigations      -- Saved investigation sessions
  └── inv_entities  -- Entities included in the investigation

api_cache           -- API call cache with TTL
postcode_centroids  -- ONSPD: UK PostCode centroids
```

---

## Data pipeline

```
External sources
    │
    ▼
[Import Scripts] ──── staging table
    │                      │
    │              COPY FROM STDIN
    │                      │
    ▼                      ▼
[Staging tables] → [INSERT ON CONFLICT UPDATE] → [Main tables]
    │
    ▼
[Entity Resolution] ─── FtM make_id() fingerprinting
    │
    ▼
[Risk Scoring] ────── SQL patterns + pgvector similarity
    │
    ▼
[Graph Building] ──── Apache AGE + NetworkX
    │
    ▼
[Geocoding] ──────── ONSPD centroids (batch) + Nominatim (on-demand)
```

---

## Detection patterns

| # | Pattern | Required data | Implementation | Phase |
|---|---------|---------------|----------------|-------|
| 1 | Shared Address | CH | SQL GROUP BY | 2 |
| 2 | Serial Director/PSC | PSC + Officers | SQL + AGE | 2/3 |
| 3 | PSC DOB Clustering | PSC | SQL window fn | 2 |
| 4 | SIC Incongruence | CH | SQL | 2 |
| 5 | Rapid Dissolution | CH | SQL date diff | 2 |
| 6 | Incorporation Clustering | CH | SQL window fn | 2 |
| 7 | Name Similarity | CH + embeddings | pgvector HNSW | 3 |
| 8 | Composite Anomaly | All | Weighted sum | 2/3 |

---

## Main dependencies

```
Python 3.12
├── PySide6              # UI framework (LGPL)
├── SQLAlchemy 2.0       # async ORM
├── Alembic              # DB migrations
├── Pydantic v2          # Settings & validation
├── psycopg2-binary      # PostgreSQL driver
├── httpx                # async HTTP client
├── ijson                # Streaming JSON parser
├── sentence-transformers # ML embeddings (Apache 2.0)
├── networkx             # Graph analysis
├── WeasyPrint           # PDF generation
├── Jinja2               # Template engine (reports)
├── APScheduler          # Background scheduling
├── python-keyring       # Secure credential storage
└── followthemoney       # FtM entity model (MIT)
```

---

## Architectural decisions

See [architectural_decisions.md](../memory/architectural_decisions.md) for the full list of ADRs (Architecture Decision Records) with rationale.

Key decisions:
- **ADR-001**: pgvector as default, RuVector optional (>10M vectors)
- **ADR-002**: pgvector binary quantization (HNSW: 30GB → 4GB)
- **ADR-003**: Sequential import required (FK dependencies)
- **ADR-007**: FtM on PostgreSQL via JSONB partial index
- **ADR-009**: ServiceRegistry singleton with Qt Signal
- **ADR-010**: Docker port binding on 127.0.0.1 (security)

---

## Advanced subsystems

### Name Normalization Engine

Responsible for normalising names in any script for cross-source entity resolution.

**Core library**: `fingerprints` (MIT) — a single normalisation point for CJK (Chinese/Japanese/Korean), Cyrillic (Russian/Ukrainian/etc.), Arabic, and European diacritics.

**Pipeline**:
1. `fingerprints.generate(name)` → lowercase ASCII canonical form
2. FtM `make_id()` → stable hash for cross-source deduplication
3. `jellyfish` Beider-Morse → phonetic key for residual phonetic homonymy (~5%)

**Storage**: `name_variants` table with index on `fingerprint` — O(log n) lookup instead of fuzzy scan.

### PEP Detection

Politically Exposed Persons (PEP) identified by cross-referencing directors/PSC with:
- OpenSanctions (including Wikidata PEP list, updated daily)
- EveryPolitician (historical mandate coverage from ~233 countries)

Match via fingerprint → FT3 risk flag for PEP connection.

### Geo-Intelligence

PostGIS + ONSPD (ONS Postcode Directory) for bulk geocoding (~95% coverage from day 1).
ST_ClusterDBSCAN for spatial clusters (eps=50m, 100m, 500m pre-computed).
Nominatim Docker only for on-demand precision (specific building).

### Link Analysis

Apache AGE (PostgreSQL graph extension) — 7 node types, 6 edge types.
NetworkX for centrality metrics on extracted subgraphs.
cytoscape.js (frontend) for interactive visualisation.

### Case Management & Reporting

Separate PostgreSQL schema `casework` (8 tables).
WeasyPrint for professional PDF output (fallback to QWebEngineView on Windows without GTK3).
Export formats: PDF, FtM JSON, XLSX, GEXF, GraphML, GeoJSON, KML.
