# Wait Watcher: outstanding actions

What's left to make the data library robust, refreshing itself, and trustworthy. Written 22 October 2026, after kitchen phases 2-4.

**Where it stands (22 October):**
- **Kitchen:** 35 steps, including the reconciliation gate, all passing.
- **GitHub:** the project is at github.com/paulconnor88/wait-watcher (public). The monthly and weekly actions are ready to run.
- **Websites:** deploys are paused, pending a decision on a public site.

**How to read this:**
- Sections are in priority order.
- **You** means only you can do it: accounts, decisions, emails, judgement.
- **Ask Claude** means it's a code change; say "do item 3.2" and it can be done in a session.
- Effort is a rough guide.

---

## 1. Get it running on its own (do these first)

Until these are done, the data only refreshes when someone runs it by hand.

- [x] **1.1 Put the project on GitHub.** Done 22 October: github.com/paulconnor88/wait-watcher, branch `main`.
- [ ] **1.2 Switch the website deploys on.** Paused by decision (see 2.5).
  - Both actions contain Netlify CLI deploy steps, switched off (`if: false`), marked "deploy paused - site IDs to be added". The `NETLIFY_AUTH_TOKEN` secret is already set.
  - To switch on: add each Netlify site ID and change `if: false` to the condition written next to it.
- [x] **1.3 Stop the repository ballooning.** Done 22 October.
  - Committed: code, docs, `site/data`, `lab/data`, findings, report facts, questions, the registry, coverage and reconciliation.
  - Kept out by `.gitignore`: `data/raw` and the big rebuildable CSVs. The actions keep those in GitHub's cache between runs.
- [ ] **1.4 Back up the raw downloads.** You, about 15 minutes, then automatic.
  - `data/raw` (3.6 GB) only exists on this laptop and, later, in GitHub's cache. GitHub can evict caches.
  - Some of it can't be fetched again: older e-RS reports came from the UK Government Web Archive, provisional cancer files get replaced, and ODS lists change weekly.
  - Copy it somewhere safe now (an external drive or cloud storage), and again every few months.
- [ ] **1.5 Upgrade Python on the laptop to 3.11 or later.** You, about 15 minutes; Ask Claude to rebuild `.venv`.
  - The laptop uses Python 3.9, which stopped getting security fixes in October 2025. Its old SSL library caused the dropped connections seen during runs.
  - The GitHub actions use 3.11, so matching them means a laptop run behaves like the automated one.
- [ ] **1.6 Watch the first automated runs.** You, about 1 hour over a week.
  - Run the monthly action by hand first ("Run workflow" on the Actions tab). The first run downloads about 4 GB and may take 2 to 3 hours.
  - Check the log ends with "All 35 steps finished" and that the reconciliation table shows no failures.
  - The weekly action needs the monthly action's cached data, so run the monthly one first.
  - Turn on GitHub's email alerts for failed workflow runs (Settings > Notifications > Actions), so a failure doesn't go unnoticed.

## 2. Decisions only you can make

- [x] **2.1 ClinicalTrials.gov terms: accepted** (22 October). Every use attributes ClinicalTrials.gov, shows the processing date and states our changes; the weekly refresh keeps the data current.
- [x] **2.2 Public or private repository: public** (the repository was created public). Nothing personal is committed; contact details are stripped from the trial registries before anything is stored.
- [x] **2.3 Weekly action: trial registries only** (22 October). It refreshes ClinicalTrials.gov, ISRCTN, the merged trials data and the Lab's data. Everything else refreshes monthly.
- [x] **2.4 Redeploy rule** (22 October). Once deploys are on:
  - **Routine data refreshes deploy automatically:** new months of the same figures, through the reconciliation gate.
  - **Anything with new findings or new wording waits for your OK:** new findings, new datasets or changed text on either site.
- [ ] **2.5 Deploys are paused pending a decision on a public site.** Decide whether Wait Watcher and the Lab go public under automation, then add the site IDs (1.2).
- [x] **2.6 Which England waiting-list figure to quote.** Decided 22 October 2026: every England total is on NHS England's commissioner basis (7,158,164 for August 2026); the headline with estimates (7,370,100) is named only when the press is using it; trusts and departments stay on all rows. The standing rule is in `kitchen/DEFINITIONS.md`.
- [x] **2.7 Allow `xlrd` (a fourth library).** Approved and done 22 October 2026: the gate now checks diagnostic waits (DM01) against NHS England's `.xls` series.

## 3. Licences and permissions to chase

Each needs an email from you. Until a reply, the source stays out and the reason stays in `kitchen/registry.json`.

- [ ] **3.1 GP Patient Survey:** GPPatientSurvey@ipsos.com. Ask: "Is the practice-level results CSV available under the Open Government Licence?"
  - The script is ready; with a yes, it's a one-line change. This is the most valuable of these for patients: it covers getting through on the phone and overall experience, by practice.
- [ ] **3.2 NIHR research activity by trust:** the NIHR Research Delivery Network.
  - No trust-level table has been published since 2018/19. Ask whether trust-level studies and participants can be published, or shared, under the OGL.
  - nihr.ac.uk was unreachable on 21 and 22 October; check it's back.
  - With it, research findings could count participants, not just studies.
- [ ] **3.3 HRA research summaries:** the Health Research Authority. Their terms allow "research or private study" only. Ask whether summaries can be re-used under the OGL.
- [ ] **3.4 PHIN** (private hospital data): their terms forbid re-publishing without written consent. Ask for it if private-sector comparisons matter to you.
- [ ] **3.5 National Joint Registry:** data only under a data-sharing agreement. Low priority.

