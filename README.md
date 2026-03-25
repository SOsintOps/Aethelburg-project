<p align="center">
  <img src="assets/logo.jpg" alt="Aethelburg" width="300"/>
</p>

# Aethelburg

Local desktop platform for analysing UK company register data (Companies House) and identifying shell companies and anomalous corporate structures.

> **Personal use only.** Data is neither distributed nor shared. See [LEGAL.md](docs/LEGAL.md) for licence and compliance details.

---

## What it does

Aethelburg automatically cross-references six public data sources to produce a risk profile for every company registered in the UK:

| Source | Contents |
|--------|----------|
| Companies House Bulk | 5.67M companies with history, SIC codes, addresses, dates |
| PSC Snapshot | 15M Persons with Significant Control with DOB and nationality |
| UK Sanctions / OpenSanctions | 329 global sanctions sources (daily updates) |
| ICIJ Offshore Leaks | Panama Papers, Pandora Papers, Paradise Papers |
| Companies House API | Officers/directors for high-risk companies |
| Nominatim / ONSPD | Address geocoding and spatial analysis |

The system applies detection patterns based on FT3 (Stripe Fraud Tactics Techniques) and produces a composite risk score for each company.

---

## Features

### Intelligence & Detection
- 8 shell company detection patterns (rapid dissolution, incorporation clustering, incongruent SIC, serial PSC, shared addresses, name similarity, offshore connections)
- Risk score 0–100 with FT3 tags for each triggered flag
- Cross-source entity resolution via FollowTheMoney fingerprinting

### Geo-Intelligence
- Interactive map with zoom-based layering (choropleth → heatmap → cluster → marker)
- DBSCAN spatial clustering on PostCode (PostGIS ST_ClusterDBSCAN)
- Hotspot analysis: anomalous concentration by postal district
- Thematic layers: sanctions, ICIJ, dissolved companies by area

### Link Analysis
- Network graph: PSC → Company → ICIJ → Offshore
- Interactive visualisation with cytoscape.js (1-hop expansion on click)
- Structural patterns: star, chain, loop (circular ownership), bridge node
- Centrality metrics: degree, betweenness, PageRank on subgraph

### Reporting
- PDF report for investigation (Jinja2 + WeasyPrint)
- FtM JSON export (Aleph / OCCRP compatible)
- Graph export: GEXF (Gephi), GraphML, GeoJSON
- Case management: save investigative sessions with annotations

---

## Prerequisites

- **Windows 10/11** (64-bit)
- **Python 3.12+**
- **Docker Desktop** with WSL2 enabled
- **Disk space**: ~80–120GB for full DB
- **RAM**: 16GB recommended (8GB minimum with reduced dataset)

---

## Quick installation

```bash
# 1. Clone the repository
git clone https://github.com/tuousername/aethelburg.git
cd aethelburg

# 2. Create the virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and configure environment variables
copy .env.example .env
# Edit .env with your credentials

# 5. Start Docker services
docker compose up -d

# 6. Initialise the database
python -m alembic upgrade head
bash scripts/setup_db.sh

# 7. Start the application
python src/main.py
```

---

## Initial data loading

The import order is **sequential and mandatory** (FK dependencies):

```bash
# Estimated total time: 4-6 hours (consumer hardware NVMe SSD, 16GB RAM)

python scripts/import_sanctions.py     # UK Sanctions OFSI (~5 min)
python scripts/import_icij.py          # ICIJ Offshore Leaks (~1h)
python scripts/import_companies.py     # Companies House 5.67M (~1-2h)
python scripts/import_psc.py           # PSC Snapshot 15M (~2-3h)
```

Companies House data can be downloaded from:
- [Companies House Data Products](https://download.companieshouse.gov.uk/en_output.html)
- [PSC Snapshot](https://download.companieshouse.gov.uk/persons-with-significant-control-snapshot-2016-04-06.zip)

---

## Project structure

```
aethelburg/
├── src/                    # Source code
│   ├── core/               # Domain logic, detection patterns
│   ├── db/                 # SQLAlchemy models, Alembic migrations
│   ├── ui/                 # PySide6 windows and widgets
│   ├── services/           # Service layer (DB, API, Vector, Geo)
│   ├── intelligence/       # Risk scoring, FT3 mapping, entity resolution
│   ├── graph/              # Link analysis, Apache AGE, NetworkX
│   └── reports/            # Report generation, export
├── scripts/                # Data import, setup, utilities
├── config/                 # Configuration (settings.py)
├── tests/                  # Test suite
├── docs/                   # Documentation
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## Data and licences

| Dataset | Licence | Notes |
|---------|---------|-------|
| Companies House | OGL v3 | Open Government Licence |
| ICIJ Offshore Leaks | CC-BY-NC | Non-commercial use only |
| OpenSanctions | CC-BY-NC-SA | Share-alike, non-commercial |
| FollowTheMoney | MIT | OCCRP |
| FT3 Framework | MIT | Stripe |

See [docs/LEGAL.md](docs/LEGAL.md) for the full licence analysis.

---

## Technologies

`Python 3.12` · `PySide6` · `PostgreSQL 16` · `PostGIS` · `pgvector` · `Apache AGE` · `Leaflet.js` · `cytoscape.js` · `FollowTheMoney` · `sentence-transformers` · `SQLAlchemy` · `Alembic` · `Docker`
