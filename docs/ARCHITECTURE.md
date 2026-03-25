# Architettura — Aethelburg

## Visione d'insieme

```
┌─────────────────────────────────────────────────────────────┐
│                     Applicazione Desktop                     │
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
    │+pgvector │   │  (opzion.) │  │             │
    │+AGE      │   └────────────┘  └─────────────┘
    └──────────┘
```

---

## Layer applicativo

### UI Layer (PySide6)
- **QMainWindow** con layout 3 pannelli (QSplitter): Search | Map | Detail
- **QWebEngineView** per rendering Leaflet.js e cytoscape.js
- **QWebChannel** per comunicazione bidirezionale Python ↔ JavaScript
- **QThreadPool** per operazioni async (DB queries, API calls, ML inference)
- **ServiceRegistry** singleton: verifica disponibilità servizi → pubblica stato via Qt Signal

### Service Layer
| Servizio | Responsabilità | Fallback offline |
|---------|----------------|-----------------|
| `DBService` | Query PostgreSQL, ORM SQLAlchemy | — (obbligatorio) |
| `GeoService` | Geocoding, query PostGIS | Centroidi ONSPD (PostCode) |
| `GraphService` | Apache AGE Cypher, NetworkX | CTE ricorsive PostgreSQL |
| `VectorService` | pgvector HNSW, embeddings | FTS PostgreSQL (tsvector) |
| `APIService` | CH API, OpenCorporates (cache) | Solo cache locale |
| `ReportService` | Generazione PDF, export FtM/GEXF | — |

### Intelligence Layer
- **RiskScorer**: calcola score composito 0–100 da flag deterministici
- **FT3Mapper**: mappa ogni flag a technique ID FT3
- **EntityResolver**: deduplicazione cross-source via FtM `make_id()`
- **PatternDetector**: 8 pattern SQL/ML per shell company detection

---

## Database schema (panoramica)

```
entities            -- Tabella core FtM (Company, Person, Address...)
  ├── entity_events -- Log versioning per ogni update
  ├── risk_flags    -- Flag di rischio con ft3_technique_id
  └── annotations   -- Note investigative dell'utente

companies           -- Campi estratti CH per query veloci
pscs                -- PSC relazionali estratti da JSONL
officers            -- Direttori (popolato da API on-demand)
sanctions_entries   -- UK Sanctions + OpenSanctions
icij_nodes          -- Entità ICIJ Offshore Leaks
icij_relationships  -- Relazioni ICIJ (officer_of, registered_address, ...)

investigations      -- Sessioni investigative salvate
  └── inv_entities  -- Entità incluse nell'investigazione

api_cache           -- Cache chiamate API con TTL
postcode_centroids  -- ONSPD: centroidi PostCode UK
```

---

## Pipeline dati

```
Fonti esterne
    │
    ▼
[Import Scripts] ──── staging table
    │                      │
    │              COPY FROM STDIN
    │                      │
    ▼                      ▼
[Tabelle staging] → [INSERT ON CONFLICT UPDATE] → [Tabelle principali]
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
[Geocoding] ──────── ONSPD centroidi (batch) + Nominatim (on-demand)
```

---

## Pattern di detection

| # | Pattern | Dati richiesti | Implementazione | Fase |
|---|---------|---------------|-----------------|------|
| 1 | Shared Address | CH | SQL GROUP BY | 2 |
| 2 | Serial Director/PSC | PSC + Officers | SQL + AGE | 2/3 |
| 3 | PSC DOB Clustering | PSC | SQL window fn | 2 |
| 4 | SIC Incongruence | CH | SQL | 2 |
| 5 | Rapid Dissolution | CH | SQL date diff | 2 |
| 6 | Incorporation Clustering | CH | SQL window fn | 2 |
| 7 | Name Similarity | CH + embeddings | pgvector HNSW | 3 |
| 8 | Composite Anomaly | Tutti | Weighted sum | 2/3 |

---

## Dipendenze principali

```
Python 3.12
├── PySide6              # UI framework (LGPL)
├── SQLAlchemy 2.0       # ORM async
├── Alembic              # DB migrations
├── Pydantic v2          # Settings & validation
├── psycopg2-binary      # PostgreSQL driver
├── httpx                # HTTP client async
├── ijson                # Streaming JSON parser
├── sentence-transformers # ML embeddings (Apache 2.0)
├── networkx             # Graph analysis
├── WeasyPrint           # PDF generation
├── Jinja2               # Template engine (report)
├── APScheduler          # Background scheduling
├── python-keyring       # Secure credential storage
└── followthemoney       # FtM entity model (MIT)
```

---

## Decisioni architetturali

Vedere [architectural_decisions.md](../memory/architectural_decisions.md) per la lista completa delle ADR (Architecture Decision Records) con motivazioni.

Decisioni chiave:
- **ADR-001**: pgvector come default, RuVector opzionale (>10M vettori)
- **ADR-002**: pgvector binary quantization (HNSW: 30GB → 4GB)
- **ADR-003**: Import sequenziale obbligatorio (dipendenze FK)
- **ADR-007**: FtM su PostgreSQL via JSONB partial index
- **ADR-009**: ServiceRegistry singleton con Qt Signal
- **ADR-010**: Docker port binding su 127.0.0.1 (sicurezza)

---

## Sottosistemi avanzati

### Name Normalization Engine

Responsabile della normalizzazione di nomi in qualunque script per entity resolution cross-source.

**Libreria core**: `fingerprints` (MIT) — un singolo punto di normalizzazione per CJK (Cinese/Giapponese/Coreano), Cirillico (Russo/Ucraino/etc.), Arabo, diacritici europei.

**Pipeline**:
1. `fingerprints.generate(name)` → forma canonica ASCII minuscola
2. FtM `make_id()` → hash stabile per deduplication cross-source
3. `jellyfish` Beider-Morse → phonetic key per omonimia fonetica residua (~5%)

**Storage**: tabella `name_variants` con indice su `fingerprint` — lookup O(log n) invece di scan fuzzy.

### PEP Detection

Persone Politicamente Esposte (PEP) identificate incrociando directors/PSC con:
- OpenSanctions (incluso Wikidata PEP, lista aggiornata giornalmente)
- EveryPolitician (copertura storica mandati da ~233 paesi)

Match via fingerprint → risk flag FT3 per connessione PEP.

### Geo-Intelligence

PostGIS + ONSPD (ONS Postcode Directory) per geocoding di massa (~95% copertura da day 1).
ST_ClusterDBSCAN per cluster spaziali (eps=50m, 100m, 500m pre-calcolati).
Nominatim Docker solo per precisione on-demand (edificio specifico).

### Link Analysis

Apache AGE (graph extension PostgreSQL) — 7 tipi nodo, 6 tipi edge.
NetworkX per centrality metrics su subgraphs estratti.
cytoscape.js (frontend) per visualizzazione interattiva.

### Case Management & Reporting

Schema PostgreSQL separato `casework` (8 tabelle).
WeasyPrint per PDF professionale (fallback QWebEngineView su Windows senza GTK3).
Export: PDF, FtM JSON, XLSX, GEXF, GraphML, GeoJSON, KML.
