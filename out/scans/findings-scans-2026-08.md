# Findings: DM01 scan waits (MRI, CT, ultrasound, DEXA), August 2026

## What we've got
208,752 rows: 29 months (April 2024 to August 2026), 484 providers, 15 tests plus TOTAL. In August 2026, 1.83 million people were waiting for a test and 24.7% had waited 6 weeks or more, against a standard of under 1%. That matches the figure we expected (24.7%). For the four scans (MRI, CT, non-pregnancy ultrasound, DEXA bone-density), 1.26 million were waiting and 254,245 (20.2%) had waited 6+ weeks, up from 215,833 (18.7%) a year earlier.

Expectation written down first: "ultrasound has the biggest queue, DEXA is proportionally the worst, MRI and CT are improving thanks to the community diagnostic centre money." The data agreed on ultrasound and CT. **It disagreed on MRI:** 6+ week waits rose from 18.8% to 22.0%, and the number of people waiting that long rose by a third (58,686 to 78,880). That's finding 3.

## What's odd (and what we did about it)
- **75 providers with names missing from lookup.json** (60 of them active in August 2026), mostly community diagnostic centres and GP-run services. *Fixed:* names and ICBs taken from the raw DM01 extracts, which carry both. Every provider is now named.
- **"Area" here means where the provider is, not where patients live.** The ICB comes from DM01's provider parent, unlike the RTT area file. *Story-safe, but say "hospitals in X", not "people in X".*
- **Every February and March dips, and every December, January and April spikes** (e.g. all tests 17.5% in February 2025 and 24.8% in December 2025). *Excluded from trends:* we only compare August with August.
- **Queues that collapsed without more scans being done**: Staffordshire ultrasound (11,871 to 4,808 waiting, scans per month flat at about 6,000), King's College ultrasound (15,380 to 5,688, scans +7%), West Suffolk DEXA (1,549 to 182). These could be real catch-up, list cleaning, or work moved elsewhere, and the data can't tell which. *Excluded from "turnaround": check before using.*
- **Royal Papworth MRI at 75%**: a specialist heart and lung hospital doing about 255 scans a month. *Excluded: specialist, not comparable.*
- **InHealth Limited**: 14,413 waiting for ultrasound, 51% over 6 weeks, registered in Thames Valley but working nationally. *Excluded from place stories: its address isn't where it scans.*
- **Electrophysiology swung from 52% to 20%** on 274 people. *Excluded: small numbers.*

## Findings, ranked

**1. Ultrasound in Sheffield: 2 in 3 have waited over 6 weeks. Next door in Rotherham, nobody has.**
- The numbers: Sheffield Teaching Hospitals, August 2026: 8,948 of 13,625 people waiting (65.7%) have waited 6+ weeks, and 5,459 over 13 weeks. A year ago it was 1,786 of 6,680 (26.7%). Rotherham: 0 of 1,342. Barnsley: 1 of 2,366. Doncaster: 86 of 3,441 (2.5%, down from 22%). Sheffield's queue doubled while its scans per month stayed flat (6,650 in August 2025, 6,306 in August 2026). The rise was steady, month on month, from autumn 2025.
- The picture: two bars (Sheffield and Rotherham, with Barnsley and Doncaster as small bars underneath), or 100 people for each.
- Strength: strong.
- Watch out: Sheffield is a big teaching hospital that takes harder cases from across South Yorkshire, so the people aren't identical. "Non-obstetric" means not pregnancy scans; say "ultrasound scans (not pregnancy)". There's no proven right to choose where you get a scan, so don't promise one. Asking is fair.

**2. MRI in London: south-west London has hit the target. North-east London: 1 in 3 wait over 6 weeks.**
- The numbers: south-west London hospitals, August 2026: 67 of 6,861 (just under 1 in 100, so meeting the under-1% standard) have waited 6+ weeks, down from 8.2% a year ago, even though the queue grew (5,707 to 6,861). Kingston and Richmond went from 239 people over 6 weeks to none. North-east London: 5,174 of 14,813 (34.9%), up from 24.6%, with 2,407 over 13 weeks. That's driven by Barking, Havering and Redbridge (42%, up from 4%) and Barts (35%).
- The picture: two bars (south-west and north-east London), or 100 people for each, with a line at the 1-in-100 standard.
- Strength: strong for the gap; medium for "hit the target" (under 1% only in July and August so far).
- Watch out: Homerton, inside north-east London, has nobody over 6 weeks. Keep it in the footnote so this doesn't read as a whole area failing. These are where hospitals are, not where patients live.

