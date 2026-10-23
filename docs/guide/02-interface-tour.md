# Interface tour

The window has a top bar and three panels.

## Top bar

- **Counters**: companies fully imported, companies flagged by FT3 rules, sanctions records, ICIJ Offshore Leaks nodes, entities in the FollowTheMoney store.
- **Export Intelligence…**: downloads the data in one of eight formats; see [Exports](exports).
- **Re-Score FT3**: re-runs entity resolution and all FT3 detection rules on the whole database; see [Risk scoring](risk-scoring).
- **? Help** (or F1): opens this guide on the chapter of the tab you are in; the [FAQ](faq) and the [Version history](version-history) are at the end of the index. Clicking the version number in the top bar opens the version history.
- **Theme**: light, classical or dark.

## Left panel: search and filters

- **Search box**: company name, company number (CRN), postcode or address line.
- **FT3 technique filter**: only companies flagged by one technique.
- **Risk filter**: all companies, flagged only (score above 0), high (35 or more) or critical (65 or more). The default shows flagged companies only: choose **All Risk Scores** to see everything.
- Each result shows name, risk score, CRN, status, postcode and up to three FT3 technique codes. Click it to open the company in every tab.
- Below the results, companies that are only in the **register index** (not imported in full) have a **Fetch** button that downloads them from Companies House (needs the REST key).

## Centre panel: seven tabs

1. [Network Graph](network-graph)
2. [GeoInt & Hubs](geoint-and-hubs)
3. [Timeline & FT3 Matrix](timeline-and-ft3-matrix)
4. [FollowTheMoney](followthemoney)
5. [Casework & Reports](casework-and-reports)
6. [Data & Updates](data-and-updates)
7. Settings: Companies House keys, daily update, backups to keep, hub threshold (see [Companies House API](companies-house-api))

## Right panel: Intelligence Dossier

Profile of the selected company: registry details, cross-dataset hits (sanctions, ICIJ), FT3 flags with UNODC grade and innocent explanations, PSC controllers, officers, co-located companies.

- **Update from CH**: downloads the current profile, every officer appointment and every PSC statement from Companies House, then re-scores. See [Companies House API](companies-house-api).
- **10-Sec Report**: opens the intelligence report of the company in a new tab (see [Casework & Reports](casework-and-reports)).
- **+ Add to Case**: adds the company to the active investigation.
