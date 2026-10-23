# Changelog — Aethelburg

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, with `-beta.N` while the program is in beta. The version is shown in the top bar and footer (read from `config/settings.py`) and in `pyproject.toml`; each release is tagged `vX.Y.Z[-beta.N]` in git.

To update the program: `git pull`, `.venv\Scripts\python.exe -m pip install -e .`, restart. The database schema is upgraded automatically on start; make a backup first (**Data & Updates → Back up now**).

---

## [Unreleased]

### Added (screenshots)
- Screenshots of every tab in the user guide (`docs/guide/images/`, 1920×1080), one in the README. The in-app help renders them too (`/guide/images/` is served from `docs/guide/images`; an image on its own line in a chapter is shown). The GeoINT one shows London.

### Changed (network graph)
- **Fewer crossing links.** The organic layout now computes several seeded placements, keeps the one with the fewest link crossings and links running across nodes, then swaps pairs of nodes while that removes more (UNODC step 7, "clarify and re-plot"); **Untangle** does the same with more seeds. A chart such as a company with its controllers, bridge companies and address hubs now draws without crossings. Big charts keep the layout quick (fewer seeds and passes above 60 nodes).
- **Link labels no longer cover each other or the nodes**: a label that would sit on another label or on a card slides along its own link.
- The **UNODC chart cover and key** no longer opens by itself over the chart: **Chart Key** opens it, and the chart then fits the space left beside it.

### Changed (installation)
- The README separates **Installation** (Windows and Linux, with where the program, the data and the preferences go and how to uninstall) from **Starting the application**. New `start.sh` for Linux, the counterpart of `start.ps1`. `docs/SETUP.md` and the Getting started chapter give the Linux commands too.

### Changed (co-registration hubs)
- **FT3-SC-001 is context, not evidence.** It fired from 5 companies at one address, scored up to 34 points with grade A1, and on its own flagged the company: on the full register it marked 807,791 of 1,030,987 companies (78 %), most of them ordinary customers of registered formation agents (71-75 Shelton Street alone hosts 60,933), and "flagged" meant nothing. Now: at least **20** companies at one address (changeable in **7. Settings → Risk scoring**, saved as `mass_address_threshold` in the user settings file, applied at the next re-score); a flat score of 10, 8 from 100 companies and 6 from 1,000 (the largest hubs are the least telling); grade B2, moderate confidence; and a company whose only finding is the shared address is **not** flagged. The GeoINT hub list and the score of companies with other findings keep working as before. The **Flagged Only** filter of the search list now means exactly that (companies with a finding that counts), not "score above 0". On the full register after the re-score: flagged companies 911,470 → 335,995; companies whose only finding is a shared address 533,271 (listed under *All Risk Scores*).

### Fixed
- A sanctions match of a person where only the **years** of birth could be compared (OFSI publishes `dd/mm/1976` for many designations) was graded A2 with high confidence, the same as a match on month and year. It is now B2, moderate confidence, score 35 instead of 45, and the flag says "same year of birth, the list gives no month". On the full register this concerned 2 of the 19 A2 matches, both common names.
- A sanctions match through a person who has **ceased** to be a controller was shown as a current link. The match is kept (the history matters) but the flag now says "former controller, ceased on …" and its score is reduced to 60 %; a current controller outranks a former one with the same evidence.
- **Sanctions matches of people now check the date of birth.** People with significant control were matched to sanctioned individuals on the name fingerprint alone, so namesakes were flagged as sanctioned (on the full register, 109 of 149 matched people were born in a different month or year). The sanctions import now keeps the dates of birth published by OFSI, including partial ones (`dd/mm/1945`, `1970`). A match with the same month and year is graded A2 with high confidence. A match where either side has no date is kept as B3 with low confidence and a lower score (25 instead of 42); the flag says "name only". A match whose dates disagree is dropped. People are no longer matched to sanctioned companies, and sanctioned people are normalised as people, without titles.
- ICIJ Offshore Leaks matches of people (no date of birth in the leaks) are graded C3 with low confidence and score 20 instead of 38, unless the same company also matches by company name.
- Keys read from the keyring are trimmed: a key pasted with a space or a line break was sent as is and refused.
- Generic environment variables changed the PostgreSQL settings: on Linux `$USER` became the database user and `$NAME` the database name. Only the `POSTGRES_*` variables are read now.
- The tests no longer depend on the machine: the settings tests ignore its database variables, and the end-to-end test is skipped (with the reason) when the configured database is not populated.
- The Companies House **Streaming key** stored with `python -m keyring set aethelburg ch_streaming_key` was never read (only the REST key was loaded from the keyring), so live updates reported a missing key.
- `data fix-person-names`: people imported before names were normalised without titles kept fingerprints such as `mr john smith`, and an import with the fixed rule created them again. The command (backup first) recomputes every fingerprint and FtM id, merges each duplicate into one person (PSC statements, appointments and case references moved, repeated PSC-derived appointments removed) and rewrites the old id inside Ownership and Directorship entities. Safe to run twice.

