# Design: Geo-Intelligence, Link Analysis, Reporting

## 1. REPORTING SYSTEM AND CASE MANAGEMENT

### Case Management — PostgreSQL Schema (separate `casework` schema)

```sql
CREATE SCHEMA IF NOT EXISTS casework;

-- Investigation as root aggregate
CREATE TABLE casework.investigations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'suspended', 'closed', 'archived')),
    classification  TEXT NOT NULL DEFAULT 'unclassified'
                        CHECK (classification IN ('unclassified', 'restricted', 'confidential')),
    investigator    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    tags            TEXT[] DEFAULT '{}',
    metadata        JSONB DEFAULT '{}'
);

-- Entities of interest linked to the investigation
CREATE TABLE casework.investigation_entities (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    entity_type         TEXT NOT NULL
                            CHECK (entity_type IN ('company','person','address',
                                                   'icij_entity','sanctions_entry')),
    entity_id           TEXT NOT NULL,      -- company_number, psc_id, icij node_id, etc.
    display_name        TEXT NOT NULL,
    is_primary          BOOLEAN DEFAULT FALSE,
    risk_score          NUMERIC(4,2),       -- 0.00-10.00
    flags               TEXT[] DEFAULT '{}', -- FT3 flags calculated by the system
    investigator_tags   TEXT[] DEFAULT '{}', -- free tags assigned by the investigator
    added_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(investigation_id, entity_type, entity_id)
);

-- Investigative annotations
CREATE TABLE casework.annotations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    entity_type         TEXT,   -- NULL = annotation on the entire investigation
    entity_id           TEXT,
    body                TEXT NOT NULL,
    annotation_type     TEXT NOT NULL DEFAULT 'note'
                            CHECK (annotation_type IN ('note','hypothesis','finding',
                                                       'caveat','source')),
    is_pinned           BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Manual links between entities (relationships not present in the source data)
CREATE TABLE casework.manual_links (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    source_type         TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    target_type         TEXT NOT NULL,
    target_id           TEXT NOT NULL,
    relationship_label  TEXT NOT NULL,  -- "suspected_nominee", "same_person", etc.
    confidence          TEXT DEFAULT 'medium'
                            CHECK (confidence IN ('low','medium','high','confirmed')),
    evidence_note       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT (source_type = target_type AND source_id = target_id))
);

-- Visual snapshots (map, cytoscape graph)
CREATE TABLE casework.visual_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    snapshot_type       TEXT NOT NULL CHECK (snapshot_type IN ('network_graph','geo_map','timeline')),
    title               TEXT NOT NULL,
    image_data          BYTEA,          -- PNG raw bytes
    viewport_state      JSONB,          -- zoom, pan, layout params
    graph_data          JSONB,          -- serialised cytoscape elements (for reload)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Generated reports
CREATE TABLE casework.generated_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    format              TEXT NOT NULL CHECK (format IN ('pdf','xlsx','ftm_json','gexf',
                                                        'graphml','csv','geojson','kml')),
    filename            TEXT NOT NULL,
    file_path           TEXT,
    file_size_bytes     INTEGER,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### PDF Generation

**Primary engine**: WeasyPrint (HTML+CSS -> PDF, professional typographic quality)
**Windows fallback**: `QWebEngineView.page().printToPdf()` (avoids GTK3 dependency)

Warning **Windows**: WeasyPrint requires the GTK3 runtime (pango, cairo). On Windows: install via `msys2` or the `weasyprint-windows` package. If problematic, use the Qt fallback.

Pipeline: `Jinja2 template` -> `HTML` -> `WeasyPrint` -> `PDF`

Map and graph screenshots: `QWebEngineView.grab()` -> PNG base64 inline in HTML

### Report Structure (10 sections)

1. Cover page (title, case number, date, classification, disclaimer)
2. Executive summary (risk score gauge, FT3 flags, key findings)
3. Primary entity (company profile, static map, SIC, shell indicators)
4. PSC ownership structure (PSC table, risk-nationality flags, ownership tree)
5. Network analysis (graph screenshot, betweenness/degree metrics)
6. Sanctions/adverse media matches (UK Sanctions, OpenSanctions, ICIJ)
7. Geographic analysis (map screenshot, address table, countries involved)
8. Events timeline (incorporation -> PSC change -> filing -> sanctions -> leak)
9. FT3 flags and indicators (full list with explanation)
10. Investigator annotations (notes, manual links, hypotheses)

### Export Formats

| Format | Tool | Priority |
|--------|------|----------|
| PDF | WeasyPrint / Qt fallback | HIGH — primary deliverable |
| FtM JSON | followthemoney library | HIGH — interoperability |
| XLSX | openpyxl | HIGH — investigator analysis |
| GEXF | stdlib XML | MEDIUM — Gephi analysis |
| GraphML | networkx + stdlib XML | MEDIUM — interoperability |
| GeoJSON | PostGIS ST_AsGeoJSON | MEDIUM — QGIS |
| KML | stdlib XML | MEDIUM — Google Earth |
| CSV | stdlib csv | LOW — raw dump |

**DO NOT implement**: STIX/TAXII (for CTI, not corporate intel), i2 ANB (undocumented proprietary format), DOCX (redundant with PDF)

---

## 2. GEO-INTELLIGENCE

### ONSPD — Critical Dataset Added

**Office for National Statistics Postcode Directory** — to be integrated as high priority.

- URL: https://geoportal.statistics.gov.uk/datasets/ons-postcode-directory
- Format: CSV, ~700MB, OGL v3 licence, quarterly updates
- **Impact**: raises geocoding coverage from ~5% to ~95% immediately, without Nominatim

```sql
CREATE TABLE geo_postcode_centroids (
    postcode    VARCHAR(8) PRIMARY KEY,   -- "EC1A 2AB" normalised
    lat         DOUBLE PRECISION NOT NULL,
    long        DOUBLE PRECISION NOT NULL,
    geom        GEOMETRY(Point, 4326) GENERATED ALWAYS AS (
                    ST_SetSRID(ST_MakePoint(long, lat), 4326)
                ) STORED,
    lsoa11      CHAR(9),    -- Lower Super Output Area
    msoa11      CHAR(9),    -- Middle Super Output Area
    laua        CHAR(9),    -- Local Authority code
    ward        CHAR(9),    -- Electoral ward
    ctry        CHAR(1),    -- E/W/S/N
    is_active   BOOLEAN DEFAULT TRUE
);
CREATE INDEX ON geo_postcode_centroids USING GIST(geom);
```

### Unified Materialized View

```sql
CREATE MATERIALIZED VIEW mv_company_geo AS
SELECT
    c.company_number,
    c.company_name,
    c.reg_address_postcode,
    c.company_status,
    c.sic_code_1,
    COALESCE(n.geom, pc.geom)   AS geom,            -- Nominatim first, ONSPD fallback
    CASE
        WHEN n.geom IS NOT NULL THEN 'nominatim'
        WHEN pc.geom IS NOT NULL THEN 'onspd'
        ELSE NULL
    END                         AS coord_source,
    pc.lsoa11,
    pc.laua,
    pc.ctry
