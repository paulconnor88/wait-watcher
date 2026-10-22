# Findings: UK clinical research next to NHS waits, October 2026

For LinkedIn: NHS insiders and patients. Every number comes from `out/research/analysis.py` (saved in `numbers.json`); the method files say exactly how.

Before looking, Leo wrote down what he expected:
- Areas and departments with the longest waits would have less research.
- Drug-company trials in the UK would still be down on before the pandemic.
- Hospitals that do lots of research would have *longer* waits, because research takes staff time.

The first held. The second was the wrong way round: industry held steady, and it's academic trials that fell. The third found nothing at all, in any direction.

## What we've got

- **The studies:** 42,795 UK clinical studies from ClinicalTrials.gov and the ISRCTN registry, de-duplicated. 1,284 are on both registries, 27,760 on ClinicalTrials.gov only and 13,751 on ISRCTN only.
  - 4,083 are recruiting now, with 18,965 UK study-sites between them.
  - Registry data processed 21 October 2026.
- **Waits:** NHS England waiting times for August 2026: 7.19 million waiting, 65.2% within 18 weeks, matching the published figures.
- **Starts over time:** UK study starts rose to a peak of 2,443 in 2021, and were 2,063 in 2024 and 1,987 in 2025.
- **No published equivalent to check against:** NIHR's own research activity by trust isn't openly published, so the registries are the only open source.

## What's odd (and what we did about it)

- **Recently started studies are still being registered**, especially academic ones. On ClinicalTrials.gov, 8 to 11% of academic studies were posted more than ten months after their start year ended, against 2 to 3% of industry ones. Excluded 2025–26 from trends; used 2022–24 against 2017–19. Trends are still slightly understated for academic studies.
- **31 studies have been "recruiting" since before 2010.** These are stale registry records. Kept, because they're too few to matter, but noted.
- **Huge enrolment targets** (a drink-drive law study counts 64.6 million people): population studies. Excluded: enrolment isn't used anywhere.
- **Department mapping is rule-based and about 3 in 4 right on a sample** (e.g. "tooth" also caught Charcot-Marie-Tooth, a nerve disease).
  - Used only for comparisons where all departments share the same noise.
  - Departments the rules never assign (paediatrics, "other", general internal medicine) are excluded rather than shown as zero.
- **Only 63% of English study-sites are matched to a trust**, so trust-level counts are lower than the truth.
  - The area finding avoids this by using site postcodes: 84% of recruiting study-sites have one.
- **"Other mental health" waiting figures cover about 3,000 people.** Excluded: RTT barely covers mental health care.

## Findings, ranked

**1. In Essex there's one trial recruiting for every 2,500 people waiting. Next door in east London, one for every 550.**
- The numbers:
  - NHS Essex ICB: 283,275 people waiting (August 2026), 115 UK studies recruiting with a site in Essex (21 October 2026), so one for every 2,463 people waiting.
  - NHS North East London ICB: 249,427 waiting, 455 recruiting, one for every 548.
  - That's about 4.5 times the gap. Essex is second-worst of 36 ICBs; the median ICB is about 1 in 745.
  - Essex also holds England's most year-long waits (14,297).
- The picture: two bars.
- Strength: strong. Neighbours, a big gap, and it doesn't depend on site-to-trust matching.
- Watch out:
  - A study counts in every area where it has a site, and people in Essex can join London studies.
  - "Recruiting nearby" isn't "recruiting people from Essex".
  - 16% of recruiting study-sites have no postcode and can't be placed. Essex's main trust is not under-counted: 99 of its 108 matched sites have postcodes.

**2. For each person waiting, lung care has about 16 times the trials of bones and joints.**
- The numbers:
  - Bones and joints (trauma and orthopaedics): 851,183 waiting, 127 recruiting studies, so about 1.5 per 10,000 people waiting.
  - Lungs (respiratory): 182,914 waiting, 428 recruiting, about 23.4 per 10,000.
  - The longest-wait surgical departments are all at the bottom: general surgery 0.3, plastic surgery 0.4, mouth and jaw 0.9, ear, nose and throat 1.2.
