# Fonti dati — Aethelburg

## Companies House — Bulk Data

**URL**: https://download.companieshouse.gov.uk/en_output.html
**Formato**: CSV zippato, aggiornamento mensile
**Dimensione**: ~600MB ZIP → 2.6GB CSV → ~40GB in PostgreSQL con indici
**Licenza**: Open Government Licence v3.0
**Contenuto**: 5.67M aziende registrate in UK

Campi principali:
- `CompanyNumber` — identificatore unico, chiave primaria di sistema
- `CompanyName`, `PreviousName_1..10` — storia dei nomi (fino a 10 cambi)
- `RegAddress.*` — indirizzo registrato (8 campi + PostCode)
- `CompanyCategory` — tipo legale (Private Limited, PLC, LLP, ...)
- `CompanyStatus` — Active, Dissolved, Liquidation, ...
- `IncorporationDate`, `DissolutionDate`
- `SICCode.SicText_1..4` — codici attività (formato testo "74100 - descrizione")
- `Accounts.*`, `Returns.*` — stato dei depositi
- `Mortgages.*` — conteggi ipoteche

Note tecniche:
- Date come stringhe vuote `""` (non NULL) per record senza data
- SIC come testo — richiede parsing del codice numerico
- Encoding: UTF-8 con BOM eventuale (usare `utf-8-sig`)

---

## Companies House — PSC Snapshot

**URL**: https://download.companieshouse.gov.uk/persons-with-significant-control-snapshot-2016-04-06.zip
**Formato**: JSONL — ogni riga è `{"company_number":"...","data":{...}}`
**Dimensione**: ~2GB ZIP → 12GB JSONL → ~25GB in PostgreSQL
**Aggiornamento**: Snapshot giornaliero disponibile
**Licenza**: Open Government Licence v3.0

Tipi di record nel campo `data.kind`:
- `individual-person-with-significant-control` — persona fisica
- `corporate-entity-person-with-significant-control` — società
- `legal-person-person-with-significant-control` — ente legale
- `super-secure-person-with-significant-control` — protetto (dati oscurati)

Campi chiave (individual):
- `name_elements` — nome strutturato (forename, surname, title)
- `date_of_birth` — `{month: N, year: YYYY}` (NO giorno, per privacy)
- `nationality`, `country_of_residence`
- `natures_of_control` — array (ownership-of-shares-25-to-50-percent, ...)
- `ceased` — boolean, record storico se true

Note tecniche:
- Record `super-secure` hanno solo company_number, nessun altro dato
- Caricare record `ceased: true` nella tabella storica, non come PSC attivo
- `natures_of_control` richiede tabella separata (relazione 1-N)

---

## UK Sanctions — OFSI Consolidated List

**URL**: https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets
**Formato**: Semicolon-delimited, ~57K righe (una riga per alias/indirizzo)
**Dimensione**: 47MB
**Licenza**: OGL v3
**Stato**: OBSOLETO — OFSI ha smesso di aggiornare il 28 gennaio 2026

⚠️ Usare OpenSanctions come fonte primaria per sanzioni UK.

Note tecniche:
- Riga 0: `Report Date: DD-MM-YYYY` — da saltare
- Encoding: UTF-8 con caratteri problematici — usare `errors='replace'`
- Campo `business_registration_number` è **sempre vuoto** — il matching con CH avviene per nome
- Più righe per la stessa entità sanzionata (una per alias, una per indirizzo)

---

## OpenSanctions

**URL**: https://www.opensanctions.org/datasets/default/
**Formato**: FtM JSON (FollowTheMoney)
**Dimensione**: ~2GB
**Aggiornamento**: Giornaliero
**Licenza**: CC-BY-NC-SA 4.0 (non commerciale, share-alike)

Include:
- UK FCDO Sanctions (sostituto OFSI da febbraio 2026)
- OFAC (USA)
- EU Consolidated Sanctions
- 326 altre fonti globali

Download bulk gratuito per uso non commerciale. Registrazione consigliata per API key (aumenta rate limit).

---

## ICIJ Offshore Leaks Database

**URL**: https://offshoreleaks.icij.org/pages/database
**Formato**: CSV (5 file)
**Dimensione**: ~500MB ZIP
**Aggiornamento**: Periodico (non giornaliero)
**Licenza**: CC-BY-NC

File inclusi:
| File | Record | Dimensione |
|------|--------|-----------|
| `nodes-entities.csv` | 814,617 | 190MB |
| `nodes-officers.csv` | 771,369 | 87MB |
| `nodes-intermediaries.csv` | ~25K | 3.8MB |
| `nodes-others.csv` | ~5K | 390KB |
| `relationships.csv` | 3,339,272 | 248MB |

Fonti incluse: Panama Papers, Pandora Papers, Paradise Papers, Offshore Leaks, Bahamas Leaks

Note tecniche:
- `node_id` NON stabile tra release annuali — non usare come FK cross-dataset persistente
- `sourceID` identifica la fonte (Panama Papers, ecc.)
- Stessa entità può apparire in leak diversi con node_id diversi
- Import order: entities+officers prima, relationships dopo (FK)

---

## Companies House — Accounts Data

**URL**: https://download.companieshouse.gov.uk/en_accountsdata.html
**Formato**: iXBRL (ZIP mensili)
**Dimensione**: Variabile, ~GB per mese
**Licenza**: OGL v3
**Stato**: Non ancora integrato — previsto in fase successiva

Contiene bilanci strutturati per le società che li depositano. Utile per: rilevare aziende con revenues anomale rispetto al tipo dichiarato, dormant companies con assets nascosti.

---

## Dataset aggiuntivi consigliati

### ONSPD (ONS Postcode Directory)
**URL**: https://geoportal.statistics.gov.uk/
**Formato**: CSV
**Dimensione**: ~100MB
**Licenza**: OGL v3
**Uso**: Centroidi PostCode UK per geo-intelligence di massa (alternativa rapida a Nominatim per mapping iniziale)

### ONS Open Geography — Boundaries
**URL**: https://geoportal.statistics.gov.uk/
**Formato**: GeoJSON/Shapefile
**Licenza**: OGL v3
**Uso**: Boundary PostCode, Local Authority, County per choropleth aggregation

### Land Registry Price Paid
**URL**: https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads
**Formato**: CSV
**Licenza**: OGL v3
**Uso**: Incrociare proprietà immobiliari con aziende suspicious (futuro)

---

## EveryPolitician

**URL**: https://github.com/everypolitician/everypolitician-data
**Formato**: CSV/JSON per paese (strutturato per mandato e partito)
**Aggiornamento**: Archiviato ~2019, dati storici disponibili su GitHub
**Licenza**: Variabile per paese, prevalentemente CC0 / pubblico dominio
**Uso**: PEP (Politically Exposed Persons) — incrocio direttori/PSC con politici noti

Include:
- ~233 paesi
- Nomi, partiti, mandati, legislature
- Copertura storica dei mandati (utile per periodi passati non coperti da OpenSanctions)

Note tecniche:
- OpenSanctions include già PEP data da 5+ fonti (Wikidata PEP list, etc.)
- EveryPolitician aggiunge copertura storica e mandati passati
- Import opzionale: caricare solo paesi rilevanti (UK, UE, OFAC jurisdictions)
- Matching via `fingerprints.generate(name)` — gestisce nomi in qualunque script
- Nuovo pattern FT3: director/PSC con connessione PEP → risk flag elevated

Campi chiave:
- `name` — nome del politico
- `country` — paese
- `group` — partito/fazione
- `start_date`, `end_date` — periodo mandato
- `legislative_period_id` — identificatore legislatura