FROM companies c
LEFT JOIN geocoded_addresses n  ON c.company_number = n.company_number
LEFT JOIN geo_postcode_centroids pc
    ON normalize_postcode(c.reg_address_postcode) = pc.postcode;

CREATE INDEX ON mv_company_geo USING GIST(geom);
```

### Spatial Clustering (pre-computed)

`ST_ClusterDBSCAN` is the correct algorithm for detecting arbitrary-density clusters:

```sql
SELECT
    company_number,
    ST_ClusterDBSCAN(geom, eps := 50, minpoints := 10) OVER () AS cluster_id
FROM mv_company_geo
WHERE geom IS NOT NULL;
```

Recommended parameters for Aethelburg:
- `eps = 50m` -> detects registered agents at the same physical address
- `eps = 500m` -> detects high-concentration zones (neighbourhoods)
- `eps = 1000m` -> city-level analysis

Pre-compute with multiple eps values in the `geo_clusters` table. Estimated time: 3-8 min for 5.67M points.

### address_fingerprint for Shared Addresses

Computed column for grouping identical addresses without geocoding:

```
Logic: normalize_postcode + house_number + first_non-stopword_keyword
Example: "40 KING STREET EC1A 2AB" -> "EC1A 2AB|40|KING"
```

```sql
ALTER TABLE companies ADD COLUMN address_fingerprint VARCHAR(100);
CREATE INDEX ON companies(address_fingerprint) WHERE address_fingerprint IS NOT NULL;
```

Python batch job computes fingerprints for 5.67M companies (~30 min). Then incremental.

### Advanced Map Layers (investigative value)

| Layer | Type | Investigative value |
|-------|------|---------------------|
| PostCode boundaries choropleth | Anomaly score per PostCode | CRITICAL |
| Director connection lines | Lines between companies of the same director | CRITICAL |
| Density heatmap (KDE 500m grid) | Geographic concentration | HIGH |
| Temporal animation | Company incorporation by year | HIGH |
| ICIJ/Sanctions overlay | Positions of known entities | HIGH |

**Director connection lines**: the most valuable layer. Shows a director controlling companies in different cities — an immediate and unambiguous visual pattern.

### Map Zoom Strategy

```
Zoom 1-8:   PostCode anomaly score choropleth (SQL GROUP BY query)
Zoom 9-12:  KDE heatmap (leaflet.heat, max 10K sampled points per viewport)
Zoom 13-15: MarkerCluster (max 5000 features, viewport-aware)
Zoom 16+:   Individual markers with detail popup
```

Max 5000 features per single QWebChannel message.

### Geo-Intelligence Export

Priority: `GeoJSON > KML > GeoPackage`
- GeoJSON: native PostGIS (`ST_AsGeoJSON()`), maximum compatibility
- KML: for Google Earth (common in law enforcement)
- GeoPackage: for QGIS, overcomes Shapefile limits (255 chars)

### Recommended Additional Datasets

| Dataset | Source | Usage |
|---------|--------|-------|
| ONSPD | ONS Open Geography | PostCode centroids — MAXIMUM PRIORITY |
| PostCode Boundaries | ONS Open Geography | Choropleth layer |
| Local Authority Boundaries | ONS Open Geography | Aggregation by LA |
| HMLR Price Paid | HM Land Registry | Address-to-property correlation |
| HMLR Overseas Entities | HM Land Registry | Foreign ownership of UK property |

---

## 3. LINK ANALYSIS

### Apache AGE Graph Schema

7 node types:

| Node | Source | Key fields |
|------|--------|------------|
| `Company` | Companies House | company_number, name_norm, sic_codes, flag_score |
| `Person` | PSC (individual) | psc_id, name_norm, nationality, dob_month/year |
| `CorporatePSC` | PSC (corporate) | psc_id, legal_form, country_registered, registration_number |
| `Address` | CH / ICIJ | address_id (hash), postcode, company_count |
| `JurisdictionEntity` | ICIJ Offshore Leaks | node_id, jurisdiction, service_provider, source_id |
| `IcijOfficer` | ICIJ nodes-officers | node_id, name_norm, country_codes |
| `SanctionedEntity` | UK Sanctions / OpenSanctions | sanction_id, scheme, listed_date, aliases |

6 edge types:

| Edge | From -> To | Key fields |
|------|-----------|------------|
| `CONTROLS` | Person/CorporatePSC -> Company | natures_of_control, ownership_pct_min/max, is_active |
| `SHARES_ADDRESS` | Company -> Address | address_type |
| `OFFSHORE_LINK` | Company/CorporatePSC -> JurisdictionEntity | match_score, match_method, verified |
| `SANCTIONED` | Company/Person -> SanctionedEntity | match_score, scheme |
| `ICIJ_OFFICER_OF` | IcijOfficer -> JurisdictionEntity | link, start_date |
| `SAME_PERSON_AS` | Person -> IcijOfficer | confidence, match_method |

### Pattern Detection with FT3 Mapping

| # | Pattern | Query | FT3 ID | Priority |
|---|---------|-------|--------|----------|
| 1 | Star PSC (>=10 companies) | AGE degree out | FT3-SC-001 | HIGH |
| 2 | Chain layering (depth >=3) | AGE path *1..7 | FT3-ML-003 | HIGH |
| 3 | Circular ownership | AGE cycle (c)-[:CONTROLS*2..6]->(c) | FT3-SC-005 | CRITICAL |
| 4 | Island node (no UBO) | AGE degree=0 on CONTROLS | FT3-SC-008 | HIGH |
| 5 | Bridge node (betweenness > 0.15) | NetworkX betweenness | FT3-SC-009 | MEDIUM |
| 6 | Shared address (>=5 companies) | AGE aggregation | FT3-SC-012 | MEDIUM |
| 7 | Offshore PSC on UK company | OFFSHORE_LINK edge present | FT3-ML-007 | HIGH |
| 8 | Sanctions match | SANCTIONED edge present | FT3-SC-015 | CRITICAL |

### Beneficial Ownership Chain Query

```sql
-- Depth 1..4 default (covers 95% of real-world cases)
SELECT * FROM cypher('aethelburg', $$
  MATCH path = (start:Person {name_norm: $name_norm})
               -[:CONTROLS|SAME_PERSON_AS*1..4]->(end)
  WHERE (end:Company OR end:JurisdictionEntity)
  RETURN
    [node IN nodes(path) | node.name]     AS chain_names,
    [node IN nodes(path) | labels(node)]  AS chain_types,
    length(path)                          AS depth
  ORDER BY depth ASC
$$) AS (...);
```

Depth thresholds: 1-2 (direct ownership, <50ms), 1-4 (default, 200-800ms), 1-5 (in-depth investigations, 1-4s), 1-7+ (only on limited subgraph, OOM risk).

### Entity Resolution CH -> ICIJ

`business_registration_number` in ICIJ does not map directly to Companies House. Heuristic matching based on normalised fingerprint (see section 5):

```
Composite score (0.0-1.0):
  normalised fingerprint match_score     x 0.60     -- fingerprints.generate() + jellyfish
  offshore jurisdiction (non-UK)         x 0.15     -- increases if offshore
  compatible incorporation year (+-2y)   x 0.15     -- if available
  ICIJ countries contain UK (GBR)        x 0.10
