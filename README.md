# Wait Watcher

Side project tracking NHS England referral to treatment (RTT) waiting times,
with a single-page website in `site/` (deployed on Netlify).

## The kitchen

Everything that fetches and prepares data lives in `kitchen/`. Each data
source has one script in `kitchen/sources/`, and every script has the same
shape:

1. **Fetch**: find the latest file(s) on the publisher's page; skip anything
   already downloaded (raw files go in `data/raw/<source>/`).
2. **Clean**: read the files and keep what we need.
3. **Write**: save to `data/processed/<source>/` (and, where the website uses
   it, a copy in `site/data/`).
4. **Report**: print a coverage summary of rows, months, and provider codes
   matched to the RTT provider codes (and how many don't match).

Each script runs on its own, e.g. `python kitchen/sources/dm01.py`. To run
everything in order and stop at the first error:

```bash
python kitchen/run_all.py
```

| Step | Script | What it makes |
| --- | --- | --- |
| 1 | `sources/rtt.py` | RTT waiting times: `rtt/history.csv` (provider history), `rtt/area_history.csv` (by ICB, where patients live), `rtt/icb_mapping.json`, `rtt/summary.json`, `rtt/lookup.json`, `rtt/by_treatment/` |
| 2 | `sources/ods.py` | Provider and site locations (`ods/locations.json`), and provider types in `lookup.json` |
| 3 | `sources/cqc.py` | CQC inspection ratings (`cqc/cqc.json`) |
| 4 | `sources/fft.py` | Friends and Family Test by month, trust and service (`fft/fft.csv`) |
| 5 | `sources/staff_survey.py` | NHS Staff Survey Q25c and Q25d by trust and year (`staff_survey/staff_survey.csv`) |
| 6 | `sources/dm01.py` | Diagnostic waiting times by month, provider and test (`dm01/dm01.csv`) |
| 7 | `sources/njr.py` | National Joint Registry: licence check only (not ingested; see the registry) |
| 8 | `sources/ers.py` | e-Referral Service appointment slot issues by provider and specialty (`ers/`) |
| 9 | `sources/wlmds.py` | Weekly waiting list (WLMDS): England by week, provider snapshot per month (`wlmds/`) |
| 10 | `sources/cancer.py` | Cancer waiting times (FDS, 31-day, 62-day) by trust - **sensitive: gentle copy** (`cancer/`) |
| 11 | `sources/gp_practices.py` | Every GP practice, located with postcodes.io (`gp_practices/practices.csv`) |
| 12 | `sources/gpad.py` | GP appointments by practice and ICB: booking-to-appointment time, mode, DNAs (`gpad/`) |
| 13 | `sources/gpps.py` | GP Patient Survey: licence check only for now (not stated - see the registry) |
| 14 | `sources/talking_therapies.py` | NHS Talking Therapies by provider (`talking_therapies/`) |
| 15 | `sources/mhsds.py` | Mental health waits by provider (`mhsds/`) |
| 16 | `sources/community.py` | Community health services waiting lists by provider and service (`community/`) |
| 17 | `sources/ae.py` | A&E four-hour waits by trust (`ae/`) |
| 18 | `sources/ambulance.py` | Ambulance response times (`ambulance/`) |
| 19 | `sources/uec_sitreps.py` | Winter daily sitreps: beds and handovers by trust (`uec_sitreps/`) |
| 20 | `sources/workforce.py` | Vacancies by region and sector; sickness absence by trust (`workforce/`) |
| 21 | `sources/fingertips.py` | Deprivation, over-65s, healthy life expectancy by ICB and council (`fingertips/`) |
| 22 | `sources/population.py` | ONS population by council, sub-ICB and ICB (`population/`) |
| 23 | `sources/dental.py` | NHS dental activity by contract and ICB (`dental/`) |
| 24 | `sources/phin.py` | PHIN: licence check only (not open - see the registry) |
| 25 | `sources/uk_nations.py` | Scotland, Wales, NI headline waits - not comparable with England (`uk_nations/`) |
| 26 | `sources/clinicaltrials.py` | ClinicalTrials.gov studies with a UK site, and their UK sites (`clinicaltrials/`) |
| 27 | `sources/isrctn.py` | ISRCTN studies recruiting in the UK, and their UK centres (`isrctn/`) |
| 28 | `sources/trials.py` | The two merged (`trials/studies.csv`), sites matched to ODS codes (`trials/sites.csv`), conditions mapped to treatment functions (`trials/condition_mapping.json`), unmatched sites to hand-map (`trials/unmatched_sites.csv`) |
| 29 | `sources/nihr_activity.py` | NIHR research activity by trust: checks, stops (not openly published) |
| 30 | `sources/hra_summaries.py` | HRA research summaries: licence check, stops (not openly licensed) |
| 31 | `sources/bepartofresearch.py` | Be Part of Research: link patterns only (`bepartofresearch/link_patterns.json`) |
| 32 | `reconcile.py` | **The gate.** Every England figure against the publisher's own (RTT, cancer, A&E, e-RS, ambulance, WLMDS, community, GP appointments, population). Writes `reconciliation.md` and `.json`; stops the run if any figure is off by more than a documented gap. Definitions: `kitchen/DEFINITIONS.md` |
| 33 | `site_data.py` | The website's `site/data/experience.json` (patient and staff figures) |
| 34 | `make_findings.py` | `findings-<month>.json` and `.md`, `report-facts-<month>.json`, `questions.md` and `questions.json` (sections 10, "what's new", and 11, research, come from `whats_new.py`) |
| 35 | `lab_data.py` | Wait Watcher Lab's data files (`lab/data/`) |

**Research registries and privacy.** Contact names, emails and phone numbers
are never stored: the scripts drop contacts, investigators and free-text
protocol numbers as data arrives, cut "Who is the main contact?" sections
from summaries, and remove any email or phone number left in free text
(`common.redact_all`). Hand-map trial sites in `kitchen/trial_site_overrides.json`;
edit condition rules in `kitchen/trial_condition_rules.json`. Attribution:
"Source: ClinicalTrials.gov" (with the processing date) and "Contains
information from the ISRCTN registry, licensed CC BY".

Every new source prints its licence before ingesting; a source without an open
licence records why in the registry and stops. Most new sources also write a
`check_before_using.json`: providers whose main figure moved 15+ points in a
month (50+ for slot issue rates), or that NHS England lists with data issues.

- `kitchen/registry.json` lists every source with its URL, update cadence,
  licence, status and when it was last fetched.
- `kitchen/provider_types.json` holds provider types checked by hand (all NHS
  trusts with 10,000+ waiting, plus mental health and community trusts the
  name patterns miss). These override the patterns in `ods.py`.
- `kitchen/common.py` holds shared helpers, including a small reader for
  `.xlsx`/`.xlsm` files, so the kitchen only needs `requests`,
  `beautifulsoup4` and `pandas`.

## Automation

`.github/workflows/refresh.yml` runs `kitchen/run_all.py` on the second
Thursday of each month at 10:30 UK time (when NHS England publishes). It then
commits any changed data files and triggers Netlify build hooks (repository
secrets `NETLIFY_BUILD_HOOK`, and `NETLIFY_LAB_BUILD_HOOK` for the Lab). Use
"Run workflow" on the Actions tab to run it straight away. Raw downloads aren't
committed; the workflow keeps them in a cache between runs (about 3 GB on the
first run, mostly GP appointments, cancer and talking therapies).

`.github/workflows/weekly.yml` runs WLMDS, e-RS and the clinical trial
registries every Thursday at 08:00 UK time, rebuilds the Lab's data, commits
and deploys. WLMDS and e-RS are in practice published monthly; the trial
registries change daily (updates since the last run, with a full fetch every
28 days).

## RTT history columns

| Column | Meaning |
| --- | --- |
| `month` | e.g. `2026-08` |
| `provider_code` | Trust code, e.g. `RJ2` (`icb` in the area history) |
| `treatment_function_code` | Specialty code, e.g. `C_110`. `C_999` is all specialties combined. |
| `rtt_part` | Still waiting, or completed (admitted / non-admitted) |
| `total_patients` | Patients with a known wait (excludes "unknown clock start") |
| `median_weeks` | Half of patients have waited this many weeks or less |
| `p80_weeks` / `p92_weeks` | 80% / 92% have waited this many weeks or less |
| `pct_within_18_weeks` | % who waited 18 weeks or less (the NHS target measure) |
| `over_52_weeks` | Number who waited more than 52 weeks |

The week figures in the history files are rounded up to the end of their
band, so they can be up to a week higher than NHS England's published
medians. `make_findings.py` interpolates within the band instead.

## Licences

RTT, DM01, FFT, ODS, Staff Survey and every phase 3 source used are
published under the Open Government Licence v3.0 (NHS England, NHS England
Digital, NHSBSA, OHID, ONS, Public Health Scotland, Welsh Government, DoH NI).
Contains CQC information. ClinicalTrials.gov data are used under its terms
(free use; attribute, keep current, show the processing date, state
modifications); ISRCTN under CC BY. Not used: the National Joint Registry,
PHIN, HRA research summaries and NIHR trust-level activity (no open licence
or not published), and the GP Patient Survey until its licence is confirmed
(see `kitchen/registry.json`).
