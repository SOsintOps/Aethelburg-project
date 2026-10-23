<p align="center">
  <img src="assets/aethelburg-logo.png" alt="Aethelburg — Chartae Regni" width="460"/>
</p>

# Aethelburg (`v0.3.0-beta.1`)

[![CI](https://github.com/SOsintOps/Aethelburg-project/actions/workflows/ci.yml/badge.svg)](https://github.com/SOsintOps/Aethelburg-project/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/SOsintOps/Aethelburg-project?include_prereleases&sort=semver)](https://github.com/SOsintOps/Aethelburg-project/releases)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)](docs/SETUP.md)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![FollowTheMoney](https://img.shields.io/badge/FollowTheMoney-v3.x-0b7285)](https://followthemoney.tech/)
[![Last commit](https://img.shields.io/github/last-commit/SOsintOps/Aethelburg-project)](https://github.com/SOsintOps/Aethelburg-project/commits/main)

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

## Installation

Aethelburg is a local application: it needs **Python 3.12 or newer** (3.13 recommended) and `git`, nothing else. Docker is optional and only for the PostgreSQL back end (see [`docs/SETUP.md`](docs/SETUP.md)); the default back end is SQLite.

Everything the installer puts on the machine stays in three places, so nothing else on the system is touched:

| What | Windows | Linux |
|---|---|---|
| Program and every Python dependency | `.venv\` inside the project folder | `.venv/` inside the project folder |
| Data folder: downloads, database, backups, documents, exports | `C:\AethelburgData` (changeable in the app) | `~/AethelburgData` (changeable in the app) |
| Preferences (a few lines: data folder, backups to keep, hub threshold) | `%APPDATA%\Aethelburg\config.toml` | `~/.config/aethelburg/config.toml` |

To uninstall, delete those three. Companies House keys, if you choose the system keyring instead of the Settings page, are the only other trace (Windows Credential Manager, or the Secret Service / KWallet on Linux).

### Windows

In PowerShell:

```powershell
git clone https://github.com/SOsintOps/Aethelburg-project.git
cd Aethelburg-project
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

`py -3` is the Python launcher that comes with the python.org installer; `python` works too if it is on the PATH. The `[ftm]` extra (`followthemoney`, `fingerprints`) needs PyICU, which has no Windows wheel for Python 3.13: the program has pure-Python fallbacks, so leave it out.

### Linux (Debian, Ubuntu and derivatives)

```bash
sudo apt install python3 python3-venv python3-pip git
git clone https://github.com/SOsintOps/Aethelburg-project.git
cd Aethelburg-project
python3 -m venv .venv
.venv/bin/python -m pip install -e .
chmod +x start.sh
```

Optional, for the full FollowTheMoney tool chain: `sudo apt install libicu-dev pkg-config build-essential` and then `.venv/bin/python -m pip install -e ".[ftm]"`. On other distributions use the equivalent packages (`python3-venv` is part of `python3` on Fedora and Arch). The test suite runs on Ubuntu in CI; the application has had less use on Linux than on Windows, so please [report](https://github.com/SOsintOps/Aethelburg-project/issues) anything that behaves differently.

### Updating

From the project folder: `git pull`, then `pip install -e .` with the venv's Python as above, then restart. The database schema is upgraded automatically on start; make a backup first (**6. Data & Updates → Back up now**).

## Starting the application

| | Windows (PowerShell) | Linux |
|---|---|---|
| Open in your browser | `.\start.ps1` | `./start.sh` |
| Server only (open http://127.0.0.1:8050 yourself) | `.venv\Scripts\python.exe -m src.main serve` | `.venv/bin/python -m src.main serve` |
| Another port | add `-Port 8060` / `--port 8060` | add `--port 8060` |

Both scripts use the project's `.venv` and stop with Ctrl+C. The browser window is the whole interface; nothing listens outside `127.0.0.1`.

**First run**: open **6. Data & Updates** → **Download all** → **Run import** (the Companies House bulk files are several gigabytes; the import is resumable). The **? Help** button (or F1) opens the full user guide; the chapters are also in [`docs/guide/`](docs/guide/).

**Companies House keys** (free, from the developer hub: one *REST* key for **Update from CH** and **Fetch**, one *Streaming* key for live updates) are pasted in **7. Settings**, which saves them in the local database and checks them with Companies House. The system keyring still works as an alternative:

```
.venv\Scripts\python.exe -m keyring set aethelburg ch_api_key          # Windows
.venv/bin/python -m keyring set aethelburg ch_api_key                  # Linux
```

and the same with `ch_streaming_key`.

## Keeping data up to date

| What | How |
|---|---|
| Data folder (downloads, database, exports) | default `C:\AethelburgData`; change it in the Data tab or with `data location PATH --move` |
| Bulk sources (Companies House companies and PSC, UK Sanctions List, ONS Postcode Directory) | `data status` shows local vs latest release; `data download` gets new releases (resumable, never twice) |
| What gets imported | every UK company goes into a light search index; a subset chosen in [`config/subset.toml`](config/subset.toml) (risk links, mass addresses, recent incorporations) is imported in full with PSC and FT3 scoring — `data import`, resumable |
| Live changes | `data watch` (or **Start** in the Data tab) follows the Companies House Streaming API and resumes from its last timepoint |
| Monthly catch-up | `data download` + `data import` after each monthly Companies House release, or whenever the stream reports a gap |
| One company now | **Update from CH** in the dossier |

Other commands: `stats`, `score`, `report CRN`, `export-ftm`, `import-ftm FILE`, `import-onspd FILE` — see the [command line chapter](docs/guide/12-cli-reference.md).

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

- [User guide](docs/guide/01-getting-started.md)
- [FAQ](docs/FAQ.md)
- [Report writing](docs/REPORT_WRITING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Design: intelligence](docs/DESIGN_INTELLIGENCE.md) 
- [Ontology](docs/ONTOLOGY.md)
- [Data sources](docs/DATA_SOURCES.md)
- [Setup](docs/SETUP.md)
- [Legal](docs/LEGAL.md)

Related SOsintOps projects: 
- [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes) (method notes on sourcing, grading and reporting) 
- [Exploratores](https://github.com/SOsintOps/Exploratores) (browser OSINT toolkit; its Public Company Records page searches OpenSanctions and SanctionsKit for officers and companies)

## Contributing and licence

Bug reports and proposals are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

The code is released under the [MIT licence](LICENSE). The data it processes keeps its own licence (Open Government Licence, ICIJ, OpenSanctions): see [NOTICE](NOTICE) and [LEGAL.md](docs/LEGAL.md).