### Added (Settings page)
- **7. Settings** tab:
  - **Companies House keys**: paste the REST and Streaming keys, **Save keys**, **Test with Companies House**, **Remove**. Keys are saved in the new `app_settings` table of the database and used at once, without a restart (Update from CH, Fetch, documents, live updates). Each key shows where it comes from (saved here, system keyring, environment variable); the browser only ever receives its last four characters.
  - A key pasted twice or with spaces inside is refused before it is saved. The test tells a wrong key from a key of the other type.
  - **Daily update** (moved here from Data & Updates, where *Run now* stays) and **backups to keep**.
  - Where the data folder, database and user settings file are.
- Key order: `CH_API_KEY` / `CH_STREAMING_KEY` environment variables, then the keys saved on the Settings page, then the system keyring.
- API: `GET /api/settings`, `POST /api/settings/ch-keys`, `POST /api/settings/ch-keys/test`, `POST /api/settings/general`.

### Added (Companies House documents)
- **Filing history**: **Update from CH** also downloads every filing of the company (`filings` table: date, form type, category, description, pages); filings appear as `FILING` events in the timeline and in a **Documents** card in the dossier. List pagination now also follows `total_count`, which the filing history uses instead of `total_results`.
- **Documents on request** through the Companies House Document API (metadata, then `/content` as PDF, whose signed download address is fetched without the key): **PDF** for one filing, **Download all accounts**, **Open** for documents already on disk. Files go to `<data folder>/documents/<company number>/<date>-<form>-<transaction>.pdf` and are never downloaded twice; only `document-api.company-information.service.gov.uk` addresses are followed and file names are checked before serving.
- Optional in the daily update (*also download latest documents*, user config `documents_auto_download`, off by default): latest accounts and confirmation statement of the 50 highest-risk flagged companies.
- API: `GET /api/companies/{n}/filings`, `POST /api/companies/{n}/filings/refresh`, `POST /api/companies/{n}/documents/{transaction}`, `POST /api/companies/{n}/documents?category=accounts`, `GET /api/documents/{n}/{file}`.

### Added (change history)
- **Company change history** (`company_changes` table, created automatically on start): every update of a company already in the database (bulk import, Streaming API, Update from CH) records what changed — address, status, name, category, SIC codes, dissolution date, accounts and confirmation statement filed, number of charges — with old and new value, date observed, date of effect where known and source. Officers appointed or resigned and PSC added or ceased after the first load are recorded too.
- Not counted as changes: the first load of a company, a stub company taking its real details, a value the earlier source did not have, and the same value written differently by the bulk file and the API (case, punctuation; addresses compared by fingerprint).
- The changes appear in the company timeline and in a **Recent changes** card in the Data tab (filter by type, subset only, CSV export); API `GET /api/data/changes`.
- PSC statements keep the time they were first seen (`created_at`) when they are updated.

