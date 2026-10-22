"""
kitchen/lab_data.py - the data files for Wait Watcher Lab (lab/).

What this script does, in plain English:
  Copies the kitchen's processed data into lab/data/ in a compact form the
  Lab page can load piece by piece. Files are split per dataset and per
  treatment or test, so the page only downloads what it needs and no file is
  over 5 MB (the script stops if one is).

  Every series file is shaped the same way: a list of months, and for each
  provider (or area) one row of numbers per month, lined up with the months
  (null where there's no figure). The meaning of each number is written in
  the file's "fields".

  lab/data/
    meta.json                 months, treatments, tests, providers (name, type,
                              town, treatment sites), areas, sources, check list
    rtt/<treatment>.json      providers: waiting / operation / clinic
    areas/<treatment>.json    ICBs (where patients live): waiting
    dm01/<test>.json          providers: diagnostic waits
    fft/<service>.json        providers: Friends and Family Test
    trusts.json               one line per provider and treatment, for the trust
                              page: latest figures, a year ago, and the % within
                              18 weeks month by month; plus latest scan waits
    staff.json                NHS Staff Survey, latest year
    cqc.json                  inspection rating per provider
    findings.json             this month's findings (make_findings.py)
    report-facts.json         this month's report facts
    questions.json            the questions the kitchen can answer, by audience (make_findings.py)
    more/<dataset>.json       the phase 3 sources, same series shape, each with its own months
    more/<dataset>/<x>.json   ... split by cancer standard or community service
                              (cancer, ae, asi, tt, mh, community, gp, gp_la, ambulance, dental)
    more/research_*.json      UK clinical research (kitchen/sources/trials.py): a snapshot, not
                              monthly - by trust, by council area, by department
    research/studies.json     every UK study recruiting now: title, phase, sponsor, registry IDs
    research/by_trust.json    which of those studies each trust has a site in

Run it with:   python kitchen/lab_data.py   (after make_findings.py)
"""

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED_DIR, PROJECT_DIR, REGISTRY_PATH  # noqa: E402
from make_findings import nice, short_icb, treatment_name  # noqa: E402

LAB_DATA = PROJECT_DIR / "lab" / "data"
MAX_BYTES = 5 * 1024 * 1024
PARTS = {"Incomplete Pathways": "waiting",
         "Completed Pathways For Admitted Patients": "operation",
         "Completed Pathways For Non-Admitted Patients": "clinic"}
RTT_FIELDS = ["people", "median_weeks", "p80_weeks", "p92_weeks", "pct_within_18_weeks", "over_52_weeks"]
UNRATED = {"Not yet rated", "Insufficient evidence to rate", "Not applicable", ""}

# Plain names for the 15 diagnostic tests.
TEST_NAMES = {
    "MRI": "MRI", "CT": "CT scan", "NON_OBSTETRIC_ULTRASOUND": "Ultrasound (non-obstetric)",
    "BARIUM_ENEMA": "Barium enema", "DEXA_SCAN": "DEXA (bone density) scan",
    "AUDIOLOGY_ASSESSMENTS": "Hearing (audiology) assessment", "ECHOCARDIOGRAPHY": "Echocardiogram (heart ultrasound)",
    "ELECTROPHYSIOLOGY": "Cardiac electrophysiology", "PERIPHERAL_NEUROPHYS": "Nerve conduction (neurophysiology)",
    "SLEEP_STUDIES": "Sleep study", "URODYNAMICS": "Urodynamics (bladder tests)", "COLONOSCOPY": "Colonoscopy",
    "FLEXI_SIGMOIDOSCOPY": "Flexible sigmoidoscopy", "CYSTOSCOPY": "Cystoscopy", "GASTROSCOPY": "Gastroscopy",
    "TOTAL": "All 15 tests",
}


def clean(value):
    """NaN -> None, whole floats -> ints, so the JSON stays small."""
    if hasattr(value, "item"):
        value = value.item()      # numpy number -> plain Python number
    if value is None or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def series(table, key, months, fields):
    """{key: [[fields...] per month, null if missing]} from a long table."""
    position = {m: i for i, m in enumerate(months)}
    out = {}
    for code, group in table.groupby(key):
        rows = [None] * len(months)
        for record in group[["month"] + fields].itertuples(index=False):
            rows[position[record[0]]] = [clean(v) for v in record[1:]]
        out[code] = rows
    return out


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))
    if path.stat().st_size > MAX_BYTES:
        raise SystemExit(f"{path} is over 5 MB ({path.stat().st_size / 1e6:.1f} MB) - split it further.")


