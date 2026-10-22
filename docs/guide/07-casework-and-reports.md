# 5. Casework & Reports

## Investigations

The tab shows the active investigation: title, classification, working hypothesis, the companies enrolled and the analyst findings.

- Add a company with **+ Add to Case** in the dossier.
- Write a finding in the text box, choose its **UNODC grade** (source reliability A to X, information credibility 1 to 4) and **confidence** (high, moderate, low), then **Save Finding**.

New investigations can be created through the API (`POST /api/investigations`).

## Reports

**10-Sec Report** in the dossier opens the intelligence report of the company in a new tab. It has eight sections:

1. Executive summary: bottom line up front (BLUF)
2. Subject corporate profile and its FollowTheMoney mapping
3. FT3 threat assessment with innocent explanations
4. Persons with significant control and officers
5. Cross-dataset correlations (sanctions, ICIJ Offshore Leaks)
6. Geospatial and address co-registration analysis
7. Event timeline
8. Source evaluation (UNODC 4x4) and intelligence gaps

The report carries a SHA-256 hash of its content so a copy can be checked later.

Print it to PDF from the browser, or generate it from the command line with `python -m src.main report CRN`; the file is saved in the `exports` sub-folder of the data folder.

Guidance on writing reports is in `docs/REPORT_WRITING.md`.
