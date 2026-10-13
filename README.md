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

The system applies detection patterns based on [FT3](https://github.com/stripe/ft3) (Stripe's Fraud Tools, Tactics, and Techniques framework) and produces a composite risk score for each company.

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
- How to write the report (risk score versus judgement, grading the register, sanctions and leak sources, personal data): [docs/REPORT_WRITING.md](docs/REPORT_WRITING.md), applying the [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes) shared by the SOsintOps tools

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
git clone https://github.com/SOsintOps/Aethelburg-project.git
cd Aethelburg-project

# 2. Create the virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Copy and configure environment variables
copy .env.example .env
# Edit .env with your credentials

# 5. Start Docker services
docker compose up -d

# 6. Initialise the database
python -m alembic upgrade head

# 7. Start the application
python -m src.main
```

---

## Initial data loading

The import order is **sequential and mandatory** (FK dependencies):

```bash
# Estimated total time: 4-6 hours (consumer hardware NVMe SSD, 16GB RAM)

python -m src.etl.import_sanctions     # UK Sanctions OFSI (~5 min)
python -m src.etl.import_icij          # ICIJ Offshore Leaks (~1h)
python -m src.etl.import_companies     # Companies House 5.67M (~1-2h)
python -m src.etl.import_psc           # PSC Snapshot 15M (~2-3h)
```

Companies House data can be downloaded from:
- [Companies House Data Products](https://download.companieshouse.gov.uk/en_output.html)
- [PSC Snapshot](https://download.companieshouse.gov.uk/en_pscdata.html)

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
└── pyproject.toml
```

---

## Data and licences

| Dataset | Licence | Notes |
|---------|---------|-------|
| Companies House | OGL v3 | Open Government Licence |
| ICIJ Offshore Leaks | ODbL 1.0 (database), CC BY-SA 3.0 (contents) | Attribution to ICIJ, share-alike |
| OpenSanctions | CC BY-NC 4.0 | Non-commercial; commercial licence from OpenSanctions |
| FollowTheMoney | MIT | OCCRP |
| [FT3](https://github.com/stripe/ft3) Framework | MIT | Stripe |

See [docs/LEGAL.md](docs/LEGAL.md) for the full licence analysis.

---

## Documentation and related projects

- [FAQ](docs/FAQ.md) · [Report writing](docs/REPORT_WRITING.md) · [Architecture](docs/ARCHITECTURE.md) · [Design: intelligence](docs/DESIGN_INTELLIGENCE.md) · [Ontology](docs/ONTOLOGY.md) · [Data sources](docs/DATA_SOURCES.md) · [Setup](docs/SETUP.md) · [Legal](docs/LEGAL.md)
- Related SOsintOps projects: [Quaesitor](https://github.com/SOsintOps/quaesitor) (case graph with Follow the Money relations), [Wukong](https://github.com/SOsintOps/Wukong) (Chinese corporate due diligence), [Argos](https://github.com/SOsintOps/Argos) and [Speculator](https://github.com/SOsintOps/Speculator-Project) (OSINT workstations), [Exploratores](https://github.com/SOsintOps/Exploratores) (browser toolkit with company-register searches), [Claudii Exploratores](https://github.com/SOsintOps/claudii-exploratores) (the same catalogue as a Claude agent skill), [Acta Diurna](https://github.com/SOsintOps/acta-diurna) (Italian law-enforcement news dashboard), [Il Conclave](https://github.com/SOsintOps/il-conclave) (ACH and premortem as an AI skill, in Italian), [Codex Machinae](https://github.com/SOsintOps/codex-machinae) (playbook for building software with LLMs, including FT3), [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes) (the shared method)

---

## Technologies

`Python 3.12` · `PySide6` · `PostgreSQL 16` · `PostGIS` · `pgvector` · `Apache AGE` · `Leaflet.js` · `cytoscape.js` · `FollowTheMoney` · `sentence-transformers` · `SQLAlchemy` · `Alembic` · `Docker`
