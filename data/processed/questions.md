# What the Wait Watcher kitchen can answer

Built by kitchen/make_findings.py from the data to August 2026. Each question says which source answers it (the name in kitchen/registry.json), the grain (what one row describes) and an example answer from the latest data. Patient examples use Walthamstow as the example place.

Cancer answers are sensitive: write them gently. Figures from Scotland, Wales and Northern Ireland are not comparable with England's.

## Patients

### How long will I wait for an operation at my hospital?
- Source: RTT (rtt)
- Grain: trust x treatment, monthly
- Example: Trauma and orthopaedics at Barts Health NHS Trust, August 2026: half of people who had their operation had waited 32 weeks or less.

### Which hospital is quickest for my treatment?
- Source: RTT + ODS locations (rtt, ods)
- Grain: trust x treatment; trust locations
- Example: For trauma and orthopaedics, South Warwickshire University NHS Foundation Trust had the highest share seen within 18 weeks among acute and specialist trusts with 1,000+ waiting: 85.6%. The Lab can compare hospitals near the one you'd go to.

### How long will I wait for a scan or test?
- Source: Diagnostic waiting times (dm01)
- Grain: trust x test, monthly
- Example: MRI at Barts Health NHS Trust, August 2026: 35% of 6,137 people waiting had waited 6 weeks or more (the standard is 1%).

### If I'm referred urgently with suspected cancer, how soon will I find out?
- Source: Cancer waiting times (cancer) - sensitive
- Grain: trust x standard, monthly
- Example: At Barts Health NHS Trust in August 2026, 81.5% of people were told whether or not they had cancer within 28 days (the standard is 75%).

### How long might I wait for a GP appointment at my practice?
- Source: GP appointments (gpad) + practice list (gp_practices)
- Grain: practice, monthly
- Example: In Waltham Forest (39 practices, August 2026): 47% of appointments were the same day as booking and 1.3% more than 28 days later.

### How busy is A&E at my hospital?
- Source: A&E (ae)
- Grain: trust, monthly
- Example: Barts Health NHS Trust, September 2026: 74.0% seen within 4 hours (61.0% in the main A&E).

### How long will I wait for talking therapy for anxiety or depression?
- Source: NHS Talking Therapies (talking_therapies)
- Grain: provider, monthly
- Example: North East London NHS Foundation Trust, August 2026: 81% of people who finished a course had started within 6 weeks.

### How long will my child wait for community paediatrics or speech therapy?
- Source: Community health services (community)
- Grain: provider x service, monthly
- Example: England, August 2026: 174,537 children waiting for community paediatrics, 79,031 for over a year; at North East London NHS Foundation Trust, 5,129 waiting.

### How long do children and young people wait for mental health support?
- Source: Mental health services (mhsds)
- Grain: provider, monthly (3-month rolling)
- Example: North East London NHS Foundation Trust, 3 months to August 2026: half of children and young people had a first contact within 16 days of referral.

### How fast will an ambulance come?
- Source: Ambulance response times (ambulance)
- Grain: ambulance trust / region, monthly
- Example: London Ambulance Service, September 2026: category 2 (e.g. stroke, heart attack) mean 33.5 minutes against an 18-minute standard.

### Can I get an NHS dentist near me?
- Source: NHS dental activity (dental) + ONS population (population)
- Grain: dental contract / ICB, monthly
- Example: North East London ICB, July 2026: 522,498 adults seen by an NHS dentist in the last 24 months, across 203 contracts.

### What do other patients think of my hospital, and what did inspectors say?
- Source: Friends and Family Test (fft), CQC ratings (cqc)
- Grain: trust / site
- Example: See the trust page in the Lab: share rating care good or very good, and the CQC rating.

## GPs

### When I refer, how often will there be no slot to book?
- Source: e-RS appointment slot issues (ers)
- Grain: provider x specialty, monthly
- Example: Barts Health NHS Trust, September 2026: Sleep Medicine had 222 slot issues per 100 bookings, the highest of its specialties with 50+ bookings.