- The picture: two bars.
- Strength: medium. The direction is clear and big; the exact counts depend on rules mapping conditions to departments.
- Watch out:
  - Trials and waiting lists don't cover exactly the same people. Lung trials include cancer and infection studies whose patients aren't on a waiting list.
  - This shows where research effort goes, not whether there's "enough".

**3. Hospitals running the most trials have waits just like everyone else's.**
- The numbers:
  - 113 acute trusts with 10,000+ waiting, split into quarters by recruiting studies.
  - % within 18 weeks: 64.0 at the quarter with the most (99 to 389 studies), 65.3 at the fewest (2 to 17). Correlation −0.06.
  - Cancer, 62 days (June to August 2026, 118 trusts): 71.1 against 73.3, correlation −0.04.
  - GP referrals with no slot to book: correlation −0.02.
- The picture: two bars, with the NHS aim (92) as a dashed line.
- Strength: medium. No link in three separate measures, but it uses matched sites (63%).
- Watch out:
  - "No link" is the finding. It doesn't show research helps or harms waits.
  - The busiest research hospitals are also the biggest and most specialist, which could hide effects either way.

**4. Drug-company trials in the UK held steady. University and NHS-led ones fell by about a seventh.**
- The numbers:
  - Interventional studies starting each year with a UK site: industry 725 (2017–19) to 703 (2022–24), down 3%. Academic and other: 1,022 to 874, down 14%.
  - By department, 2017–19 against 2022–24: bones and joints down 20%, eyes down 20%, mouth and jaw down 18%; skin up 9%.
- The picture: before/after bars.
- Strength: medium. Late registration still slightly understates recent academic studies; on ClinicalTrials.gov about 1 in 12 academic studies starting in 2023 were posted more than ten months after that year ended.
- Watch out:
  - Counts studies, not participants. The well-known fall in UK commercial trials was about recruitment, which registries can't see.
  - Department counts in the small surgical specialties are only a few dozen a year.

## What didn't make the cut

- **"Universities lead most UK research now (43%), not drug companies (39%)":** true, but not a surprise to insiders, and no place.
- **"Two-thirds of skin research is industry-funded; almost none for older people":** interesting, but small counts at the low end (elderly medicine: 20 studies). It needs homework about what "industry-sponsored" means.
- **"Imperial and Oxford each sponsor more UK trials than AstraZeneca":** a sponsor league with no human unit, and it reads as an institution ranking.
- **Research per 100,000 residents by council (Camden 317, many districts 0):** this is just "teaching hospitals do research", which we were told to skip.
- **Phase 1 trials up since 2021:** a registry formatting change (ISRCTN's "Phase I" spelling), not real.

## Questions for next time

- **Participants, not studies.** How many patients join trials by trust or area? That needs NIHR's recruitment data, which isn't openly licensed; worth asking the NIHR Research Delivery Network.
- **Distance.** Is "nearby" better measured by travel time from where people live to the nearest recruiting site? That needs site coordinates (we have postcodes) and a travel-time model.
- **Who joins.** Do studies in long-wait specialties recruit people *from* the waiting list? Registries don't say where participants come from.
- **Better matching.** Hand-mapping the top unmatched sites (`kitchen/trial_site_overrides.json`) would firm up finding 3.

## Files

- **Slides** (1080x1350, findings 1 to 3): `1-essex.png`, `2-lungs-and-bones.png`, `3-research-and-waits.png`, drawn by `slides_research.py` with the leo-infographic house style.
- **Method files:** `method-1.md` to `method-4.md`. Each has the exact files and rows used, the code that produced each number (quoted from `analysis.py`), the definitions and the results.
- **Reproduce:**
  1. `.venv/bin/python out/research/analysis.py`
  2. `.venv/bin/python out/research/make_methods.py`
  3. `.venv-slides/bin/python out/research/slides_research.py` (that environment holds matplotlib, kept out of the kitchen).
