# Data check: out/research (UK clinical research next to NHS waits, October 2026)

Checked 21 October 2026 against `findings.md`, `method-1.md` to `method-4.md`, `analysis.py`, `numbers.json` and the three slides.
I didn't write any of these. Every number below was recomputed with my own code, not with `analysis.py`. It reads the raw RTT
extract (`data/raw/rtt/20260831-RTT-August-2026-full-extract.csv`), the raw ClinicalTrials.gov store (`data/raw/clinicaltrials/studies.jsonl`)
and the kitchen's processed trials, cancer and e-RS files.

**Overall: every number reproduces exactly. The problems are in the claims and the framing.**

---

## Shared checks (apply to every finding)

| Step | Result | Note |
|---|---|---|
| 1 Sources | pass | RTT from NHS England (Aug 2026 full extract, published 8 Oct 2026); cancer and e-RS from NHS England / NHS Digital; ClinicalTrials.gov API and ISRCTN pulled 21 Oct 2026 (`state.json`). Raw files kept. Postcode-to-ICB from postcodes.io (cached in `data/raw/trials/postcode_icb.json`). |
| 2 Code, not chat | pass | Every figure comes from `analysis.py` and reproduces from an independent re-implementation. |
| 3 Reconcile | **fail** | File total is **7,189,213** pathways, 65.16% within 18 weeks, 112,958 over 52 weeks. The NHS England press notice says **7.4 million** (including estimates for missing trusts), 65.2%, 113,339 over 52 weeks, and about **6.2 million unique patients**. `findings.md` says 7.19m is "matching the published figures". It isn't: the gap is about 0.2m, not the usual 0.1m, because **four trusts didn't submit for August**: Sheffield Teaching (RHQ, missing since July 2025), Torbay (RA9, since April 2026), Plymouth (RK9, since July 2026) and Northampton (RNS, August 2026). The 18-week % does match. |
| 5 Definitions | **fail** | "People waiting" is used throughout for RTT **pathways** (NHS England: about 85 patients per 100 pathways). No project definitions file found; the method files' "shared definitions" are the nearest thing. |
| 8 Licence | partial | ClinicalTrials.gov (processing date + changes) and ISRCTN CC BY lines are on every slide and method file. **Missing:** the OGL line for NHS England data ("Contains public sector information licensed under the Open Government Licence v3.0"). Also missing: postcodes.io as its own entry in `kitchen/registry.json`, and its ONS/OS/Royal Mail attribution (needed for finding 1, which depends on postcode-to-ICB). `findings.md` has no attribution lines at all; the LinkedIn post text needs them. |
| 8 Personal data | pass (outputs) / **warn** (kitchen) | Nothing personal in `out/research/` (findings, methods, `numbers.json`, slides) or in my recompute CSVs. But `data/processed/trials/sites.csv` has **132 facility names that are individuals** ("Dr …", "Professor …"). They don't appear in these outputs. Strip them before any Lab or CSV release that shows facility names. |
| 9 Human eyes | to do | Macarena: to do. Leo: to do. |
| 10 Working | partial | Methodology footers on all slides. No visible corrections policy found in the repo. |

---

## Finding 1: Essex 1 recruiting study per 2,463 waiting; North East London 1 per 548

| Step | Result | Note |
|---|---|---|
| 1 Sources | pass | As above. |
| 2 Reproduce | pass | From raw RTT, Essex 283,275 and NEL 249,427 pathways (C_999, Part_2, by commissioner parent). 115 and 455 distinct recruiting studies with a site postcode in each ICB. 2,463 and 548; ratio 4.49. Median ICB 745; Essex 2nd of 36; Essex over-52s 14,297, England's highest ICB. All match. |
| 3 Reconcile | **fail (context only)** | Essex and NEL are complete, but the ranking is not. The non-submitters make the "best" end of the table look better than it is. Devon (shown 280) has lost about 70k pathways since March; Northamptonshire (751) fell 40% in one month; South Yorkshire (314) has had no Sheffield data for 14 months; Cornwall (421) too. Using their last full months: median about 785, not 745. Essex stays 2nd. |
| 4 Two ways | pass / to do | Re-implemented independently (fresh context). Spreadsheet check: `recompute-1.csv`. |
| 6 Flags | pass | No RTT `check_before_using.json` exists. Site-matching caveat: this finding uses site postcodes (84% of recruiting sites have one), not trust matching. Essex's trusts are covered: RAJ 99/108, RDE 62/66, RQW 5/6 have postcodes. |
| 6 Small numbers | pass | Large counts. |
| 6 Like with like | warn | "Trial" in the headline and slide, but 32% of recruiting studies are **observational**. Interventional only: Essex 96 (1 per 2,951), NEL 394 (1 per 633), ratio 4.7. The finding holds; the word is wrong. |
| 7 Denominators | **fail** | "People waiting" means pathways. "Second-worst" is ranking language. |
| 7 Periods | pass | RTT Aug 2026 against studies recruiting on 21 Oct 2026; stated. |
| 7 Causal | pass | None. |
| 7 Evidence vs guess | pass | Caveats on cross-border recruitment are good. |
| 8 Licence | partial | Needs the OGL line and postcode attribution (see shared). |

