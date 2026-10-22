# Getting started

Aethelburg is a local tool: everything runs on your computer and the data stays in your data folder. Nothing is uploaded anywhere except the requests you make to Companies House.

## Start the application

From the project folder, in PowerShell:

```
.venv\Scripts\python.exe -m src.main serve
```

Then open **http://127.0.0.1:8050** in your browser. `start.ps1` does the same and opens a browser window.

## Where your data lives

All downloads, the database (`aethelburg.sqlite`), exports and logs are kept in one **data folder**. The default on Windows is `C:\AethelburgData`. You can change it in the **6. Data & Updates** tab or with:

```
.venv\Scripts\python.exe -m src.main data location D:\MyAethelburgData --move
```

`--move` copies the database and downloads to the new folder; the old folder is never deleted for you. Restart Aethelburg afterwards. See [Data & Updates](data-and-updates).

## Keys for Companies House

Two keys from the Companies House developer hub (developer.company-information.service.gov.uk), both free:

| Key | Used for | Store it with |
|---|---|---|
| REST key | **Update from CH** in the dossier, **Fetch** in search results | `.venv\Scripts\python.exe -m keyring set aethelburg ch_api_key` |
| Streaming key | Live updates in **6. Data & Updates** | `.venv\Scripts\python.exe -m keyring set aethelburg ch_streaming_key` |

Run the command in PowerShell and paste the key when asked: it is stored in the Windows Credential Manager, never in a file. Restart Aethelburg after storing a key.

## First data load

1. **6. Data & Updates → Download all** (about 3.3 GB to download, about 17 GB once unpacked).
2. **Run import**: builds the search index of every UK company and imports the selected subset in full.
3. Use the search box on the left.

The same steps can be run from the command line: see [Command line](cli-reference).
