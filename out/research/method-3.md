# Method 3: Research activity against waits, acute trusts

**Finding:** Hospitals running the most trials have waits just like everyone else's.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/sites.csv` | study-sites of recruiting studies with a `provider_code` (matched to one of our providers): 11,716 rows |
| `data/processed/rtt/history.csv` | month `2026-08`, `C_999`, `Incomplete Pathways`, acute trusts (`lookup.json` provider type "acute") with 10,000+ waiting: 113 trusts |
| `data/processed/cancer/provider_standards.csv` | 2026-06 to 2026-08, standards 62D and FDS, acute trusts with 150+ patients over the three months: 118 trusts |
| `data/processed/ers/asi_provider.csv` | month `2026-09`, acute trusts with 1,000+ bookings: 91 trusts |

## Definitions

- **Research activity of a trust**: distinct recruiting studies with a site matched to the trust (match
  methods: hand override, exact name and postcode, trust name, single-trust postcode, close name in the same
  town - never a guess). About 63% of English study-sites are matched, so counts are minimums.
- **Cancer trials**: recruiting studies whose MeSH terms or conditions mention a cancer (neoplasm,
  carcinoma, lymphoma, leukaemia, myeloma, melanoma, sarcoma, glioma, cancer, tumour).
- **Quarters**: trusts ranked by studies (ties broken by order) and cut into four equal groups; the median
  of each group's waiting measure is shown. Correlation: Pearson, studies against the measure.

## Code

```python
def quarters(table, by, value):
    table = table.assign(q=pd.qcut(table[by].rank(method="first"), 4, labels=["fewest", "second", "third", "most"]))
    g = table.groupby("q", observed=True)
    return [{"quarter": str(q), "trusts": int(len(x)), "studies_from": int(x[by].min()), "studies_to": int(x[by].max()),
             "median": round(float(x[value].median()), 1)} for q, x in g]
```

```python
def finding_3_research_v_waits(studies, sites):
    recruiting = set(studies.loc[studies["status"] == "recruiting", "study_id"])
    matched = sites[sites["study_id"].isin(recruiting)].dropna(subset=["provider_code"])
    per_trust = matched.groupby("provider_code")["study_id"].nunique()
    acute = lambda codes: codes.map(LOOKUP["provider_types"]).eq("acute")

    # 18 weeks: acute trusts with 10,000+ waiting, August 2026.
    h = pd.read_csv(P / "rtt" / "history.csv", usecols=["month", "provider_code", "treatment_function_code", "rtt_part",
                                                       "total_patients", "pct_within_18_weeks"])
    h = h[(h["month"] == h["month"].max()) & (h["treatment_function_code"] == "C_999") & (h["rtt_part"] == "Incomplete Pathways")]
    h = h[acute(h["provider_code"]) & (h["total_patients"] >= 10_000)].copy()
    h["studies"] = h["provider_code"].map(per_trust).fillna(0)
    rtt = {"trusts": len(h), "month": h["month"].iloc[0], "correlation": round(float(np.corrcoef(h["studies"], h["pct_within_18_weeks"])[0, 1]), 2),
           "quarters": quarters(h, "studies", "pct_within_18_weeks")}

    # Cancer: trials whose conditions are cancers, against the 62-day and 28-day standards (last 3 months, 150+ patients).
    cancer_words = r"neoplasm|carcinoma|lymphoma|leuka?emia|myeloma|melanoma|sarcoma|glioma|cancer|tumou?r"
    cancer_ids = set(studies.loc[(studies["status"] == "recruiting") & (studies["mesh_terms"].fillna("") + " " + studies["conditions"].fillna(""))
                                 .str.contains(cancer_words, case=False), "study_id"])
    per_trust_cancer = sites[sites["study_id"].isin(cancer_ids)].dropna(subset=["provider_code"]).groupby("provider_code")["study_id"].nunique()
    c = pd.read_csv(P / "cancer" / "provider_standards.csv", dtype={"provider_code": str})
    months = sorted(c["month"].unique())[-3:]
    c = c[c["month"].isin(months)].groupby(["provider_code", "standard"])[["within", "total"]].sum().reset_index()
    c["pct"] = c["within"] / c["total"] * 100
    cancer = {"months": f"{months[0]} to {months[-1]}"}
    for std in ("62D", "FDS"):
        x = c[(c["standard"] == std) & (c["total"] >= 150) & acute(c["provider_code"])].copy()
        x["studies"] = x["provider_code"].map(per_trust_cancer).fillna(0)
        cancer[std] = {"trusts": len(x), "correlation": round(float(np.corrcoef(x["studies"], x["pct"])[0, 1]), 2),
                       "quarters": quarters(x, "studies", "pct")}

    # GP referrals with no slot to book (e-RS), latest month, acute trusts with 1,000+ bookings.
    a = pd.read_csv(P / "ers" / "asi_provider.csv", dtype={"provider_code": str})
    a = a[(a["month"] == a["month"].max()) & (a["dbs_bookings"] >= 1000) & acute(a["provider_code"])].copy()
    a["studies"] = a["provider_code"].map(per_trust).fillna(0)
    asi = {"trusts": len(a), "month": a["month"].iloc[0], "correlation": round(float(np.corrcoef(a["studies"], a["asi_rate_pct"])[0, 1]), 2)}
    return {"rtt": rtt, "cancer": cancer, "slot_issues": asi}
```

