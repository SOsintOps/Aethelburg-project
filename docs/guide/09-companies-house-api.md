# Companies House API

## Update from CH

The **Update from CH** button in the dossier downloads, for the selected company:

- the company profile (name, status, registered office, dates, SIC codes, accounts, previous names);
- every officer appointment, current and past (all pages, not only the first 35);
- every PSC statement;
- the filing history (every form filed: date, form type, description, pages).

The data is written with the same rules as the bulk import, then FT3 scoring runs again. Pressing it twice does not create duplicates.

A company that is not in the database yet (for example one found in the search index) is created from its profile: use **Fetch** next to it in the search results.

## Documents

The **Documents** card in the dossier lists the filing history, newest first. **Get filing list** / **Refresh list** downloads it on its own; **PDF** downloads one filing through the Companies House Document API and opens it; **Open** shows a document already downloaded; **Download all accounts** fetches every accounts filing that has an image. Files are kept in `documents\<company number>` inside the data folder and never downloaded twice. A filing without an image (some paper filings) shows —.

## Keys (7. Settings)

**7. Settings** holds the two keys. Paste a key and press **Save keys**: it is saved in the `app_settings` table of the database and used at once by **Update from CH**, **Fetch**, the documents and the live updates. **Test with Companies House** asks Companies House whether each key is accepted (the REST key reads one company, the Streaming key opens the stream and closes it). **Remove** deletes a saved key; the keyring key, if any, is used again.

Each key shows where it comes from: *saved here (database)*, *system keyring*, or *environment variable*, which wins over the page. A key pasted twice, or with spaces in it, is refused before it is saved. The other settings on the page are the daily update, how many backups to keep, the co-registration hub threshold (see [Risk scoring](risk-scoring)), and where the data folder, database and user settings file are.

Saved keys are stored in the database file, so they are also in its backups.

## Limits and errors

Companies House allows **600 requests every 5 minutes** per key. Aethelburg spaces its requests to stay inside the limit; a company with many officers can take several requests.

| Message | Meaning | What to do |
|---|---|---|
| No Companies House API key configured | no REST key saved | paste it in **7. Settings** |
| rejected the API key (401) | the key is wrong, revoked, or a Streaming key in the REST field | create a new key and save it again in **7. Settings** |
| Not found on Companies House | the company number does not exist | check the number |
| rate limit exceeded | too many requests in 5 minutes | wait a few minutes |
| Invalid company number | not 1 to 8 letters and digits | numbers like `123456` are padded to `00123456` |

## People across the whole register

Type a name in the search box and press **Search officers on Companies House**: every officer whose name contains all the words typed, with date of birth (month and year) and address, and for each one the list of appointments, current and past, with **Fetch** to load the company. Companies House returns loose matches; Aethelburg keeps only full-name matches.

## What the stream adds

The REST API answers one company at a time. To follow the whole register continuously use the Streaming API in [Data & Updates](data-and-updates).
