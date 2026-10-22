"""
out/research/make_methods.py - writes out/research/method-1.md to method-4.md.

Each method file quotes the exact code from analysis.py (pulled out with inspect, so it can't drift),
lists the files and rows used, the definitions, and the numbers it produced (from numbers.json).

Run after analysis.py:   .venv/bin/python out/research/make_methods.py
"""

import inspect
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis  # noqa: E402

N = json.loads((HERE / "numbers.json").read_text())
P = analysis.P
studies, sites = analysis.load()
recruiting = studies[studies["status"] == "recruiting"]
live_sites = sites[sites["study_id"].isin(recruiting["study_id"])]
PROCESSED = f"ClinicalTrials.gov data processed {N['processed']['clinicaltrials']}; ISRCTN {N['processed']['isrctn']}"


def code(*functions):
    return "\n\n".join(f"```python\n{inspect.getsource(f).rstrip()}\n```" for f in functions)


def block(obj):
    return f"```json\n{json.dumps(obj, indent=1, default=str)}\n```"


COMMON = f"""## Shared definitions (all findings)

- **Recruiting**: `status == "recruiting"` in `data/processed/trials/studies.csv` - ClinicalTrials.gov
  RECRUITING or ENROLLING_BY_INVITATION; ISRCTN: today is between the recruitment start and end dates
  (from the most recently updated record when a study is on both registries). {len(recruiting):,} studies.
- **A study in an area / at a trust**: the study has at least one UK site there. A study counts in every
  area or trust where it has a site.
- **People waiting**: NHS England RTT incomplete pathways, all treatments (`C_999`), August 2026.
- **Registries**: {PROCESSED}. Contains information from the ISRCTN registry, licensed CC BY. Changes made
  by Wait Watcher: UK sites only, contact details removed, the two registries merged (linked by ISRCTN,
  IRAS or NCT number), sites matched to NHS trusts, conditions mapped to departments.
- **Reproduce**: `.venv/bin/python out/research/analysis.py` (writes `numbers.json`), then this file with
  `.venv/bin/python out/research/make_methods.py`.
"""


def method_1():
    f = N["finding_1"]
    england = live_sites[live_sites["nation"] == "England"]
    return f"""# Method 1: Essex against east London - recruiting studies per person waiting

**Finding:** In Essex there's one trial recruiting for every 2,500 people waiting. Next door in east London,
one for every 550.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/studies.csv` | {len(recruiting):,} recruiting studies (of {len(studies):,}) |
| `data/processed/trials/sites.csv` | {len(live_sites):,} study-sites of recruiting studies; {len(england):,} with an English postcode (`nation == "England"`, from postcodes.io); {f['recruiting_sites_without_postcode']:,} recruiting study-sites have no postcode and can't be placed |
| `data/raw/trials/postcode_icb.json` | each site postcode's current ICB, from postcodes.io (Open Government Licence) |
| `data/processed/rtt/area_history.csv` | month `{f['rtt_month']}`, `treatment_function_code == "C_999"`, ICB names containing "INTEGRATED CARE BOARD" (36 rows) |

## Definitions

- **ICB**: the integrated care board the site's postcode is in today (postcodes.io `icb`), matched by name
  to the RTT area (the ICB where patients live).
- **Recruiting studies in an ICB**: distinct `study_id`s with at least one recruiting site in that ICB.
- **People waiting per recruiting study** = `total_patients` / recruiting studies.
- No England-wide figure is given: a study counts in every ICB where it has a site, so ICB figures don't add up.

## Code

{code(analysis.site_icbs, analysis.finding_1_areas)}

## Result

{block({k: f[k] for k in ("essex", "north_east_london", "ratio", "essex_rank_of_36", "median_icb_waiting_per_study", "sites_placed", "mid_and_south_essex_sites")})}

All 36 ICBs (most people waiting per recruiting study first):

| ICB | People waiting | Recruiting studies | Waiting per study |
|---|---|---|---|
""" + "\n".join(f"| {r['icb'].title().replace('Nhs ', 'NHS ')} | {r['waiting']:,} | {r['recruiting_studies']:,} | {r['waiting_per_study']:,} |"
               for r in f["all_icbs"]) + f"""

## Caveats

- People in Essex can and do join London studies; "nearby" here means inside the ICB boundary.
- Recruiting sites with no postcode ({f['recruiting_sites_without_postcode']:,}) can't be placed. Mid and South
  Essex's matched recruiting sites: {f['mid_and_south_essex_sites']['with_postcode']} of {f['mid_and_south_essex_sites']['matched']} have a
  postcode, so Essex isn't specially under-counted.

{COMMON}"""


