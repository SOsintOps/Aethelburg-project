# Aethelburg

Piattaforma desktop locale per l'analisi di dati del registro societario UK (Companies House) e l'identificazione di shell company e strutture societarie anomale.

> **Uso personale.** I dati non vengono distribuiti né condivisi. Vedere [LEGAL.md](docs/LEGAL.md) per dettagli su licenze e compliance.

---

## Cosa fa

Aethelburg incrocia automaticamente sei fonti di dati pubblici per produrre un profilo di rischio di ogni azienda registrata nel UK:

| Fonte | Contenuto |
|-------|-----------|
| Companies House Bulk | 5.67M aziende con storia, SIC, indirizzi, date |
| PSC Snapshot | 15M Persons with Significant Control con DOB e nazionalità |
| UK Sanctions / OpenSanctions | 329 fonti sanzionatorie globali (aggiornamento giornaliero) |
| ICIJ Offshore Leaks | Panama Papers, Pandora Papers, Paradise Papers |
| Companies House API | Officers/direttori per aziende ad alto rischio |
| Nominatim / ONSPD | Geocodifica e analisi spaziale degli indirizzi |

Il sistema applica pattern di detection basati su FT3 (Stripe Fraud Tactics Techniques) e produce un risk score composito per ogni azienda.

---

## Funzionalità

### Intelligence & Detection
- 8 pattern di rilevamento shell company (dissolution rapida, clustering incorporazione, SIC incongruente, PSC seriali, indirizzi condivisi, similarità nomi, connessioni offshore)
- Risk score 0–100 con tag FT3 per ogni flag attivato
- Entity resolution cross-source tramite FollowTheMoney fingerprinting

### Geo-Intelligence
- Mappa interattiva con stratificazione per zoom (choropleth → heatmap → cluster → marker)
- Clustering spaziale DBSCAN su PostCode (PostGIS ST_ClusterDBSCAN)
- Hotspot analysis: concentrazione anomala per distretto postale
- Layer tematici: sanzioni, ICIJ, aziende dissolte per area

### Link Analysis
- Grafo di rete: PSC → Company → ICIJ → Offshore
- Visualizzazione interattiva con cytoscape.js (espansione 1-hop on click)
- Pattern strutturali: star, chain, loop (ownership circolare), bridge node
- Metriche di centralità: degree, betweenness, PageRank su subgraph

### Reportistica
- Report PDF per investigazione (Jinja2 + WeasyPrint)
- Export FtM JSON (compatibile Aleph / OCCRP)
- Export grafo: GEXF (Gephi), GraphML, GeoJSON
- Case management: salvataggio sessioni investigative con annotazioni

---

## Prerequisiti

- **Windows 10/11** (64-bit)
- **Python 3.12+**
- **Docker Desktop** con WSL2 abilitato
- **Spazio disco**: ~80–120GB per DB completo
- **RAM**: 16GB consigliati (8GB minimo con dataset ridotto)

---

## Installazione rapida

```bash
# 1. Clona il repository
git clone https://github.com/tuousername/aethelburg.git
cd aethelburg

# 2. Crea l'ambiente virtuale
python -m venv .venv
.venv\Scripts\activate

# 3. Installa le dipendenze
pip install -r requirements.txt

# 4. Copia e configura le variabili d'ambiente
copy .env.example .env
# Edita .env con le tue credenziali

# 5. Avvia i servizi Docker
docker compose up -d

# 6. Inizializza il database
python -m alembic upgrade head
bash scripts/setup_db.sh

# 7. Avvia l'applicazione
python src/main.py
```

---

## Caricamento dati iniziale

L'ordine di import è **sequenziale e obbligatorio** (dipendenze FK):

```bash
# Stima tempi totali: 4-6 ore (hardware consumer SSD NVMe, 16GB RAM)

python scripts/import_sanctions.py     # UK Sanctions OFSI (~5 min)
python scripts/import_icij.py          # ICIJ Offshore Leaks (~1h)
python scripts/import_companies.py     # Companies House 5.67M (~1-2h)
python scripts/import_psc.py           # PSC Snapshot 15M (~2-3h)
```

I dati di Companies House si scaricano da:
- [Companies House Data Products](https://download.companieshouse.gov.uk/en_output.html)
- [PSC Snapshot](https://download.companieshouse.gov.uk/persons-with-significant-control-snapshot-2016-04-06.zip)

---

## Struttura del progetto

```
aethelburg/
├── src/                    # Codice sorgente
│   ├── core/               # Domain logic, detection patterns
│   ├── db/                 # SQLAlchemy models, Alembic migrations
│   ├── ui/                 # PySide6 windows e widgets
│   ├── services/           # Service layer (DB, API, Vector, Geo)
│   ├── intelligence/       # Risk scoring, FT3 mapping, entity resolution
│   ├── graph/              # Link analysis, Apache AGE, NetworkX
│   └── reports/            # Generazione report, export
├── scripts/                # Import dati, setup, utilità
├── config/                 # Configurazioni (settings.py)
├── tests/                  # Test suite
├── docs/                   # Documentazione
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## Dati e licenze

| Dataset | Licenza | Note |
|---------|---------|------|
| Companies House | OGL v3 | Open Government Licence |
| ICIJ Offshore Leaks | CC-BY-NC | Solo uso non commerciale |
| OpenSanctions | CC-BY-NC-SA | Share-alike, non commerciale |
| FollowTheMoney | MIT | OCCRP |
| FT3 Framework | MIT | Stripe |

Vedere [docs/LEGAL.md](docs/LEGAL.md) per analisi completa delle licenze.

---

## Tecnologie

`Python 3.12` · `PySide6` · `PostgreSQL 16` · `PostGIS` · `pgvector` · `Apache AGE` · `Leaflet.js` · `cytoscape.js` · `FollowTheMoney` · `sentence-transformers` · `SQLAlchemy` · `Alembic` · `Docker`