def main():
    if LAB_DATA.exists():
        shutil.rmtree(LAB_DATA)
    lookup = json.loads((PROCESSED_DIR / "rtt" / "lookup.json").read_text())
    locations = json.loads((PROCESSED_DIR / "ods" / "locations.json").read_text())
    history = pd.read_csv(PROCESSED_DIR / "rtt" / "history.csv")
    months = sorted(history["month"].unique())

    # Waiting times by provider, one file per treatment.
    history = history.rename(columns={"total_patients": "people"})
    for code, rows in history.groupby("treatment_function_code"):
        write(LAB_DATA / "rtt" / f"{code}.json", {
            "treatment": code, "months": months, "fields": RTT_FIELDS,
            "parts": {PARTS[part]: series(part_rows, "provider_code", months, RTT_FIELDS)
                      for part, part_rows in rows.groupby("rtt_part")}})

    # Waiting times by area (ICB), one file per treatment.
    areas = pd.read_csv(PROCESSED_DIR / "rtt" / "area_history.csv").rename(columns={"total_patients": "people"})
    areas = areas[areas["icb"].str.contains("INTEGRATED CARE BOARD")]
    areas["icb"] = areas["icb"].map(short_icb)
    for code, rows in areas.groupby("treatment_function_code"):
        write(LAB_DATA / "areas" / f"{code}.json", {
            "treatment": code, "months": months, "fields": RTT_FIELDS,
            "parts": {"waiting": series(rows, "icb", months, RTT_FIELDS)}})

    # Diagnostic waits, one file per test.
    dm01 = pd.read_csv(PROCESSED_DIR / "dm01" / "dm01.csv")
    dm01_fields = ["total_waiting", "pct_6_weeks_plus", "pct_13_weeks_plus"]
    dm01_months = sorted(dm01["month"].unique())
    for test, rows in dm01.groupby("test"):
        write(LAB_DATA / "dm01" / f"{test}.json", {
            "test": test, "months": dm01_months, "fields": ["people", "pct_6_weeks_plus", "pct_13_weeks_plus"],
            "rows": series(rows, "provider_code", dm01_months, dm01_fields)})

    # The trust page's summary: per provider and treatment, people waiting,
    # typical wait, % within 18 weeks and over 52 weeks now, the % within 18
    # weeks a year ago, and the % within 18 weeks every month (for a small
    # trend line); and per test, the latest diagnostic waits.
    year_ago = months[-13] if len(months) >= 13 else months[0]
    waiting = history[history["rtt_part"] == "Incomplete Pathways"]
    trusts = {}
    for (code, tf), rows in waiting.groupby(["provider_code", "treatment_function_code"]):
        by_month = rows.set_index("month")
        if months[-1] not in by_month.index:
            continue
        now = by_month.loc[months[-1]]
        trusts.setdefault(code, {"rtt": {}, "dm01": {}})["rtt"][tf] = [
            clean(now["people"]), clean(now["median_weeks"]), clean(now["pct_within_18_weeks"]), clean(now["over_52_weeks"]),
            clean(by_month["pct_within_18_weeks"].get(year_ago)),
            [clean(by_month["pct_within_18_weeks"].get(m)) for m in months]]
    latest_dm01 = dm01[dm01["month"] == dm01["month"].max()]
    for r in latest_dm01.itertuples(index=False):
        if r.total_waiting:
            trusts.setdefault(r.provider_code, {"rtt": {}, "dm01": {}})["dm01"][r.test] = [
                clean(r.total_waiting), clean(r.pct_6_weeks_plus), clean(r.pct_13_weeks_plus)]
    write(LAB_DATA / "trusts.json", {"months": months, "year_ago": year_ago, "dm01_month": dm01["month"].max(),
                                     "rtt_fields": ["people", "median_weeks", "pct_within_18_weeks", "over_52_weeks",
                                                    "pct_within_18_weeks_year_ago", "pct_within_18_weeks_by_month"],
                                     "dm01_fields": ["people", "pct_6_weeks_plus", "pct_13_weeks_plus"],
                                     "rows": trusts})

    # Friends and Family Test, one file per service.
    fft = pd.read_csv(PROCESSED_DIR / "fft" / "fft.csv")
    fft_months = sorted(fft["month"].unique())
    for service, rows in fft.groupby("service"):
        write(LAB_DATA / "fft" / f"{service}.json", {
            "service": service, "months": fft_months, "fields": ["responses", "pct_good_or_very_good"],
            "rows": series(rows, "provider_code", fft_months, ["responses", "pct_positive"])})

    # Staff Survey, latest year.
    staff = pd.read_csv(PROCESSED_DIR / "staff_survey" / "staff_survey.csv")
    year = int(staff["year"].max())
    latest_staff = staff[staff["year"] == year]
    write(LAB_DATA / "staff.json", {"year": year, "rows": {
        r.provider_code: {"treatment_pct": clean(r.recommend_place_for_treatment_pct),
                          "work_pct": clean(r.recommend_place_to_work_pct),
                          "responses": clean(r.recommend_place_for_treatment_responses)}
        for r in latest_staff.itertuples(index=False)}})

    # CQC: the trust-wide rating if there is one, else the best-matched rated site.
    cqc = json.loads((PROCESSED_DIR / "cqc" / "cqc.json").read_text())
    ratings = {}
    for code in lookup["providers"]:
        trust = cqc["trusts"].get(code)
        if trust and trust["rating"] not in UNRATED:
            ratings[code] = {"rating": trust["rating"], "date": trust["date"], "url": trust["url"], "scope": "trust"}
            continue
        site = next((e for e in cqc["providers"].get(code, []) if e["overall"]["rating"] not in UNRATED), None)
        if site:
            ratings[code] = {"rating": site["overall"]["rating"], "date": site["overall"]["date"], "url": site["url"],
                             "scope": "hospital", "site": nice(site["cqc_name"])}
    write(LAB_DATA / "cqc.json", ratings)

    # Findings and report facts for the latest month.
    latest = months[-1]
    findings = json.loads((PROCESSED_DIR / f"findings-{latest}.json").read_text())
    write(LAB_DATA / "findings.json", findings)
    write(LAB_DATA / "report-facts.json", json.loads((PROCESSED_DIR / f"report-facts-{latest}.json").read_text()))

    # The phase 3 sources, for Explore and the trust page.
    more = more_datasets()
    questions_path = PROCESSED_DIR / "questions.json"
    write(LAB_DATA / "questions.json", json.loads(questions_path.read_text()) if questions_path.exists() else [])

    # Meta: everything the page needs to build its menus.
    providers = {}
    for code, name in lookup["providers"].items():
        place = locations.get(code, {})
        sites = [[round(s["latitude"], 4), round(s["longitude"], 4)] for s in place.get("sites", [])
                 if s.get("treatment") and s.get("latitude") is not None]
        providers[code] = {"name": nice(name), "type": lookup.get("provider_types", {}).get(code, "unknown"),
                           "town": nice(place.get("town", "") or ""), "sites": sites}
    registry = json.loads(REGISTRY_PATH.read_text())
    write(LAB_DATA / "meta.json", {
        "latest_month": latest, "months": months, "dm01_months": dm01_months, "fft_months": fft_months,
        "staff_year": year,
        "treatments": {code: treatment_name(code, lookup) for code in sorted(history["treatment_function_code"].unique())},
        "tests": {t: TEST_NAMES.get(t, t.title()) for t in sorted(dm01["test"].unique(), key=lambda t: (t == "TOTAL", t))},
        # Only areas that exist in the latest month (an abolished ICB, e.g.
        # Frimley until March 2026, stays in the files but isn't listed).
        "areas": sorted(areas[areas["month"] == latest]["icb"].unique()),
        "providers": providers,
        "check_before_using": {c["code"]: c["reason"] for c in findings["check_before_using"]},
        "sources": [{k: s.get(k) for k in ("name", "title", "publisher", "url", "cadence", "licence", "status",
                                           "last_fetched", "latest_month", "latest_year", "last_period", "reason",
                                           "sensitive", "note")}
                    for s in registry["sources"]],
        "more": more["datasets"],
        "names": {c: n for c, n in more["names"].items() if c not in providers},
    })

    files = sorted(LAB_DATA.rglob("*.json"))
    biggest = max(files, key=lambda p: p.stat().st_size)
    total = sum(p.stat().st_size for p in files)
    print(f"Saved {len(files)} files to lab/data/ ({total / 1e6:.1f} MB in all; "
          f"biggest {biggest.relative_to(LAB_DATA)} at {biggest.stat().st_size / 1e6:.1f} MB).")


