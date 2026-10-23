# Risk scoring

Aethelburg applies eleven detection rules taken from [FT3](https://github.com/stripe/ft3), Stripe's Financial Threat Taxonomy. Each rule that matches a company adds its score; the company score is the sum, capped at 100. A company with at least one match is **flagged**, with one exception: a shared address (FT3-SC-001) on its own never flags a company.

| Code | Technique | Score | Default grade |
|---|---|---|---|
| FT3-SC-007 | Sanctioned entity connection | 45 | A1 |
| FT3-SC-004 | Circular ownership structure | 40 | A2 |
| FT3-SC-017 | Cross-dataset offshore entity (ICIJ) | 38 | B2 |
| FT3-SC-008 | Politically exposed person link | 30 | B2 |
| FT3-SC-015 | Phoenix company pattern | 28 | B2 |
| FT3-SC-003 | Layered corporate ownership chain | 26 | B2 |
| FT3-SC-002 | Nominee / hyper-active director | 25 | B2 |
| FT3-SC-020 | Opaque / unverified beneficial control | 18 | A1 |
| FT3-SC-009 | Rapid director / PSC turnover | 16 | B2 |
| FT3-SC-014 | Dormant / overdue filing anomaly | 14 | A1 |
| FT3-SC-001 | Mass co-registration hub | 10 (8 from 100 companies, 6 from 1,000) | B2 |

## Co-registration hubs

FT3-SC-001 fires when at least **20** companies share the same address fingerprint (change the number in **7. Settings → Risk scoring**, then re-score). It is context rather than evidence: most companies at a big hub are ordinary customers of a registered formation agent, so the score is flat and low, lowest for agents with thousands of companies, and the flag alone never marks a company as flagged. It still adds to any other finding, and the **GeoINT** tab lists the hubs with the number of flagged companies at each.

Before this rule was tamed (threshold 5, up to 34 points, A1), it fired on 78 % of a subset built around shared addresses and made "flagged" meaningless.

## Grades

Every finding carries a **UNODC 4x4** grade: a letter for the source and a number for the information.

- Source: **A** always reliable (official registry, sanctions list), **B** mostly reliable (self-reported filings, ICIJ), **C** sometimes reliable (fuzzy or unverified match), **X** untested.
- Information: **1** confirmed, **2** probably true, **3** possibly true, **4** doubtful.

And an **analytic confidence** (ICD 203): **high**, **moderate** or **low**.

## How sanctioned and offshore names are matched

- **Companies** match a sanctions designation by UK company number (A1, score 48) or by the same name fingerprint (B2, 42). Only designations of entities count, never of individuals.
- **People with significant control** must have the same name fingerprint as a sanctioned individual, and then the date of birth decides. Companies House publishes month and year; OFSI publishes a full or partial date (`dd/mm/1945` is the year only).
  - Same month and year: **A2**, high confidence, score 45.
  - Same year, but one side gives no month (OFSI often publishes `dd/mm/1976`): **B2**, moderate confidence, score 35. The flag says "same year of birth". With a common name this is usually a namesake: check the designation.
  - Different year or month: the match is dropped as a namesake.
  - No date on either side: kept as **B3**, low confidence, score 25. The flag says "name only".
  - A person who has **ceased** to be a controller is still matched (the link is history worth knowing), but the flag says "former controller, ceased on …" and the score is reduced to 60 %.
- **ICIJ Offshore Leaks** publishes no dates of birth, so a person found there is matched on the name alone: **C3**, low confidence, score 20. A company or corporate owner found there keeps B2 and 38.

A name fingerprint ignores case, accents, titles, legal suffixes and word order: *Wilson Joseph* and *Mr Joseph Wilson* are the same fingerprint. Always check a low-confidence match against the designation before relying on it.

## Innocent explanations

Each technique lists lawful situations that produce the same pattern: accountants, company secretaries and virtual offices for mass registration; acquisition-finance stacks (TopCo, MidCo, BidCo) and subsidiaries of foreign groups for layered ownership; trademark-protection and pre-trading companies for dormant accounts; and so on. A flag is a reason to look closer, never a conclusion.

## When scores change

Scores are recalculated by **Re-Score FT3**, at the end of **Run import**, after **Update from CH**, and every 15 minutes while live updates bring changes.