```

Thresholds: >=0.95 (create edge, visual flag), 0.85-0.94 (create edge, requires review), 0.75-0.84 (dashed edge), <0.75 (do not create edge).

The `match_score` on the name uses `fingerprints.generate()` as a first step (exact match = 1.0) and `jellyfish.jaro_winkler_similarity()` on fingerprints as a fuzzy fallback. Full detail in section 5.

### cytoscape.js <-> Python Communication (QWebChannel)

```
Typical perceived latency: ~100-250ms for 1-hop expansion
  JS -> QWebChannel:      <5ms
  AGE query (1-hop):      20-80ms
  NetworkX centrality:    <10ms (<=50 nodes)
  JSON serialisation:     <5ms
  JS add + cola layout:   50-150ms
```

Recommended layouts: `dagre` (ownership hierarchy, top-down), `cola` (complex network), `concentric` (star pattern), `preset` (export with curated positions).

Rendering limits: <=200 nodes (smooth), <=500 (usable with zoom), <=1000 (maximum -- disable labels).

### Graph Export

| Format | Tool | Priority |
|--------|------|----------|
| GraphML | Universal standard (Gephi, yEd, i2) | HIGH -- for case sharing |
| GEXF | Gephi native (dynamic attributes, timeline) | HIGH -- for visual analysis |
| Cytoscape JSON | Full session save with positions and annotations | HIGH |
| DOT (Graphviz) | Only for graphs <100 nodes, for inline PDF reports | LOW |

---

## 4. PROJECT FILE STRUCTURE (updated)

```
src/
├── core/
│   └── service_registry.py     -- ServiceRegistry singleton
├── db/
│   ├── models.py               -- SQLAlchemy models
│   └── migrations/             -- Alembic
├── ui/
│   ├── main_window.py
│   ├── web_bridge.py           -- QWebChannel GraphBridge
│   └── frontend/
│       ├── map_view.js         -- Leaflet + layer manager
│       ├── graph_view.js       -- cytoscape.js renderer
│       ├── graph_styles.js     -- cytoscape stylesheet
│       └── timeline_view.js    -- Chart.js timeline
├── services/
│   ├── db_service.py
│   ├── geo_service.py          -- PostGIS, ONSPD, geocoding
│   ├── vector_service.py       -- pgvector ABC + PgVectorProvider
│   └── api_service.py          -- CH API, cache
├── intelligence/
│   ├── risk_scorer.py          -- composite score calculation
│   ├── ft3_mapper.py           -- flag -> FT3 technique ID mapping
│   └── entity_resolver.py      -- FtM make_id(), CH<->ICIJ matching
├── graph/
│   ├── age_schema.sql          -- full Apache AGE DDL
│   ├── graph_service.py        -- subgraph extraction, NetworkX centrality
│   ├── graph_exporter.py       -- GraphML, GEXF, Cytoscape JSON, DOT
│   └── patterns.py             -- star/chain/loop/island/bridge detection
├── etl/
│   ├── import_companies.py     -- CH CSV -> PostgreSQL (COPY FROM STDIN)
│   ├── import_psc.py           -- PSC JSONL -> PostgreSQL (ijson streaming)
│   ├── import_icij.py          -- ICIJ CSV -> PostgreSQL
│   ├── import_sanctions.py     -- UK Sanctions -> PostgreSQL
│   ├── import_onspd.py         -- ONSPD -> geo_postcode_centroids
│   └── compute_fingerprints.py -- batch address_fingerprint
└── reports/
    ├── pdf_generator.py        -- Jinja2 -> WeasyPrint -> PDF
    ├── export_service.py       -- all export formats
    └── templates/              -- Jinja2 HTML templates
        ├── investigation_report.html
        └── report.css