# ---------------------------------------------------------------------------
# The phase 3 sources
# ---------------------------------------------------------------------------

def series_file(path, table, key, fields, flags=None, months=None):
    """Write one series file and return its months."""
    months = months or sorted(table["month"].unique())
    write(path, {"months": months, "fields": fields, "rows": series(table, key, months, fields),
                 "flags": flags or {}})
    return months


def flags_of(source):
    path = PROCESSED_DIR / source / "check_before_using.json"
    return json.loads(path.read_text()) if path.exists() else {}


def more_datasets():
    """Writes lab/data/more/ and returns {"datasets": {name: {months, variants, keys}}, "names": {code: name}}."""
    out, names = {}, {}
    more = LAB_DATA / "more"

    def remember(table, key, label):
        for code, name in table.drop_duplicates(key)[[key, label]].itertuples(index=False):
            if isinstance(name, str):
                names.setdefault(code, nice(name))

    # Cancer: one file per standard. Sensitive.
    cancer = pd.read_csv(PROCESSED_DIR / "cancer" / "provider_standards.csv", dtype={"provider_code": str})
    cancer = cancer.rename(columns={"total": "people"})
    remember(cancer, "provider_code", "provider_name")
    cancer_flags = flags_of("cancer")
    for standard, rows in cancer.groupby("standard"):
        months = series_file(more / "cancer" / f"{standard}.json", rows, "provider_code", ["pct_within", "people"], cancer_flags)
    out["cancer"] = {"months": months, "variants": {"FDS": "Told within 28 days (Faster Diagnosis Standard)",
                                                    "31D": "Treated within 31 days of deciding to treat",
                                                    "62D": "Treated within 62 days of urgent referral"}}

    # A&E.
    ae = pd.read_csv(PROCESSED_DIR / "ae" / "provider_month.csv", dtype={"provider_code": str})
    ae = ae.rename(columns={"attendances": "people"})
    remember(ae, "provider_code", "provider_name")
    out["ae"] = {"months": series_file(more / "ae.json", ae, "provider_code",
                                       ["type1_pct_within_4_hours", "pct_within_4_hours", "dta_over_12_hours", "people"],
                                       flags_of("ae"))}

    # e-RS appointment slot issues.
    asi = pd.read_csv(PROCESSED_DIR / "ers" / "asi_provider.csv", dtype={"provider_code": str})
    asi = asi.rename(columns={"dbs_bookings": "people"})
    remember(asi, "provider_code", "provider_name")
    out["asi"] = {"months": series_file(more / "asi.json", asi, "provider_code", ["asi_rate_pct", "total_asis", "people"],
                                        flags_of("ers"))}

    # NHS Talking Therapies.
    tt = pd.read_csv(PROCESSED_DIR / "talking_therapies" / "provider_month.csv", dtype={"provider_code": str})
    tt = tt.rename(columns={"finished_treatment": "people"})
    remember(tt, "provider_code", "provider_name")
    out["tt"] = {"months": series_file(more / "tt.json", tt, "provider_code",
                                       ["pct_within_6_weeks", "pct_within_18_weeks", "pct_recovery", "people"],
                                       flags_of("talking_therapies"))}

    # Mental health waits.
    mh = pd.read_csv(PROCESSED_DIR / "mhsds" / "provider_month.csv", dtype={"provider_code": str})
    mh = mh.rename(columns={"cyp_first_contacts": "people"})
    remember(mh, "provider_code", "provider_name")
    out["mh"] = {"months": series_file(more / "mh.json", mh, "provider_code",
                                       ["cyp_median_days_to_first", "adult_median_days_to_second", "cyp_pct_within_4_weeks", "people"],
                                       flags_of("mhsds"))}

    # Community services: one file per service (providers only).
    community = pd.read_csv(PROCESSED_DIR / "community" / "waits.csv", dtype={"org_code": str})
    community = community[community["org_type"] == "Provider"].rename(columns={"total_waiting": "people"})
    remember(community, "org_code", "org_name")
    community_flags = flags_of("community")
    variants = {}
    for number, (service, rows) in enumerate(sorted(community.groupby("service"), key=lambda x: x[0]), 1):
        key = f"s{number:02d}"
        variants[key] = service.replace("(A) ", "Adults: ").replace("(CYP) ", "Children: ")
        prefix = f" | {service}"
        service_flags = {k.split(" | ")[0]: v for k, v in community_flags.items() if k.endswith(prefix)}
        months = series_file(more / "community" / f"{key}.json", rows, "org_code",
                             ["pct_over_18_weeks", "over_52_weeks", "people"], service_flags)
    out["community"] = {"months": months, "variants": variants}

    # GP appointments by area: ICB, and local authority (practices added up, flagged ones left out).
    gp = pd.read_csv(PROCESSED_DIR / "gpad" / "practice_month.csv", dtype={"practice_code": str})
    gp = gp[~gp["practice_code"].isin(flags_of("gpad"))]
    where = pd.read_csv(PROCESSED_DIR / "gp_practices" / "practices.csv", dtype=str)[["practice_code", "local_authority"]]
    icb_names = pd.read_csv(PROCESSED_DIR / "gpad" / "icb_month.csv").drop_duplicates("icb_code").set_index("icb_code")["icb_name"]
    gp = gp.merge(where, on="practice_code", how="left")
    gp["icb"] = gp["icb_code"].map(icb_names).fillna("").str.upper().map(short_icb)
    counts = ["appointments", "attended", "dna", "same_day", "day_1", "days_2_7", "days_8_14", "days_15_21",
              "days_22_28", "over_28"]
    for name, key in (("gp", "icb"), ("gp_la", "local_authority")):
        area = gp[gp[key].fillna("") != ""].groupby(["month", key], as_index=False)[counts].sum()
        known = area[counts[3:]].sum(axis=1)
        area["pct_same_day"] = (area["same_day"] / known * 100).round(1)
        area["pct_over_28_days"] = (area["over_28"] / known * 100).round(1)
        area["pct_dna"] = (area["dna"] / (area["attended"] + area["dna"]) * 100).round(1)
        area = area.rename(columns={"appointments": "people"})
        months = series_file(more / f"{name}.json", area, key, ["pct_same_day", "pct_over_28_days", "pct_dna", "people"])
        latest = area[area["month"] == months[-1]]
        out[name] = {"months": months, "keys": sorted(latest[key].unique())}

    # Ambulance response times: trusts and England (minutes).
    amb = pd.read_csv(PROCESSED_DIR / "ambulance" / "response_month.csv")
    amb = amb[amb["level"] != "Region"].copy()
    amb["name"] = amb.apply(lambda r: "England" if r["level"] == "England" else nice(r["org_name"]), axis=1)
    amb = amb.rename(columns={"cat2_incidents": "people"})
    months = series_file(more / "ambulance.json", amb, "name",
                         ["cat2_mean_minutes", "cat2_p90_minutes", "cat1_mean_minutes", "people"])
    out["ambulance"] = {"months": months, "keys": sorted(amb["name"].unique())}

    # NHS dental activity by commissioner (ICB).
    dental = pd.read_csv(PROCESSED_DIR / "dental" / "icb_month.csv")
    dental["name"] = dental["icb_name"].str.replace(r"^NHS |\s*ICB$", "", regex=True).map(nice)
    dental = dental.rename(columns={"contracts": "people"})
    months = series_file(more / "dental.json", dental, "name", ["adults_seen_24m", "children_seen_12m", "people"])
    out["dental"] = {"months": months, "keys": sorted(dental[dental["month"] == months[-1]]["name"].unique())}
    out.update(research_datasets(names))
    return {"datasets": out, "names": names}