## 4. Data quality jobs that need a person

- [ ] **4.1 Hand-map trial sites.** You (with Claude's help), 1 to 2 hours.
  - The list is `data/processed/trials/unmatched_sites.csv`, most common first. Add entries to `kitchen/trial_site_overrides.json`.
  - Real NHS hospitals that don't match yet: St Bartholomew's, the Royal London, Royal Brompton, Churchill, Queen Elizabeth Birmingham, the National Hospital for Neurology and Neurosurgery, Brighton and Sussex (now merged), Papworth.
  - Universities and units (UCL, King's College London, Imperial, the MRC Clinical Trials Unit) should be set to `null`, meaning checked and not a hospital.
  - Each hour here lifts the 63% match rate and firms up trust-level research claims. Ask Claude to pre-fill a draft for you to check.
- [ ] **4.2 Review the condition rules** in `kitchen/trial_condition_rules.json`. You, or with Macarena, about 1 hour.
  - About 3 in 4 studies land in the right department on a sample.
  - Known slip: "tooth" catches Charcot-Marie-Tooth, a nerve disease. Ask Claude to fix that one now.
  - A clinician's eye on the cancer-by-body-site mapping would be worth having.
- [ ] **4.3 Fix Frimley.** You decide; Claude builds.
  - Frimley ICB was abolished in March 2026 and its local commissioner codes don't appear in later data, so its patients up to March 2026 show as "Frimley" rather than under today's ICBs.
  - Needs a decision on which current ICB(s) to fold it into. NHS England's ICB boundary changes list would settle it.
- [ ] **4.4 Clinical review by Macarena** of the cancer and mental health wording on the Lab and in findings sections 10 and 11. The data-check skill makes this a standing step.
- [ ] **4.5 Recompute two headline numbers by hand** in a spreadsheet from a raw file. Say:
  - England's waiting list for August 2026 (7.19 million).
  - The Essex trials figure (one recruiting study for every 2,463 people waiting).
  - This is data-check step 4 and has never been done independently.

## 5. Robustness work to ask Claude to build

- [x] **5.1 Reconciliation gates.** Done 22 October 2026: `kitchen/reconcile.py` runs before anything is published and fails the run on any unexplained difference. 2,739 checks across 11 sources (DM01 and winter sitreps added), all exact; see `kitchen/DEFINITIONS.md`.
  - Still open: DM01 needs `xlrd` to read NHS England's `.xls` series (your OK), and the winter sitreps check against their ENGLAND rows.
  - Your decision: should England totals be quoted on NHS England's commissioner basis (7,158,164), not all rows (7,189,213)? See DEFINITIONS.md.
- [ ] **5.2 Privacy gate.** `trials.py` refuses to save if any email address or phone number appears in research outputs. Today this is checked by hand.
- [ ] **5.3 Definitions file:** `kitchen/DEFINITIONS.md`, one place every analysis reads from, built from Leo's `nhs-waiting-data.md` notes. Data-check step 5.
- [ ] **5.4 Handle "too many requests" from postcodes.io.** Downloads already wait and retry when ONS says "too many requests"; postcode lookups don't. The first automated run will look up about 35,000 postcodes.
- [ ] **5.5 A small test suite** for the fiddly parsers: the xlsx reader, e-RS header variants, GPAD regional file splits, cancer date formats, the trial site matcher. A publisher changing a file layout then fails a test rather than quietly producing wrong numbers.
- [ ] **5.6 Watch for layout changes.** Each source records the column headings it saw and warns when they change. This month alone, e-RS renamed its columns (July 2026), cancer changed its date format, and the 2024-25 winter files differ from 2025-26.
- [ ] **5.7 Fingertips and ONS on 2026 boundaries.** Both still use the 42 pre-2026 ICBs, while GP and dental data use today's 36. Switch when ONS publishes the 2026 ICB lookup, or build the lookup from sub-ICB codes.
- [ ] **5.8 ClinicalTrials.gov licence check.** It finds the terms by searching the site's JavaScript files, because the page needs JavaScript. If the site changes, the source stops safely. Consider a simpler check, e.g. a fixed copy of the terms with a monthly "has it changed?" comparison.

## 6. Habits to keep

- **Before every post, chart or Lab release:** run the data-check skill ("data check"). No post goes out without human review.
- **Each month:** skim the coverage summaries (`data/processed/coverage.txt`) and the "check before using" lists for anything new or odd.
- **Each quarter:** re-read `kitchen/registry.json` licences, because terms change, and retry the sources that stopped (3.1 to 3.5).
- **Publish a corrections policy** on the site, and correct mistakes quickly and openly (data-check step 10).
- **Dates to expect:**
  - Winter sitreps: early December.
  - Next vacancy statistics: 26 November 2026.
  - GP Patient Survey: July.
  - NHS Staff Survey: March.
  - ONS population: autumn.

---

## The short version

1. ~~Put it on GitHub after slimming what gets committed (1.1, 1.3).~~ Done. Run the monthly action by hand and watch it (1.6).
2. Back up `data/raw` (1.4).
3. Decide on a public site (2.5). ~~The England figure (2.6) and `xlrd` (2.7)~~ are decided.
4. Email Ipsos about the GP Patient Survey (3.1).
5. Spend an hour hand-mapping trial sites (4.1).
6. Ask Claude for the privacy gate (5.2). ~~The reconciliation gate (5.1)~~ is done.
