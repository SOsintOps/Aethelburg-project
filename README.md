<p align="center">
  <img src="assets/logo.png" alt="Aethelburg" width="260"/>
</p>

# Aethelburg (`v0.2.0-beta.1`)

Local investigative corporate intelligence platform for analysing UK company register data (Companies House), UK FCDO/OFSI Sanctions, and the ICIJ Offshore Leaks Database to identify shell companies and anomalous corporate structures.

**100% Compatible with the [FollowTheMoney (`FtM v3.x`)](https://followthemoney.tech/) Ontology** (interoperable with OCCRP Aleph, OpenSanctions, and [Quaesitor](https://github.com/SOsintOps/quaesitor)).

> **Personal use only.** Data is neither distributed nor shared. See [LEGAL.md](docs/LEGAL.md) for licence and compliance details.

---

## What it does

Aethelburg automatically cross-references six public data sources to produce an intelligence dossier and FT3 risk profile for UK-registered companies:

| Source | Contents | UNODC Default Grade |
|--------|----------|---------------------|
| Companies House Bulk | 5.67M companies with history, SIC codes, addresses, dates | `A1` |
| PSC Snapshot | 15M Persons with Significant Control (individual, corporate, super-secure, OE) | `B2` |
| UK FCDO / OFSI Sanctions | Official UK Sanctions List (with extracted UK BRNs & aliases) | `A1` |
| ICIJ Offshore Leaks | Panama Papers, Pandora Papers, Paradise Papers, Bahamas Leaks (6 CSVs) | `B2` |
| Companies House API | Officers/directors on-demand with local persistence | `B2` |
| ONSPD / Nominatim | UK Postcode WGS84 centroids & spatial clustering | `A1` |

The system applies **11 detection patterns** mapped to [FT3](https://github.com/stripe/ft3) (Stripe's Financial Threat Taxonomy), grades every finding using the **UNODC 4×4 system (`A1`–`X4`)** and **ICD 203 analytic confidence (`high`, `moderate`, `low`)**, and includes mandatory **innocent explanations** for balanced assessment.

---

## Quick Start (Zero-Docker Local Beta or Full Docker Stack)

```powershell
# 1. One-command Windows Quick Start (auto-bootstraps dati/aethelburg.sqlite if needed and opens UI)
.\start.ps1

# Or via CLI commands:
python -m src.main bootstrap     # Import real datasets from dati/ & run FT3 scoring
python -m src.main serve         # Start Web & API server on http://127.0.0.1:8050
python -m src.main desktop       # Launch native desktop app window
python -m src.main stats         # Show DB & FollowTheMoney entity counts
python -m src.main score         # Re-run Entity Resolution & all 11 FT3 detection rules
python -m src.main export-ftm -o dati/exports/aethelburg.ftm.json --target-only
python -m src.main report 14900101
```

---

## FollowTheMoney (`FtM v3.x`) Ontology Compatibility

Every entity and relationship in Aethelburg is stored both in high-speed relational tables and in the canonical `ftm_entities` store, validated against [`src/core/ftm_schema.json`](src/core/ftm_schema.json):

| Domain Table | FtM Schema | Key FtM Properties |
|---|---|---|
| `companies` | `Company` | `name`, `registrationNumber`, `jurisdiction`, `incorporationDate`, `dissolutionDate`, `status`, `sector`, `previousName`, `addressEntity` |
| `persons` / `pep_persons` | `Person` | `name`, `firstName`, `lastName`, `birthDate`, `nationality`, `country`, `topics` (`role.pep`) |
| `legal_entities` | `Company` / `LegalEntity` | `name`, `jurisdiction`, `registrationNumber`, `legalForm`, `topics` (`corp.offshore`) |
| `addresses` | `Address` | `full`, `street`, `city`, `postalCode`, `country`, `latitude`, `longitude` |
| `psc_ownerships` | `Ownership` | `owner`, `asset`, `role`, `percentage`, `startDate`, `endDate`, `status` |
| `directorships` | `Directorship` | `director`, `organization`, `role`, `startDate`, `endDate`, `status` |
| `sanctions` | `Sanction` + Subject | `entity`, `authority`, `authorityId`, `program`, `reason`, `provisions`, `listingDate` |
| `icij_*` | `Company` / `Person` / `Ownership` / `Directorship` / `Representation` | Full Panama/Pandora/Paradise Papers node & edge mapping |

---

## Documentation and Related Projects

- [FAQ](docs/FAQ.md) · [Report writing](docs/REPORT_WRITING.md) · [Architecture](docs/ARCHITECTURE.md) · [Design: intelligence](docs/DESIGN_INTELLIGENCE.md) · [Ontology](docs/ONTOLOGY.md) · [Data sources](docs/DATA_SOURCES.md) · [Setup](docs/SETUP.md) · [Legal](docs/LEGAL.md)
- Related SOsintOps projects: [Quaesitor](https://github.com/SOsintOps/quaesitor) · [Wukong](https://github.com/SOsintOps/Wukong) · [Argos](https://github.com/SOsintOps/Argos) · [Speculator](https://github.com/SOsintOps/Speculator-Project) · [Exploratores](https://github.com/SOsintOps/Exploratores) · [Claudii Exploratores](https://github.com/SOsintOps/claudii-exploratores) · [Acta Diurna](https://github.com/SOsintOps/acta-diurna) · [Il Conclave](https://github.com/SOsintOps/il-conclave) · [Codex Machinae](https://github.com/SOsintOps/codex-machinae) · [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes)
