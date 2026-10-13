# Writing the Investigation Report

How to turn what Aethelburg finds into a written report on a company or a network of companies. The general method (analytic standards, source evaluation, estimative language, report structure, prose rules) is kept in the [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes), the notes shared by the SOsintOps tools; this page covers what is specific to corporate and financial investigation on UK register data. The PDF report the program will generate is designed in [DESIGN_INTELLIGENCE.md](DESIGN_INTELLIGENCE.md#report-structure-10-sections); this page is about what goes into it.

---

## The risk score is not a judgement

The 0–100 risk score measures how far a company departs from the norm on up to eight detection patterns, each tagged with an [FT3](https://github.com/stripe/ft3) technique. It is an anomaly indicator, not a probability and not a finding.
- **Never translate the score into a likelihood word.** A score of 85 does not mean "very likely a shell company". The likelihood term is the analyst's judgement after looking at the flags, the filings and the alternatives.
- **Explain the flags, not the number.** The reader needs to know which patterns fired and why they matter for this company, not the composite.
- **Name the innocent explanations.** A shared address is often a formation agent; a dormant company with a foreign director is often just that. List the alternatives you checked and why you rejected them ([ICD 203](https://www.dni.gov/files/documents/ICD/ICD-203.pdf) tradecraft standard 4, analysis of alternatives).

## Sources and how to grade them

Grade every item with the UNODC 4 x 4 system of the [*Criminal Intelligence: Manual for Analysts*](https://www.unodc.org/documents/organized-crime/Law-Enforcement/Criminal_Intelligence_for_Analysts.pdf) (source A, B, C or X; information 1 to 4), as in [Source Evaluation](https://github.com/SOsintOps/intelligence-field-notes/blob/main/docs/source-evaluation.md).

| Source | How to treat it |
| :--- | :--- |
| **Companies House register and filings** | The register is an `A` source for what was filed and when. What a company or an officer declared (address, nature of business, persons with significant control) is their claim, recorded by the state: often accurate, sometimes false, rarely checked in the past. Grade the content accordingly. |
| **PSC register** | Self-declared control. A missing or "no registrable person" statement is itself information, not an absence of it. |
| **Sanctions lists (via OpenSanctions)** | The issuing authority (FCDO, OFAC, EU) is the source; OpenSanctions is the aggregator. Grade the listing, not the copy. |
| **ICIJ Offshore Leaks** | Genuine leaked records, but old and partial. Their presence shows a connection at a date; it shows no wrongdoing. |
| **Name matches** | A fuzzy match is a candidate, not an identity. Report it with its match score as "possible match" until a second identifier (date of birth, address, company number) confirms it. |
| **Geocoding** | A postcode centroid locates an area, not a building. Say which one you used. |

## Structure of the report

The ten sections of the designed PDF follow the order of [Report Writing](https://github.com/SOsintOps/intelligence-field-notes/blob/main/docs/report-writing.md), with these choices:
1. **Cover:** case number, date, version, handling marking (for example `TLP:AMBER`), and the personal-data notice.
2. **Bottom line** (section 2 of the design): the question and the answer in three to five sentences, opening on the judgement, for example "Company X is very likely a nominee vehicle…", not on the score or on the incorporation date. The risk gauge supports this section; it does not replace it.
3. **Primary entity**, 4. **ownership**, 5. **network**, 6. **sanctions and adverse matches**, 7. **geography**, 8. **timeline**: the findings, each with its sources and grades.
9. **FT3 flags:** each flag with its technique ID, what triggered it and the innocent explanation considered.
10. **Analyst's assessment:** the judgements (likelihood or confidence, never both in one sentence), the alternatives, the gaps and what would close them. The design calls this section "investigator annotations"; it is where the analysis lives, so it should carry the analyst's name and date.

## Personal data

PSC and officer records contain personal data. Under the domestic exemption described in [LEGAL.md](LEGAL.md), reports are for personal use: do not share or publish a report that names natural persons, and redact individuals who are not subjects of the investigation. When a report must travel, remove personal data first and state that it was removed.

## Further reading

- [Intelligence Field Notes](https://github.com/SOsintOps/intelligence-field-notes): the common method and the full [Reading List](https://github.com/SOsintOps/intelligence-field-notes/blob/main/docs/reading-list.md).
- **"Criminal Intelligence: Manual for Analysts"** (UNODC, 2011): chapters 6 and 8 on link analysis and flow analysis, the method behind ownership charts and money flows. [PDF](https://www.unodc.org/documents/organized-crime/Law-Enforcement/Criminal_Intelligence_for_Analysts.pdf)
- **FT3: Fraud Tools, Tactics, and Techniques** (Stripe): the taxonomy behind the risk flags. [GitHub](https://github.com/stripe/ft3)
- **Follow the Money**: the data model Aethelburg's ontology builds on. [followthemoney.tech](https://followthemoney.tech)
- **"Open Source Guide to Investigating Chinese Companies"** (GIJN): when an ownership chain leaves the UK for China or Hong Kong. [gijn.org](https://gijn.org/resource/asia-focus-open-source-guide-investigating-chinese-companies/)
