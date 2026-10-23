# Troubleshooting

**Where are the logs?** `<data folder>\logs\aethelburg.log`. When the interface shows an *error id*, search it in the log: the full details are next to it.

**Something broke the data.** **6. Data & Updates → Backups → Restore** brings back an earlier copy (the current database is saved first).

**"database is locked".** Another Aethelburg process is writing (for example an import started from the command line); it waits up to a minute. If it persists, check that no other copy of the program is running.

**The map shows "Access blocked" tiles.** The browser is not sending the page address to OpenStreetMap. Reload the page with Ctrl+F5; if it persists, check that no browser extension strips the `Referer` header for `tile.openstreetmap.org`.

**Markers are dashed rings / many companies on one point.** Positions are approximate because the ONS Postcode Directory is not imported. Download it in [Data & Updates](data-and-updates) and run the import.

**The page does not open / "address already in use".** Another Aethelburg is already running on port 8050. Close it, or start with `serve --port 8051`.

**"No Companies House API key configured".** Paste the REST key in **7. Settings** and press **Save keys**, then **Test with Companies House**. If the test answers 401, the key in the field is wrong (often the Streaming key, or the key pasted twice).

**The stream reports a gap.** Aethelburg was off longer than the stream keeps its history. Run the monthly refresh: **Check for new releases**, **Download all**, **Run import**.

**An import stopped half-way.** Press **Run import** again (or `data import`): it continues from the last saved point.

**A company is missing from the search.** The default risk filter shows flagged companies only: choose **All Risk Scores**. Companies not imported in full appear below the results with a **Fetch** button.

**Search finds nothing in the register index.** The index is filled by **Run import**; before the first import only the fully imported companies are searchable.

**The program seems frozen.** Look at the top bar: the activity indicator says what is being waited for and for how long. Yellow is a request in progress; red after eight seconds means the database is busy (a re-score, an import or a big query), and the text names the task when there is one; "server not responding" means the server window was closed or the server crashed: restart it. A typed search answers in a fraction of a second; if the whole window stays white or unresponsive for minutes, the browser tab itself is stuck: reload it (F5), the server keeps running.
