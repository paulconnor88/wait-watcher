# NHS waiting-time data: definitions, fair comparisons and traps

Read before analysing anything from the Wait Watcher kitchen.

## Referral to treatment (RTT)

**What it is.** A stopwatch. Starts when a hospital receives a GP referral for non-urgent consultant-led treatment; stops when treatment starts (or a decision that none is needed). Published monthly by NHS England, about six weeks after the month ends, on the second Thursday.

**Two flavours, never mixed without saying so:**
- **Incomplete pathways ("still waiting").** Everyone whose clock is running at month end, in weekly bands of how long they've waited *so far*. This is what the NHS App and My Planned Care show. It is a snapshot of a queue, not a forecast.
- **Completed pathways ("treated").** People whose clock stopped that month, in weekly bands of how long they waited *in total*. Split into admitted (needed a bed: an operation or procedure) and non-admitted (treated in clinic). This is how long treatment actually took.

The gap between the two is the single most misunderstood thing in NHS waiting data: at one London trust in August 2026, still-waiting median was 14 weeks; admitted median was 48. Both true. Different people.

**The standard.** 92% of people still waiting should have waited 18 weeks or less. Measured on incomplete pathways. Last met nationally in early 2016. Government milestones: 65% by March 2026, 92% by March 2029. August 2026: 65.2%.

**Grain.** Provider (trust) × treatment function (24 departments, e.g. Trauma and Orthopaedics) × commissioner (where the patient lives). Rows are split by commissioner; sum them for a trust total. The "Total" treatment function row is the whole trust. Department, not procedure: "bones and joints" mixes hips, knees and fractures.

**Medians.** Compute by interpolation within the weekly band. NHS England's published medians match this (June 2026: 11.9 weeks).

**Three England figures, all legitimate (August 2026):**

| Figure | August 2026 | What it is | Use it for |
| --- | --- | --- | --- |
| All rows of the Full CSV | 7,189,213 waiting; 112,958 over 52 weeks | Everyone on an English hospital's list, including patients commissioned outside England (commissioner code NONC, mostly Welsh patients at border hospitals) | Trust and department figures |
| Commissioner basis ("reported only") | 7,158,164; 109,936 | NHS England's England figure in the RTT Overview Timeseries: all rows minus NONC | **The England figure Wait Watcher quotes** |
| NHS England headline | 7,370,100; 113,339 | Reported only plus an estimate for trusts that didn't submit | Naming when the press uses it |

NONC in August 2026: 31,049 waiting, 3,022 over 52 weeks (9.7% over a year vs 1.6% across England). August 2025: 33,188 and 3,322. Removing NONC matches NHS England to the unit in every month since April 2024. Full working in kitchen/DEFINITIONS.md and RECONCILIATION-2026-10.md.

Other checks: 65.2% within 18 weeks (August 2026); 60.9% (August 2025).

## Fair comparisons

- Compare acute and specialist trusts with each other. Community and mental-health trusts report small, different activity and top league tables for the wrong reasons. Provider types are in lookup.json.
- Independent-sector providers (codes not starting with R) do NHS work, mostly simpler day cases. Their waits look short partly because of case mix. Say so when they appear as "fastest".
- Same month vs same month a year earlier for trends (seasonality). Three months combined for completed pathways (small numbers).
- A trust is the unit, not a hospital building. Waits are reported for the whole trust.
- Areas (ICBs) are where patients live, not where hospitals are. Old ICB boundaries are mapped to current ones in icb_mapping.json.

## Traps

- **Suspiciously short admitted waits** (under 5 weeks for a department) are usually recording quirks or heavy day-case mix, not miracles. Exclude from "fastest".
- **Jumps of more than 15 points in a month** usually mean a reporting change. The findings file marks these "check before using". Exclude from "most improved".
- **Small counts.** Under 30 treated people in a period: say "small numbers". Under 150: don't rank.
- **"Still waiting" median rises when a trust clears old cases first**, which is good management looking like bad news. Pair it with the over-52-week count.
- **Incomplete-pathway medians cannot be turned into "you will wait X more weeks."** The data doesn't follow people.

## Other kitchen sources

- **DM01 (diagnostics).** 15 tests, monthly, by provider. Standard: fewer than 1% waiting 6+ weeks. Measures: total waiting, % 6+ weeks, % 13+ weeks. Community diagnostic centres report separately and may not match a trust.
- **CQC ratings.** Overall and per core service, with inspection date. Ratings can be years old; always show the year. Match by ODS code, never by name. Say "contains CQC information".
- **Friends and Family Test.** Share of patients who rated care *good or very good*. The "would you recommend" question ended in 2020; never use "recommend" wording. Monthly, by trust and service (inpatient, outpatient, A&E).
- **NHS Staff Survey.** Annual (published each March). Q25d: would be happy with the standard of care for a friend or relative. Trusts only; independents are "not surveyed".
- **ODS.** Trust and site locations. Trusts own clinics far from home; use treatment sites (names containing Hospital or Treatment Centre, within 30 miles of HQ) for distance, not any site.
- **National Joint Registry.** Not in the kitchen: no open licence.

## Plain-English names for departments

Trauma and Orthopaedics = bones and joints. Ophthalmology = eyes. ENT = ear, nose and throat. Gastroenterology = gut (procedures are mostly endoscopies, not surgery). Dermatology = skin. Urology = bladder, kidneys, prostate. Gynaecology = women's health. Oral Surgery = mouth and jaw. Cardiology = heart. Rheumatology = joints and autoimmune. Neurology = brain and nerves.