## Result

```json
{
 "rtt": {
  "trusts": 113,
  "month": "2026-08",
  "correlation": -0.06,
  "quarters": [
   {
    "quarter": "fewest",
    "trusts": 29,
    "studies_from": 2,
    "studies_to": 17,
    "median": 65.3
   },
   {
    "quarter": "second",
    "trusts": 28,
    "studies_from": 17,
    "studies_to": 30,
    "median": 65.4
   },
   {
    "quarter": "third",
    "trusts": 28,
    "studies_from": 33,
    "studies_to": 99,
    "median": 64.7
   },
   {
    "quarter": "most",
    "trusts": 28,
    "studies_from": 99,
    "studies_to": 389,
    "median": 64.0
   }
  ]
 },
 "cancer": {
  "months": "2026-06 to 2026-08",
  "62D": {
   "trusts": 118,
   "correlation": -0.04,
   "quarters": [
    {
     "quarter": "fewest",
     "trusts": 30,
     "studies_from": 0,
     "studies_to": 3,
     "median": 73.3
    },
    {
     "quarter": "second",
     "trusts": 29,
     "studies_from": 4,
     "studies_to": 11,
     "median": 73.1
    },
    {
     "quarter": "third",
     "trusts": 29,
     "studies_from": 11,
     "studies_to": 32,
     "median": 69.5
    },
    {
     "quarter": "most",
     "trusts": 30,
     "studies_from": 32,
     "studies_to": 161,
     "median": 71.1
    }
   ]
  },
  "FDS": {
   "trusts": 118,
   "correlation": 0.16,
   "quarters": [
    {
     "quarter": "fewest",
     "trusts": 30,
     "studies_from": 0,
     "studies_to": 3,
     "median": 80.7
    },
    {
     "quarter": "second",
     "trusts": 29,
     "studies_from": 4,
     "studies_to": 11,
     "median": 79.0
    },
    {
     "quarter": "third",
     "trusts": 29,
     "studies_from": 11,
     "studies_to": 32,
     "median": 79.3
    },
    {
     "quarter": "most",
     "trusts": 30,
     "studies_from": 32,
     "studies_to": 161,
     "median": 81.4
    }
   ]
  }
 },
 "slot_issues": {
  "trusts": 91,
  "month": "2026-09",
  "correlation": -0.02
 }
}
```

## Caveats

- No link either way is the finding; it doesn't show research helps or harms waits.
- The busiest research trusts are also large and specialist; this compares trusts, not like-for-like patients.

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
