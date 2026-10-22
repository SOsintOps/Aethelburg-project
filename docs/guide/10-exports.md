# Exports

**Export Intelligence…** in the top bar downloads flagged companies; when a company is selected, graph formats contain its network.

| Format | Contents | Opens in |
|---|---|---|
| FollowTheMoney (`.ftm.json`) | entities and links, one per line | Aleph, OpenSanctions tools, Quaesitor |
| Excel (`.xlsx`) | sheets for companies, PSC, risk flags and FtM entities | Excel, LibreOffice |
| CSV (`.csv`) | companies with scores and techniques | any spreadsheet |
| Gephi (`.gexf`) | network graph | Gephi |
| GraphML (`.graphml`) | network graph | yEd, Maltego, Cytoscape |
| Graphviz (`.dot`) | network graph | Graphviz |
| GeoJSON (`.geojson`) | map points and links | QGIS, Kepler.gl |
| KML (`.kml`) | map points | Google Earth |

Exports saved from the command line (`export-ftm`, `report`) go to the `exports` sub-folder of the data folder.
