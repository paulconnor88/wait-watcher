"""
out/research/analysis.py - every number in out/research/findings.md and the slides.

Run from the project folder:   .venv/bin/python out/research/analysis.py
Writes out/research/numbers.json (all figures, for the brief, the slides and the method files).

Inputs (all produced by the kitchen; nothing here downloads data except one
postcode lookup, cached):
  data/processed/trials/studies.csv     one row per UK study (ClinicalTrials.gov + ISRCTN, merged)
  data/processed/trials/sites.csv       one row per study x UK site
  data/processed/rtt/area_history.csv   people waiting by ICB (where patients live) and month
  data/processed/rtt/history.csv        people waiting by trust and month
  data/processed/rtt/lookup.json        provider types and treatment function names
  data/processed/cancer/provider_standards.csv   cancer standards by trust and month
  data/processed/ers/asi_provider.csv   appointment slot issues by provider and month
  data/processed/findings-2026-08.json  section 2: England typical waits by department
  data/raw/trials/postcode_icb.json     cache: site postcode -> ICB (from postcodes.io, OGL)

Definitions used throughout:
  "recruiting"      study status 'recruiting' in trials/studies.csv (ClinicalTrials.gov RECRUITING or
                    ENROLLING_BY_INVITATION; ISRCTN: today is between the recruitment start and end dates)
  "a study in an area / at a trust"   the study has at least one UK site there. A study counts in
                    every area / trust where it has a site.
  "people waiting"  RTT incomplete pathways, all treatments (C_999), August 2026
  "interventional"  study type INTERVENTIONAL (either registry's spelling)
  "industry"        lead sponsor class INDUSTRY (ClinicalTrials.gov) or 'Commercial' (ISRCTN)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "kitchen"))
from common import post_json  # noqa: E402

P = PROJECT / "data" / "processed"
OUT = Path(__file__).resolve().parent
ICB_CACHE = PROJECT / "data" / "raw" / "trials" / "postcode_icb.json"
LOOKUP = json.loads((P / "rtt" / "lookup.json").read_text())


def load():
    studies = pd.read_csv(P / "trials" / "studies.csv", dtype=str)
    sites = pd.read_csv(P / "trials" / "sites.csv", dtype=str)
    studies["year"] = pd.to_numeric(studies["start_date"].str[:4], errors="coerce")
    studies["interventional"] = studies["study_type"].str.upper().eq("INTERVENTIONAL")
    return studies, sites


def registry_date():
    registry = {s["name"]: s for s in json.loads((PROJECT / "kitchen" / "registry.json").read_text())["sources"]}
    return str(registry["clinicaltrials"]["last_period"])[:10], str(registry["isrctn"]["last_period"])[:10]


# ---------------------------------------------------------------------------
# Macro pass
# ---------------------------------------------------------------------------

def macro(studies, sites):
    recruiting = studies[studies["status"] == "recruiting"]
    live_sites = sites[sites["study_id"].isin(recruiting["study_id"])]
    england = live_sites[live_sites["nation"] == "England"]
    return {
        "studies": len(studies), "recruiting": len(recruiting),
        "sources": studies["sources"].value_counts().to_dict(),
        "status": studies["status"].value_counts().to_dict(),
        "starts_by_year": studies.groupby("year").size().loc[2012:2026].astype(int).to_dict(),
        "study_sites": len(sites), "recruiting_study_sites_england": len(england),
        # A site's nation comes from its postcode, so coverage is measured on all recruiting UK sites.
        "recruiting_sites_with_postcode_pct": round(live_sites["postcode"].notna().mean() * 100, 1),
        "match_rate_england_pct": round(sites["ods_code"].notna().sum() / (sites["match_method"] != "outside England").sum() * 100, 1),
        "recruiting_but_started_before_2010": int((recruiting["year"] < 2010).sum()),
        "largest_enrolment_target": studies.assign(e=pd.to_numeric(studies["enrolment_target"], errors="coerce"))
            .nlargest(1, "e")[["study_id", "e", "title"]].to_dict("records"),
    }


# ---------------------------------------------------------------------------
# Finding 1 - recruiting studies per person waiting, by ICB (Essex v east London)
# ---------------------------------------------------------------------------

def site_icbs(postcodes):
    """{postcode: ICB name} from postcodes.io, cached."""
    cache = json.loads(ICB_CACHE.read_text()) if ICB_CACHE.exists() else {}
    wanted = sorted(set(postcodes) - set(cache))
    for start in range(0, len(wanted), 100):
        for item in post_json("https://api.postcodes.io/postcodes", {"postcodes": wanted[start:start + 100]}).json()["result"]:
            cache[item["query"]] = (item["result"] or {}).get("icb")
    ICB_CACHE.write_text(json.dumps(cache))
    return cache


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


# ---------------------------------------------------------------------------
# Finding 2 - recruiting studies per 10,000 people waiting, by department
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Finding 3 - research activity against waits (acute trusts)
# ---------------------------------------------------------------------------

def quarters(table, by, value):
    table = table.assign(q=pd.qcut(table[by].rank(method="first"), 4, labels=["fewest", "second", "third", "most"]))
    g = table.groupby("q", observed=True)
    return [{"quarter": str(q), "trusts": int(len(x)), "studies_from": int(x[by].min()), "studies_to": int(x[by].max()),
             "median": round(float(x[value].median()), 1)} for q, x in g]


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


# ---------------------------------------------------------------------------
# Finding 4 - interventional trial starts over time, by sponsor and department
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Sponsors (didn't make a slide)
# ---------------------------------------------------------------------------

def sponsor_kind(row):
    """industry (registry class) / NHS (a trust or hospital as lead sponsor) / university / other."""
    import re
    name = str(row["lead_sponsor"] or "")
    if row["sponsor_class"] == "INDUSTRY":
        return "industry"
    if re.search(r"NHS|\bTrust\b|Hospital", name, re.I) and not re.search(r"Universit|College|Institute|Cancer Research", name, re.I):
        return "NHS"
    if re.search(r"Universit|College|Institute|School|Imperial|UCL|King's", name, re.I):
        return "university"
    return "other"


def sponsors(studies):
    recruiting = studies[studies["status"] == "recruiting"]
    kinds = recruiting.apply(sponsor_kind, axis=1).value_counts(normalize=True).mul(100).round(1).to_dict()
    # Phase spelling: ClinicalTrials.gov writes "PHASE1"; ISRCTN writes "Phase I". Count ISRCTN-style phase 1 by start year.
    isrctn_style = studies[studies["phase"].fillna("").str.contains(r"Phase I\b", regex=True)]
    phase_spelling = isrctn_style.groupby("year").size().loc[2018:2025].astype(int).to_dict()
    exploded = recruiting.assign(tf=recruiting["treatment_functions"].str.split("; ")).explode("tf").dropna(subset=["tf"])
    industry_share = (exploded.groupby("tf")["industry_or_academic"].apply(lambda k: (k == "industry").mean() * 100).round(0))
    return {"recruiting_by_sponsor_kind_pct": kinds, "isrctn_style_phase_1_by_start_year": phase_spelling,
            "top_recruiting_sponsors": recruiting["lead_sponsor"].value_counts().head(10).to_dict(),
            "industry_share_recruiting_pct": round((recruiting["industry_or_academic"] == "industry").mean() * 100, 1),
            "industry_share_by_department": {LOOKUP["treatment_functions"].get(k, k): v for k, v in industry_share.sort_values().items()}}


def main():
    studies, sites = load()
    ct_date, isrctn_date = registry_date()
    numbers = {"processed": {"clinicaltrials": ct_date, "isrctn": isrctn_date},
               "macro": macro(studies, sites), "finding_1": finding_1_areas(studies, sites),
               "finding_2": finding_2_departments(studies), "finding_3": finding_3_research_v_waits(studies, sites),
               "finding_4": {**finding_4_trends(studies), "registration_lag": registration_lag()}, "sponsors": sponsors(studies)}
    (OUT / "numbers.json").write_text(json.dumps(numbers, indent=1, default=str))
    print(json.dumps({k: v for k, v in numbers.items() if k != "finding_1"}, indent=1, default=str)[:6000])
    f1 = numbers["finding_1"]
    print("finding 1:", {k: f1[k] for k in ("essex", "north_east_london", "ratio", "essex_rank_of_36", "median_icb_waiting_per_study",
                                            "sites_placed", "recruiting_sites_without_postcode", "recruiting_sites_all")})


if __name__ == "__main__":
    main()