```

---

## 5. Name Normalisation & Entity Resolution

### General Principle

Name normalisation is the foundation of cross-dataset matching. Different sources represent the same entity using different scripts, transliterations, and conventions. A robust normalisation system must handle this before any comparison takes place.

### Normalisation Pipeline

The `fingerprints` library (MIT licence, `pip install fingerprints`) is the only component needed for multi-script normalisation. It replaces the entire previous stack (`pypinyin`, `opencc-python-reimplemented`, `cyrtranslit`, `anyascii`).

`fingerprints.generate(name)` handles all of the following in a single call:
- CJK (Simplified and Traditional Chinese, Japanese, Korean) -- pinyin/romaji/romanisation transliteration
- Cyrillic -- ISO transliteration
- Arabic and other non-Latin scripts
- Diacritics (accents, umlauts, composed characters)
- Punctuation, articles, legal suffixes (`Ltd`, `Corp`, `GmbH`, `S.A.`, etc.)

Cross-script convergence example:

```python
from fingerprints import generate as fp

# All of these produce the same fingerprint:
fp("江澤民")          # -> "jiang zemin"
fp("Jiang Zemin")    # -> "jiang zemin"
fp("江泽民")          # -> "jiang zemin"  (simplified characters)
fp("Цзян Цзэминь")   # -> "jiang zemin"  (Cyrillic)
```

FtM `make_id()` generates a stable canonical hash that enables reliable cross-source deduplication without repeated textual comparisons.

`jellyfish` is used exclusively as a residual phonetic fallback (Beider-Morse) to handle phonetic homonyms in cases where fingerprints do not match (~5% of cases: Smith/Smyth, Meyer/Meier, etc.).

### `name_variants` Table Schema

```sql
CREATE TABLE name_variants (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       UUID NOT NULL,
    entity_type     VARCHAR(20) NOT NULL,    -- 'person' | 'company'
    variant_text    VARCHAR(500) NOT NULL,   -- original text
    fingerprint     VARCHAR(500),           -- fingerprints.generate(variant_text)
    ftm_id          VARCHAR(64),            -- make_id() hash for cross-source dedup
    variant_type    VARCHAR(30),            -- 'original' | 'alias' | 'phonetic_key'
    source_id       UUID REFERENCES data_sources(id)
);
CREATE INDEX idx_name_variants_fingerprint ON name_variants(fingerprint);
CREATE INDEX idx_name_variants_text ON name_variants USING gin(to_tsvector('simple', variant_text));
```

Note: the index on `fingerprint` is the primary lookup key -- most matches occur by exact fingerprint equality. The GIN index on `variant_text` supports free-text searches from the investigative interface.

### Entity Resolution Matching -- Implementation

```python
from fingerprints import generate as fp
import jellyfish

