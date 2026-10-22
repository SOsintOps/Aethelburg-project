# Companies House API

## Update from CH

The **Update from CH** button in the dossier downloads, for the selected company:

- the company profile (name, status, registered office, dates, SIC codes, accounts, previous names);
- every officer appointment, current and past (all pages, not only the first 35);
- every PSC statement.

The data is written with the same rules as the bulk import, then FT3 scoring runs again. Pressing it twice does not create duplicates.

A company that is not in the database yet (for example one found in the search index) is created from its profile: use **Fetch** next to it in the search results.

## Limits and errors

Companies House allows **600 requests every 5 minutes** per key. Aethelburg spaces its requests to stay inside the limit; a company with many officers can take several requests.

| Message | Meaning | What to do |
|---|---|---|
| No Companies House API key configured | no REST key stored | store it, see [Getting started](getting-started) |
| rejected the API key (401) | the key is wrong or revoked | create a new key and store it again |
| Not found on Companies House | the company number does not exist | check the number |
| rate limit exceeded | too many requests in 5 minutes | wait a few minutes |
| Invalid company number | not 1 to 8 letters and digits | numbers like `123456` are padded to `00123456` |

## What the stream adds

The REST API answers one company at a time. To follow the whole register continuously use the Streaming API in [Data & Updates](data-and-updates).
