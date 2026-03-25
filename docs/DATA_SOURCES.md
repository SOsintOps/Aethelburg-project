# Data Sources — Aethelburg

## Companies House — Bulk Data

**URL**: https://download.companieshouse.gov.uk/en_output.html
**Format**: Zipped CSV, monthly update
**Size**: ~600MB ZIP → 2.6GB CSV → ~40GB in PostgreSQL with indexes
**Licence**: Open Government Licence v3.0
**Content**: 5.67M companies registered in the UK

Main fields:
- `CompanyNumber` — unique identifier, system primary key
- `CompanyName`, `PreviousName_1..10` — name history (up to 10 changes)
- `RegAddress.*` — registered address (8 fields + PostCode)
- `CompanyCategory` — legal type (Private Limited, PLC, LLP, ...)
- `CompanyStatus` — Active, Dissolved, Liquidation, ...
- `IncorporationDate`, `DissolutionDate`
- `SICCode.SicText_1..4` — activity codes (text format "74100 - description")
- `Accounts.*`, `Returns.*` — filing status
- `Mortgages.*` — mortgage counts

Technical notes:
- Dates as empty strings `""` (not NULL) for records without a date
- SIC as text — requires parsing of the numeric code
- Encoding: UTF-8 with optional BOM (use `utf-8-sig`)

---

## Companies House — PSC Snapshot

**URL**: https://download.companieshouse.gov.uk/persons-with-significant-control-snapshot-2016-04-06.zip
**Format**: JSONL — each line is `{"company_number":"...","data":{...}}`
**Size**: ~2GB ZIP → 12GB JSONL → ~25GB in PostgreSQL
**Update**: Daily snapshot available
**Licence**: Open Government Licence v3.0

Record types in the `data.kind` field:
- `individual-person-with-significant-control` — natural person
- `corporate-entity-person-with-significant-control` — company
- `legal-person-person-with-significant-control` — legal entity
- `super-secure-person-with-significant-control` — protected (data redacted)

Key fields (individual):
- `name_elements` — structured name (forename, surname, title)
- `date_of_birth` — `{month: N, year: YYYY}` (NO day, for privacy)
- `nationality`, `country_of_residence`
- `natures_of_control` — array (ownership-of-shares-25-to-50-percent, ...)
- `ceased` — boolean, historical record if true

Technical notes:
- `super-secure` records contain only company_number, no other data
- Load `ceased: true` records into the historical table, not as active PSC
- `natures_of_control` requires a separate table (1-N relationship)

---

## UK Sanctions — OFSI Consolidated List

**URL**: https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets
**Format**: Semicolon-delimited, ~57K rows (one row per alias/address)
**Size**: 47MB
**Licence**: OGL v3
**Status**: OBSOLETE — OFSI stopped updating on 28 January 2026

⚠️ Use OpenSanctions as the primary source for UK sanctions.

Technical notes:
- Row 0: `Report Date: DD-MM-YYYY` — must be skipped
- Encoding: UTF-8 with problematic characters — use `errors='replace'`
- Field `business_registration_number` is **always empty** — matching with CH is by name
- Multiple rows per sanctioned entity (one per alias, one per address)

---

## OpenSanctions

**URL**: https://www.opensanctions.org/datasets/default/
**Format**: FtM JSON (FollowTheMoney)
**Size**: ~2GB
**Update**: Daily
**Licence**: CC-BY-NC-SA 4.0 (non-commercial, share-alike)

Includes:
- UK FCDO Sanctions (OFSI replacement from February 2026)
- OFAC (USA)
- EU Consolidated Sanctions
- 326 other global sources

Free bulk download for non-commercial use. Registration recommended for API key (increases rate limit).

---

## ICIJ Offshore Leaks Database

**URL**: https://offshoreleaks.icij.org/pages/database
**Format**: CSV (5 files)
**Size**: ~500MB ZIP
**Update**: Periodic (not daily)
**Licence**: CC-BY-NC

Included files:
| File | Records | Size |
|------|---------|------|
| `nodes-entities.csv` | 814,617 | 190MB |
| `nodes-officers.csv` | 771,369 | 87MB |
| `nodes-intermediaries.csv` | ~25K | 3.8MB |
| `nodes-others.csv` | ~5K | 390KB |
| `relationships.csv` | 3,339,272 | 248MB |

Sources included: Panama Papers, Pandora Papers, Paradise Papers, Offshore Leaks, Bahamas Leaks

Technical notes:
- `node_id` is NOT stable across annual releases — do not use as a persistent cross-dataset FK
- `sourceID` identifies the source (Panama Papers, etc.)
- The same entity may appear in different leaks with different node_ids
- Import order: entities+officers first, relationships after (FK)

---

## Companies House — Accounts Data

**URL**: https://download.companieshouse.gov.uk/en_accountsdata.html
**Format**: iXBRL (monthly ZIPs)
**Size**: Variable, ~GB per month
**Licence**: OGL v3
**Status**: Not yet integrated — planned for a later phase

Contains structured financial statements for companies that file them. Useful for: detecting companies with revenues anomalous relative to their declared type, and dormant companies with hidden assets.

---

## Recommended additional datasets

### ONSPD (ONS Postcode Directory)
**URL**: https://geoportal.statistics.gov.uk/
**Format**: CSV
**Size**: ~100MB
**Licence**: OGL v3
**Use**: UK PostCode centroids for bulk geo-intelligence (fast alternative to Nominatim for initial mapping)

### ONS Open Geography — Boundaries
**URL**: https://geoportal.statistics.gov.uk/
**Format**: GeoJSON/Shapefile
**Licence**: OGL v3
**Use**: PostCode, Local Authority, and County boundaries for choropleth aggregation

### Land Registry Price Paid
**URL**: https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads
**Format**: CSV
**Licence**: OGL v3
**Use**: Cross-reference property ownership with suspicious companies (future)

---

## EveryPolitician

**URL**: https://github.com/everypolitician/everypolitician-data
**Format**: CSV/JSON per country (structured by term and party)
**Update**: Archived ~2019, historical data available on GitHub
**Licence**: Varies by country, predominantly CC0 / public domain
**Use**: PEP (Politically Exposed Persons) — cross-reference directors/PSC with known politicians

Includes:
- ~233 countries
- Names, parties, terms, legislatures
- Historical mandate coverage (useful for past periods not covered by OpenSanctions)

Technical notes:
- OpenSanctions already includes PEP data from 5+ sources (Wikidata PEP list, etc.)
- EveryPolitician adds historical coverage and past mandates
- Optional import: load only relevant countries (UK, EU, OFAC jurisdictions)
- Matching via `fingerprints.generate(name)` — handles names in any script
- New FT3 pattern: director/PSC with PEP connection → elevated risk flag

Key fields:
- `name` — politician's name
- `country` — country
- `group` — party/faction
- `start_date`, `end_date` — term period
- `legislative_period_id` — legislature identifier
