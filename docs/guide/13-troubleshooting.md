# Troubleshooting

**The map shows "Access blocked" tiles.** The browser is not sending the page address to OpenStreetMap. Reload the page with Ctrl+F5; if it persists, check that no browser extension strips the `Referer` header for `tile.openstreetmap.org`.

**Markers are dashed rings / many companies on one point.** Positions are approximate because the ONS Postcode Directory is not imported. Download it in [Data & Updates](data-and-updates) and run the import.

**The page does not open / "address already in use".** Another Aethelburg is already running on port 8050. Close it, or start with `serve --port 8051`.

**"No Companies House API key configured".** Store the REST key with `.venv\Scripts\python.exe -m keyring set aethelburg ch_api_key` in PowerShell and restart.

**The stream reports a gap.** Aethelburg was off longer than the stream keeps its history. Run the monthly refresh: **Check for new releases**, **Download all**, **Run import**.

**An import stopped half-way.** Press **Run import** again (or `data import`): it continues from the last saved point.

**A company is missing from the search.** The default risk filter shows flagged companies only: choose **All Risk Scores**. Companies not imported in full appear below the results with a **Fetch** button.

**Search finds nothing in the register index.** The index is filled by **Run import**; before the first import only the fully imported companies are searchable.