### Changed (repository)
- **Continuous integration** (`.github/workflows/ci.yml`): ruff and the test suite on Windows and Linux with Python 3.13, for every push to `main` and every pull request that changes code.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue forms (bug report, feature request, security link), a pull request checklist and Dependabot (monthly, Python packages and GitHub Actions).
- `LICENSE` holds only the MIT text, so GitHub recognises the licence; the third-party data notices moved to `NOTICE`. The README ends with a contributing and licence section and opens with badges for CI, release, licence, Python, platform, Ruff, FollowTheMoney and last commit.
- `.github/social-preview.png`: the 1280×640 image shown when the repository is linked.
- **New logo**, redrawn in the same style: transparent background, cropped close to the emblem (`assets/aethelburg-logo.png`, 1400 px wide, larger in the README). The drawing it comes from is kept as `assets/aethelburg-logo-source.jpg`. New square icon with the charter's gold arms, a castle over two fleurs-de-lis, on navy (`assets/aethelburg-icon.png` in the top bar, `assets/aethelburg.ico` as favicon from 16 to 256 px); every file has a new name, so no browser can show the old logo from its cache. Removed the unused `logo.svg`, `logo.jpg`, `logo-dark.png` and `roman-helmet.ico`.
- `SECURITY.md` (how to report a vulnerability, where keys belong); `.gitattributes` keeps text files LF in the repository and PowerShell scripts CRLF.
- The README lists only the related projects that share this work: Intelligence Field Notes (method) and Exploratores (sanctions and company record searches), each with what it adds.
- `pyproject.toml` declares authors, keywords, classifiers and project links.
- Removed the duplicate Inter font files at the top of `assets/` (the app uses `assets/fonts/`) and the outdated `todo.txt` (this file records what is done).
- `ruff check src tests config migrations` passes (365 findings fixed: type annotations, unused imports, a repeated key in the CJK transliteration table).
- The daily scheduler starts through the FastAPI lifespan instead of the deprecated `on_event`, and stops when the server stops.
- Every comment, docstring, script message and example file is in English (`config/`, `migrations/`, `docker/`, `scripts/setup_db.sh`, `.env.example`, `.gitignore`, `pyproject.toml`).
- `docker/Dockerfile.db` is now in the repository: the `*.db` ignore rule had kept it out, so `docker compose up db` failed on a fresh clone.
- `.env.example` no longer sets `DATA_DIR=./dati`, which overrode the data folder chosen in the app; the commented-out RuVector service is gone from `docker-compose.yml`.

---

## [0.3.0-beta.1] — 2026-10-22

### Changed
- One version everywhere (`0.3.0-beta.1`); the UI reads it from `/api/health`.
- `pyproject.toml` declares the web/CLI dependencies that were missing (FastAPI, Uvicorn, Jinja2, Typer, Rich, aiosqlite). `followthemoney` and `fingerprints` moved to the optional `[ftm]` extra (they need PyICU, which has no Windows wheel for Python 3.13; pure-Python fallbacks exist), PySide6 to `[desktop]`, WeasyPrint (unused) to `[pdf]`: `pip install -e .` now works on Windows.
- `start.ps1` uses the project virtual environment and points first-time users to the Data & Updates tab.
- `serve`/`desktop` no longer build the demo database on their own (`serve --auto-bootstrap` still can); on start they flag imports a previous run left unfinished.
- README: quick start and "Keeping data up to date".

### Added (documentation)
- **FAQ rewritten** to match the program (it described Docker, PostgreSQL, automatic APScheduler updates and features that do not exist) and answering: where the data is, how to update, how to download PSC and officers, company changes, documents, backups, logs, versions; available in the app (**? Help → FAQ**).
- **Version history** in the app (**? Help → Version history**, or click the version number); versioning and update rules at the top of this file.
- Guide chapters updated for backups, daily update, officers in bulk, officer search, logs.

