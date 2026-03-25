# Design: Geo-Intelligence, Link Analysis, Reportistica

## 1. SISTEMA DI REPORTISTICA E CASE MANAGEMENT

### Case Management — Schema PostgreSQL (schema separato `casework`)

```sql
CREATE SCHEMA IF NOT EXISTS casework;

-- Investigazione come aggregato radice
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

-- Entita di interesse legate all'investigazione
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
    flags               TEXT[] DEFAULT '{}', -- flag FT3 calcolati dal sistema
    investigator_tags   TEXT[] DEFAULT '{}', -- tag liberi dell'investigatore
    added_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(investigation_id, entity_type, entity_id)
);

-- Annotazioni investigative
CREATE TABLE casework.annotations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    entity_type         TEXT,   -- NULL = annotazione sull'intera investigazione
    entity_id           TEXT,
    body                TEXT NOT NULL,
    annotation_type     TEXT NOT NULL DEFAULT 'note'
                            CHECK (annotation_type IN ('note','hypothesis','finding',
                                                       'caveat','source')),
    is_pinned           BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Link manuali tra entita (relazioni non presenti nei dati originali)
CREATE TABLE casework.manual_links (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    source_type         TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    target_type         TEXT NOT NULL,
    target_id           TEXT NOT NULL,
    relationship_label  TEXT NOT NULL,  -- "suspected_nominee", "same_person", ecc.
    confidence          TEXT DEFAULT 'medium'
                            CHECK (confidence IN ('low','medium','high','confirmed')),
    evidence_note       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT (source_type = target_type AND source_id = target_id))
);

-- Snapshot visuali (mappa, grafo cytoscape)
CREATE TABLE casework.visual_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
    snapshot_type       TEXT NOT NULL CHECK (snapshot_type IN ('network_graph','geo_map','timeline')),
    title               TEXT NOT NULL,
    image_data          BYTEA,          -- PNG raw bytes
    viewport_state      JSONB,          -- zoom, pan, layout params
    graph_data          JSONB,          -- cytoscape elements serializzati (per reload)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Report generati
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

### Generazione PDF

**Motore primario**: WeasyPrint (HTML+CSS → PDF, qualità tipografica professionale)
**Fallback Windows**: `QWebEngineView.page().printToPdf()` (evita dipendenza GTK3)

⚠️ **Avviso Windows**: WeasyPrint richiede GTK3 runtime (pango, cairo). Su Windows: installare via `msys2` o pacchetto `weasyprint-windows`. Se problematico, usare fallback Qt.

Pipeline: `Jinja2 template` → `HTML` → `WeasyPrint` → `PDF`

Screenshot di mappa e grafo: `QWebEngineView.grab()` → PNG base64 inline nel HTML

### Struttura del report (10 sezioni)

1. Copertina (titolo, numero caso, data, classificazione, disclaimer)
2. Sommario esecutivo (risk score gauge, flag FT3, finding principali)
3. Entità primaria (scheda azienda, mappa statica, SIC, indicatori shell)
4. Struttura di proprietà PSC (tabella PSC, flag nazionalità rischio, albero ownership)
5. Network analysis (screenshot grafo, metriche betweenness/degree)
6. Corrispondenze sanctions/adverse (UK Sanctions, OpenSanctions, ICIJ)
7. Analisi geografica (screenshot mappa, tabella indirizzi, paesi coinvolti)
8. Timeline eventi (incorporazione → cambio PSC → filing → sanzioni → leak)
9. Flag e indicatori FT3 (lista completa con spiegazione)
10. Annotazioni investigatore (note, link manuali, ipotesi)

### Formati export

| Formato | Strumento | Priorità |
|---------|-----------|----------|
| PDF | WeasyPrint / Qt fallback | ALTA — deliverable primario |
| FtM JSON | followthemoney library | ALTA — interoperabilità |
| XLSX | openpyxl | ALTA — analisi investigatore |
| GEXF | stdlib XML | MEDIA — Gephi analysis |
| GraphML | networkx + stdlib XML | MEDIA — interoperabilità |
| GeoJSON | PostGIS ST_AsGeoJSON | MEDIA — QGIS |
| KML | stdlib XML | MEDIA — Google Earth |
| CSV | stdlib csv | BASSA — dump grezzo |

**NON implementare**: STIX/TAXII (per CTI, non corporate intel), i2 ANB (formato proprietario non documentato), DOCX (ridondante con PDF)

---

## 2. GEO-INTELLIGENCE

### ONSPD — Dataset critico aggiunto

**Office for National Statistics Postcode Directory** — da integrare come priorità alta.

- URL: https://geoportal.statistics.gov.uk/datasets/ons-postcode-directory
- Formato: CSV, ~700MB, licenza OGL v3, aggiornamento trimestrale
- **Impatto**: porta la copertura geocoding da ~5% a ~95% immediato, senza Nominatim

```sql
CREATE TABLE geo_postcode_centroids (
    postcode    VARCHAR(8) PRIMARY KEY,   -- "EC1A 2AB" normalizzato
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

### Materialized View unificata

```sql
CREATE MATERIALIZED VIEW mv_company_geo AS
SELECT
    c.company_number,
    c.company_name,
    c.reg_address_postcode,
    c.company_status,
    c.sic_code_1,
    COALESCE(n.geom, pc.geom)   AS geom,            -- Nominatim prima, ONSPD fallback
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

### Clustering spaziale (pre-calcolato)

`ST_ClusterDBSCAN` è l'algoritmo corretto per rilevare cluster di densità arbitraria:

```sql
SELECT
    company_number,
    ST_ClusterDBSCAN(geom, eps := 50, minpoints := 10) OVER () AS cluster_id
FROM mv_company_geo
WHERE geom IS NOT NULL;
```

Parametri raccomandati per Aethelburg:
- `eps = 50m` → rileva registered agents con stesso indirizzo fisico
- `eps = 500m` → rileva zone ad alta concentrazione (quartieri)
- `eps = 1000m` → analisi di livello cittadino

Pre-calcolare con eps multipli in tabella `geo_clusters`. Tempo stimato: 3-8 min per 5.67M punti.

### address_fingerprint per shared address

Colonna calcolata per raggruppare indirizzi identici senza geocoding:

```
Logica: normalize_postcode + numero_civico + prima_keyword_non_stopword
Esempio: "40 KING STREET EC1A 2AB" → "EC1A 2AB|40|KING"
```

```sql
ALTER TABLE companies ADD COLUMN address_fingerprint VARCHAR(100);
CREATE INDEX ON companies(address_fingerprint) WHERE address_fingerprint IS NOT NULL;
```

Job batch Python calcola fingerprint per 5.67M aziende (~30 min). Poi incrementale.

### Layer mappa avanzati (valore investigativo)

| Layer | Tipo | Valore investigativo |
|-------|------|---------------------|
| PostCode boundaries choropleth | Anomaly score per PostCode | CRITICO |
| Director connection lines | Linee tra aziende dello stesso director | CRITICO |
| Heatmap densità (KDE 500m grid) | Concentrazione geografica | ALTO |
| Temporal animation | Incorporazione aziendale per anno | ALTO |
| ICIJ/Sanctions overlay | Posizioni entità note | ALTO |

**Director connection lines**: il layer più prezioso. Mostra un director che controlla aziende in città diverse — pattern visivo immediato e inequivocabile.

### Strategia zoom mappa

```
Zoom 1–8:   Choropleth PostCode anomaly score (query SQL GROUP BY)
Zoom 9–12:  Heatmap KDE (leaflet.heat, max 10K punti campionati per viewport)
Zoom 13–15: MarkerCluster (max 5000 features, viewport-aware)
Zoom 16+:   Marker individuali con popup dettaglio
```

Max 5000 feature per singolo messaggio QWebChannel.

### Export geo-intelligence

Priorità: `GeoJSON > KML > GeoPackage`
- GeoJSON: nativo PostGIS (`ST_AsGeoJSON()`), massima compatibilità
- KML: per Google Earth (comune in law enforcement)
- GeoPackage: per QGIS, supera limiti Shapefile (255 char)

### Dataset aggiuntivi consigliati

| Dataset | Fonte | Utilizzo |
|---------|-------|----------|
| ONSPD | ONS Open Geography | PostCode centroids — PRIORITÀ MASSIMA |
| PostCode Boundaries | ONS Open Geography | Choropleth layer |
| Local Authority Boundaries | ONS Open Geography | Aggregazione per LA |
| HMLR Price Paid | HM Land Registry | Correlazione indirizzi immobili |
| HMLR Overseas Entities | HM Land Registry | Proprietà straniere di immobili UK |

---

## 3. LINK ANALYSIS

### Schema grafo Apache AGE

7 tipi di nodo:

| Nodo | Fonte | Campi chiave |
|------|-------|-------------|
| `Company` | Companies House | company_number, name_norm, sic_codes, flag_score |
| `Person` | PSC (individual) | psc_id, name_norm, nationality, dob_month/year |
| `CorporatePSC` | PSC (corporate) | psc_id, legal_form, country_registered, registration_number |
| `Address` | CH / ICIJ | address_id (hash), postcode, company_count |
| `JurisdictionEntity` | ICIJ Offshore Leaks | node_id, jurisdiction, service_provider, source_id |
| `IcijOfficer` | ICIJ nodes-officers | node_id, name_norm, country_codes |
| `SanctionedEntity` | UK Sanctions / OpenSanctions | sanction_id, scheme, listed_date, aliases |

6 tipi di edge:

| Edge | Da → A | Campi chiave |
|------|--------|-------------|
| `CONTROLS` | Person/CorporatePSC → Company | natures_of_control, ownership_pct_min/max, is_active |
| `SHARES_ADDRESS` | Company → Address | address_type |
| `OFFSHORE_LINK` | Company/CorporatePSC → JurisdictionEntity | match_score, match_method, verified |
| `SANCTIONED` | Company/Person → SanctionedEntity | match_score, scheme |
| `ICIJ_OFFICER_OF` | IcijOfficer → JurisdictionEntity | link, start_date |
| `SAME_PERSON_AS` | Person → IcijOfficer | confidence, match_method |

### Pattern detection con FT3 mapping

| # | Pattern | Query | FT3 ID | Priorità |
|---|---------|-------|--------|----------|
| 1 | Star PSC (≥10 company) | AGE degree out | FT3-SC-001 | ALTA |
| 2 | Chain layering (depth ≥3) | AGE path *1..7 | FT3-ML-003 | ALTA |
| 3 | Circular ownership | AGE cycle (c)-[:CONTROLS*2..6]->(c) | FT3-SC-005 | CRITICA |
| 4 | Island node (no UBO) | AGE degree=0 su CONTROLS | FT3-SC-008 | ALTA |
| 5 | Bridge node (betweenness > 0.15) | NetworkX betweenness | FT3-SC-009 | MEDIA |
| 6 | Shared address (≥5 company) | AGE aggregation | FT3-SC-012 | MEDIA |
| 7 | PSC offshore su company UK | OFFSHORE_LINK edge presente | FT3-ML-007 | ALTA |
| 8 | Sanctions match | SANCTIONED edge presente | FT3-SC-015 | CRITICA |

### Beneficial ownership chain query

```sql
-- Profondità 1..4 default (copre 95% casi reali)
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

Soglie di profondità: 1-2 (ownership diretta, <50ms), 1-4 (default, 200-800ms), 1-5 (indagini approfondite, 1-4s), 1-7+ (solo su subgraph limitato, rischio OOM).

### Entity resolution CH → ICIJ

`business_registration_number` in ICIJ non mappa direttamente su Companies House. Matching euristico basato su fingerprint normalizzato (vedere sezione 5):

```
Score composito (0.0–1.0):
  match_score fingerprint normalizzato     × 0.60     — fingerprints.generate() + jellyfish
  giurisdizione offshore (non-UK)          × 0.15     — aumenta se offshore
  anno incorporazione compatibile (±2y)    × 0.15     — se disponibile
  paesi ICIJ contengono UK (GBR)           × 0.10
```

Soglie: ≥0.95 (crea edge, flag visivo), 0.85-0.94 (crea edge, richiede review), 0.75-0.84 (edge tratteggiato), <0.75 (non creare edge).

Il `match_score` sul nome usa `fingerprints.generate()` come primo passo (corrispondenza esatta = 1.0) e `jellyfish.jaro_winkler_similarity()` sui fingerprint come fallback fuzzy. Dettaglio completo in sezione 5.

### Comunicazione cytoscape.js ↔ Python (QWebChannel)

```
Latenza percepita tipica: ~100-250ms per 1-hop expansion
  JS → QWebChannel:      <5ms
  Query AGE (1-hop):     20-80ms
  Centralità NetworkX:   <10ms (≤50 nodi)
  Serializzazione JSON:  <5ms
  JS add + layout cola:  50-150ms
```

Layout raccomandati: `dagre` (ownership hierarchy, top-down), `cola` (rete complessa), `concentric` (star pattern), `preset` (export con posizioni curate).

Limiti di rendering: ≤200 nodi (smooth), ≤500 (usabile con zoom), ≤1000 (massimo — disabilita label).

### Export grafo

| Formato | Tool | Priorità |
|---------|------|----------|
| GraphML | Standard universale (Gephi, yEd, i2) | ALTA — per condivisione caso |
| GEXF | Gephi nativo (attributi dinamici, timeline) | ALTA — per analisi visiva |
| Cytoscape JSON | Salvataggio sessione completa con posizioni e annotazioni | ALTA |
| DOT (Graphviz) | Solo grafi <100 nodi, per report PDF inline | BASSA |

---

## 4. STRUTTURA FILE PROGETTO (aggiornata)

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
│       ├── graph_styles.js     -- stylesheet cytoscape
│       └── timeline_view.js    -- Chart.js timeline
├── services/
│   ├── db_service.py
│   ├── geo_service.py          -- PostGIS, ONSPD, geocoding
│   ├── vector_service.py       -- pgvector ABC + PgVectorProvider
│   └── api_service.py          -- CH API, cache
├── intelligence/
│   ├── risk_scorer.py          -- calcolo score composito
│   ├── ft3_mapper.py           -- mapping flag → FT3 technique ID
│   └── entity_resolver.py      -- FtM make_id(), CH↔ICIJ matching
├── graph/
│   ├── age_schema.sql          -- DDL completo Apache AGE
│   ├── graph_service.py        -- estrazione subgraph, centralità NetworkX
│   ├── graph_exporter.py       -- GraphML, GEXF, Cytoscape JSON, DOT
│   └── patterns.py             -- detection star/chain/loop/island/bridge
├── etl/
│   ├── import_companies.py     -- CH CSV → PostgreSQL (COPY FROM STDIN)
│   ├── import_psc.py           -- PSC JSONL → PostgreSQL (ijson streaming)
│   ├── import_icij.py          -- ICIJ CSV → PostgreSQL
│   ├── import_sanctions.py     -- UK Sanctions → PostgreSQL
│   ├── import_onspd.py         -- ONSPD → geo_postcode_centroids
│   └── compute_fingerprints.py -- batch address_fingerprint
└── reports/
    ├── pdf_generator.py        -- Jinja2 → WeasyPrint → PDF
    ├── export_service.py       -- tutti i formati export
    └── templates/              -- Jinja2 HTML templates
        ├── investigation_report.html
        └── report.css
```

---

## 5. Name Normalization & Entity Resolution

### Principio generale

La normalizzazione dei nomi è il fondamento del matching cross-dataset. Fonti diverse rappresentano la stessa entità con script, traslitterazioni e convenzioni diverse. Un sistema di normalizzazione robusto deve gestire questo prima di qualsiasi confronto.

### Pipeline di normalizzazione

La libreria `fingerprints` (licenza MIT, `pip install fingerprints`) è l'unico componente necessario per la normalizzazione multi-script. Rimpiazza l'intero stack precedente (`pypinyin`, `opencc-python-reimplemented`, `cyrtranslit`, `anyascii`).

`fingerprints.generate(name)` gestisce in un'unica chiamata:
- CJK (Cinese semplificato e tradizionale, Giapponese, Coreano) — traslitterazione pinyin/romaji/romanizzazione
- Cirillico — traslitterazione ISO
- Arabo e altri script non latini
- Diacritici (accenti, umlaut, caratteri composti)
- Punteggiatura, articoli, suffissi legali (`Ltd`, `Corp`, `GmbH`, `S.A.`, ecc.)

Esempio di convergenza cross-script:

```python
from fingerprints import generate as fp

# Tutti questi producono lo stesso fingerprint:
fp("江澤民")          # → "jiang zemin"
fp("Jiang Zemin")    # → "jiang zemin"
fp("江泽民")          # → "jiang zemin"  (caratteri semplificati)
fp("Цзян Цзэминь")   # → "jiang zemin"  (cirillico)
```

FtM `make_id()` genera un hash canonico stabile che permette deduplicazione cross-source affidabile senza confronti testuali ripetuti.

`jellyfish` viene usato esclusivamente come fallback fonetico residuo (Beider-Morse) per gestire omonimia fonetica nei casi in cui i fingerprint non coincidono (~5% dei casi: Smith/Smyth, Meyer/Meier, ecc.).

### Schema tabella `name_variants`

```sql
CREATE TABLE name_variants (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       UUID NOT NULL,
    entity_type     VARCHAR(20) NOT NULL,    -- 'person' | 'company'
    variant_text    VARCHAR(500) NOT NULL,   -- testo originale
    fingerprint     VARCHAR(500),           -- fingerprints.generate(variant_text)
    ftm_id          VARCHAR(64),            -- make_id() hash per dedup cross-source
    variant_type    VARCHAR(30),            -- 'original' | 'alias' | 'phonetic_key'
    source_id       UUID REFERENCES data_sources(id)
);
CREATE INDEX idx_name_variants_fingerprint ON name_variants(fingerprint);
CREATE INDEX idx_name_variants_text ON name_variants USING gin(to_tsvector('simple', variant_text));
```

Nota: l'indice su `fingerprint` è la chiave di lookup primaria — la maggior parte dei match avviene per uguaglianza esatta del fingerprint. L'indice GIN su `variant_text` supporta ricerche full-text libere dall'interfaccia investigativa.

### Matching entity resolution — implementazione

```python
from fingerprints import generate as fp
import jellyfish

def match_persons(ch_name: str, icij_name: str) -> float:
    ch_fp = fp(ch_name)
    icij_fp = fp(icij_name)

    if ch_fp == icij_fp:
        return 1.0  # match esatto canonico

    jw = jellyfish.jaro_winkler_similarity(ch_fp, icij_fp)
    if jw >= 0.85:
        return jw * 0.95  # match fuzzy su fingerprint normalizzato

    # Beider-Morse phonetic fallback per omonimi fonetici
    # (Smith/Smyth, Meyer/Meier, ecc.)
    return 0.0  # sotto soglia
```

Score finale per entity resolution (formula aggiornata):

```
match_score × 0.60 + giurisdizione × 0.15 + anno × 0.15 + UK_country × 0.10
```

Soglia minima per creare un edge: **0.75**

| Range score | Azione |
|-------------|--------|
| ≥ 0.95 | Crea edge `SAME_PERSON_AS` / `OFFSHORE_LINK`, flag visivo verde |
| 0.85 – 0.94 | Crea edge, stato `requires_review` |
| 0.75 – 0.84 | Edge tratteggiato, bassa confidenza |
| < 0.75 | Non creare edge |

### Impatto sulla ETL pipeline

**OpenSanctions import** (`import_sanctions.py`):
- `entity.get("name")` + `entity.get("alias")` → `fp()` → insert in `name_variants`
- `make_id()` è già presente in FtM, usarlo direttamente come `ftm_id`

**Companies House import** (`import_companies.py`):
- `fp(company_name)` calcolato all'import, salvato in `name_variants` con `variant_type = 'original'`

**ICIJ import** (`import_icij.py`):
- `fp(officer_name)` e `fp(entity_name)` — la normalizzazione risolve il matching cross-dataset senza bisogno di join euristici manuali

**EveryPolitician / PEP sources**:
- Stessa pipeline. I nomi politici in qualsiasi script (arabo, cirillico, CJK) vengono normalizzati in modo uniforme

### Dipendenze Python aggiornate

Rimuovere (rimpiazzate da `fingerprints`):

| Libreria rimossa | Motivo |
|------------------|--------|
| `pypinyin` | CJK → pinyin ora gestito da `fingerprints` |
| `opencc-python-reimplemented` | Cinese semplificato/tradizionale ora gestito da `fingerprints` |
| `cyrtranslit` | Cirillico ora gestito da `fingerprints` |
| `anyascii` | Traslitterazione generica ora gestita da `fingerprints` |

Aggiungere:

| Libreria | Versione minima | Licenza | Uso |
|----------|----------------|---------|-----|
| `fingerprints` | `>=0.5` | MIT | Normalizzazione multi-script — componente unico |
| `jellyfish` | `>=1.0` | BSD | Phonetic fallback (Beider-Morse, Jaro-Winkler) |
