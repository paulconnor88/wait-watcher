# The RTT discrepancy, and how we stop it happening again

Written 22 October 2026. The working is in `kitchen/DEFINITIONS.md`; the gate's latest output is `data/processed/reconciliation.md`.

## What we found

**The question.** For August 2026, Wait Watcher said 7,189,213 people were waiting and 112,958 had waited over a year. NHS England's own reported-only figures say 7,158,164 and 109,936. Why the gap of 31,049 and 3,022?

**The answer: a difference in basis, not an error.**
- **How NHS England counts England:** its figure is built on a *commissioner* basis. It leaves out patients at English hospitals who aren't commissioned by an English ICB; the data marks them with the commissioner code **NONC**.
- **Who they are:** mostly people from Wales treated at border hospitals: Robert Jones and Agnes Hunt in Oswestry, Wye Valley in Hereford, the Walton Centre, Countess of Chester.
- **How we counted:** our figure added up every row in the file, so it included them.
- **Proof:** NONC holds exactly 31,049 waiting and 3,022 over a year in August 2026, and exactly 33,188 and 3,322 in August 2025. Take them out and both months match NHS England to the unit.
- **Every month:** the new reconciliation gate re-checks all 29 months from April 2024; all are exact.

**Why it took a while to find.** The gap was a different share of each figure: 0.4% of the waiting list but 3% of year-long waits. That pointed at a small group with very long waits, and NONC patients are exactly that: 9.7% of them have waited over a year, against 1.6% across England.

**Ruled out along the way:**
- Unknown clock starts.
- Double counting.
- Duplicate rows.
- Band boundaries.
- Independent providers.
- Late data from the four trusts that didn't submit.
- An out-of-date file: our August 2025 file is byte-identical to NHS England's current "revised-2" version.

**There are three England figures, all legitimate:**

| Figure | August 2026 | What it is |
|---|---|---|
| All rows of the file | 7,189,213 | Everyone on an English hospital's list. Right for trusts and departments. |
| Commissioner basis ("reported only") | 7,158,164 | NHS England's England figure, in its RTT Overview Timeseries |
| NHS England headline | 7,370,100 | Reported only, plus an estimate for trusts that didn't submit |

## Three more problems the check uncovered

Building a gate for every source found three more issues. Two were genuinely ours, and both are fixed.

1. **GP appointments: we were reading old versions of most months. (Ours, fixed.)**
   - NHS England reissues each month's practice-level figures in the next two publications, revised each time. Our script was meant to take each month from the newest one, but its loop skipped them.
   - Now each month comes from the last publication that includes it, and matches NHS England's National Overview in that publication to the appointment.
   - NHS England keeps revising national totals after that, by about 1% for April and May 2024, but never republishes practice-level data. The gate reports those revisions but doesn't fail on them.
2. **Revised files would never have been downloaded. (Ours, fixed.)**
   - Some scripts saved raw files under fixed names (`rtt-2025-08.zip`) and skipped anything already on disk. A later revision of an old month would have been silently ignored. RTT happened to be up to date only because we first downloaded everything after the last revisions.
   - Now every raw folder records the web address each file came from (`_sources.json`). A revision at a new address is fetched again, and RTT replaces the old month's file cleanly.
3. **Some published series get revised after we read them. (Not ours, now recorded.)**
   - The cancer provisional series differs from the final figures. WLMDS revises old weeks by up to about 4% in later files.
   - The gate checks each figure against the version published alongside it, and lists every later revision with its size.

## How we stop this happening again

1. **A gate on every run.**
   - What it checks: `kitchen/reconcile.py` runs after the sources and before anything is published. It compares every England figure, every month, against the publisher's own: 559 checks across RTT, cancer, A&E, e-RS, ambulance, WLMDS, community services, GP appointments and population.
   - What counts as a pass: a difference is allowed only if it's documented and computed from the data (NONC; three national-only community services), never a fixed tolerance. Anything else fails the whole run, so a wrong month can't reach the site, the Lab or a report.
   - Proven: a one-patient error stops it.
2. **Definitions in one place.** `kitchen/DEFINITIONS.md` says what each figure counts, which published series it matches, and which one Wait Watcher quotes.
3. **Revisions handled automatically.** Raw files are re-downloaded when the publisher posts a new version, and each month comes from its latest publication.
4. **Each figure checked against its own publication.** Where publishers revise later, we check against the version we used and report the revision, so a revision is never mistaken for an error.
5. **Before every post:** run the data-check skill. It reconciles to published totals, checks every figure two ways, and gets a human review.
6. **When something doesn't match:** don't publish. Test explanations one at a time until one closes every figure exactly, record the answer in DEFINITIONS.md, and add it to the gate.

## Still open

- **Which England figure to quote (your decision).** Recommendation: the commissioner basis (7,158,164), so anyone can find the same number in NHS England's timeseries, naming the 7.37 million headline when the press uses it. Trust and area figures don't change.
- **Diagnostic waits (DM01).** Not yet checked: NHS England's England series is only in an old-format `.xls` file, which needs one more library (`xlrd`). Needs your OK.
- **Winter sitreps.** A check against the files' own ENGLAND rows is still to build.
- **Leo's notes.** The leo-analyst notes (`nhs-waiting-data.md`) still describe 7.19 million as "the file total" against a 7.3 million headline. Worth updating to the three-figure table above.
