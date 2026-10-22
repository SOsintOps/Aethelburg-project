# Frequently Asked Questions (FAQ)

The user guide (the **? Help** button, or `docs/guide/` in the repository) explains every tab and command; this page answers the questions people ask most.

## Installation and data

### Do I need Docker or PostgreSQL?

No. Aethelburg runs on Windows with Python and a local SQLite database: `python -m venv .venv`, `.venv\Scripts\python.exe -m pip install -e .`, then `start.ps1`. The PostgreSQL schema in `migrations/` is kept for a future server deployment but is not needed.

### How much disk space is needed?

About 3.3 GB of downloads, which unpack to about 17 GB (the PSC snapshot alone is 14 GB), plus the database: about 1.5 GB for the register index and grows with the imported subset (several GB for a subset of one million companies). Put the data folder on a disk with at least 50 GB free; it can be moved at any time (**6. Data & Updates → Data folder**).

### Where is my data?

In the data folder, `C:\AethelburgData` by default: `downloads\`, `aethelburg.sqlite`, `backups\`, `exports\`, `logs\`. Nothing is uploaded anywhere; the only network traffic is downloads from the publishers and requests to Companies House.

## Keeping data up to date

### How do I update the data?

Three levels, all in **6. Data & Updates** (and on the command line):

- **Daily update** (`data daily`, or on a schedule while Aethelburg is open): downloads new releases, imports when something changed, fetches officers of new flagged companies.
- **Live updates** (`data watch`, Streaming key needed): every change filed at Companies House, as it happens.
- **One company now**: **Update from CH** in the dossier.

To run the daily update even when Aethelburg is closed, create a Windows scheduled task yourself, for example:

```
schtasks /Create /SC DAILY /ST 06:00 /TN "Aethelburg daily update" /TR "\"C:\path\to\Aethelburg-project\.venv\Scripts\python.exe\" -m src.main data daily"
```

(run it from the project folder, or set the task's "Start in" to the project folder).

### How do I download the PSC (persons with significant control)?

- **All of them**: the PSC snapshot is published every day by Companies House. **Download** it in the Data tab (`data download -s ch_psc`) and **Run import**: the PSC of the companies in your subset are imported, and the snapshot is also used to select the subset (foreign/offshore/super-secure controllers, chosen nationalities).
- **One company**: **Update from CH** in the dossier downloads its current PSC statements.

### How do I download the officers (directors, secretaries)?

Companies House does not publish officers in a free bulk file: they come from the API, one company at a time, within 600 requests every 5 minutes (about 7,000 companies per hour).

- **One company**: **Update from CH**.
- **Many companies**: **Fetch officers** in the Data tab, or `data officers --scope flagged|case|subset`. The run is resumable and skips companies fetched in the last 30 days.
- **One person across the whole register**: type the name in the search box and press **Search officers on Companies House**: every appointment of that person, current and past, with **Fetch** for each company.

### How are changes to a company handled?

Every update (monthly bulk, live stream, Update from CH) overwrites the company's current registry fields — name, status, address, accounts dates — while its risk score, FT3 flags and your case notes are kept. Previous names come from Companies House itself; officer appointments and PSC statements keep their start and end dates, so resignations and ceased controllers stay visible in the timeline.

Before overwriting, Aethelburg compares the stored company with the update and records every difference in a **change history**: address, status, name, category, SIC codes, dissolution date, accounts and confirmation statement filed, number of charges, plus officers appointed or resigned and PSC added or ceased. Each change keeps the old and new value, when it was observed and the source (for example `ch_companies 2026-11-01`, `ch_stream`, `ch_api`). The first load of a company is not a change, and the same value written differently by two sources (upper case in the bulk file, mixed case in the API) is not either; addresses are compared by their fingerprint (postcode, house number, street). Changes appear in the company's timeline and in **Data & Updates → Recent changes**, which filters by type and exports CSV (`/api/data/changes?format=csv`). History starts from this version: earlier updates were not recorded.

### Can Aethelburg download company documents (accounts, confirmation statements)?

Yes, on request. **Update from CH** also downloads the company's **filing history** (every form filed, with date, type and description; it appears in the dossier's **Documents** card and in the timeline). From that card, **PDF** downloads one filing and **Download all accounts** all the accounts with an image; the files go to `<data folder>\documents\<company number>\<date>-<form>-<transaction>.pdf`, are never downloaded twice and open in the browser. They come from the Companies House Document API with the same REST key and the same rate limit (600 requests per 5 minutes; a document costs about 2 requests). Some old or paper filings have no image (shown as —).

The daily update can also fetch the latest accounts and confirmation statement of the 50 highest-risk flagged companies (*also download latest documents* in the Data tab, off by default). Importing the figures of the accounts (iXBRL bulk files) is not part of Aethelburg yet.

### Are sanctions and ICIJ data updated?

The **UK Sanctions List** (FCDO, the only UK list since the OFSI Consolidated List closed on 28 January 2026) is downloaded and imported with the other sources. **ICIJ Offshore Leaks** is a static archive: replace the folder `ICIJ Offshore Leaks Database` when ICIJ publishes a new release.

## Backups and errors

### Is there a backup?

Yes. **Back up now** in the Data tab (`data backup`) makes a consistent copy in `backups\`; one is made automatically before every import; the newest 7 are kept. **Restore** (`data restore NAME`) backs up the current database first.

### Something went wrong: where do I look?

`<data folder>\logs\aethelburg.log`. Unexpected errors in the interface show an **error id**: search that id in the log to find the full details. Downloads retry by themselves; an interrupted import continues from where it stopped with **Run import**.

## Analysis

### What does the 0–100 risk score mean?

The sum of the FT3 techniques a company matches, capped at 100. It ranks what to look at first; it is not a verdict. Every technique lists the lawful situations that produce the same pattern (see *Risk scoring* in the guide).

### Why do some ICIJ matches look wrong?

The subset selection matches ICIJ names to UK company names without a registration number, so common names produce coincidences. Treat an ICIJ match as a lead to verify (UNODC grade C), not as a link.

### Why are some positions on the map approximate?

Without the ONS Postcode Directory a company sits at the centre of its postcode district or area (dashed ring). Import ONSPD for exact positions.

### Can I search for a person?

Yes: the search box finds people (PSC and officers) in your database by any order of their names, with their companies; **Search officers on Companies House** extends the search to the whole UK register.

## Privacy and legality

### Is it legal to use this data?

Companies House, the UK Sanctions List and the ONS Postcode Directory are published under the Open Government Licence v3.0; ICIJ data under ODbL / CC BY-SA. See `docs/LEGAL.md`.

### Does UK GDPR apply?

Yes: directors and PSC are personal data. Keep the data in your data folder, share findings rather than raw records, and keep a lawful basis for each investigation.

## Versions

### How do I know what changed in a version?

**? Help → Version history** shows the changelog; the version is in the top bar and footer. Versions follow Semantic Versioning (`MAJOR.MINOR.PATCH`, with `-beta.N` while the program is in beta).

### How do I update the program?

`git pull`, then `.venv\Scripts\python.exe -m pip install -e .` and restart. The database is upgraded automatically on start; make a backup first.
