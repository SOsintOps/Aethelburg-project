# Frequently Asked Questions (FAQ)

Frequently asked questions about Aethelburg — installation, data sources, analysis, licences and the technical choices.

## Table of Contents

* [Is Docker required?](#is-docker-required)
* [How much disk space is needed?](#how-much-disk-space-is-needed)
* [Does it work on an external SSD or HDD?](#does-it-work-on-an-external-ssd-or-hdd)
* [How much RAM is needed?](#how-much-ram-is-needed)
* [How do I update Companies House data?](#how-do-i-update-companies-house-data)
* [How do I update sanctions?](#how-do-i-update-sanctions)
* [Is the UK Sanctions OFSI file up to date?](#is-the-uk-sanctions-ofsi-file-up-to-date)
* [Are ICIJ Offshore Leaks data updated automatically?](#are-icij-offshore-leaks-data-updated-automatically)
* [Why do many companies have no coordinates on the map?](#why-do-many-companies-have-no-coordinates-on-the-map)
* [Why are officers not available for all companies?](#why-are-officers-not-available-for-all-companies)
* [What does the 0–100 risk score mean?](#what-does-the-0100-risk-score-mean)
* [How many false positives are there?](#how-many-false-positives-are-there)
* [How does sanctions matching work when there is no company number?](#how-does-sanctions-matching-work-when-there-is-no-company-number)
* [Does a high risk score mean a company is a shell?](#does-a-high-risk-score-mean-a-company-is-a-shell)
* [How do I write up an investigation?](#how-do-i-write-up-an-investigation)
* [Can the system identify circular ownership?](#can-the-system-identify-circular-ownership)
* [Is it legal to use this data?](#is-it-legal-to-use-this-data)
* [Does GDPR / UK GDPR apply?](#does-gdpr--uk-gdpr-apply)
* [Can I use Aethelburg for professional or commercial purposes?](#can-i-use-aethelburg-for-professional-or-commercial-purposes)
* [Are there related SOsintOps projects?](#are-there-related-sosintops-projects)
* [Why PySide6 and not PyQt5?](#why-pyside6-and-not-pyqt5)
* [Why PostgreSQL and not SQLite?](#why-postgresql-and-not-sqlite)
* [Is RuVector included?](#is-ruvector-included)
* [Can I run Aethelburg without Docker?](#can-i-run-aethelburg-without-docker)

---

## Installation and setup

### Is Docker required?

The PostgreSQL database (with PostGIS, pgvector and Apache AGE) runs in Docker. It is the most reliable way on Windows to have all extensions compiled correctly. Without Docker the system will not start.

### How much disk space is needed?

- Full PostgreSQL database (all sources): ~80–120GB
- Raw datasets (data/): ~15GB
- ML model sentence-transformers: ~80MB
- MBTiles UK map tiles: ~2–5GB (optional, for offline use)
- Recommended total: at least 200GB free on SSD

### Does it work on an external SSD or HDD?

The initial data import (especially the 12GB PSC file) is much slower on HDD — estimate 6-12 hours instead of 2-4. For normal use after import, an HDD is acceptable.

### How much RAM is needed?

16GB is the recommended minimum. With 8GB the system can be used, but the PSC import requires smaller chunk sizes and some network analyses may fail on large subgraphs.

---

## Data

### How do I update Companies House data?

Companies House publishes a new bulk snapshot monthly. APScheduler manages the automatic download and differential loading. You can also trigger it manually from `Settings → Data update`.

### How do I update sanctions?

OpenSanctions publishes daily updates. The system automatically downloads the dataset every night (if the application is open) or on the next start.

### Is the UK Sanctions OFSI file up to date?

No. The OFSI Consolidated List closed on 28 January 2026 and is no longer updated; since then the FCDO [UK Sanctions List](https://www.gov.uk/government/publications/the-uk-sanctions-list) is the only source for all UK sanctions designations. Aethelburg uses OpenSanctions as the primary source, which includes the UK Sanctions List, OFAC and over 300 other global sources. The OFSI importer (`python -m src.etl.import_sanctions`) still reads the old file format, so treat an OFSI file as an archive.

### Are ICIJ Offshore Leaks data updated automatically?

No. ICIJ publishes periodic but not daily updates. Check https://offshoreleaks.icij.org/ for new releases and re-run `python -m src.etl.import_icij` manually.

### Why do many companies have no coordinates on the map?

Full geocoding of 5.67M addresses would take weeks with local Nominatim. Aethelburg uses two approaches: (1) PostCode centroids from the ONSPD dataset (immediate ~90% coverage) and (2) precise on-demand geocoding via Nominatim when the user opens a company record.

### Why are officers not available for all companies?

Companies House does not distribute officers data in bulk. They are only available via API (`/company/{id}/officers`), limited to 600 calls every 5 minutes. The system automatically fetches officers for the companies with the highest risk scores.

---

## Analysis and intelligence

### What does the 0–100 risk score mean?

It is a composite score calculated from up to 8 detection patterns. A high score does not indicate certainty of wrongdoing — it indicates statistical anomalies that warrant further investigation. Each flag is labelled with an FT3 technique ID to document the rationale.

### How many false positives are there?

It depends on the pattern. The "shared address" pattern alone produces many false positives (legitimate incorporation agents). The system uses a composite score: the more patterns overlap, the more reliable the signal. Never use a single flag as definitive evidence.

### How does sanctions matching work when there is no company number?

The `business_registration_number` field in the OFSI file is always empty. Matching is done by name (normalisation + Levenshtein/Jaro-Winkler). The result is expressed as a match score (0–1), not a definitive match, and a score below 0.7 is shown as "possible match". A match score measures name similarity: it is neither a likelihood nor an analytic confidence level (high, moderate, low), which the analyst states separately in the report.

### Does a high risk score mean a company is a shell?

No. The score measures anomalies; the judgement is the analyst's. Explain which FT3 flags fired and why, name the innocent explanations you checked (formation agents, dormant companies, family businesses), and only then state a likelihood. See [REPORT_WRITING.md](REPORT_WRITING.md#the-risk-score-is-not-a-judgement).

### How do I write up an investigation?

With the bottom line first, every finding graded with the UNODC 4 x 4 system, name matches reported as "possible match" until a second identifier confirms them, and personal data kept out of anything that leaves your machine. [REPORT_WRITING.md](REPORT_WRITING.md) applies to corporate investigation the [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes), the method shared by the SOsintOps tools.

### Can the system identify circular ownership?

Yes, via Apache AGE (graph database integrated in PostgreSQL). Cypher queries search for `(A)-[:CONTROLS*1..5]->(A)` patterns (cycles). This works only when officer data is available to form the complete chain.

---

## Privacy and legality

### Is it legal to use this data?

Yes for personal use. Companies House data is Open Government Licence v3. PSC data is publicly available by law (Companies Act 2006). OpenSanctions data is [CC BY-NC 4.0](https://www.opensanctions.org/licensing/) (non-commercial); the ICIJ Offshore Leaks database is under the Open Database License and its contents under CC BY-SA 3.0, with ICIJ always cited. See [LEGAL.md](LEGAL.md) for the full analysis.

### Does GDPR / UK GDPR apply?

PSC data contains personal data (name, partial DOB, nationality). The domestic exemption (Art. 2(2)(c) UK GDPR) covers processing for strictly personal use. Do not share or publish system output containing personal data of individuals. API queries with names of natural persons sent to external services fall outside the domestic exemption.

### Can I use Aethelburg for professional or commercial purposes?

Not in the current configuration. The CC BY-NC 4.0 licence of OpenSanctions prohibits commercial use; the ICIJ licences allow it with attribution and share-alike. For professional use, contact OpenSanctions directly for a commercial licence.

---

## Related projects

### Are there related SOsintOps projects?

Yes:
- [Quaesitor](https://github.com/SOsintOps/quaesitor): a local case graph whose Follow the Money relations (ownership with percentage, directorship, payment) draw the same chains by hand.
- [Wukong](https://github.com/SOsintOps/Wukong): the China-focused workstation, whose due-diligence layer starts where a UK ownership chain reaches a Chinese company.
- [Argos](https://github.com/SOsintOps/Argos) and [Speculator](https://github.com/SOsintOps/Speculator-Project): OSINT workstations with report templates.
- [Exploratores](https://github.com/SOsintOps/Exploratores): a browser toolkit with company-register searches for several countries.
- [Elementary CTI](https://github.com/SOsintOps/elementary-CTI): ransomware threat intelligence, for when a company under review turns up as a victim.
- [Acta Diurna](https://github.com/SOsintOps/acta-diurna): an OSINT dashboard (in Italian) for news on law-enforcement operations in Italy, with source checks and structured reports, for when a company turns up in an Italian investigation.
- [Claudii Exploratores](https://github.com/SOsintOps/claudii-exploratores): the Exploratores catalogue as an agent skill and MCP server for Claude, which builds company-register search links from an indicator (alpha).
- [Il Conclave](https://github.com/SOsintOps/il-conclave): an LLM assistant skill (in Italian) that runs ACH, a premortem and other analytic procedures on a question, useful to test the "shell company or innocent explanation?" judgement.
- [Codex Machinae](https://github.com/SOsintOps/codex-machinae): the modular playbook for building software with LLM collaborators; its classification module covers the FT3 taxonomy Aethelburg uses for risk flags.
- [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes): the method all of them share.

---

## Technical

### Why PySide6 and not PyQt5?

PySide6 is the official Qt Company release, licensed under LGPL (not GPL). The API is identical to PyQt5. For a distributable desktop application, LGPL is far more flexible than GPL.

### Why PostgreSQL and not SQLite?

For the extensions: PostGIS (geospatial), pgvector (vector search), Apache AGE (graph database). None of these exist for SQLite. With 20M+ records and complex analytical queries, PostgreSQL is the only viable choice.

### Is RuVector included?

RuVector (Docker microservice for vector search with GNN self-learning) is included in docker-compose but commented out by default. It is activated manually when the vector volume exceeds ~10M and you want to enable the GNN layer. pgvector with binary quantization handles the initial use cases.

### Can I run Aethelburg without Docker?

No. PostgreSQL with the required extensions (PostGIS, pgvector, Apache AGE) cannot be installed easily on Windows without Docker. A pre-configured portable PostgreSQL could be evaluated in the future.
