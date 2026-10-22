# Method 1: Essex against east London - recruiting studies per person waiting

**Finding:** In Essex there's one trial recruiting for every 2,500 people waiting. Next door in east London,
one for every 550.

## Files and rows used

| File | Rows used |
|---|---|
| `data/processed/trials/studies.csv` | 4,083 recruiting studies (of 42,795) |
| `data/processed/trials/sites.csv` | 18,965 study-sites of recruiting studies; 13,631 with an English postcode (`nation == "England"`, from postcodes.io); 3,107 recruiting study-sites have no postcode and can't be placed |
| `data/raw/trials/postcode_icb.json` | each site postcode's current ICB, from postcodes.io (Open Government Licence) |
| `data/processed/rtt/area_history.csv` | month `2026-08`, `treatment_function_code == "C_999"`, ICB names containing "INTEGRATED CARE BOARD" (36 rows) |

## Definitions

- **ICB**: the integrated care board the site's postcode is in today (postcodes.io `icb`), matched by name
  to the RTT area (the ICB where patients live).
- **Recruiting studies in an ICB**: distinct `study_id`s with at least one recruiting site in that ICB.
- **People waiting per recruiting study** = `total_patients` / recruiting studies.
- No England-wide figure is given: a study counts in every ICB where it has a site, so ICB figures don't add up.

## Code

```python
def site_icbs(postcodes):
    """{postcode: ICB name} from postcodes.io, cached."""
    cache = json.loads(ICB_CACHE.read_text()) if ICB_CACHE.exists() else {}
    wanted = sorted(set(postcodes) - set(cache))
    for start in range(0, len(wanted), 100):
        for item in post_json("https://api.postcodes.io/postcodes", {"postcodes": wanted[start:start + 100]}).json()["result"]:
            cache[item["query"]] = (item["result"] or {}).get("icb")
    ICB_CACHE.write_text(json.dumps(cache))
    return cache
```

```python
def finding_1_areas(studies, sites):
    recruiting = set(studies.loc[studies["status"] == "recruiting", "study_id"])
    live = sites[sites["study_id"].isin(recruiting)]
    placed = live[live["nation"] == "England"].dropna(subset=["postcode"]).copy()
    icb_of = site_icbs(placed["postcode"])
    placed["icb"] = placed["postcode"].map(icb_of).str.upper()
    studies_per_icb = placed.dropna(subset=["icb"]).groupby("icb")["study_id"].nunique()

    areas = pd.read_csv(P / "rtt" / "area_history.csv")
    latest = areas["month"].max()
    areas = areas[(areas["month"] == latest) & (areas["treatment_function_code"] == "C_999")
                  & areas["icb"].str.contains("INTEGRATED CARE BOARD")].copy()
    areas["recruiting_studies"] = areas["icb"].str.upper().map(studies_per_icb).fillna(0).astype(int)
    areas["waiting_per_study"] = areas["total_patients"] / areas["recruiting_studies"]
    areas = areas.sort_values("waiting_per_study", ascending=False)
    pick = lambda name: areas[areas["icb"] == name].iloc[0]
    essex, nel = pick("NHS ESSEX INTEGRATED CARE BOARD"), pick("NHS NORTH EAST LONDON INTEGRATED CARE BOARD")
    # (No England-wide figure: a study counts in every ICB where it has a site, so ICB figures don't add up to it.)
    return {
        "rtt_month": latest,
        "sites_placed": int(len(placed)), "recruiting_sites_without_postcode": int(live["postcode"].isna().sum()),
        "recruiting_sites_all": int(len(live)),
        "essex": {"waiting": int(essex["total_patients"]), "over_52": int(essex["over_52_weeks"]),
                  "recruiting_studies": int(essex["recruiting_studies"]), "waiting_per_study": round(float(essex["waiting_per_study"]))},
        "north_east_london": {"waiting": int(nel["total_patients"]), "over_52": int(nel["over_52_weeks"]),
                              "recruiting_studies": int(nel["recruiting_studies"]), "waiting_per_study": round(float(nel["waiting_per_study"]))},
        "ratio": round(float(essex["waiting_per_study"] / nel["waiting_per_study"]), 1),
        # Is Essex under-counted? Its main trust's (Mid and South Essex, RAJ) matched recruiting sites with a postcode.
        "mid_and_south_essex_sites": {"matched": int((live["provider_code"] == "RAJ").sum()),
                                      "with_postcode": int(((live["provider_code"] == "RAJ") & live["postcode"].notna()).sum())},
        "essex_rank_of_36": int(list(areas["icb"]).index("NHS ESSEX INTEGRATED CARE BOARD")) + 1,
        "median_icb_waiting_per_study": round(float(areas["waiting_per_study"].median())),
        "all_icbs": [{"icb": r.icb, "waiting": int(r.total_patients), "recruiting_studies": int(r.recruiting_studies),
                      "waiting_per_study": round(float(r.waiting_per_study))} for r in areas.itertuples()],
    }
```