### Added (officers and daily update)
- **Officers in bulk** (`data officers --scope flagged|case|subset`, *Fetch officers* in the Data tab): Companies House has no free bulk officers file, so officers come from the API one company at a time (about 7,000 companies per hour); resumable, skips companies fetched in the last 30 days, a failing company does not stop the batch.
- **Daily update** (`data daily`, or every day at a set time while Aethelburg is open — Data tab): downloads new releases (the PSC snapshot is daily), imports only when something changed (backup first), then fetches officers of up to 500 flagged companies; a day missed while the program was closed is caught up at the next start; one attempt per day.

### Added (search)
- **Officer search on the whole register**: from the people results, *Search officers on Companies House* queries the Companies House officer search (results filtered to names containing every word typed) and lists each officer's appointments, current and past, with **Fetch** for each company.
- **People search**: the search box also finds people (PSC controllers and officers) by any order of their names (`ROSSI, Mario` = `Mario Rossi`), with nationality, birth month and the companies they are linked to, each with its role.

### Added (backups)
- **Backups**: `data backup`, `data backups`, `data restore NAME` and a Backups card in the Data tab. A consistent copy (SQLite online backup, safe while the server or an import runs, integrity-checked) goes to `<data folder>/backups/` with the user config; one is made automatically before every import; the newest 7 are kept (`backup_keep`). Restoring backs up the current database first.

### Added (error handling)
- Log file `<data folder>/logs/aethelburg.log` (rotating, 5 × 5 MB) next to the console.
- Unexpected server errors return a JSON message with an **error id** that matches the traceback in the log file; failed background tasks are logged too.
- Downloads retry up to 3 times on network errors and HTTP 5xx, resuming the partial file.

### Fixed (dossier and people)
- The dossier never listed PSC controllers (the page read `pscs`, the API sends `psc_ownerships`) nor sanctions matches (`sanctions_matches` vs `sanction_matches`); legal-entity jurisdictions now show too.
- People's names were normalised as company names, so titles stayed in the fingerprint and "Mr Lorenzo Antonelli" (PSC) and "ANTONELLI, Lorenzo" (officer) became two people. Person names now drop titles everywhere (PSC import, officers, controller matching, searches). People stored before this fix keep their old fingerprint until the next import or **Update from CH**.

