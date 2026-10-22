# Kitchen changes - October 2026

Written 20 October 2026, after the full run of `kitchen/run_all.py` (all 9 steps passed, 4.2 minutes). Latest data month: **August 2026**.

## What changed, in short

- **One folder for the kitchen.** Every data script now lives in `kitchen/sources/`, one per source, and each works the same way: fetch the latest file (skipping anything already downloaded), clean it, save it to `data/processed/<source>/`, and print a coverage summary.
- **One command runs everything:** `python kitchen/run_all.py`. It runs the sources in order and stops loudly at the first error.
- **A list of sources:** `kitchen/registry.json` records each source's link, how often it updates, its licence and when it was last fetched.
- **Three new sources:** diagnostic waiting times (DM01), the Friends and Family Test (inpatient, outpatient and A&E, monthly) and the NHS Staff Survey. The National Joint Registry was checked but **not** used, because its data has no open licence.
- **Waiting lists by area:** the RTT data now also has a history by ICB (where patients live), with old ICBs mapped to today's so years compare fairly.
- **Hospital types:** every provider is now tagged acute, specialist, community, mental health or independent. The findings' league table and most/least improved lists use acute and specialist trusts only.
- **Fixed CQC matching:** ratings are now matched by exact organisation code, never by guessing from names.
- **Monthly automation, written but not switched on yet** (see "What you need to do").
- Only three code libraries are needed now (requests, beautifulsoup4, pandas).

## 1. The data sources

"Matched" means the provider codes in that source that are also in the waiting-list (RTT) data, out of 566 providers.

| Source | What it is | Updates | Covers | Matched | Not matched | Licence |
|---|---|---|---|---|---|---|
| RTT | NHS waiting times by hospital, treatment and month | Monthly (second Thursday) | Apr 2024 - Aug 2026 (29 months) | 566 | 0 | Open Government Licence |
| ODS | Where each hospital and site is | Continuously; refreshed monthly | Current lists | 565 | 0 (1 closed provider has no address) | Open Government Licence |
| CQC | Inspection ratings | Monthly | October 2026 files | 441 | 0 (the rest have no CQC match) | Open Government Licence (contains CQC information) |
| FFT | Friends and Family Test: inpatient, outpatient, A&E | Monthly | Apr 2024 - Aug 2026 (29 months, all three services every month) | 418 | 25 | Open Government Licence |
| Staff Survey | Staff views: "place to work" and "place for treatment" | Yearly (each March) | 2025 survey | 158 | 80 (ICBs, social enterprises and other non-hospital bodies) | Open Government Licence |
| DM01 | Waits for 15 diagnostic tests (MRI, CT, etc.) | Monthly | Apr 2024 - Aug 2026 (29 months) | 401 | 83 (mostly test-only providers, such as community diagnostic centres) | Open Government Licence |
| NJR | Hip and knee replacements by hospital | Yearly | Not ingested | - | - | No open licence ("Copyright NJR"; data only by request under a data-sharing agreement) |

Notes:
- The FFT figure is the share of patients who rated their care **good or very good**. The FFT stopped asking "would you recommend?" in 2020, so it's stored as `pct_positive`, not as a recommend score.
- "Recommend as a place for treatment" in the Staff Survey is question Q25d: "If a friend or relative needed treatment I would be happy with the standard of care provided by this organisation."

## 2. RTT details

