# Method 2: Research per person waiting, by department

**Finding:** For each person waiting, lung care has about 16 times the trials of bones and joints.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/studies.csv` | 4,083 recruiting studies; the `treatment_functions` column (set by `kitchen/sources/trials.py` using the rules in `kitchen/trial_condition_rules.json`) |
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

```python
def finding_2_departments(studies):
    recruiting = studies[studies["status"] == "recruiting"]
    exploded = recruiting.assign(tf=recruiting["treatment_functions"].str.split("; ")).explode("tf").dropna(subset=["tf"])
    per_tf = exploded.groupby("tf")["study_id"].nunique()
    findings = json.loads(max(P.glob("findings-*.json")).read_text())
    rows = []
    for t in findings["2_treatments"]:
        # Left out: all treatments; mental health (RTT covers little of it); and the departments the
        # condition rules never assign (paediatrics, general internal medicine, "other"), which would
        # otherwise show zero research that isn't really zero.
        if t["code"] in ("C_999", "X03", "X04", "X06", "C_300"):
            continue
        n = int(per_tf.get(t["code"], 0))
        rows.append({"code": t["code"], "name": t["name"], "waiting": t["waiting_now"], "typical_wait_weeks": t["median_now"],
                     "recruiting_studies": n, "per_10k_waiting": round(n / t["waiting_now"] * 10_000, 1)})
    rows.sort(key=lambda r: r["per_10k_waiting"])
    get = lambda code: next(r for r in rows if r["code"] == code)
    return {"departments": rows, "bones_and_joints": get("C_110"), "lungs": get("C_340"), "eyes": get("C_130"),
            "mouth": get("C_140"), "ratio_lungs_to_bones": round(get("C_340")["per_10k_waiting"] / get("C_110")["per_10k_waiting"])}
```

## Result

```json
{
 "bones_and_joints": {
  "code": "C_110",
  "name": "Trauma and Orthopaedic",
  "waiting": 851183,
  "typical_wait_weeks": 13.9,
  "recruiting_studies": 127,
  "per_10k_waiting": 1.5
 },
 "lungs": {
  "code": "C_340",
  "name": "Respiratory Medicine",
  "waiting": 182914,
  "typical_wait_weeks": 10.4,
  "recruiting_studies": 428,
  "per_10k_waiting": 23.4
 },
 "eyes": {
  "code": "C_130",
  "name": "Ophthalmology",
  "waiting": 625063,
  "typical_wait_weeks": 10.4,
  "recruiting_studies": 104,
  "per_10k_waiting": 1.7
 },
 "mouth": {
  "code": "C_140",
  "name": "Oral Surgery",
  "waiting": 316357,
  "typical_wait_weeks": 16.4,
  "recruiting_studies": 29,
  "per_10k_waiting": 0.9
 },
 "ratio_lungs_to_bones": 16
}
```

| Department | People waiting | Recruiting studies | Per 10,000 waiting |
|---|---|---|---|
| General Surgery | 384,914 | 11 | 0.3 |
| Plastic Surgery | 109,605 | 4 | 0.4 |
| Oral Surgery | 316,357 | 29 | 0.9 |
| Ear Nose and Throat | 590,233 | 69 | 1.2 |
| Trauma and Orthopaedic | 851,183 | 127 | 1.5 |
| Ophthalmology | 625,063 | 104 | 1.7 |
| Gynaecology | 586,582 | 109 | 1.9 |
| Other surgical | 474,806 | 118 | 2.5 |
| Dermatology | 423,217 | 115 | 2.7 |
| Urology | 367,027 | 191 | 5.2 |
| Other medical | 622,434 | 436 | 7.0 |
| Elderly Medicine | 27,431 | 20 | 7.3 |
| Rheumatology | 118,397 | 91 | 7.7 |
| Gastroenterology | 358,127 | 343 | 9.6 |
| Cardiology | 362,143 | 476 | 13.1 |
| Neurosurgical | 54,748 | 89 | 16.3 |
| Neurology | 208,030 | 384 | 18.5 |
| Respiratory Medicine | 182,914 | 428 | 23.4 |
| Cardiothoracic Surgery | 8,798 | 26 | 29.6 |

## Caveats

- Trials and waiting lists don't cover the same people: lung trials include lung cancer and infection
  studies whose patients aren't on a waiting list for respiratory medicine.
- The ratio is the shape, not a precise figure; both departments carry similar mapping noise.

## Shared definitions (all findings)

- **Recruiting**: `status == "recruiting"` in `data/processed/trials/studies.csv` - ClinicalTrials.gov
  RECRUITING or ENROLLING_BY_INVITATION; ISRCTN: today is between the recruitment start and end dates
  (from the most recently updated record when a study is on both registries). 4,083 studies.
- **A study in an area / at a trust**: the study has at least one UK site there. A study counts in every
  area or trust where it has a site.
- **People waiting**: NHS England RTT incomplete pathways, all treatments (`C_999`), August 2026.
- **Registries**: ClinicalTrials.gov data processed 2026-10-21; ISRCTN 2026-10-21. Contains information from the ISRCTN registry, licensed CC BY. Changes made
  by Wait Watcher: UK sites only, contact details removed, the two registries merged (linked by ISRCTN,
  IRAS or NCT number), sites matched to NHS trusts, conditions mapped to departments.
- **Reproduce**: `.venv/bin/python out/research/analysis.py` (writes `numbers.json`), then this file with
  `.venv/bin/python out/research/make_methods.py`.
