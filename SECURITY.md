# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub: **Security → Report a vulnerability** on this repository. Do not open a public issue for them. Reports are acknowledged as soon as possible; fixes go into the next release and the [CHANGELOG](CHANGELOG.md).

## Supported versions

Only the latest release receives fixes. Aethelburg is in beta.

## Keys and data

- Companies House keys are entered in **7. Settings** and saved in the `app_settings` table of the local database, or kept in the operating-system keyring (`python -m keyring set aethelburg ch_api_key`, `... ch_streaming_key`); never in `.env` or in the repository. The page never sends a saved key back to the browser, only its last four characters. Database backups contain the saved keys: keep the data folder private.
- The web interface listens on `127.0.0.1` by default and has no authentication: do not start it with `--host 0.0.0.0` or expose it on a network.
- The database and the downloaded files stay in the local data folder (`C:\AethelburgData` by default) and are never committed.