### Which nearby hospital has the shortest wait for this specialty?
- Source: RTT (rtt) + ODS (ods)
- Grain: trust x treatment
- Example: Use the Lab's Explore view with 'near' set to your practice postcode.

### How does my practice's booking-to-appointment time compare with my ICB?
- Source: GP appointments (gpad)
- Grain: practice and ICB, monthly
- Example: North East London ICB, August 2026: 46.9% same day, 90.0% within 14 days, 2.0% over 28 days.

### What's my practice's did-not-attend rate?
- Source: GP appointments (gpad)
- Grain: practice, monthly
- Example: North East London ICB, August 2026: 6.8% of appointments with a known outcome were missed.

### Which trusts are meeting the cancer standards?
- Source: Cancer waiting times (cancer) - sensitive
- Grain: trust x standard, monthly
- Example: August 2026: 10 of 101 trusts met the 62-day standard of 85%; England 71.9%.

### Do patients wait again between their first and second talking therapy session?
- Source: NHS Talking Therapies (talking_therapies)
- Grain: provider, latest month
- Example: North East London NHS Foundation Trust: 21% waited over 90 days for a second appointment.

### How long are waits for community services like MSK or podiatry?
- Source: Community health services (community)
- Grain: provider x service, monthly
- Example: North East London NHS Foundation Trust, August 2026: 3,816 waiting for adult MSK, 3% over 18 weeks.

### How long are adult community mental health waits?
- Source: Mental health services (mhsds)
- Grain: provider, 3-month rolling
- Example: North East London NHS Foundation Trust: half of adults with serious mental illness had a second contact within 41 days.

## NHS insiders

### Which trusts improved most on 18 weeks this year?
- Source: RTT (rtt)
- Grain: trust, monthly
- Example: Countess of Chester Hospital NHS Foundation Trust: 48.8% to 68.4% within 18 weeks (+19.5 points).

### Where are the year-long waits?
- Source: RTT (rtt)
- Grain: trust x treatment, monthly
- Example: Mid and South Essex NHS Foundation Trust has 13,427 people waiting over a year, 11.9% of England's.

### What has the waiting list done since the last official month?
- Source: WLMDS weekly (wlmds)
- Grain: England by week; provider monthly snapshot
- Example: Week ending 2026-08-30: 7,122,072 pathways from 632 providers (63.9% within 18 weeks). Management information; RTT stays the official count.

### Where is the front door blocked - referrals with no slot to book?
- Source: e-RS (ers)
- Grain: provider x specialty, monthly
- Example: Manchester University NHS Foundation Trust: 286.7 slot issues per 100 bookings in September 2026 (England 36.6).

### How full were hospitals last winter, and how long did ambulance handovers take?
- Source: UEC daily sitreps (uec_sitreps)
- Grain: trust x day, winter
- Example: Winter 2025-26: general and acute beds 93.4% occupied; 27% of handovers took over 30 minutes.

### Do trusts with more sickness absence have longer waits?
- Source: Sickness absence (workforce) + RTT (rtt)
- Grain: trust, monthly
- Example: Across 122 large acute trusts, correlation 0.06 - a picture, not a cause.

### What are vacancy rates in my region?
- Source: NHS vacancy statistics (workforce)
- Grain: region x sector, quarterly
- Example: London, acute trusts, 2026-06: 7.5% of posts vacant.

### Which figures should I check before using?
- Source: every source's check_before_using.json
- Grain: provider / practice
- Example: 66 RTT providers and 713 flags across the new sources moved 15+ points in a month (50+ for ASI rates) or are listed by NHS England with data issues.

## Journalists

### How many people are waiting, and is it going down?
- Source: RTT (rtt)
- Grain: England, monthly
- Example: 7,189,213 in August 2026, down from 7,345,544 a year earlier; 65.2% within 18 weeks (the aim is 92%).

