# Legal notes — Aethelburg

## Data sources: licence analysis

### Companies House
- **Licence**: Open Government Licence v3.0 (OGL)
- **URL**: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
- **Commercial use**: Permitted with attribution
- **Redistribution**: Permitted with attribution
- **Notes**: Aethelburg does not redistribute the data. Local use is compliant with OGL.

### PSC (Persons with Significant Control)
- **Source**: Companies House (same OGL regime)
- **Contents**: Personal data of natural persons (name, partial DOB, nationality)
- **Regime**: UK GDPR / Data Protection Act 2018
- **Applicable exemption**: Art. 2(2)(c) UK GDPR — activities of a purely personal or domestic nature
- **Limit**: The domestic exemption does NOT cover disclosure to third parties or API queries containing personal data sent to external servers.

### ICIJ Offshore Leaks Database
- **Licence**: Open Database License (ODbL 1.0) for the database; Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0) for its contents
- **URL**: https://offshoreleaks.icij.org/pages/database
- **Commercial use**: Not prohibited by the licences, subject to attribution and share-alike
- **Redistribution**: Permitted with attribution, under the same licences (share-alike)
- **Notes**: ICIJ asks to always cite the International Consortium of Investigative Journalists when using the data.

### OpenSanctions
- **Licence**: Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)
- **URL**: https://www.opensanctions.org/licensing/
- **Commercial use**: Prohibited without a commercial licence
- **Redistribution**: Permitted with attribution, for non-commercial use
- **Conflict**: A distributed dataset combining OGL data with OpenSanctions data inherits the non-commercial restriction, and one combining it with ICIJ data inherits the ICIJ share-alike terms. For personal non-distributed use: no conflict.
- **Commercial licence**: Available on request from OpenSanctions.

### FollowTheMoney (FtM)
- **Licence**: MIT
- **Author**: OCCRP (Organized Crime and Corruption Reporting Project)
- **Commercial use**: Permitted
- **Notes**: Python library, not a dataset.

### FT3 Framework (Stripe)
- **Licence**: MIT
- **URL**: https://github.com/stripe/ft3
- **Notes**: JSON/CSV knowledge base, not an executable library. MIT permits free use.

### sentence-transformers / all-MiniLM-L6-v2
- **Licence**: Apache 2.0
- **Commercial use**: Permitted

---

## UK GDPR: domestic exemption analysis

The processing of PSC data falls within the domestic exemption (Art. 2(2)(c) UK GDPR) provided that:

1. Processing takes place on a local machine (not cloud)
2. Results are not shared with third parties
3. Data is not used to make decisions that directly affect individuals
4. API queries to external services do not contain identifiable personal data

**Grey areas**:
- API queries to Companies House, OpenCorporates or other services with search parameters containing names of natural persons = transfer of data outside the domestic perimeter. Not covered by the exemption.
- Aggregated output (e.g. "top 10 most common directors in sanctioned companies") = probably covered by the exemption if it remains personal.

**Recommendation**: Prefer local datasets (bulk download) for searches on natural persons, avoiding nominative queries to external APIs.

---

## Note on investigative use

Aethelburg produces statistical risk indicators, not legal evidence. A high risk score indicates anomalies worthy of further investigation, not certainty of wrongdoing. The user is responsible for verifying information before drawing conclusions or taking action.

The system is neither designed nor authorised to:
- Make automated decisions affecting the rights of natural persons
- Be used as a surveillance tool
- Produce evidence for legal proceedings without independent verification