**Verdict: FIX FIRST.** The headline survives; the wording and context need changing.

---

## Finding 2: Lung care about 16× the recruiting studies of bones and joints, per person waiting

| Step | Result | Note |
|---|---|---|
| 2 Reproduce | pass | Raw RTT: C_340 182,914, C_110 851,183 pathways. 428 and 127 recruiting studies. 23.4 and 1.49 per 10,000; ratio 15.7. Department table matches. |
| 3 Reconcile | warn | The four missing trusts are absent from the department totals too. Small effect on rates; say so. |
| 4 Two ways | pass / to do | `recompute-2.csv` flags each study as cancer or infection. |
| 6 Small numbers | **fail** | "General surgery 0.3" is 11 studies and "plastic surgery 0.4" is 4. These are under 30 and are being ranked. 1,025 of 4,083 recruiting studies (25%) map to no department at all. "3 in 4 right" comes from 15 studies per department. |
| 6 Like with like | **fail** | The rules put lung cancer, mesothelioma and pneumonia into "lungs": 157 of the 428 are cancer studies and 43 are infection studies. Bones gets only sarcoma and bone cancer (37). Excluding cancer and infection on both sides gives **12.5×** (12.5 against 1.0 per 10,000), not 16×. |
| 7 Claim check | **fail** | "The longest-wait surgical departments are all at the bottom: general surgery 0.3…" is wrong twice. (a) General surgery's typical wait is 12.8 weeks, 8th longest. Gynaecology (14.2, 3rd longest) is missing from that list. (b) General surgery's 0.3 is very likely a mapping artefact: none of the 202 recruiting breast or colorectal cancer studies map to C_100 (they go to X05, C_301 etc.). In RTT, breast and colorectal surgery sit inside General Surgery (verify against NHS England's treatment function grouping). |
| 7 Denominators | **fail** | "Per person waiting" means per pathway; "trials" means studies. |
| 7 Evidence vs guess | pass | Slide footer says "rule-based guess"; good. |
| 8 Licence | partial | As shared. |

**Verdict: FIX FIRST.** Say "12 to 16 times" or exclude cancer and infection, drop the general-surgery and plastic-surgery line, and fix the wording.

---

## Finding 3: Trusts running the most studies have the same waits as everyone else

| Step | Result | Note |
|---|---|---|
| 2 Reproduce | pass | 113 acute trusts; r = −0.06; quartile medians 65.3 / 65.4 / 64.7 / 64.0. From raw RTT the top quartile is 63.9: the kitchen rounds each trust to 1 dp before taking the median. Harmless. Cancer 62D: 118 trusts, r = −0.04, 71.1 against 73.3. e-RS: 91 trusts, r = −0.02. All match. |
| 3 Reconcile | warn | RHQ, RA9, RK9 and RNS have no August RTT, so they're silently absent from the 113. Say so. |
| 4 Two ways | pass / to do | Rank correlation −0.11 (RTT), −0.07 (62D); interventional-only −0.06. `recompute-3.csv`. |
| 6 Flags | **fail** | `analysis.py` never reads `check_before_using.json`. Cancer: 21 flagged trusts are in the 62D set; excluding them gives r = −0.07, so the conclusion holds. **e-RS: 9 flagged trusts are in the set (RBK, RC9, RF4, RFS, RKE, RL4, RNA, RNN, RTX); excluding them moves r from −0.02 to +0.20.** That's a weak sign that research-heavy trusts have *more* slot issues. The "no link in three separate measures" claim doesn't survive for e-RS. |
| 6 Site matching | pass | 63% caveat is on the slide and in the brief (62.8% recomputed). |
| 6 Like with like | pass | Acute only; specialist trusts excluded (say so). |
| 7 Claim check | **fail** | The brief leaves out the cancer **28-day FDS** result (r = **+0.16**), which `numbers.json` holds. It says "nothing at all, in any direction"; with FDS and flag-cleaned e-RS, it's "weak and mixed". Quartile labels overlap ("2 to 17", "17 to 30"; "33 to 99", "99 to 389") because 5 trusts have exactly 17 studies. Values are **medians**; the brief doesn't say so (the slide's "typical trust" does). "Trials" again means studies. |
| 7 Causal | pass | "A picture, not a cause" and "no link is the finding". Good. |

**Verdict: FIX FIRST.** Drop e-RS or report it with flags excluded, mention FDS, name the four missing trusts, and say "studies".

---

## Finding 4: Industry trial starts held steady (−3%); academic fell (−14%)

| Step | Result | Note |
|---|---|---|
| 2 Reproduce | pass | Interventional starts a year: industry 725 → 703 (−3.0%); academic and other 1,021.7 → 873.7 (−14.5%). Registration lag from the raw ClinicalTrials.gov file: 11.3 / 3.0 (2019), 8.0 / 1.8 (2023). All match. Department table matches. |
| 7 Comparison periods | **fail** | **The two periods are not like-for-like.** Since 1 January 2022 the HRA has **automatically registered** clinical trials of medicines (CTIMPs) going through combined review on ISRCTN. Industry trials on ISRCTN jump from about 27 a year (2017–19) to about 118 a year (2022–24). On ClinicalTrials.gov alone, industry starts **fell about 16%** (698 → 586 a year). So "industry held steady" is very likely an artefact of the registry change, not a real trend. The same change also adds academic CTIMPs from 2022, so the academic −14% is not clean either: ClinicalTrials.gov alone gives −21%, ISRCTN alone −3%. |
| 6 Small numbers | **fail** | The department table ranks plastic surgery (6 → 2 a year), general surgery (5 → 3) and cardiothoracic (3 → 5); "mouth and jaw −18%" is 15 → 12 a year. Too small to rank. |
| 7 Claim check | **fail** | The brief opens by saying the industry expectation "was the wrong way round". That claim rests on this artefact. "University and NHS-led" really means "academic and other", which includes charities and government. |
| 7 Causal | pass | No causal language. |

**Verdict: DON'T PUBLISH** in its current form. It has no slide, but the brief's opening paragraph depends on it. Re-do it either on one registry, or with registration source controlled and HRA auto-registration named.

---

## Other claims in findings.md

- "42,795 studies; 1,284 both / 27,760 / 13,751; 4,083 recruiting; 18,965 sites; 31 recruiting since before 2010; 16% no postcode; 63% matched": all **pass**.
- "Starts peaked at 2,443 in 2021; 2,063 in 2024; 1,987 in 2025": **pass**. But 2025 is quoted while the brief itself says 2025–26 is still filling in. Label it provisional.
- "7.19 million waiting, matching the published figures": **fail**. See step 3.

---

## Recompute files (spreadsheet checks)

| File | Key number | How to check |
|---|---|---|
| `recompute-1.csv` | Essex 2,463 and NEL 548 | Block A (raw RTT rows): SUM `waiting_pathways` by `icb`. Block B (recruiting site rows): COUNT UNIQUE `study_id` by `icb`. Divide. Postcodes cut to district; no facility names. |
| `recompute-2.csv` | 23.4 against 1.5 per 10,000 (16×) | Block A: SUM `waiting_pathways` by `department`. Block B: COUNT UNIQUE `study_id`, then again with `is_cancer_study` = no and `is_infection_study` = no (gives 12.5×). |
| `recompute-3.csv` | Quartile medians 64.0 against 65.3 | Block A: by `provider_code`, SUM(`within_18_weeks`) / SUM(`waiting_pathways`). Block B: COUNT `study_id` by `provider_code`. Rank, cut into 4 groups (29/28/28/28), MEDIAN. `within_18_weeks` is the raw file's first 18 weekly columns, summed per row. |
| `recompute-4.csv` | Industry 725 → 703, academic 1,022 → 874 a year | Pivot `industry_or_academic` × `period` count ÷ 3. Add `sources` to the pivot to see the ISRCTN jump. |

---

## Fixes needed

1. Replace "matching the published figures": say the file has 7.19m pathways against NHS England's 7.4m headline (including estimates), and name the four non-submitting trusts.
2. Say "waits" or "pathways", not "people", throughout the brief and all three slides (or footnote "pathways; about 85 patients per 100").
3. Say "studies", not "trials", on slides 1–3 (or rerun on interventional only: finding 1 becomes 2,951 against 633).
4. Finding 1: note the missing-trust effect on Devon, Northamptonshire, South Yorkshire and Cornwall; quote the median as about 750–785; drop "second-worst".
5. Finding 2: give the ratio as "12 to 16 times" (or exclude cancer and infection); delete the "longest-wait surgical departments are all at the bottom" line; flag counts under 30.
6. Finding 3: read `check_before_using.json`. Drop e-RS or report it with flags excluded (r = +0.20). Report the FDS +0.16. Label the figures as medians and fix the overlapping quartile labels.
7. Finding 4: pull it from the brief, and rewrite the opening "expectations" paragraph, until registry coverage (HRA auto-registration from 2022) is controlled for.
8. Add "Contains public sector information licensed under the Open Government Licence v3.0" for NHS England data. Add postcodes.io to `kitchen/registry.json` with its ONS/OS/Royal Mail attribution. Add attribution lines to the post text.
9. Strip personal names from `facility` in `data/processed/trials/sites.csv` before any release that shows facility names.
10. Human review: Macarena (clinical wording, especially the general-surgery mapping) and Leo (method).

Sources checked: [NHS England RTT statistical press notice, August 2026](https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/10/Aug26-RTT-statistical-press-notice-PDF-389K-vjgRdG.pdf); [HRA: combined review and automatic registration](https://www.hra.nhs.uk/about-us/news-updates/combined-review-here-and-applicants-benefit-automatic-registration/); [HRA–ISRCTN partnership Q&A](https://hra.nhs.uk/planning-and-improving-research/research-planning/research-registration-research-project-identifiers/hra-isrctn-registry-partnership-questions-and-answers).

Human review: Macarena to do, Leo to do

Verdict: FIX FIRST (findings 1–3 after fixes 1–6, 8 and 10; finding 4 DON'T PUBLISH until fix 7)