**Area history: yes.** `data/processed/rtt/area_history.csv` covers **36 ICBs** (today's boundaries) for every month from April 2024 to August 2026. There's also an "Unknown" group for patients commissioned by NHS England's specialised services or with no recorded commissioner. The mapping from old ICBs to new is in `data/processed/rtt/icb_mapping.json`. For example, Hertfordshire and West Essex is split between Central East and Essex by local commissioner.

**Provider types** (in `lookup.json`):

| Type | Providers |
|---|---|
| Acute | 119 |
| Specialist | 16 |
| Community | 7 |
| Mental health | 15 |
| Independent | 409 |

140 of these were checked by hand (`kitchen/provider_types.json`): every NHS trust with 10,000+ people waiting, plus 15 mental health and community trusts the automatic rules got wrong.

**Flagged "check before using" in the August 2026 findings: 66 providers.** A provider is flagged if its % within 18 weeks jumped more than 15 points between two months in the last year. Flagged providers stay in the league table but are left out of the "most improved" and "fastest" lists. No acute or specialist trust is flagged this month.

- **NHS trusts (3, all mental health):** Herefordshire and Worcestershire Health and Care NHS Trust (% within 18 weeks moved 18 points in a month (to March 2026)); Oxleas NHS Foundation Trust (% within 18 weeks moved 34 points in a month (to June 2026)); Cambridgeshire and Peterborough NHS Foundation Trust (% within 18 weeks moved 32 points in a month (to October 2025)).
- **Independent providers (63):** Aces Nottingham; Newmedica - Swindon; One Hatfield Hospital; Newmedica - Berkshire - Bracknell; Optegra at Havant Health Centre (Havant); Aces Bolton; Aces Carlisle; The Royal Buckinghamshire Hospital Ltd; Modality Llp; Aces Bradford; Aces Harley Street; Anglia Community Eye Service - Bury St Edmunds; Newmedica - Hertforshire - Welwyn Garden City; Aces Newcastle; Spamedica Stevenage Community Diagnostic & Treatment Centre; Anglia Community Eye Service - Norwich; Aces Torquay; Pioneer Healthcare Limited; Standard Health Ltd; Communitas Clinics; Sirona Care & Health; Bespoke Healthcare Ltd; St Martins Hospital; Nuffield Health, Brentwood Hospital; Nuffield Health, Cambridge Hospital; Nuffield Health, Cheltenham Hospital; Nuffield Health, Wessex Hospital; Nuffield Health, Guildford Hospital; Nuffield Health, Haywards Heath Hospital; Nuffield Health, Tunbridge Wells Hospital; Nuffield Hospital Oxford (The Manor); Spire Southampton Hospital; Spire Norwich Hospital; Spire Leicester Hospital; Spire Manchester Hospital; Spire Clare Park Hospital; Spire Fylde Coast Hospital; Hampshire Clinic; Harbour Hospital; Shelburne Hospital; St Edmunds Hospital; Southend Private Hospital; Practice Plus Group Ophthalmology - North West; Anglia Community Eye Service - Fakenham Medical Practice; Anglia Community Eye Service - Thetford Healthy Living Centre; Aces Plymouth; Aces Leeds White Rose; Aces Southampton; Nuffield Health Parkside Hospital; Border Health Alliance Limited; Aces Darlington; Aces Birmingham; Aces Manchester Trafford; Aces Lincoln; Aces Bristol; Aces Chiswick; Pastel Health; Aces Manchester; Aces Leeds King Street; Aces Maidstone; Aces Lakeside; Aces Wilmslow; Aces Southampton - East St.

**The under-5-weeks rule now only applies to single treatments.** In the postcode lottery, a trust's figure for one treatment is left out if its typical operation wait is under 5 weeks: 142 trust-and-treatment pairs this month, listed in the findings JSON. Example: Royal Berkshire's orthopaedic wait (3.8 weeks) isn't shown as "fastest". The rule no longer flags whole trusts, because a trust doing a lot of quick day-case work can have a short typical wait overall without anything being wrong.

## 3. Automation (GitHub Action)

File: `.github/workflows/refresh.yml`.

- **Schedule:** second Thursday of each month at **10:30 UK time**. GitHub can't schedule "second Thursday" directly, so it wakes every Thursday at 09:30 and 10:30 UTC and only carries on when it's day 8-14 of the month and 10:30 in London (this works in both GMT and British Summer Time).
- **What it does:** runs `kitchen/run_all.py` (which ends with the findings), commits any changed data files, then triggers a Netlify rebuild.
- **Manual trigger:** yes. "Run workflow" on the GitHub Actions tab runs it straight away.
- **Netlify hook:** written into the workflow, reading a repository secret called `NETLIFY_BUILD_HOOK`. **Not set up yet:** the project isn't on GitHub, so the secret doesn't exist. If it's missing, the deploy step stops with a clear error.

## 4. Report facts for August 2026

Contents of `data/processed/report-facts-2026-08.json`:

```json
{
 "month": "2026-08",
 "compared_with": "2025-08",
 "england": {
  "waiting": {
   "then": 7345544,
   "now": 7189213
  },
  "pct_within_18_weeks": {
   "then": 60.9,
   "now": 65.2,
   "change_points": 4.2
  },
  "over_52_weeks": {
   "then": 192024,
   "now": 112958
  }
 },
 "most_improved_trusts": [
  {
   "name": "Countess of Chester Hospital NHS Foundation Trust",
   "waiting_now": 31910,
   "pct_18_then": 48.8,
   "pct_18_now": 68.4,
   "change_points": 19.5
  },
  {
   "name": "Mid Cheshire Hospitals NHS Foundation Trust",
   "waiting_now": 30270,
   "pct_18_then": 54.8,
   "pct_18_now": 70.6,
   "change_points": 15.7
  },
  {
   "name": "Liverpool Women's NHS Foundation Trust",
   "waiting_now": 11052,
   "pct_18_then": 46.0,
   "pct_18_now": 61.3,
   "change_points": 15.3
  },
  {
   "name": "The Princess Alexandra Hospital NHS Trust",
   "waiting_now": 40233,
   "pct_18_then": 52.8,
   "pct_18_now": 67.1,
   "change_points": 14.4
  },
  {
   "name": "East Lancashire Hospitals NHS Trust",
   "waiting_now": 46343,
   "pct_18_then": 60.1,
   "pct_18_now": 72.1,
   "change_points": 12.0
  }
 ],
 "least_improved_trusts": [
  {
   "name": "County Durham and Darlington NHS Foundation Trust",
   "waiting_now": 54410,
   "pct_18_then": 68.7,
   "pct_18_now": 64.2,
   "change_points": -4.5
  },
  {
   "name": "Barking, Havering and Redbridge University Hospitals NHS Trust",
   "waiting_now": 65760,
   "pct_18_then": 71.6,
   "pct_18_now": 68.2,
   "change_points": -3.3
  },
  {
   "name": "North Tees and Hartlepool NHS Foundation Trust",
   "waiting_now": 24063,
   "pct_18_then": 72.7,
   "pct_18_now": 69.6,
   "change_points": -3.1
  },
  {
   "name": "University Hospitals of North Midlands NHS Trust",
   "waiting_now": 75543,
   "pct_18_then": 62.9,
   "pct_18_now": 60.0,
   "change_points": -2.9
  },
  {
   "name": "Great Western Hospitals NHS Foundation Trust",
   "waiting_now": 42540,
   "pct_18_then": 60.5,
   "pct_18_now": 57.7,
   "change_points": -2.8
  }
 ],
 "trust_types_included": [
  "acute",
  "specialist"
 ],
 "most_improved_areas": [
  {
   "name": "Shropshire, Telford and Wrekin",
   "waiting_now": 68115,
   "pct_18_then": 59.2,
   "pct_18_now": 69.4,
   "change_points": 10.2
  },
  {
   "name": "Birmingham and Solihull",
   "waiting_now": 161173,
   "pct_18_then": 58.5,
   "pct_18_now": 67.3,
   "change_points": 8.8
  },
  {
   "name": "Norfolk and Suffolk",
   "waiting_now": 212871,
   "pct_18_then": 56.6,
   "pct_18_now": 64.3,
   "change_points": 7.7
  },
  {
   "name": "Cheshire and Merseyside",
   "waiting_now": 340941,
   "pct_18_then": 58.4,
   "pct_18_now": 65.9,
   "change_points": 7.6
  },
  {
   "name": "West and North London",
   "waiting_now": 490660,
   "pct_18_then": 60.4,
   "pct_18_now": 67.9,
   "change_points": 7.5
  }
 ],
 "least_improved_areas": [
  {
   "name": "Humber and North Yorkshire",
   "waiting_now": 227338,
   "pct_18_then": 60.6,
   "pct_18_now": 60.5,
   "change_points": -0.1
  },
  {
   "name": "Staffordshire and Stoke-On-Trent",
   "waiting_now": 149128,
   "pct_18_then": 63.2,
   "pct_18_now": 63.6,
   "change_points": 0.4
  },
  {
   "name": "Devon",
   "waiting_now": 78994,
   "pct_18_then": 62.1,
   "pct_18_now": 62.8,
   "change_points": 0.6
  },
  {
   "name": "Hampshire and Isle of Wight",
   "waiting_now": 212432,
   "pct_18_then": 62.0,
   "pct_18_now": 63.1,
   "change_points": 1.1
  },
  {
   "name": "Nottingham and Nottinghamshire",
   "waiting_now": 127125,
   "pct_18_then": 62.7,
   "pct_18_now": 63.9,
   "change_points": 1.3
  }
 ],
 "most_year_long_waits": {
  "name": "Mid and South Essex NHS Foundation Trust",
  "over_52_weeks": 13427,
  "share_of_england_pct": 11.9
 },
 "biggest_postcode_lottery": {
  "name": "Oral Surgery",
  "gap_weeks": 65.0,
  "fastest": "Frimley Health NHS Foundation Trust",
  "fastest_weeks": 6.8,
  "slowest": "Mid and South Essex NHS Foundation Trust",
  "slowest_weeks": 71.7
 },
 "milestones": {
  "65_pct_within_18_weeks_met": true,
  "92_pct_within_18_weeks_met": false
 },
 "check_before_using": 66
}
```

## 5. What failed, what was skipped, and what needs you

**Failed:** nothing in the final run. Problems found and fixed along the way:
- The NHS England website dropped a connection once, so all downloads now retry automatically.
- Three months of FFT files used short names ("ip", "op", "ae") and two used "outpatients" with an s. They were being missed and are now picked up.
- Matching CQC by ODS code alone left 25 NHS trusts unmatched. It now also uses CQC's provider ID, which for NHS trusts is the same code.

**Skipped:**
- **National Joint Registry**: not ingested, because there's no open re-use licence. The reason is recorded in `kitchen/registry.json`.
- 4 NHS trusts still have no CQC rating at any level: Sheffield Children's, Cornwall Partnership, Lincolnshire Partnership, and Cambridgeshire and Peterborough.

**Needs you:**
1. **Put the project on GitHub.** It isn't a Git repository yet, so the monthly Action can't run. Processed data will be committed; raw downloads (about 3 GB) are excluded.
2. **Connect the Netlify site to that GitHub repository** and create a build hook. The site is currently deployed from this computer with the Netlify command-line tool.
3. **Add the repository secret** `NETLIFY_BUILD_HOOK` with the build hook's URL.
4. **NJR licence (optional):** to use NJR data you'd need to apply with their data request form and sign their data-sharing agreement, which may cost money.
5. **Deploy when ready.** The website's data files in `site/data/` were refreshed by this run (same formats; the site still works locally), but nothing has been deployed.

## Update - under-5-weeks rule

On your instruction, the "typical operation wait under 5 weeks" check now applies only to single treatments (the postcode lottery), not to whole trusts. Before this change it flagged three acute trusts with steady figures and lots of quick day-case work (University Hospitals Birmingham, Royal Berkshire and Milton Keynes) and kept them out of "most improved". After re-running the findings:
- The "check before using" list went from 81 providers to 66, with no acute or specialist trusts.
- University Hospitals Birmingham (+10.9 points) is back in the most improved top 10, in 10th place, and still counts as a turnaround. Milton Keynes (+8.7 points) is no longer flagged but isn't in the top 10.
- The postcode lottery is unchanged at the top. Oral surgery is still the biggest gap (65 weeks), and trust-and-treatment pairs under 5 weeks are still left out of "fastest".

*Correction to an earlier message in this session: I said no acute trusts were flagged "check before using". That was wrong at the time - three were. After this change, none are.*