def match_persons(ch_name: str, icij_name: str) -> float:
    ch_fp = fp(ch_name)
    icij_fp = fp(icij_name)

    if ch_fp == icij_fp:
        return 1.0  # exact canonical match

    jw = jellyfish.jaro_winkler_similarity(ch_fp, icij_fp)
    if jw >= 0.85:
        return jw * 0.95  # fuzzy match on normalised fingerprint

    # Beider-Morse phonetic fallback for phonetic homonyms
    # (Smith/Smyth, Meyer/Meier, etc.)
    return 0.0  # below threshold
```

Final score for entity resolution (updated formula):

```
match_score x 0.60 + jurisdiction x 0.15 + year x 0.15 + UK_country x 0.10
```

Minimum threshold to create an edge: **0.75**

| Score range | Action |
|-------------|--------|
| >= 0.95 | Create `SAME_PERSON_AS` / `OFFSHORE_LINK` edge, green visual flag |
| 0.85 - 0.94 | Create edge, status `requires_review` |
| 0.75 - 0.84 | Dashed edge, low confidence |
| < 0.75 | Do not create edge |

### Impact on ETL Pipeline

**OpenSanctions import** (`import_sanctions.py`):
- `entity.get("name")` + `entity.get("alias")` -> `fp()` -> insert into `name_variants`
- `make_id()` is already present in FtM, use it directly as `ftm_id`

**Companies House import** (`import_companies.py`):
- `fp(company_name)` computed at import time, saved in `name_variants` with `variant_type = 'original'`

**ICIJ import** (`import_icij.py`):
- `fp(officer_name)` and `fp(entity_name)` -- normalisation resolves cross-dataset matching without manual heuristic joins

**EveryPolitician / PEP sources**:
- Same pipeline. Political names in any script (Arabic, Cyrillic, CJK) are normalised uniformly

### Updated Python Dependencies

Remove (replaced by `fingerprints`):

| Removed library | Reason |
|-----------------|--------|
| `pypinyin` | CJK -> pinyin now handled by `fingerprints` |
| `opencc-python-reimplemented` | Simplified/Traditional Chinese now handled by `fingerprints` |
| `cyrtranslit` | Cyrillic now handled by `fingerprints` |
| `anyascii` | General transliteration now handled by `fingerprints` |

Add:

| Library | Minimum version | Licence | Usage |
|---------|----------------|---------|-------|
| `fingerprints` | `>=0.5` | MIT | Multi-script normalisation -- single component |
| `jellyfish` | `>=1.0` | BSD | Phonetic fallback (Beider-Morse, Jaro-Winkler) |