### Fixed (link chart)
- **Overlapping entities** in every layout: company cards are 138×46 px but the force layout kept centres only 135 px apart, positions were clamped to the window, forces had no cooling, and ring/row sizes ignored the number of nodes. New `graph-layout.js`: d3-force (many-body, links, collision on each node's real size including its label) computed before drawing, a final rectangle overlap-removal pass, rings and rows sized from the nodes, free layout then fit-to-view (**Fit** re-fits), seeded and reproducible (also **Untangle**), link labels hidden by default above 12 links, and hubs with more than 6 plain company leaves collapsed into an expandable "+N companies" node. Measured on real charts: 0 overlapping nodes in all layouts.

### Fixed (concurrent use)
- **"database is locked" during imports**: the web server and a bulk import write to the same SQLite file; connections waited only sqlite3's default 5 s for the lock. They now wait up to 60 s.
- Starting the server marked every running import as interrupted, including one still working in another process; a run is now considered interrupted only when it has not checkpointed for 10 minutes (`ingest_runs.heartbeat_at`).
- Resuming an interrupted import no longer re-runs the 15-minute subset selection.

### Fixed (Data & Updates tab)
- Bulk-source buttons looked dead: downloading a release already on disk finished in under a second and only said "completed". Each source now shows **Up to date ✓** (disabled), **Download <new release>** or **Download latest**; the task result says per source "already up to date (release …), nothing to download" or "downloaded release … (size)"; downloads show MB and percentage; **Check for new releases** shows that it is working; publishers are checked automatically when the tab is first opened and the answer is cached for 10 minutes; buttons are disabled while a task runs.
- The tab re-read every subset member (a million rows) on each refresh; counts per criterion are now stored when the subset is selected.

### Added
- **In-app user guide**: **? Help** (or F1) opens a guide with a chapter for every tab and function — getting started, interface, the six tabs, Companies House API, exports, risk scoring, command line, troubleshooting, data licences — with search; chapters live in `docs/guide/` and are served by `/api/help`.
- **6. Data & Updates tab**: data folder (change and copy), bulk sources with local and latest release, download buttons, subset filters with counts per criterion, import runs, live-update controls and status.
- **Update from CH** in the dossier and **Fetch** for search results that are only in the register index; `POST /api/companies/{n}/refresh`, `GET /api/index/search`, `GET /api/ch/status`, `/api/data/*`.
- **Bulk downloads** (`python -m src.main data status | download`): finds the latest release of Companies House Basic Company Data, the PSC snapshot, the UK Sanctions List (FCDO) and the ONS Postcode Directory, downloads it into `<data folder>/downloads/<source>/<version>/` with resume, SHA-256 and a manifest, and never downloads a release twice.
- Subset filters: the two broad criteria combine with **AND** by default (recent incorporations at mass registration addresses, about 570,000 companies; OR would select over half of the register), and a new **PSC nationality** criterion (default `Italian`) selects every company with an individual PSC of the chosen nationalities, also applied to live updates.
- **Subset import** (`python -m src.main data import`): every UK company goes into a light search index (`company_index`); the companies selected by `config/subset.toml` (risk links — sanctions, ICIJ name matches, foreign/offshore corporate PSC, super-secure PSC, plus one hop through shared controllers — mass registration addresses, recent incorporations) are imported in full with their PSC, then scored. Long steps commit in batches and resume after an interruption (`ingest_runs`).
- **Progressive updates** (`python -m src.main data watch`): follows the Companies House Streaming API (companies, officers, PSC), applies events to the subset, adds new incorporations and companies with risky PSC, keeps the index current, resumes from the saved timepoint and reports when a gap needs the monthly bulk refresh.
- ONSPD import reads the year-suffixed column names of current releases (`lad26cd`, `ctry26cd`, …) as well as the old ones.
- **Configurable data folder** for downloads, the database, exports and logs: `python -m src.main data location [PATH] [--move]`. The choice is stored in a per-user `config.toml` (`%APPDATA%\Aethelburg` on Windows); `DATA_DIR` still overrides it. Default `C:\AethelburgData`; an existing database in the old `dati/` project folder keeps being used until a folder is chosen. `--move` copies the database (SQLite backup API) and the data sub-folders and never deletes the source.
- Companies House REST client `refresh_company()`: profile, every officer appointment and every PSC statement for one company, written through the same code paths as the bulk importers. Companies that are not in the local database are created from their profile; API values are translated to the bulk wording the FT3 rules expect (`src/services/ch_mapping.py`).
- `python -m src.main import-onspd PATH` imports exact postcode centroids from an ONS Postcode Directory CSV.
- Map markers carry a `location_precision` (`postcode`, `district`, `area`); approximate positions are drawn as dashed rings with an explanation in the popup and in the legend.

### Fixed
- **Wrong cities on the map**: the postcode-area fallback kept every letter of the outward code, so `W1A`, `W1N` and `W1R` (London) were placed in Warrington, Wigan and Worcester; `SE10` was truncated to `SE1`. The area is now the leading letters only, and only a trailing sub-district letter is dropped (`EC1V` → `EC1`).
- **Invented positions**: the built-in fallback no longer adds a random offset around the area centre; existing approximate centroids are cleared on first start and re-resolved with their precision.
- **ONSPD overwritten**: syncing company postcodes replaced exact ONSPD centroids with approximate ones; approximate rows now never overwrite a `postcode`-precision row.
- **Companies House officers truncated, duplicated or silently missing**: only the first page (35) was read, every call inserted the appointments again, HTTP errors fell back to local data without a word, and companies absent from the local database failed on a foreign key. The client now pages through `total_results`, upserts appointments on a deterministic id, raises `CompaniesHouseApiError` for missing/invalid keys, unknown companies and rate limits (honouring `Retry-After` once), and validates company numbers.
- Import cycle (`src.etl` → `src.intelligence` → `src.services`) when `src.intelligence` was imported first.
- **Broken FollowTheMoney links**: ownerships and directorships referenced companies and people with ids built from lower-case schema names (`company`, `person`), while the entities themselves were stored under `Company`/`Person` ids, so 99.7% of the links in an export pointed at nothing. Ids are now consistent; a fresh bootstrap leaves only links to ICIJ nodes outside the import limits unresolved. Re-run `bootstrap` (or re-import) to rebuild existing databases.
- **Duplicated PSC controllers**: the lookup of an existing person or legal entity used a different id from the one stored, so every PSC statement created a new controller. Controllers are now reused.
- **Re-imports wiped analysis results**: companies were written with `INSERT OR REPLACE`, which deletes the row, so updating a company lost its risk score, FT3 techniques, flag and officer-fetch date. Companies are now upserted on registry fields only, and the per-address company count no longer grows on every re-import.
- **Map tiles blocked**: the UI sent no `Referer` (`<meta name="referrer" content="no-referrer">`), so OpenStreetMap served its "Access blocked" tile for every request. The page now uses `strict-origin-when-cross-origin` and the Leaflet tile layer sets the same `referrerPolicy`.

---

## [0.2.0-beta.1] — 2026-10-22

### Added
- **FollowTheMoney (`FtM v3.x`) Full Database & Ontology Compatibility**:
  - Added canonical `ftm_entities` table (JSONB + GIN indexes on PostgreSQL; JSON + indexed columns on SQLite) and `addresses` (`Address`) table, plus `ftm_id` and `ftm_schema` columns across all domain tables (`companies`, `persons`, `legal_entities`, `psc_ownerships`, `directorships`, `sanctions`, `pep_persons`, `icij_*`).
  - Added [`src/core/ftm.py`](src/core/ftm.py) and official [`src/core/ftm_schema.json`](src/core/ftm_schema.json) (synchronized with sibling project `Quaesitor`) supporting full validation, inheritance resolution (`Thing` → `LegalEntity` → `Organization` → `Company`, `Interval` → `Ownership` / `Directorship` / `Representation` / `Sanction`), and `.ftm.json` JSONL import/export.
- **Complete ETL Pipeline (`src/etl/`) for Real Datasets in `dati/`**:
  - `import_sanctions.py`: right-anchored parser for `UK-Sanctions-List.txt` handling unquoted semicolons in `Statement of Reasons` (`len(row) > 58`), consolidating records by `Unique ID` and extracting UK company registration numbers (`row[-11]`).
  - `import_icij.py`: imports all 6 ICIJ Offshore Leaks CSVs (`nodes-entities`, `nodes-officers`, `nodes-intermediaries`, `nodes-addresses`, `nodes-others`, `relationships`).
  - `import_companies.py`: streams `BasicCompanyDataAsOneFile` CSV (stripping leading spaces from headers), extracts SIC codes, and computes ADR-015 address fingerprints.
  - `import_psc.py`: handles all 6 PSC `kind` types (including `super-secure-person-with-significant-control` and Overseas Entities `OE...`) and auto-creates historical/dissolved company stubs to preserve phoenix company networks (`FT3-SC-015`).
  - `bootstrap_beta.py`: fast Beta bootstrap populating `dati/aethelburg.sqlite` with 19,200+ canonical FtM entities from `dati/`.
- **FT3 Intelligence Engine (`src/intelligence/`), Graph (`src/graph/`) & 10-Section Reports (`src/reports/`)**:
  - Implemented all 11 FT3 shell-company techniques (`FT3-SC-001` through `FT3-SC-020`) with UNODC 4×4 source/information grades (`A1`–`X4`), ICD 203 confidence levels (`high`, `moderate`, `low`), and mandatory innocent explanations.
  - Implemented multi-hop NetworkX + Cytoscape graph analysis, cycle detection, and 8 export formats (`.ftm.json`, `.xlsx`, `.csv`, `.gexf`, `.graphml`, `.dot`, `.geojson`, `.kml`) plus 10-section HTML/PDF intelligence dossiers with BLUF and SHA-256 verification.
- **Interactive 3-Panel Web & Desktop UI (`src/ui/`) & Graphic Assets (`assets/`)**:
  - Generated vector [`assets/logo.svg`](assets/logo.svg), high-resolution `1024x1024` RGBA [`assets/logo.png`](assets/logo.png), [`assets/logo-dark.png`](assets/logo-dark.png), Windows multi-size [`assets/icon.ico`](assets/icon.ico), and bundled local `Inter` (`woff2`) web fonts.
  - Built 3-panel UI (Search & FT3 Filters | Network Graph, UK Coordinate Map & Hubs, Timeline & FT3 Matrix, FtM Ontology Inspector, Casework | Entity Dossier) with Light/Dark mode and `start.ps1` / `src/main.py` CLI.

---

## [0.1.1] — 2026-10-13

### Documentation
- **Changed:** intelligence vocabulary aligned with the [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes): confidence is `high`, `moderate` or `low`; "confirmed" applies only to links graded A1, A2, B1 or B2 (UNODC 4 x 4), not as a confidence level. `DESIGN_INTELLIGENCE.md` (manual links) and `ONTOLOGY.md` (`SANCTIONED` edge, which no longer uses "probable"/"possible") updated, with a note on how the implemented `FLOAT` confidence of `casework.manual_links` maps to the three levels.
- **Changed:** report section 2 is the **Bottom line**, not an executive summary, as in `REPORT_WRITING.md`; ICD 203 and the UNODC manual linked at first mention.
- **Fixed:** licences verified at source: OpenSanctions is CC BY-NC 4.0 (not CC BY-NC-SA); the ICIJ Offshore Leaks database is under the Open Database License with contents under CC BY-SA 3.0 (not CC BY-NC). `DATA_SOURCES.md`, `LEGAL.md`, README and FAQ corrected.
- **Fixed:** the OFSI Consolidated List closed on 28 January 2026; the FCDO UK Sanctions List is the only UK source. `DATA_SOURCES.md`, `SETUP.md` and FAQ updated.
- **Docs:** FAQ restructured with a table of contents; related projects now include Codex Machinae, Acta Diurna, Il Conclave and Claudii Exploratores.

---

## [0.1.0] — Phase 0 baseline

### Added
- Initial project structure with complete documentation
- README, FAQ, LEGAL, ARCHITECTURE, DATA_SOURCES, SETUP, DESIGN_INTELLIGENCE, ONTOLOGY
- Complete architectural analysis (swarm of 5 specialised agents)
- 6-phase implementation plan (Phase 0 → Phase 5)
- Architecture Decision Records (ADR-001 — ADR-018)
- Geo-intelligence system design with ONSPD, PostGIS clustering, hotspot analysis
- Link analysis system design with Apache AGE, cytoscape.js, FT3 structural patterns
- Reporting system design with case management and multi-format export
- Multi-layer ontology v1.0.0: FtM entity model, AGE schema (7 nodes, 6 edges), FT3 taxonomy (11 patterns), casework (8 tables), data provenance
- Name normalisation engine: `fingerprints` library for multi-script names (CJK, Cyrillic, Arabic)
- `name_variants` schema with fingerprint index for O(log n) entity resolution
- PEP source: EveryPolitician supplementary to OpenSanctions (historical politicians, 233 countries)

### Documentation (2026-10-13)
- `docs/REPORT_WRITING.md`: how to write the investigation report: the risk score is an anomaly indicator and not a judgement, how to grade the register, PSC, sanctions, ICIJ and name-match sources (UNODC 4 x 4), the ten report sections with the bottom line first, personal data. It applies the [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes), the method shared by the SOsintOps tools.
- FAQ: risk score versus judgement, how to write up an investigation, related SOsintOps projects; README: documentation index and related projects.
- Fixed: the FAQ gave the old ICIJ import script (`scripts/import_icij.py`); it is `python -m src.etl.import_icij`. FT3 is Stripe's *Fraud Tools, Tactics, and Techniques* framework, now linked.

### Architectural decisions (ADR)
- **ADR-001**: pgvector as default, RuVector optional beyond 10M vectors
- **ADR-002**: pgvector binary quantization (HNSW 30GB → 4GB with <5% recall loss)
- **ADR-003**: Mandatory sequential import (Sanctions → ICIJ → Companies → PSC)
- **ADR-004**: COPY FROM STDIN for Companies House (no pandas, RAM <1GB vs >8GB)
- **ADR-005**: Staging table pattern for bulk load with clean rollback
- **ADR-006**: UK Sanctions matching by name (`business_registration_number` always empty)
- **ADR-007**: FtM on PostgreSQL via JSONB partial index (no pure EAV)
- **ADR-008**: GNN premature without bulk officers and labelled data (deferred to Phase 4+)
- **ADR-009**: ServiceRegistry singleton with Qt Signal for graceful degradation
- **ADR-010**: Docker port binding explicitly on 127.0.0.1 (not 0.0.0.0)
- **ADR-011**: ONSPD as primary geocoding source (95% day-1 coverage vs ~5% Nominatim)
- **ADR-012**: Case management in separate PostgreSQL schema `casework`
- **ADR-013**: PDF generation via WeasyPrint with QWebEngineView Qt fallback
- **ADR-014**: Definitive export formats: PDF, FtM JSON, XLSX, GEXF, GraphML, GeoJSON, KML
- **ADR-015**: `address_fingerprint` column for shared address detection (no libpostal)
- **ADR-016**: FT3 thresholds for pattern detection (circular FT3-SC-005 and sanctions FT3-SC-015 = CRITICAL)
- **ADR-017**: `fingerprints` library (MIT, OpenSanctions) as the sole multi-script name normalisation engine
- **ADR-018**: EveryPolitician as supplementary historical PEP source alongside OpenSanctions

---

## Version format

### Software versioning (MAJOR.MINOR.PATCH)

| Type | When |
|------|------|
| **MAJOR** | Backwards-incompatible changes (breaking schema, API break) |
| **MINOR** | New backwards-compatible features |
| **PATCH** | Backwards-compatible bug fixes |

### Ontology versioning (independent from software)

The ontology versions separately — see `docs/ONTOLOGY.md`.

| Type | When |
|------|------|
| **MAJOR** | Removal of AGE node/edge, change of FtM property type, removal of FT3 pattern |
| **MINOR** | New node/edge, new FT3 pattern, new FtM property |
| **PATCH** | Documentation corrections, FT3 threshold updates |

**Current ontology version**: `1.0.0`

### Database schema versioning (Alembic)

Alembic migrations track PostgreSQL schema versioning independently.
Each migration has a unique ID and a descriptive message.

| Migration ID | Version | Description |
|-------------|---------|-------------|
| `0001` | _(to be created in Phase 0)_ | Full initial schema |

### Data versioning

Data sources are tracked in the `data_sources` table (PostgreSQL) with:
- `source_version`: snapshot date or file version
- `file_hash`: SHA-256 of the source file
- `collected_at`: import timestamp

---

## Planned version roadmap

| Version | Phase | Main contents |
|---------|-------|---------------|
| `v0.1.0` | Phase 0 | Docker infrastructure, DB schema, base configuration |
| `v0.2.0` | Phase 1 | ETL Companies House + PSC + OpenSanctions |
| `v0.3.0` | Phase 2 | Risk scoring, FT3 pattern detection, shell company flags |
| `v0.4.0` | Phase 3 | PySide6 UI: search, company detail, basic map |
| `v0.5.0` | Phase 4 | Geo-intelligence, link analysis, network graph |
| `v1.0.0` | Phase 5 | Case management, reporting, full export, packaging |
