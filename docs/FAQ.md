# FAQ — Aethelburg

## Installation and setup

**Q: Is Docker required?**
The PostgreSQL database (with PostGIS, pgvector and Apache AGE) runs in Docker. It is the most reliable way on Windows to have all extensions compiled correctly. Without Docker the system will not start.

**Q: How much disk space is needed?**
- Full PostgreSQL database (all sources): ~80–120GB
- Raw datasets (data/): ~15GB
- ML model sentence-transformers: ~80MB
- MBTiles UK map tiles: ~2–5GB (optional, for offline use)
- Recommended total: at least 200GB free on SSD

**Q: Does it work on an external SSD or HDD?**
The initial data import (especially the 12GB PSC file) is much slower on HDD — estimate 6-12 hours instead of 2-4. For normal use after import, an HDD is acceptable.

**Q: How much RAM is needed?**
16GB is the recommended minimum. With 8GB the system can be used, but the PSC import requires smaller chunk sizes and some network analyses may fail on large subgraphs.

---

## Data

**Q: How do I update Companies House data?**
Companies House publishes a new bulk snapshot monthly. APScheduler manages the automatic download and differential loading. You can also trigger it manually from `Settings → Data update`.

**Q: How do I update sanctions?**
OpenSanctions publishes daily updates. The system automatically downloads the dataset every night (if the application is open) or on the next start.

**Q: Is the UK Sanctions OFSI file up to date?**
No — OFSI stopped updating the Consolidated List on 28 January 2026. Aethelburg uses OpenSanctions as the primary source, which includes UK FCDO Sanctions, OFAC and 327 other global sources.

**Q: Are ICIJ Offshore Leaks data updated automatically?**
No. ICIJ publishes periodic but not daily updates. Check https://offshoreleaks.icij.org/ for new releases and re-run `scripts/import_icij.py` manually.

**Q: Why do many companies have no coordinates on the map?**
Full geocoding of 5.67M addresses would take weeks with local Nominatim. Aethelburg uses two approaches: (1) PostCode centroids from the ONSPD dataset (immediate ~90% coverage) and (2) precise on-demand geocoding via Nominatim when the user opens a company record.

**Q: Why are officers not available for all companies?**
Companies House does not distribute officers data in bulk. They are only available via API (`/company/{id}/officers`), limited to 600 calls every 5 minutes. The system automatically fetches officers for the companies with the highest risk scores.

---

## Analysis and intelligence

**Q: What does the 0–100 risk score mean?**
It is a composite score calculated from up to 8 detection patterns. A high score does not indicate certainty of wrongdoing — it indicates statistical anomalies that warrant further investigation. Each flag is labelled with an FT3 technique ID to document the rationale.

**Q: How many false positives are there?**
It depends on the pattern. The "shared address" pattern alone produces many false positives (legitimate incorporation agents). The system uses a composite score: the more patterns overlap, the more reliable the signal. Never use a single flag as definitive evidence.

**Q: How does sanctions matching work when there is no company number?**
The `business_registration_number` field in the OFSI file is always empty. Matching is done by name (normalisation + Levenshtein/Jaro-Winkler). The result is expressed as a confidence score, not a definitive match. Confidence < 0.7 is shown as "possible match".

**Q: Can the system identify circular ownership?**
Yes, via Apache AGE (graph database integrated in PostgreSQL). Cypher queries search for `(A)-[:CONTROLS*1..5]->(A)` patterns (cycles). This works only when officer data is available to form the complete chain.

---

## Privacy and legality

**Q: Is it legal to use this data?**
Yes for personal use. Companies House data is Open Government Licence v3. PSC data is publicly available by law (Companies Act 2006). OpenSanctions and ICIJ are CC-BY-NC (non-commercial). See [LEGAL.md](LEGAL.md) for the full analysis.

**Q: Does GDPR / UK GDPR apply?**
PSC data contains personal data (name, partial DOB, nationality). The domestic exemption (Art. 2(2)(c) UK GDPR) covers processing for strictly personal use. Do not share or publish system output containing personal data of individuals. API queries with names of natural persons sent to external services fall outside the domestic exemption.

**Q: Can I use Aethelburg for professional or commercial purposes?**
Not in the current configuration. The CC-BY-NC licences of OpenSanctions and ICIJ prohibit commercial use. For professional use, contact OpenSanctions directly for a commercial licence.

---

## Technical

**Q: Why PySide6 and not PyQt5?**
PySide6 is the official Qt Company release, licensed under LGPL (not GPL). The API is identical to PyQt5. For a distributable desktop application, LGPL is far more flexible than GPL.

**Q: Why PostgreSQL and not SQLite?**
For the extensions: PostGIS (geospatial), pgvector (vector search), Apache AGE (graph database). None of these exist for SQLite. With 20M+ records and complex analytical queries, PostgreSQL is the only viable choice.

**Q: Is RuVector included?**
RuVector (Docker microservice for vector search with GNN self-learning) is included in docker-compose but commented out by default. It is activated manually when the vector volume exceeds ~10M and you want to enable the GNN layer. pgvector with binary quantization handles the initial use cases.

**Q: Can I run Aethelburg without Docker?**
No. PostgreSQL with the required extensions (PostGIS, pgvector, Apache AGE) cannot be installed easily on Windows without Docker. A pre-configured portable PostgreSQL could be evaluated in the future.
