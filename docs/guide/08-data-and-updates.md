# 6. Data & Updates

This tab answers three questions: where the data is, how fresh it is, and how it is kept up to date.

## How Aethelburg gets its data

| Source | Publisher | Released | What Aethelburg uses it for |
|---|---|---|---|
| Basic Company Data | Companies House | monthly | every UK company: name, status, address, dates, SIC codes |
| PSC snapshot | Companies House | daily | persons with significant control of every company |
| UK Sanctions List | FCDO | several times a week | sanctioned people and entities, UK company numbers they control |
| ONS Postcode Directory | Office for National Statistics | quarterly | exact map position of every postcode |
| Companies House REST API | Companies House | live, on demand | full profile, officers and PSC of one company |
| Companies House Streaming API | Companies House | live, continuous | every change filed at Companies House, as it happens |

ICIJ Offshore Leaks is a static archive and is read from the `ICIJ Offshore Leaks Database` folder in the data folder (or in the old `dati` project folder).

## Data folder

Shows where the downloads, the database, exports and logs are, where the setting comes from and the free space. To move everything: type the new folder, keep **copy data** ticked and press **Change**, then restart Aethelburg. The old folder is kept; delete it yourself once you have checked the new one.

## Bulk sources

For every source: the release on disk and, after **Check for new releases**, the latest one published (shown in red when newer). **Download** gets one source, **Download all** gets them all.

- Files go to `<data folder>\downloads\<source>\<release date>\`.
- A release already on disk is never downloaded again.
- An interrupted download resumes where it stopped when the server allows it, otherwise it starts again.
- Each download is checked with SHA-256 and recorded with its source and date.

## Subset imported in full

The UK register has about 5.7 million companies. Aethelburg keeps **all of them in a light search index** (name, number, postcode, status, incorporation date) and imports **in full**, with PSC controllers and FT3 scoring, only the companies selected by these filters:

- **Risk links**: company numbers and names on the UK Sanctions List, names that match an ICIJ Offshore Leaks entity, a corporate PSC registered outside the UK or in an offshore jurisdiction, a super-secure PSC.
- **+ one hop**: the other companies controlled by the same PSC controllers.
- **Mass registration addresses**: addresses shared by at least *N* companies (default 50).
- **Recent incorporations**: incorporated in the last *N* years (default 3).
- **Live companies only** for the two broad criteria above.

**Save filters** stores your choice (in your user configuration file); **Run import** applies it. The badges show how many companies each criterion selected; a company can match several.

Any other company can still be found with the search box and loaded on demand with **Fetch** (REST key needed).

### What Run import does

1. Builds the search index from Basic Company Data.
2. Selects the subset (reads the PSC snapshot up to three times: about 14 GB each).
3. Imports the full records of the subset, then their PSC statements.
4. Imports the UK Sanctions List and the ONS Postcode Directory.
5. Runs FT3 scoring.

Every step saves its progress: if the window is closed or the computer stops, **Run import** continues from where it stopped. **Recent import runs** shows each step, its release and how many rows it wrote.

## Keeping it up to date

There are two complementary ways.

**Live updates (Streaming API).** Press **Start** (Streaming key needed). Aethelburg then receives every change filed at Companies House:

- companies already imported are updated (profile, officers, PSC);
- new incorporations join the subset when *Recent incorporations* is on;
- a company that gets a foreign, offshore or super-secure PSC joins the subset;
- every company change also updates the search index;
- FT3 scores are recalculated at most every 15 minutes while changes arrive.

Each stream remembers the last event it processed (its *timepoint*), so after a restart it continues from there. The table shows events received and applied, the timepoint and any error.

**Monthly refresh.** The stream can only go back a limited time. If Aethelburg stays off too long the stream reports a gap: then **Check for new releases**, **Download all** and **Run import** bring everything back in line. Doing this once a month (when Companies House publishes a new Basic Company Data) is a good routine even when the stream runs.

**One company now.** **Update from CH** in the dossier refreshes a single company immediately.

From the command line: `data status`, `data download`, `data import`, `data watch`; see [Command line](cli-reference).