def research_datasets(names):
    """UK clinical research from trials.py and this month's findings (section 11): a snapshot, written
    as one-"month" series files so Explore can rank them; plus the recruiting studies for trust pages."""
    studies = pd.read_csv(PROCESSED_DIR / "trials" / "studies.csv", dtype=str)
    sites = pd.read_csv(PROCESSED_DIR / "trials" / "sites.csv", dtype=str)
    latest = max(PROCESSED_DIR.glob("findings-*.json"))
    research = json.loads(latest.read_text()).get("11_research")
    if research is None:
        return {}
    registry = {s["name"]: s for s in json.loads(REGISTRY_PATH.read_text())["sources"]}
    as_of = str(registry.get("clinicaltrials", {}).get("last_period") or "")[:10]
    snapshot = as_of[:7]
    live = studies[studies["status"] == "recruiting"]
    live_sites = sites[sites["study_id"].isin(live["study_id"])].dropna(subset=["provider_code"])
    out = {}

    # By trust: recruiting studies, all studies, % of recruiting ones industry-sponsored.
    kind = live.set_index("study_id")["industry_or_academic"]
    trust = live_sites.drop_duplicates(["study_id", "provider_code"]).assign(industry=lambda t: t["study_id"].map(kind) == "industry")
    all_studies = sites.dropna(subset=["provider_code"]).groupby("provider_code")["study_id"].nunique()
    table = trust.groupby("provider_code").agg(recruiting_studies=("study_id", "nunique"), industry=("industry", "mean"))
    table["industry_pct_recruiting"] = (table["industry"] * 100).round(1)
    table["people"] = all_studies.reindex(table.index)
    table = table.reset_index().assign(month=snapshot)
    series_file(LAB_DATA / "more" / "research_trusts.json", table, "provider_code",
                ["recruiting_studies", "industry_pct_recruiting", "people"], months=[snapshot])
    out["research_trusts"] = {"months": [snapshot], "as_of": as_of}

    # By council area: recruiting studies per 100,000 people (every council area, from the findings).
    population = pd.read_csv(PROCESSED_DIR / "population" / "local_authority.csv")
    population = population[population["geography"].isin(["Unitary Authority", "Non-metropolitan District",
                                                         "Metropolitan District", "London Borough"])]
    per_area = sites[sites["study_id"].isin(live["study_id"]) & (sites["nation"] == "England")] \
        .groupby("local_authority")["study_id"].nunique()
    areas = population.assign(recruiting_studies=population["area_name"].map(per_area).fillna(0).astype(int))
    # Per head only for areas of 50,000+ people (as in the findings): tiny ones like the City of London
    # have a big hospital and few residents, which says nothing useful.
    areas["per_100k"] = (areas["recruiting_studies"] / areas["population"] * 100_000).round(1) \
        .where(areas["population"] >= 50_000)
    areas = areas.rename(columns={"population": "people"}).assign(month=snapshot)
    series_file(LAB_DATA / "more" / "research_areas.json", areas, "area_name",
                ["per_100k", "recruiting_studies", "people"], months=[snapshot])
    out["research_areas"] = {"months": [snapshot], "as_of": as_of, "keys": sorted(areas["area_name"])}

    # By department (treatment function): waits against recruiting studies, industry share.
    departments = pd.DataFrame(research["11c_departments"]).rename(columns={"waiting_now": "people"})
    departments = departments.assign(month=snapshot)
    series_file(LAB_DATA / "more" / "research_departments.json", departments, "name",
                ["recruiting_per_10k_waiting", "recruiting_studies", "median_wait_weeks", "industry_pct",
                 "industry_pct_recruiting", "all_studies", "people"], months=[snapshot])
    out["research_departments"] = {"months": [snapshot], "as_of": as_of, "keys": sorted(departments["name"])}

    # The recruiting studies themselves, and which trusts each has a site at (for trust pages).
    fields = ["title", "phase", "industry_or_academic", "nct_id", "isrctn", "uk_sites", "treatment_functions", "start_date"]
    write(LAB_DATA / "research" / "studies.json", {"as_of": as_of, "fields": fields, "rows": {
        r.study_id: [clean(getattr(r, f)) for f in fields] for r in live.itertuples(index=False)}})
    write(LAB_DATA / "research" / "by_trust.json", {"as_of": as_of, "rows": {
        code: sorted(group["study_id"].unique()) for code, group in live_sites.groupby("provider_code")}})
    return out


if __name__ == "__main__":
    main()