def method_2():
    f = N["finding_2"]
    return f"""# Method 2: Research per person waiting, by department

**Finding:** For each person waiting, lung care has about {f['ratio_lungs_to_bones']} times the trials of bones and joints.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/studies.csv` | {len(recruiting):,} recruiting studies; the `treatment_functions` column (set by `kitchen/sources/trials.py` using the rules in `kitchen/trial_condition_rules.json`) |
| `data/processed/findings-2026-08.json` | section `2_treatments`: people waiting (`waiting_now`) and typical wait (`median_now`) by department, England, August 2026 |

## Definitions

- **A study's department(s)**: from its conditions - MeSH terms first, then MeSH ancestors, then condition
  text, then ISRCTN disease class - by regular-expression rules. A study can map to several departments,
  and counts once in each. A random sample of 15 per department was about 3 in 4 right for eyes, bones and
  joints, and lungs alike.
- **Recruiting studies per 10,000 people waiting** = recruiting studies mapped to the department / people
  waiting in that department x 10,000.
- Left out: all treatments (C_999); mental health (X03: RTT covers about 3,000 people); paediatrics (X04),
  "other" (X06) and general internal medicine (C_300), which the rules never assign.

## Code

{code(analysis.finding_2_departments)}

## Result

{block({k: f[k] for k in ("bones_and_joints", "lungs", "eyes", "mouth", "ratio_lungs_to_bones")})}

| Department | People waiting | Recruiting studies | Per 10,000 waiting |
|---|---|---|---|
""" + "\n".join(f"| {r['name']} | {r['waiting']:,} | {r['recruiting_studies']:,} | {r['per_10k_waiting']} |" for r in f["departments"]) + f"""

## Caveats

- Trials and waiting lists don't cover the same people: lung trials include lung cancer and infection
  studies whose patients aren't on a waiting list for respiratory medicine.
- The ratio is the shape, not a precise figure; both departments carry similar mapping noise.

{COMMON}"""


def method_3():
    f = N["finding_3"]
    return f"""# Method 3: Research activity against waits, acute trusts

**Finding:** Hospitals running the most trials have waits just like everyone else's.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/sites.csv` | study-sites of recruiting studies with a `provider_code` (matched to one of our providers): {live_sites['provider_code'].notna().sum():,} rows |
| `data/processed/rtt/history.csv` | month `{f['rtt']['month']}`, `C_999`, `Incomplete Pathways`, acute trusts (`lookup.json` provider type "acute") with 10,000+ waiting: {f['rtt']['trusts']} trusts |
| `data/processed/cancer/provider_standards.csv` | {f['cancer']['months']}, standards 62D and FDS, acute trusts with 150+ patients over the three months: {f['cancer']['62D']['trusts']} trusts |
| `data/processed/ers/asi_provider.csv` | month `{f['slot_issues']['month']}`, acute trusts with 1,000+ bookings: {f['slot_issues']['trusts']} trusts |

## Definitions

- **Research activity of a trust**: distinct recruiting studies with a site matched to the trust (match
  methods: hand override, exact name and postcode, trust name, single-trust postcode, close name in the same
  town - never a guess). About 63% of English study-sites are matched, so counts are minimums.
- **Cancer trials**: recruiting studies whose MeSH terms or conditions mention a cancer (neoplasm,
  carcinoma, lymphoma, leukaemia, myeloma, melanoma, sarcoma, glioma, cancer, tumour).
- **Quarters**: trusts ranked by studies (ties broken by order) and cut into four equal groups; the median
  of each group's waiting measure is shown. Correlation: Pearson, studies against the measure.

## Code

{code(analysis.quarters, analysis.finding_3_research_v_waits)}

## Result

{block(f)}

## Caveats

- No link either way is the finding; it doesn't show research helps or harms waits.
- The busiest research trusts are also large and specialist; this compares trusts, not like-for-like patients.

{COMMON}"""


def method_4():
    f = N["finding_4"]
    return f"""# Method 4: UK trial starts over time, by sponsor and department

**Finding:** Drug-company trials in the UK held steady. University and NHS-led ones fell by about a seventh.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/studies.csv` | interventional studies (`study_type` INTERVENTIONAL, either registry's spelling) starting 2017-2024: periods 2017-19, 2020-21, 2022-24 |
| `data/raw/clinicaltrials/studies.jsonl` | ClinicalTrials.gov first-posted dates (for the registration-lag check only) |

## Definitions

- **Start year**: the year of `start_date` (ClinicalTrials.gov study start; ISRCTN recruitment start).
- **Industry**: lead sponsor class INDUSTRY (ClinicalTrials.gov) or "Commercial" (ISRCTN). Everything else is
  "academic and other" (universities, NHS trusts, charities, government).
- **Per year**: distinct studies in the period / number of years in it.
- 2025-26 left out: recent studies are still being registered. Registration lag (ClinicalTrials.gov,
  interventional, share posted more than ten months after the start year ended): {block(f['registration_lag'])}

## Code

{code(analysis.finding_4_trends, analysis.registration_lag)}

## Result

{block({k: f[k] for k in ('per_year', 'academic_change_pct', 'industry_change_pct')})}

| Department | Starts a year, 2017-19 | Starts a year, 2022-24 | Change |
|---|---|---|---|
""" + "\n".join(f"| {d['name']} | {d['per_year_2017_19']} | {d['per_year_2022_24']} | {d['change_pct']:+d}% |" for d in f["departments"] if d["change_pct"] is not None) + f"""

## Caveats

- Counts studies, not participants: the widely reported fall in UK commercial trial recruitment can't be
  seen in registries.
- Late registration means 2022-24 academic counts may still rise slightly.

{COMMON}"""


for n, make in enumerate((method_1, method_2, method_3, method_4), 1):
    (HERE / f"method-{n}.md").write_text(make())
    print(f"wrote out/research/method-{n}.md")
