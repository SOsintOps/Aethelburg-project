# 4. FollowTheMoney (FtM)

Every entity in Aethelburg is also stored in the [FollowTheMoney](https://followthemoney.tech/) format used by OCCRP Aleph and OpenSanctions: companies, people, legal entities, addresses, ownerships, directorships, sanctions and ICIJ records.

The tab shows the FtM entity of the selected company (schema, id, properties, datasets) and its links.

- **Download Subject .ftm.json**: the selected company and its linked entities.
- **Export All Flagged .ftm.json**: every flagged company with its network.

The files are line-delimited JSON (one entity per line) and can be loaded into Aleph, OpenSanctions tooling or Quaesitor. From the command line: `python -m src.main export-ftm` and `python -m src.main import-ftm FILE`.

Entity ids are deterministic: the same company or person always gets the same id, so repeated exports merge cleanly.