**3. MRI waits have gone backwards in Derbyshire, Staffordshire and Lincolnshire: from about 1 in 10 to nearly half.**
- The numbers: share waiting 6+ weeks for an MRI, August 2025 to August 2026. Derbyshire hospitals 12.6% to 47.9%. Staffordshire 6.5% to 40.6%. Lincolnshire 16.3% to 49.7%. In each case the queue roughly doubled (Derby and Burton 3,656 to 6,883) while scans per month stayed flat or rose (North Midlands 8,057 to 8,828). Across England, about 20,000 more people have waited 6+ weeks for an MRI than a year ago (58,686 to 78,880), even though England did 3.4% more MRI scans over the year.
- The picture: before/after bars, three places, 2025 and 2026 side by side.
- Strength: strong. Steady month-on-month rises, not a one-month jump.
- Watch out: "more people being sent for scans" is the arithmetic (queue up, scans flat), not a proven cause. Don't call it a "crisis". Lincolnshire also leads finding 5, so keep only one Lincolnshire slide per month.

**4. Good news: CT waits are getting shorter. People waiting over 3 months fell by a third.**
- The numbers: people waiting 13+ weeks for a CT scan in England: 6,895 (August 2025) to 4,690 (August 2026), down 32%, while the queue grew 11%. 28 hospitals with 500+ people waiting meet the under-1% standard. Cornwall is the turnaround: 31% over 6 weeks to under 1% (8 of 1,160), with 10% more scans done over the year (61,557 to 67,576).
- The picture: big number ("a third fewer"), or before/after bars for Cornwall.
- Strength: strong (Cornwall is backed by more scans, not a cleaned list).
- Watch out: England's CT share over 6 weeks is still 11.2%, flat for two years, and still 11 times the standard. Good news, not "fixed".

**5. Lincolnshire's ultrasound queue: 1 in 7 waited over 6 weeks a year ago. Now it's 6 in 10.**
- The numbers: United Lincolnshire (the county's only NHS hospital trust for this): 918 of 6,788 (13.5%) to 10,523 of 17,153 (61.3%). Over 13 weeks: 12 to 5,208. Scans per month were up 11%. Next door in Leicestershire: 1.9%, down from 29%, and that queue halved with slightly more scans done.
- The picture: two bars, Lincolnshire and Leicestershire.
- Strength: strong, but held back so Lincolnshire isn't on two slides in one month (see finding 3).
- Watch out: Lincolnshire and Leicestershire only just touch (Rutland, Stamford). Say "neighbouring", not "next door".

## What didn't make the cut
- **Bone-density (DEXA) scans in Essex, 7 in 10 over 6 weeks (Mid and South Essex) vs none at the Colchester and Ipswich trust.** True, but DEXA is a low-urgency scan, the neighbour's queue is small (264), and it needs the "what's a DEXA" homework.
- **Community diagnostic centres are faster for ultrasound (5.7% vs 22.5% at hospitals).** Not fair: they take simpler, routine cases, and some are slow (Mid and South Bucks diagnostic centre MRI 48%).
- **Staffordshire and King's College ultrasound "turnarounds".** The queues fell faster than scans rose, so we can't tell catch-up from list cleaning.
- **National scene-setter (24.7% against a standard of under 1%, at least 20% in every month since April 2024).** Useful as the opening slide, but no place in it.
- **East Kent: 2 in 3 over 6 weeks for ultrasound, nearly half for MRI and CT.** True, but it's one trust bad at everything, which reads as naming and shaming. Save it for a "worst spot" month.

## Questions for next time
- Why did the queues in Sheffield and the Midlands for MRI double? DM01 doesn't record referrals. Waiting-list activity plus queue change gives a rough proxy; worth adding to the kitchen.
- Did Staffordshire's and King's ultrasound patients move to a community diagnostic centre? Matching CDC providers to their host trust would answer it.
- Where do patients live? DM01 has commissioner rows (dropped in the kitchen). Keeping them would give a fair "people in X" view like RTT.
- Does a 6-week wait for a scan delay treatment? Linking DM01 to RTT by trust and specialty (e.g. MRI vs bones-and-joints waits) is possible, but it would show correlation, not cause.