### Where's the biggest postcode lottery for an operation?
- Source: RTT (rtt)
- Grain: trust x treatment, 3 months
- Example: Oral Surgery: typical operation wait 6.8 weeks at Frimley Health NHS Foundation Trust vs 71.7 at Mid and South Essex NHS Foundation Trust.

### Where is it hardest to get a GP appointment soon?
- Source: GP appointments (gpad)
- Grain: practice / ICB / local authority, monthly
- Example: Gloucestershire: 11.1% of appointments more than 28 days after booking (August 2026).

### Which A&Es are furthest from the four-hour standard?
- Source: A&E (ae)
- Grain: trust, monthly
- Example: University Hospitals Plymouth NHS Trust: 36.2% of major A&E patients seen within 4 hours in September 2026 (England 60.6%).

### How much NHS surgery is done in private hospitals?
- Source: RTT (rtt)
- Grain: provider, 3 months
- Example: 17.1% of completed operations, across all treatments, were at independent providers (-0.5 points on a year ago).

### How do Scotland, Wales and Northern Ireland compare?
- Source: Devolved headline waits (uk_nations)
- Grain: nation
- Example: They don't compare directly (different standards and counting). Wales, July 2026: 709,687 pathways waiting, 65.7% within 26 weeks.

### How many adults are seeing an NHS dentist?
- Source: NHS dental activity (dental)
- Grain: contract / ICB, monthly
- Example: 17,747,148 adults seen in the 24 months to July 2026.

### Are waits longer in more deprived areas?
- Source: Fingertips (fingertips) + RTT areas (rtt)
- Grain: ICB
- Example: Across the 30 ICBs whose boundaries didn't change in 2026, the correlation between deprivation (IMD 2025) and % within 18 weeks is 0.13 - a picture, not a cause.

### Are ambulances meeting their targets?
- Source: Ambulance response times (ambulance)
- Grain: ambulance trust / region, monthly
- Example: England, September 2026: category 2 mean 31.3 minutes (standard 18, interim aim 30).

### How many children wait over a year for community services?
- Source: Community health services (community)
- Grain: provider x service, monthly
- Example: Community paediatrics alone: 79,031 waiting over 52 weeks in August 2026.

## Research

### Which studies are recruiting at my hospital?
- Source: Trials (trials: ClinicalTrials.gov + ISRCTN)
- Grain: study x site
- Example: Barts Health NHS Trust: 235 UK studies recruiting with a site matched to the trust. Each links to its registry page and a Be Part of Research search.

### Are there trials for my condition - say, a knee or hip problem?
- Source: Trials (trials)
- Grain: study, mapped to treatment functions
- Example: 127 UK studies recruiting now map to trauma and orthopaedics (by their conditions).

### Which trusts run the most research?
- Source: Trials (trials)
- Grain: trust
- Example: Manchester University NHS Foundation Trust: 389 studies recruiting now. By participants: not available (NIHR doesn't openly publish it by trust).

### Where in England is research most within reach?
- Source: Trials (trials) + ONS population (population)
- Grain: local authority
- Example: Camden: 317.1 recruiting studies per 100,000 people (England 5.4). A study counts everywhere it has a site.

### Do departments with long waits have much research?
- Source: Trials (trials) + RTT (rtt)
- Grain: treatment function
- Example: Oral Surgery has the longest typical wait (16.4 weeks) and 29 recruiting studies (0.9 per 10,000 waiting).

### Is research in a department mostly industry or academic?
- Source: Trials (trials)
- Grain: treatment function
- Example: Dermatology: 65.8% of UK studies are industry-sponsored.

### Do hospitals that do more research have shorter waits?
- Source: Trials (trials) + RTT (rtt)
- Grain: acute trust
- Example: Across 113 large acute trusts, correlation -0.06 between recruiting studies and % within 18 weeks - a picture, not a cause.

### Is a study on both registries?
- Source: Trials (trials)
- Grain: study
- Example: 1,284 of 42,795 UK studies are on both ClinicalTrials.gov and ISRCTN (linked by ISRCTN, IRAS or NCT number).