## Result

```json
{
 "essex": {
  "waiting": 283275,
  "over_52": 14297,
  "recruiting_studies": 115,
  "waiting_per_study": 2463
 },
 "north_east_london": {
  "waiting": 249427,
  "over_52": 2773,
  "recruiting_studies": 455,
  "waiting_per_study": 548
 },
 "ratio": 4.5,
 "essex_rank_of_36": 2,
 "median_icb_waiting_per_study": 745,
 "sites_placed": 13631,
 "mid_and_south_essex_sites": {
  "matched": 108,
  "with_postcode": 99
 }
}
```

All 36 ICBs (most people waiting per recruiting study first):

| ICB | People waiting | Recruiting studies | Waiting per study |
|---|---|---|---|
| NHS Herefordshire And Worcestershire Integrated Care Board | 97,654 | 36 | 2,713 |
| NHS Essex Integrated Care Board | 283,275 | 115 | 2,463 |
| NHS Lincolnshire Integrated Care Board | 109,727 | 56 | 1,959 |
| NHS Shropshire, Telford And Wrekin Integrated Care Board | 68,115 | 38 | 1,792 |
| NHS Kent And Medway Integrated Care Board | 247,693 | 146 | 1,697 |
| NHS Surrey And Sussex Integrated Care Board | 414,102 | 257 | 1,611 |
| NHS Lancashire And South Cumbria Integrated Care Board | 231,851 | 179 | 1,295 |
| NHS Gloucestershire Integrated Care Board | 73,901 | 58 | 1,274 |
| NHS Staffordshire And Stoke-On-Trent Integrated Care Board | 149,128 | 118 | 1,264 |
| NHS Black Country Integrated Care Board | 172,245 | 141 | 1,222 |
| NHS Derby And Derbyshire Integrated Care Board | 116,650 | 96 | 1,215 |
| NHS Humber And North Yorkshire Integrated Care Board | 227,338 | 194 | 1,172 |
| NHS Norfolk And Suffolk Integrated Care Board | 212,871 | 196 | 1,086 |
| NHS Coventry And Warwickshire Integrated Care Board | 120,555 | 121 | 996 |
| NHS Dorset Integrated Care Board | 98,174 | 101 | 972 |
| NHS Central East Integrated Care Board | 410,252 | 491 | 836 |
| NHS Bath And North East Somerset, Swindon And Wiltshire Integrated Care Board | 115,531 | 139 | 831 |
| NHS Northamptonshire Integrated Care Board | 56,358 | 75 | 751 |
| NHS Cheshire And Merseyside Integrated Care Board | 340,941 | 462 | 738 |
| NHS North East And North Cumbria Integrated Care Board | 375,486 | 519 | 723 |
| NHS Somerset Integrated Care Board | 68,105 | 107 | 636 |
| NHS Hampshire And Isle Of Wight Integrated Care Board | 212,432 | 374 | 568 |
| NHS West Yorkshire Integrated Care Board | 250,052 | 447 | 559 |
| NHS North East London Integrated Care Board | 249,427 | 455 | 548 |
| NHS Greater Manchester Integrated Care Board | 411,464 | 754 | 546 |
| NHS South West London Integrated Care Board | 215,557 | 398 | 542 |
| NHS Leicester, Leicestershire And Rutland Integrated Care Board | 131,898 | 294 | 449 |
| NHS Cornwall And The Isles Of Scilly Integrated Care Board | 54,352 | 129 | 421 |
| NHS Nottingham And Nottinghamshire Integrated Care Board | 127,125 | 308 | 413 |
| NHS Thames Valley Integrated Care Board | 226,010 | 550 | 411 |
| NHS West And North London Integrated Care Board | 490,660 | 1,324 | 371 |
| NHS Birmingham And Solihull Integrated Care Board | 161,173 | 454 | 355 |
| NHS South East London Integrated Care Board | 223,705 | 681 | 328 |
| NHS South Yorkshire Integrated Care Board | 110,297 | 351 | 314 |
| NHS Bristol, North Somerset And South Gloucestershire Integrated Care Board | 94,894 | 337 | 282 |
| NHS Devon Integrated Care Board | 78,994 | 282 | 280 |

## Caveats

- People in Essex can and do join London studies; "nearby" here means inside the ICB boundary.
- Recruiting sites with no postcode (3,107) can't be placed. Mid and South
  Essex's matched recruiting sites: 99 of 108 have a
  postcode, so Essex isn't specially under-counted.

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
