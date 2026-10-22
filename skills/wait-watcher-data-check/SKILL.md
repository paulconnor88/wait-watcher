---
name: "wait-watcher-data-check"
description: Run before every Wait Watcher post, chart, report, CSV or Lab release, and whenever a new dataset, definition or method is added, or someone questions a published figure. Ensures NHS data and the claims made from it are accurate, reproducible, licensed and trustworthy. Reliability is the mission-critical part of this project, so no finding goes out without passing this check. Trigger on "check this", "data check", "is this right", "before I post", "sense check", or after leo-analyst or leo-infographic has produced something headed for publication.
---

# Wait Watcher data reliability check

Wait Watcher's whole value is that its numbers can be trusted. One wrong figure damages the project more than ten good posts help it. Run this checklist before publishing any post, chart, report or downloadable file.

The core rule: AI builds and checks the process, never the numbers. Every published figure must come from re-runnable code over official source files, not from anything an AI model said. And the data being right is only half the job: the claims made from it have to be right too.

This skill is the gate. `leo-analyst` finds, `leo-infographic` draws, this checks. Keep them separate so the check is independent of the work it's checking.

## The checklist

### 1. Official sources only
- Use files downloaded directly from NHS England's published statistics (or the equivalent official body for the dataset in question).
- Never use another site's processed or cleaned version of the data.
- For every file used, record: source URL, file name, and publish date. Keep the raw file unmodified.

### 2. AI writes the code, code produces the numbers
- Do not ask a chat model a data question ("what's the wait for knees in London") and use its answer.
- Instead, have AI write a query or script you can read, and run it yourself on the raw files.
- The same input must always produce the same output. If you re-run it and get a different number, stop and find out why before continuing.

### 3. Reconcile to published totals
- Check your numbers add up to NHS England's own headline figures for the same period (national waiting list total, 18-week performance, and any other published aggregates relevant to the finding).
- RTT has three England figures: the file's all-rows total (includes NONC - patients commissioned outside England, mostly Welsh); NHS England's commissioner-basis figure (all rows minus NONC, in the RTT Overview Timeseries); and the headline (commissioner basis plus estimates for non-submitting trusts). Wait Watcher quotes the commissioner basis for England. It must match to the unit. Trust and department figures use all rows.
- The kitchen's gate (kitchen/reconcile.py, output data/processed/reconciliation.md) must show a pass for every figure in the post. Allowed differences are only those documented and computed in kitchen/DEFINITIONS.md, never a tolerance.
- Revised series (cancer provisional vs final, WLMDS later weeks, GP appointment national totals): check against the version published alongside, and say which version.
- If your figures don't reconcile beyond known gaps, do not publish. Find the discrepancy first.

### 4. Check every finding two ways
- Get a second AI model, in a fresh conversation with no shared context, to review the method and actively try to break it.
- Then recompute one or two of the key numbers by hand in a spreadsheet from the raw file.

### 5. Keep a definitions file
- Maintain a short, reusable definitions file that every analysis reads from, so terms never drift between posts. Record for each dataset:
  - What "18-week RTT" actually counts: the clock start, the clock stop, and what pauses or resets it.
  - Pathways vs patients: the NHS counts pathways, and one person can be on more than one. Never report a pathway count as a patient count.
  - Exclusions: which trusts, specialties or pathway types are left out, and why.
  - Which months are covered, and how specialties are grouped.
- Most errors in RTT data are definition errors, not maths errors. If a definition changes between posts, say so in the post.
- The leo-analyst reference `nhs-waiting-data.md` is the starting point for this file.

### 6. Check the kitchen's own flags
- Exclude any provider listed in the relevant `check_before_using.json` from "fastest", "most improved" and "worst" claims, or say clearly why it's included.
- Small numbers: under 30 people, say so; under 150, don't rank.
- Like with like: acute and specialist trusts compared with each other; private providers' case mix stated when they appear as fastest.
- For research data: a study counts in every area where it has a site, and only about 63% of English study-sites are matched. Per-head and per-trust research claims must say so.

### 7. Check the claims, not just the data
Before publishing, run a pre-publish pass over the write-up itself. Correct data can still support a wrong claim.
- Denominators: every percentage or rate says out of what. "Waits fell 20%" means 20% of which group, at which date?
- Comparison periods: any trend names both periods and says why they are comparable. Watch for bank holidays, strikes and seasonal effects making one period an unfair baseline.
- Causal claims: "this trust improved because of X" needs evidence of X, not just a coincidence in timing. If there is no evidence, write it as an observation, not a cause.
- Evidence vs hypothesis: label which statements the data proves and which are interpretation or a guess. A good guess, clearly labelled, is fine. A guess presented as a finding is not.
- Sensitive datasets (cancer, mental health, children's services): gentle wording, never "worst", always "furthest from the standard".

### 8. Licence and attribution
- Every dataset in the post is cleared in `kitchen/registry.json`.
- Attribution line present where required: "Contains CQC information"; "Contains information from the ISRCTN registry, licensed CC BY"; ClinicalTrials.gov requires attribution, the data's processing date and a note of changes made.
- No personal data: no named contacts, investigators, emails or phone numbers, in any output.

### 9. Human eyes before publishing
- Macarena checks the clinical meaning: does this finding make sense to a clinician, and is the wording accurate?
- A data-literate reviewer (Leo, when available) checks the method.
- Even 20 minutes of human review per post is worth it. No post goes out with zero human review.

### 10. Show your working
- Every post carries a short methodology line: sources, period, and definitions used.
- Keep a visible corrections policy, and correct mistakes quickly and openly. Fast, honest corrections build more trust than never being wrong.

## Output

Return a short pass/fail sheet:

```
# Data check: <post or file>
| Step | Result | Note |
| 1 Sources | pass / fail | URLs and publish dates |
| ... | | |
Verdict: PUBLISH / FIX FIRST / DON'T PUBLISH
Fixes needed: <numbered list>
Human review: Macarena <done / to do>, Leo <done / to do>
```

## Scope discipline

Start narrow. One dataset, one finding, fully checked, before adding more. A small number of rock-solid findings beats a wide tool with shaky numbers.

## When to use this

- Before publishing any Wait Watcher post, chart, report or CSV
- Before redeploying the Lab with a new dataset
- When adding a new dataset or data source
- When changing a definition or method, even slightly
- When drafting a claim about a trend, an improvement, or a cause
- When someone questions a published figure (re-run the full check before responding)
