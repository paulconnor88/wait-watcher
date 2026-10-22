# Kitchen changes - phases 3 and 4 (October 2026)

Written 21 October 2026, after the full run of `kitchen/run_all.py`: all 34 steps passed in 10.7 minutes. This follows `CHANGELOG-2026-10.md` (phase 2). Latest waiting-time month: **August 2026**.

## What changed, in short

- **Wait Watcher Lab is live** at https://wait-watcher-lab.netlify.app, built for Macarena. It was redeployed on 21 October with the phase 3 data. Phase 4 isn't in the Lab yet.
- **Phase 3: 18 new NHS access sources.** These cover cancer, A&E, GP appointments, mental health, community services, ambulances, dentistry, workforce, the weekly waiting list, area context and the other UK nations. Three of them stop at the licence check.
- **Phase 4: UK clinical research.** ClinicalTrials.gov and ISRCTN are merged into one list of 42,795 UK studies, with sites matched to our trusts. NIHR, HRA and Be Part of Research were checked; none could be ingested.
- **The monthly findings gained two sections.** Section 10 is "what's new" across the new sources; section 11 is research. Both are written as pictures, never causal claims.
- **`questions.md`:** every question the kitchen can answer, grouped as patients, GPs, NHS insiders, journalists and research, each with an example answer from the latest data.
- **Privacy rule for research data:** no contact names, emails or phone numbers are ever stored.
- **No changes to the public website** (`site/`).

## 1. Phase 3 sources (NHS access)

Every source prints its licence before ingesting. All the ingested ones are under the Open Government Licence. "Ours" means the 566 provider codes in the waiting-list data. Coverage is April 2024 to the latest month unless stated.

