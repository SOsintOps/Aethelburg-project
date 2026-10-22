# Command line

Run every command from the project folder with the project's Python:

```
.venv\Scripts\python.exe -m src.main COMMAND [OPTIONS]
```

Add `--help` to any command for its options.

## Application

| Command | What it does |
|---|---|
| `serve [--port 8050]` | starts the web interface on http://127.0.0.1:8050 |
| `desktop` | starts the interface in an app window (Edge or Chrome) |
| `stats` | counts of companies, people, flags and FtM entities |

## Data

| Command | What it does |
|---|---|
| `data location [PATH] [--move]` | shows or changes the data folder; `--move` copies the existing data |
| `data status [--offline]` | release on disk and latest published release of each bulk source |
| `data download [-s SOURCE ...]` | downloads the latest releases (`ch_companies`, `ch_psc`, `uk_sanctions`, `onspd`) |
| `data import [--no-score]` | builds the index, selects the subset, imports it, scores (resumes if interrupted) |
| `data watch` | follows the Companies House Streaming API until Ctrl+C |
| `data daily` | daily update: new releases, import if needed, officers of new flagged companies |
| `data officers [--scope flagged\|case\|subset] [--limit N]` | officers for many companies through the API (resumable) |
| `data fix-person-names` | once, after upgrading from a version before 0.3.0-beta.1: recompute person fingerprints without titles and merge the duplicates (backup first) |
| `data backup` / `data backups` / `data restore NAME` | back up, list and restore the database |
| `import-onspd FILE` | imports postcode positions from an ONS Postcode Directory CSV |
| `bootstrap` | small demonstration database from the files in the old `dati` folder |

## Analysis and exports

| Command | What it does |
|---|---|
| `score` | entity resolution and all FT3 rules |
| `report CRN` | intelligence report of a company, saved in `exports` |
| `export-ftm [-o FILE] [--target-only]` | FollowTheMoney export |
| `import-ftm FILE` | loads a FollowTheMoney file |
