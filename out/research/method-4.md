# Method 4: UK trial starts over time, by sponsor and department

**Finding:** Drug-company trials in the UK held steady. University and NHS-led ones fell by about a seventh.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/studies.csv` | interventional studies (`study_type` INTERVENTIONAL, either registry's spelling) starting 2017-2024: periods 2017-19, 2020-21, 2022-24 |
| `data/raw/clinicaltrials/studies.jsonl` | ClinicalTrials.gov first-posted dates (for the registration-lag check only) |

## Definitions

- **Start year**: the year of `start_date` (ClinicalTrials.gov study start; ISRCTN recruitment start).
- **Industry**: lead sponsor class INDUSTRY (ClinicalTrials.gov) or "Commercial" (ISRCTN). Everything else is
  "academic and other" (universities, NHS trusts, charities, government).
- **Per year**: distinct studies in the period / number of years in it.
- 2025-26 left out: recent studies are still being registered. Registration lag (ClinicalTrials.gov,
  interventional, share posted more than ten months after the start year ended): ```json
{
 "academic_2019_pct_posted_late": 11.3,
 "industry_2019_pct_posted_late": 3.0,
 "academic_2023_pct_posted_late": 8.0,
 "industry_2023_pct_posted_late": 1.8
}
```

## Code

```python
def finding_4_trends(studies):
    s = studies[studies["interventional"]]
    period = pd.cut(s["year"], [2016, 2019, 2021, 2024], labels=["2017-19", "2020-21", "2022-24"])
    years = {"2017-19": 3, "2020-21": 2, "2022-24": 3}
    by_kind = s.assign(period=period).dropna(subset=["period"]).groupby(["industry_or_academic", "period"], observed=True)["study_id"].nunique()
    per_year = {f"{k}|{p}": round(v / years[p]) for (k, p), v in by_kind.items()}
    e = s.assign(period=period, tf=s["treatment_functions"].str.split("; ")).explode("tf").dropna(subset=["tf", "period"])
    by_tf = e.groupby(["tf", "period"], observed=True)["study_id"].nunique().unstack()
    depts = []
    for code, row in by_tf.iterrows():
        before, after = row["2017-19"] / 3, row["2022-24"] / 3
        depts.append({"code": code, "name": LOOKUP["treatment_functions"].get(code, code).removesuffix(" Services").removesuffix(" Service"),
                      "per_year_2017_19": round(before), "per_year_2022_24": round(after),
                      "change_pct": round((after / before - 1) * 100) if before else None})
    depts.sort(key=lambda d: d["change_pct"] if d["change_pct"] is not None else 0)
    yearly = s[(s["year"] >= 2012) & (s["year"] <= 2025)].groupby(["year", "industry_or_academic"]).size().unstack().fillna(0).astype(int)
    academic = (per_year["academic and other|2022-24"] / per_year["academic and other|2017-19"] - 1) * 100
    industry = (per_year["industry|2022-24"] / per_year["industry|2017-19"] - 1) * 100
    return {"per_year": per_year, "academic_change_pct": round(academic), "industry_change_pct": round(industry),
            "departments": depts, "yearly": {int(y): r.to_dict() for y, r in yearly.iterrows()}}
```

```python
def registration_lag():
    """How late studies are registered, from ClinicalTrials.gov's first-posted dates (raw store): the share of
    interventional studies starting in a year that were first posted more than ten months after that year ended
    (i.e. after 21 October of the next year - the same point in the calendar as today's snapshot)."""
    rows = []
    with open(PROJECT / "data" / "raw" / "clinicaltrials" / "studies.jsonl") as f:
        for line in f:
            p = json.loads(line)["protocolSection"]
            status = p.get("statusModule", {})
            rows.append({"start": status.get("startDateStruct", {}).get("date"),
                         "posted": status.get("studyFirstPostDateStruct", {}).get("date"),
                         "industry": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("class") == "INDUSTRY",
                         "interventional": p.get("designModule", {}).get("studyType") == "INTERVENTIONAL"})
    c = pd.DataFrame(rows)
    c = c[c["interventional"]]
    c["year"] = pd.to_numeric(c["start"].str[:4], errors="coerce")
    c["posted"] = pd.to_datetime(c["posted"], errors="coerce")
    out = {}
    for year in (2019, 2023):
        for industry, label in ((False, "academic"), (True, "industry")):
            g = c[(c["year"] == year) & (c["industry"] == industry)]
            out[f"{label}_{year}_pct_posted_late"] = round(float((g["posted"] > pd.Timestamp(f"{year + 1}-10-21")).mean() * 100), 1)
    return out
```

## Result

```json
{
 "per_year": {
  "academic and other|2017-19": 1022,
  "academic and other|2020-21": 792,
  "academic and other|2022-24": 874,
  "industry|2017-19": 725,
  "industry|2020-21": 700,
  "industry|2022-24": 703
 },
 "academic_change_pct": -14,
 "industry_change_pct": -3
}
```

| Department | Starts a year, 2017-19 | Starts a year, 2022-24 | Change |
|---|---|---|---|
| Plastic Surgery | 6 | 2 | -59% |
| General Surgery | 5 | 3 | -47% |
| Gastroenterology | 138 | 109 | -21% |
| Trauma and Orthopaedic | 63 | 50 | -20% |
| Ophthalmology | 50 | 40 | -20% |
| Oral Surgery | 15 | 12 | -18% |
| Other - Medical | 178 | 148 | -17% |
| Ear Nose and Throat | 28 | 24 | -15% |
| Gynaecology | 30 | 27 | -12% |
| Cardiology | 144 | 130 | -10% |
| Elderly Medicine | 11 | 10 | -9% |
| Urology | 56 | 52 | -7% |
| Rheumatology | 35 | 32 | -7% |
| Other - Surgical | 41 | 39 | -6% |
| Neurology | 139 | 140 | +1% |
| Other - Mental Health | 141 | 142 | +1% |
| Respiratory Medicine | 159 | 165 | +3% |
| Dermatology | 64 | 70 | +9% |
| Neurosurgical | 20 | 25 | +21% |
| Cardiothoracic Surgery | 3 | 5 | +75% |

## Caveats

- Counts studies, not participants: the widely reported fall in UK commercial trial recruitment can't be
  seen in registries.
- Late registration means 2022-24 academic counts may still rise slightly.

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