| Source | What it gives | Grain | Latest | Coverage |
|---|---|---|---|---|
| e-RS appointment slot issues | GP referrals with no slot to book, per 100 bookings | provider; provider x specialty | Sep 2026 | 360 providers (189 ours). England 36.6 per 100 bookings |
| WLMDS | Weekly waiting list (management information, not the official count) | England by week; provider snapshot monthly | w/e 30 Aug 2026 | 7.12m waiting. Weekly series back to 2021 |
| Cancer waiting times | FDS (told within 28 days), 31-day, 62-day. **Sensitive: gentle copy required** | trust x standard (x cancer type) | Aug 2026 | 191 providers (154 ours). England FDS 78.6%, 31D 92.1%, 62D 71.9%. 10 of 125 trusts meet 62D |
| GP practices | Every practice, located (postcodes.io) | practice | current | 6,556 active |
| GP appointments (GPAD) | Booking-to-appointment time, mode, missed appointments | practice; ICB | Aug 2026 | 6,106 practices. 45.1% same day, 5.6% more than 28 days |
| Talking therapies | Referrals, 6/18-week starts, recovery, second-appointment waits | provider | Aug 2026 | 154 providers. 83.4% within 6 weeks, 50.3% recovered |
| Mental health (MHSDS) | Children: referral to first contact. Adults: to **second** contact | provider (3-month rolling) | Aug 2026 | 462 providers. No spells file for Jan 2025 |
| Community services | 47 services (e.g. children's speech therapy, wheelchairs) by wait band | provider x service | Aug 2026 | 1.25m waiting. 79,031 children over a year for community paediatrics |
| A&E | 4-hour %, 12-hour waits from decision to admit | trust | Sep 2026 | England 74.4% (major A&E 60.6%) |
| Ambulance | Category 1 and 2 response times | ambulance trust; region | Sep 2026 | Category 2 mean 31.3 minutes |
| Winter sitreps | Bed occupancy, handover delays | trust x day (winter only) | winter 2025-26 | 93.4% beds occupied; 27% of handovers over 30 minutes |
| Workforce | Vacancy rate (**region x sector only**); sickness absence by trust | region; trust | Jun 2026 | England vacancy rate 6.7% |
| Fingertips | Deprivation, over-65s, healthy life expectancy | ICB (pre-2026); council | 2022-25 | 42 ICBs, 153 councils |
| ONS population | Population and over-65s | council; ICB | mid-2025 / mid-2024 | England 58.8m |
| NHS dental | Adults and children seen | contract; ICB | Jul 2026 | 17.7m adults seen in the last 24 months |
| Scotland, Wales, NI | Headline waits, flagged **not comparable** with England | nation | Aug 2026 | |
| GP Patient Survey | Not ingested: the licence isn't stated (Ipsos-hosted) | | | |
| PHIN | Not ingested: its terms forbid republishing | | | |

Notes:
- **"Check before using" files:** most sources write a `check_before_using.json` of providers whose main figure moved 15+ points in a month. For appointment slot issues the threshold is 50 points, because the rates run into the hundreds. WLMDS also lists providers NHS England names as having data issues.
- **Not published:**
  - Trust-level vacancy rates (only region and sector).
  - Referral counts by provider (e-RS).
  - Adult referral-to-first-contact mental health waits.
  - A provider-by-treatment table for WLMDS.

## 2. Phase 4 sources (UK clinical research)

| Source | Status | Coverage |
|---|---|---|
| ClinicalTrials.gov (API v2) | Ingested. Terms allow free use if you attribute it, keep the data current, show the processing date and state your changes. **Treated as equivalent to an open licence: needs your OK** | 29,059 studies with a UK site, 100,776 UK sites, 2,822 recruiting |
| ISRCTN (XML API) | Ingested, CC BY ("Contains information from the ISRCTN registry, licensed CC BY") | 15,082 UK studies, 44,112 centres, 1,178 recruiting |
| Merged list (`trials`) | Built | 42,795 studies. 1,284 in both registries, 27,760 on ClinicalTrials.gov only, 13,751 on ISRCTN only. 4,083 recruiting |
| NIHR research activity league table | **Not ingested.** No trust-level table since 2018/19; RDN portfolio data is by region and specialty only; "© NIHR" only; nihr.ac.uk was unreachable on 21 Oct | |
| HRA research summaries | **Not ingested.** HRA copyright allows "research or private study" only; no bulk download (about 68,600 pages) | |
| Be Part of Research | Links only. Study pages use an internal ID, so each study gets a search link instead | |

**How the research data works**
- **Refresh:** weekly, fetching only studies updated since the last run. A full fetch runs every 28 days.
- **De-duplication:** records are linked by a shared ISRCTN, IRAS or NCT number. Most of the 1,284 links (1,265) come from ISRCTN records naming their NCT number, 263 from a shared ISRCTN number and 42 from IRAS.
- **Site matching never guesses.** The rules apply in this order:
  1. Hand overrides.
  2. Exact name plus postcode: 27% of study-sites.
  3. Named exactly as an NHS trust: 6%.
  4. The postcode belongs to one NHS trust: 18%.
  5. A very close name in the same town: 5%, with strict tie rules.
  - **Not matched:** 24% unmatched, 9% placeholder names like "Research Site", and 11% outside England.
  - **Result:** 63% of English study-sites match, at 169 of our providers.
- **Conditions:** 71% of studies map to one of our treatment functions, using reviewable rules in `kitchen/trial_condition_rules.json`. The result is in `trials/condition_mapping.json`. Cancers are mapped by body site, which is a reasoned guess.
- **Privacy:**
  - Contacts, named investigators and free-text protocol numbers are dropped as data arrives.
  - "Who is the main contact?" sections are cut from summaries.
  - Any email or phone number left in free text is removed.
  - A final scan found no email addresses in any research file.

## 3. Findings and questions

**Section 10, "what's new":**
- **Slot issues:** the highest appointment slot issue rates.
- **Cancer:** standards most and least met, written gently ("furthest from the standard", never "worst").
- **GP access:** best and worst by ICB and council. Gloucestershire has 11.1% of appointments more than 28 days after booking; North East London has 2.0%.
- **A&E:** trusts furthest from four hours.
- **Staffing and waits, as a picture:** no clear link between sickness absence and waits (correlation 0.06).

**Section 11, research:**
- **Per head:** recruiting studies per 100,000 people range from Camden (317) and Oxford (283) to many districts with none.
- **Trust ranking:** trusts ranked by recruiting studies. Manchester University (388) and Guy's and St Thomas' (385) lead.
- **Departments:** waits against research. Oral surgery has the longest typical wait (16.4 weeks) and 0.9 recruiting studies per 10,000 waiting.
- **Industry share:** dermatology is the most industry-led, at 66% of its studies.
- **Research and waits:** recruiting studies against % within 18 weeks for 113 acute trusts shows no clear link (correlation −0.06). This stands in for NIHR activity, which isn't published by trust.

**`questions.md`** has 46 questions across five audiences. Patient examples are anchored on Walthamstow (Barts Health, NELFT, North East London ICB). There is also a `questions.json` copy for the Lab.

## 4. The Lab (for Macarena)

- **Explore:** 10 new datasets:
  - Cancer waits (with a gentleness note).
  - A&E.
  - Slot issues.
  - Talking therapies.
  - Mental health.
  - Community services.
  - GP access by ICB and by council.
  - Ambulances.
  - Dentistry.
- **Home:** six new question cards, plus "questions by who's asking".
- **Trust pages:** now show A&E, slot issues and cancer.
- **About the data:** describes every source.
- **Not yet in the Lab:** the phase 4 research data and the Research questions. The Lab ignores the new audience.

## 5. Automation

- **Monthly** (`.github/workflows/refresh.yml`, second Thursday): runs all 34 steps. The timeout was raised to 180 minutes, because the first run downloads about 3 GB.
- **Weekly** (`.github/workflows/weekly.yml`, Thursday 08:00 UK): WLMDS, e-RS and the trial registries, then the Lab's data.
  - WLMDS and e-RS actually publish monthly, so those steps mostly find nothing.
  - The registries change daily.
- **Both actions are written but not running yet:** the project isn't a git repository.

## 6. What you need to do

1. **Put the project on GitHub** and add the secrets `NETLIFY_BUILD_HOOK` and `NETLIFY_LAB_BUILD_HOOK`. Until then nothing refreshes automatically.
2. **Confirm the ClinicalTrials.gov terms are acceptable.** They're attribution-style and not the OGL, and they note copyright applies outside the US.
3. **Hand-map trial sites** in `kitchen/trial_site_overrides.json`.
   - The list is `data/processed/trials/unmatched_sites.csv`, most common first.
   - Real NHS hospitals to map include St Bartholomew's, the Royal London, Royal Brompton, Churchill, Queen Elizabeth Birmingham, the National Hospital for Neurology and Neurosurgery, Brighton and Sussex (now merged) and Papworth.
   - Universities and units (UCL, King's College London, the MRC Clinical Trials Unit) should be set to `null`, meaning checked and deliberately unmatched.
4. **Licences to ask about:**
   - GP Patient Survey: GPPatientSurvey@ipsos.com.
   - NIHR trust-level research activity under the OGL.
   - HRA research summaries.
   - PHIN and the National Joint Registry: written consent would be needed.
5. **Decide whether the Lab should get the research data**, and redeploy only with your approval.

## 7. Known limits and loose ends

- **Frimley ICB** (abolished March 2026) has no mapping to today's areas.
- **Fingertips and ONS ICB data** use the 42 pre-2026 ICBs; GP appointments and dental use today's 36.
- **Winter sitreps for 2026-27** are expected from early December.
- **GP "time to appointment"** starts at booking, not at first asking.
- **Mental health waits** may break around November 2024, when NHS England changed its method; the jump check flags affected providers.
- **Research data:**
  - A facility name occasionally contains a person's name (it's the registry's own facility field). Investigator and contact fields are never stored.
  - A study counts in every area where it has a site.
  - Scottish, Welsh and Northern Irish sites aren't matched (ODS is England only).
