# Wait Watcher definitions

One place for what each figure means and which published series it matches. Every analysis reads from this, so terms don't drift between posts (data-check step 5). `kitchen/reconcile.py` checks every figure here against the publisher's own each run, and the run fails if one doesn't match.

Last updated 22 October 2026.

## RTT: people waiting for hospital treatment

**What's counted.** RTT "incomplete pathways": people still waiting at the end of the month since a referral for consultant-led treatment, in weekly bands. These are pathways, not people; someone can be on more than one list.

**Two bases, both exact:**

| Basis | What it includes | August 2026 | August 2025 |
|---|---|---|---|
| **All rows of the Full CSV extract** | Every patient on an English provider's list | 7,189,213 waiting; 112,958 over 52 weeks | 7,345,544; 192,024 |
| **Commissioner basis** (NHS England's England figure, "reported only") | All of the above, less patients whose commissioner code is **NONC** | 7,158,164; 109,936 | 7,312,356; 188,702 |
| NONC (the difference) | Patients at English providers not commissioned by an English ICB, mostly people from Wales at border hospitals | 31,049; 3,022 | 33,188; 3,322 |

**Proof.** In August 2026 and August 2025, ours minus NONC equals NHS England's "RTT Overview Timeseries Including Estimates for Missing Trusts" (reported-only columns: "No. within 18 weeks" plus "No. > 18 weeks"; "No. > 52 weeks") to the unit. That file was published 8 October 2026. The gate re-checks this for every month from April 2024, all 29 months exact.

**Ruled out on the way** (21–22 October 2026): unknown clock starts (zero), double counting of Total and department rows, duplicate rows, band boundaries, independent providers, late data for non-submitting trusts, and an out-of-date file. Our August 2025 file is byte-identical to the current "revised-2" file.

**Where NONC patients are.** 109 providers. The biggest are Robert Jones and Agnes Hunt (Oswestry) with 9,475 waiting, 2,151 of them over a year; Wye Valley (Hereford) 4,902; the Walton Centre 3,076; and Countess of Chester 2,899. They're long-wait heavy: 9.7% over a year, against 1.6% for England.

**NHS England's headline** (7.37 million in August 2026) is a third figure: reported-only plus an estimate for trusts that didn't submit data (four in August 2026). It's in the same timeseries, "with estimates for missing data".

**Standing rule: which figure Wait Watcher quotes** (decided by Paul, 22 October 2026):
- **Every England total is on the commissioner basis:** NHS England's reported-only figure, all rows minus NONC (7,158,164 waiting and 109,936 over a year in August 2026). Any reader can find the same number in NHS England's own timeseries.
- **The headline with estimates** (7,370,100 and 113,339 in August 2026) is named only when the press is using it, and always labelled as including NHS England's estimates for trusts that didn't submit.
- **Trusts, departments and areas stay on all rows of the file.** A trust's list includes its NONC patients, as they really are waiting there.
- **Shares of England** (a trust's or department's share of everyone over a year, say) are worked out on all rows, so they add up to 100%.
- **The same rule applies to DM01** (below): England totals on NHS England's basis, trusts on all rows.

`kitchen/make_findings.py` takes England totals from the commissioner basis and checks them against `data/processed/rtt/england_basis.csv`, which holds all three columns (all, NONC, commissioner basis) for every month; the run stops if they differ. `report-facts` and the Lab read the same findings.

## DM01: people waiting for a diagnostic test

**What's counted.** People waiting at the end of the month for one of 13 key tests, from the DM01 Full CSV extract (provider × commissioner × test).

**Same NONC exclusion as RTT.** NHS England's England series ("Monthly Diagnostics Time series", sheets "Total Waiting List" and "6+ Week Waits") leaves out NONC patients, although the file says "Basis: Provider".

| Basis | August 2026 waiting | 6+ weeks |
|---|---|---|
| All rows of the Full CSV | 1,833,070 | 452,306 |
| NONC | 5,851 | 1,298 |
| **NHS England's England figure** (all rows minus NONC) | **1,827,219** | **451,008** |

The gate checks every test and the total, every month since April 2024 (464 checks for each measure), all exact. `data/processed/dm01/england_basis.csv` holds the columns. The timeseries is a legacy `.xls` file, read with `xlrd` (approved by Paul, 22 October 2026).

## The other sources the gate checks

| Source | Our England figure | Checked against | Gap allowed |
|---|---|---|---|
| Cancer waiting times | Sum of trusts, all cancers, each standard (FDS, 31D, 62D) | National "Monthly Time Series with Revisions", provider basis, newest publication containing the month | None. The provisional series differs for 2025-26; the revised one matches. |
| A&E | Sum of organisations: attendances, over 4 hours, 12+ hours from decision to admit | The TOTAL row in each monthly CSV | None |
| e-RS slot issues | Sum of providers: slot issues and bookings | The ENGLAND row in each report | None |
| Ambulance | Sum of the 11 trusts: category 1 and 2 incidents | The England row in AmbSYS | None |
| WLMDS | Sum of each monthly provider snapshot | The national weekly figure for the same week **in the same file** | None. Later files revise earlier weeks (by up to about 4%); the gate reports this but doesn't fail. |
| Community services | Sum of providers, all services | The National row in each monthly file | Three services published for England only (adult safeguarding, children's safeguarding, looked after children teams) |
| GP appointments | Sum of practices | NHS England's National Overview **from the publication the month was read from** | None. NHS England later revises national totals (April and May 2024 by about 1%) but never republishes practice-level data; the gate reports this. |
| Population | Sum of council areas | ONS's ENGLAND row | None |
| DM01 | Sum of all rows, each test and the total: waiting and 6+ weeks | NHS England's Monthly Diagnostics Time series | NONC (see above) |
| Winter sitreps: beds | Sum of acute trusts: G&A beds open and occupied, each day | The file's own "ENGLAND (All Acute Trusts)" row | None |
| Winter sitreps: ambulance handovers | Sum of trusts: handovers, over 30 minutes, over 60 minutes, each day | The file's own "ENGLAND (All Trusts)" row | Handovers on the file's "Unknown" row, which belong to no trust |

**How each figure is taken:**
- **Revised files:** every raw file records the address it came from (`_sources.json` in each raw folder). When a publisher posts a revision at a new address, it's downloaded again.
- **GP appointments:** each month is read from the last publication that includes it, two months after the month itself.

## Not yet checked, and why

- **Talking therapies and workforce:** England figures are taken from the publisher's England rows as published; nothing is re-added.
- **Mental health, Friends and Family Test:** no England figure is quoted.
- **Dental:** no monthly England headline is published (NHSBSA's official statistics are annual).
- **Clinical trials:** no published England total exists.

## Research data

- **Recruiting:** ClinicalTrials.gov RECRUITING or ENROLLING_BY_INVITATION; on ISRCTN, today falls between the recruitment start and end dates.
- **A study in an area or at a trust:** it has at least one UK site there. A study counts in every area where it has a site.
- **Matching:** about 63% of English study-sites are matched to a trust, so trust-level counts are minimums.
- **Attribution:** ClinicalTrials.gov with its processing date and our changes stated. "Contains information from the ISRCTN registry, licensed CC BY."
