"""
kitchen/whats_new.py - "what's new this month" from the phase 3 sources, and questions.md.

Called by make_findings.py (it isn't run on its own). Two jobs:

  1. findings(...) works out the new sections of the month's findings:
       10a  what's been published: each source's latest period
       10b  biggest appointment slot issue (ASI) rates: where GPs most often
            can't book a first hospital appointment
       10c  cancer standards most and least met (SENSITIVE - gentle copy:
            "furthest from the standard", never "worst")
       10d  GP access best and worst by area: share of appointments booked
            more than 28 days ahead, by ICB and by local authority
       10e  A&E: furthest from the four-hour standard, and most 12-hour
            waits from decision to admit
       10f  staffing and waits, as a picture only (no causal claim): sickness
            absence by trust against % within 18 weeks, and regional
            vacancy rates against regional waits
     Providers each source flags "check before using" are left out of
     best and worst lists, and the flags are counted.

  1b. research_findings(...) works out section 11, UK clinical research, as
     pictures - never causal claims:
       11a  recruiting UK studies per 100,000 people, by local authority
       11b  trusts ranked by recruiting studies (from the two registries; NIHR's
            participant numbers aren't openly published by trust, so they can't
            be used)
       11c  departments: longest waits against fewest recruiting studies
       11d  industry against academic share of studies, by department
       11e  recruiting studies against % within 18 weeks, acute trusts (in
            place of NIHR research activity, for the same reason as 11b)

  2. questions_md(...) writes data/processed/questions.md: every question the
     kitchen can answer, grouped by audience (patient, GP, NHS insider,
     journalist), each with its source, grain and an example answer worked
     out from the latest data. Example answers for patients are anchored on
     Walthamstow (Barts Health, North East London ICB, NELFT), as the Lab is.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROCESSED = PROJECT_DIR / "data" / "processed"
REGISTRY = PROJECT_DIR / "kitchen" / "registry.json"

SHOWN = 5
LEAGUE_TYPES = {"acute", "specialist"}
CANCER_STANDARDS = {"FDS": ("Faster Diagnosis Standard: told within 28 days", 75),
                    "31D": ("31 days from decision to treat to treatment", 96),
                    "62D": ("62 days from urgent referral to first treatment", 85)}
CANCER_MIN = {"FDS": 100, "31D": 20, "62D": 20}     # patients in the month, to be listed

# The Walthamstow anchor for example answers.
HOME = {"place": "Walthamstow", "trust": "R1H", "community_trust": "RAT", "icb": "QMF",
        "local_authority": "Waltham Forest", "ambulance": "RRU", "region": "London"}


def read(path, **kw):
    return pd.read_csv(PROCESSED / path, **kw)


def flags(source):
    path = PROCESSED / source / "check_before_using.json"
    return set(json.loads(path.read_text())) if path.exists() else set()


def latest(table, column="month"):
    return table[table[column] == table[column].max()]


def r1(x):
    return None if x is None or pd.isna(x) else round(float(x), 1)


def month_label(month):
    return pd.to_datetime(month + "-01").strftime("%B %Y") if isinstance(month, str) and len(month) == 7 else str(month)


# ---------------------------------------------------------------------------
# 1. The findings
# ---------------------------------------------------------------------------

def published():
    """Each source's latest period, from the registry."""
    out = []
    for s in json.loads(REGISTRY.read_text())["sources"]:
        out.append({"source": s["name"], "title": s.get("title", s["name"]), "status": s.get("status"),
                    "last_period": s.get("last_period"), "sensitive": s.get("sensitive")})
    return out


def asi_rates(nice):
    asi = read("ers/asi_provider.csv", dtype={"provider_code": str})
    now = latest(asi)
    england = now["total_asis"].sum() / now["dbs_bookings"].sum() * 100
    flagged = flags("ers")
    big = now[(now["dbs_bookings"] >= 1000) & ~now["provider_code"].isin(flagged)]
    top = big.sort_values("asi_rate_pct", ascending=False).head(10)
    return {"month": now["month"].iloc[0], "england_per_100_bookings": r1(england),
            "providers_compared": len(big), "left_out_flagged": int(now["provider_code"].isin(flagged).sum()),
            "highest": [{"code": r.provider_code, "name": nice(r.provider_name), "asis": int(r.total_asis),
                         "bookings": int(r.dbs_bookings), "asi_per_100_bookings": r1(r.asi_rate_pct)}
                        for r in top.itertuples()]}


def cancer_standards(nice):
    cancer = read("cancer/provider_standards.csv", dtype={"provider_code": str})
    now = latest(cancer)
    flagged = flags("cancer")
    out = {"month": now["month"].iloc[0], "sensitive": "gentle copy required", "standards": []}
    for standard, (meaning, target) in CANCER_STANDARDS.items():
        rows = now[now["standard"] == standard]
        # NHS trusts only (codes starting R): independent providers see a narrow mix of patients.
        listed = rows[(rows["total"] >= CANCER_MIN[standard]) & ~rows["provider_code"].isin(flagged)
                      & rows["provider_code"].str.match(r"R\w\w$")]
        listed = listed.sort_values("pct_within", ascending=False)
        pick = lambda t: [{"code": r.provider_code, "name": nice(r.provider_name), "patients": int(r.total),
                           "pct_within": r1(r.pct_within)} for r in t.itertuples()]
        out["standards"].append({
            "standard": standard, "meaning": meaning, "target_pct": target,
            "england_pct": r1(rows["within"].sum() / rows["total"].sum() * 100),
            "trusts_meeting": int((listed["pct_within"] >= target).sum()), "trusts_listed": len(listed),
            "closest_to_or_above": pick(listed.head(SHOWN)), "furthest_from": pick(listed.tail(SHOWN)[::-1])})
    return out


def gp_access(short_icb):
    """Areas added up from practices, leaving out practices flagged "check before using"."""
    flagged = flags("gpad")
    practices = latest(read("gpad/practice_month.csv", dtype={"practice_code": str}))
    practices = practices[~practices["practice_code"].isin(flagged)]
    where = read("gp_practices/practices.csv", dtype=str)[["practice_code", "local_authority"]]
    practices = practices.merge(where, on="practice_code", how="left")
    names = latest(read("gpad/icb_month.csv")).set_index("icb_code")["icb_name"]
    counts = ["appointments", "same_day", "day_1", "days_2_7", "days_8_14", "days_15_21", "days_22_28", "over_28"]

    def by(column, minimum):
        table = practices.groupby(column, as_index=False)[counts].sum()
        table = table[table["appointments"] >= minimum]
        known = table[counts[1:]].sum(axis=1)
        table["pct_over_28_days"] = (table["over_28"] / known * 100).round(1)
        table["pct_same_day"] = (table["same_day"] / known * 100).round(1)
        return table.sort_values("pct_over_28_days")

    icb, la = by("icb_code", 100_000), by("local_authority", 50_000)
    icb["icb_name"] = icb["icb_code"].map(names).str.upper()   # short_icb expects the RTT spelling
    area = lambda t, name: [{"name": name(r), "pct_over_28_days": r1(r.pct_over_28_days), "pct_same_day": r1(r.pct_same_day),
                             "appointments": int(r.appointments)} for r in t.itertuples()]
    return {"month": practices["month"].iloc[0], "measure": "share of appointments with a known booking time that were "
                                                             "more than 28 days after booking (lower is better)",
            "icb_best": area(icb.head(SHOWN), lambda r: short_icb(r.icb_name)),
            "icb_worst": area(icb.tail(SHOWN)[::-1], lambda r: short_icb(r.icb_name)),
            "local_authorities_compared": len(la),
            "la_best": area(la.head(SHOWN), lambda r: r.local_authority),
            "la_worst": area(la.tail(SHOWN)[::-1], lambda r: r.local_authority),
            "practices_left_out_flagged": len(flagged)}


def ae_worst(nice):
    ae = latest(read("ae/provider_month.csv", dtype={"provider_code": str}))
    flagged = flags("ae")
    big = ae[(ae["type1_attendances"] >= 3000) & ~ae["provider_code"].isin(flagged)]
    row = lambda r: {"code": r.provider_code, "name": nice(r.provider_name), "type1_attendances": int(r.type1_attendances),
                     "type1_pct_within_4_hours": r1(r.type1_pct_within_4_hours), "dta_over_12_hours": int(r.dta_over_12_hours)}
    return {"month": ae["month"].iloc[0],
            "england_pct_within_4_hours": r1((1 - ae["over_4_hours"].sum() / ae["attendances"].sum()) * 100),
            "england_type1_pct": r1((1 - ae["type1_over_4_hours"].sum() / ae["type1_attendances"].sum()) * 100),
            "trusts_compared": len(big),
            "furthest_from_four_hours": [row(r) for r in big.sort_values("type1_pct_within_4_hours").head(10).itertuples()],
            "most_12_hour_waits": [row(r) for r in big.sort_values("dta_over_12_hours", ascending=False).head(SHOWN).itertuples()]}


def rtt_trusts(lookup):
    """Acute and specialist trusts' latest % within 18 weeks and waiting, from history.csv."""
    history = read("rtt/history.csv", usecols=["month", "provider_code", "treatment_function_code", "rtt_part",
                                                "total_patients", "pct_within_18_weeks"])
    now = history[(history["month"] == history["month"].max()) & (history["treatment_function_code"] == "C_999")
                  & (history["rtt_part"] == "Incomplete Pathways")]
    now = now[now["provider_code"].map(lookup["provider_types"]).isin(LEAGUE_TYPES)]
    return now.rename(columns={"total_patients": "waiting", "pct_within_18_weeks": "pct_18"})


def workforce_picture(lookup, nice):
    trusts = rtt_trusts(lookup)
    sickness = latest(read("workforce/sickness_trust_month.csv", dtype={"org_code": str}))
    both = trusts.merge(sickness, left_on="provider_code", right_on="org_code")
    both = both[both["waiting"] >= 10_000]
    both["sickness_quarter"] = pd.qcut(both["sickness_rate_pct"], 4, labels=["lowest", "second", "third", "highest"])
    quarters = both.groupby("sickness_quarter", observed=True).agg(
        trusts=("provider_code", "count"), sickness_from=("sickness_rate_pct", "min"),
        sickness_to=("sickness_rate_pct", "max"), median_pct_18=("pct_18", "median")).reset_index()
    # Regions: waits added up from trusts (each trust's region from the sickness file), against acute vacancy rates.
    region_of = sickness.set_index("org_code")["region"]
    trusts = trusts.assign(region=trusts["provider_code"].map(region_of),
                           within=trusts["waiting"] * trusts["pct_18"] / 100).dropna(subset=["region"])
    regions = trusts.groupby("region", as_index=False)[["waiting", "within"]].sum()
    regions["pct_18"] = (regions["within"] / regions["waiting"] * 100).round(1)
    vacancy = read("workforce/vacancy_region_quarter.csv")
    vacancy = vacancy[(vacancy["sector"] == "Acute") & (vacancy["quarter_end"] == vacancy["quarter_end"].max())]
    regions = regions.merge(vacancy[["region", "vacancy_rate_pct", "quarter_end"]], on="region", how="left")
    return {"note": "A picture, not a cause: staffing and waits move together for many reasons (size, case mix, "
                    "deprivation, estate). Vacancy rates aren't published by trust.",
            "sickness_month": sickness["month"].iloc[0], "rtt_month": trusts["month"].iloc[0],
            "trusts": len(both),
            "correlation_sickness_vs_pct_18": round(float(np.corrcoef(both["sickness_rate_pct"], both["pct_18"])[0, 1]), 2),
            "by_sickness_quarter": [{"quarter": str(q.sickness_quarter), "trusts": int(q.trusts),
                                     "sickness_range": f"{q.sickness_from:.1f}-{q.sickness_to:.1f}%",
                                     "median_pct_within_18_weeks": r1(q.median_pct_18)} for q in quarters.itertuples()],
            "vacancy_quarter": vacancy["quarter_end"].max(),
            "regions": [{"region": r.region, "acute_vacancy_rate_pct": r1(r.vacancy_rate_pct), "pct_within_18_weeks": r1(r.pct_18),
                         "waiting": int(r.waiting)} for r in regions.sort_values("vacancy_rate_pct").itertuples()]}


# ---------------------------------------------------------------------------
# 1b. Research (section 11)
# ---------------------------------------------------------------------------

RESEARCH_NOTE = ("A picture, not a cause: where studies run depends on hospital size, university links, "
                 "specialist services and how sites are registered. Counts are studies with at least one site "
                 "there; one study can count in many places.")


def research_data():
    studies = read("trials/studies.csv", dtype=str)
    sites = read("trials/sites.csv", dtype=str)
    return studies, sites


def research_findings(lookup, nice, f):
    studies, sites = research_data()
    recruiting = studies[studies["status"] == "recruiting"]
    live_sites = sites[sites["study_id"].isin(recruiting["study_id"])]

    # 11a. Per 100,000 people, by local authority (England).
    population = read("population/local_authority.csv")
    population = population[population["geography"].isin(["Unitary Authority", "Non-metropolitan District",
                                                         "Metropolitan District", "London Borough"])]
    per_la = live_sites[live_sites["nation"] == "England"].groupby("local_authority")["study_id"].nunique()
    la = population.assign(studies=population["area_name"].map(per_la).fillna(0).astype(int))
    la = la[la["population"] >= 50_000]
    la["per_100k"] = (la["studies"] / la["population"] * 100_000).round(1)
    la = la.sort_values("per_100k", ascending=False)
    area = lambda t: [{"area": r.area_name, "recruiting_studies": int(r.studies), "population": int(r.population),
                       "per_100k": r1(r.per_100k)} for r in t.itertuples()]

    # 11b. Trusts by recruiting studies (acute and specialist).
    by_trust = live_sites.dropna(subset=["provider_code"]).groupby("provider_code")["study_id"].nunique()
    all_by_trust = sites.dropna(subset=["provider_code"]).groupby("provider_code")["study_id"].nunique()
    league = [{"code": c, "name": nice(lookup["providers"].get(c, c)), "recruiting_studies": int(n),
               "all_studies": int(all_by_trust.get(c, 0))}
              for c, n in by_trust.sort_values(ascending=False).items()
              if lookup["provider_types"].get(c) in LEAGUE_TYPES]

    # 11c and 11d. Departments.
    tf_rows = []
    waits = {t["code"]: t for t in f["2_treatments"]}
    exploded = studies.assign(tf=studies["treatment_functions"].str.split("; ")).explode("tf").dropna(subset=["tf"])
    for code, group in exploded.groupby("tf"):
        live = group[group["status"] == "recruiting"]
        wait = waits.get(code, {})
        kind = group["industry_or_academic"].value_counts()
        tf_rows.append({"code": code, "name": wait.get("name") or treatment_short(lookup, code),
                        "recruiting_studies": len(live), "all_studies": len(group),
                        "waiting_now": wait.get("waiting_now"), "median_wait_weeks": wait.get("median_now"),
                        # RTT covers little mental health care (X03 is a few thousand people), so no rate there.
                        "recruiting_per_10k_waiting": r1(len(live) / wait["waiting_now"] * 10_000)
                        if wait.get("waiting_now") and code != "X03" else None,
                        "industry_pct": r1(kind.get("industry", 0) / kind.sum() * 100) if kind.sum() else None,
                        "industry_pct_recruiting": r1((live["industry_or_academic"] == "industry").mean() * 100)
                        if len(live) else None})
    departments = sorted([t for t in tf_rows if t["median_wait_weeks"] is not None],
                         key=lambda t: -t["median_wait_weeks"])

    # 11e. Recruiting studies against % within 18 weeks, acute trusts.
    rtt = rtt_trusts(lookup)
    rtt = rtt[rtt["provider_code"].map(lookup["provider_types"]) == "acute"]
    rtt = rtt.assign(studies=rtt["provider_code"].map(by_trust).fillna(0))
    rtt = rtt[rtt["waiting"] >= 10_000]
    rtt["quarter"] = pd.qcut(rtt["studies"].rank(method="first"), 4, labels=["fewest", "second", "third", "most"])
    quarters = rtt.groupby("quarter", observed=True).agg(trusts=("provider_code", "count"), studies_from=("studies", "min"),
                                                         studies_to=("studies", "max"), median_pct_18=("pct_18", "median"))
    return {
        "note": RESEARCH_NOTE,
        "registries": {"studies": len(studies), "recruiting": len(recruiting),
                       "in_both": int(studies["sources"].str.contains(";").sum())},
        "11a_per_100k": {"local_authorities": len(la), "highest": area(la.head(10)), "lowest": area(la.tail(10)[::-1]),
                         "england_per_100k": r1(live_sites[live_sites["nation"] == "England"]["study_id"].nunique()
                                                / population["population"].sum() * 100_000)},
        "11b_trusts": {"top": league[:15], "trusts_with_recruiting_studies": len(league),
                       "nihr_participants": "NIHR doesn't openly publish recruitment by trust"},
        "11c_departments": departments,
        "11d_industry_share": sorted(tf_rows, key=lambda t: -(t["industry_pct"] or 0)),
        "11e_scatter": {"trusts": len(rtt), "rtt_month": rtt["month"].iloc[0],
                        "correlation": round(float(np.corrcoef(rtt["studies"], rtt["pct_18"])[0, 1]), 2),
                        "points": [{"code": r.provider_code, "name": nice(lookup["providers"].get(r.provider_code, "")),
                                    "recruiting_studies": int(r.studies), "pct_within_18_weeks": r1(r.pct_18)}
                                   for r in rtt.itertuples()],
                        "by_quarter": [{"quarter": str(q), "trusts": int(r.trusts),
                                        "studies": f"{int(r.studies_from)}-{int(r.studies_to)}",
                                        "median_pct_within_18_weeks": r1(r.median_pct_18)}
                                       for q, r in quarters.iterrows()],
                        "instead_of": "NIHR research activity (not openly published by trust)"},
    }


def treatment_short(lookup, code):
    return lookup["treatment_functions"].get(code, code).replace(" Service", "")


def research_markdown(r):
    a, b, e = r["11a_per_100k"], r["11b_trusts"], r["11e_scatter"]
    out = ["## 11. UK clinical research", "", r["note"], "",
           f"{r['registries']['studies']:,} UK studies from ClinicalTrials.gov and ISRCTN "
           f"({r['registries']['in_both']:,} in both), {r['registries']['recruiting']:,} recruiting now. "
           "Source: ClinicalTrials.gov (processed weekly; UK sites only, contact details removed); "
           "contains information from the ISRCTN registry, licensed CC BY.", "",
           "### 11a. Recruiting studies per 100,000 people, by council area", "",
           f"England: {a['england_per_100k']} per 100,000. Council areas of 50,000+ people; a study counts in "
           "every area where it has a site.", "",
           _table(["Most", "Studies", "Per 100k", "Fewest", "Studies", "Per 100k"],
                  [[h["area"], h["recruiting_studies"], h["per_100k"], l["area"], l["recruiting_studies"], l["per_100k"]]
                   for h, l in zip(a["highest"], a["lowest"])]), "",
           "### 11b. Trusts by recruiting studies", "",
           f"Acute and specialist trusts, studies recruiting now with a site matched to the trust. "
           f"Ranking by participants isn't possible: {b['nihr_participants']}.", "",
           _table(["Trust", "Recruiting studies", "All studies (any status)"],
                  [[t["name"], t["recruiting_studies"], t["all_studies"]] for t in b["top"]]), "",
           "### 11c. Departments: longest waits and recruiting studies", "",
           "Typical wait (England, people still waiting) against UK studies recruiting now whose conditions map to "
           "the department (kitchen/trial_condition_rules.json - a sensible guess, not a fact). No rate for mental "
           "health: waiting-time figures cover very little mental health care.", "",
           _table(["Department", "Typical wait (wks)", "Waiting", "Recruiting studies", "Per 10,000 waiting"],
                  [[t["name"], t["median_wait_weeks"], f"{t['waiting_now']:,}", t["recruiting_studies"],
                    t["recruiting_per_10k_waiting"] if t["recruiting_per_10k_waiting"] is not None else "-"]
                   for t in r["11c_departments"]]), "",
           "### 11d. Industry and academic studies, by department", "",
           _table(["Department", "All studies", "% industry", "Recruiting", "% industry (recruiting)"],
                  [[t["name"], t["all_studies"], t["industry_pct"], t["recruiting_studies"], t["industry_pct_recruiting"]]
                   for t in r["11d_industry_share"]]), "",
           "### 11e. Research and waits, acute trusts: a picture", "",
           f"{e['trusts']} acute trusts with 10,000+ waiting: recruiting studies against % within 18 weeks "
           f"({month_label(e['rtt_month'])}). Used in place of {e['instead_of']}. Correlation: {e['correlation']}.", "",
           _table(["Studies quarter", "Trusts", "Recruiting studies", "Median % within 18 weeks"],
                  [[q["quarter"], q["trusts"], q["studies"], q["median_pct_within_18_weeks"]] for q in e["by_quarter"]]), ""]
    return "\n".join(out)


def findings(lookup, nice, short_icb):
    return {"10a_published": published(), "10b_asi": asi_rates(nice), "10c_cancer": cancer_standards(nice),
            "10d_gp_access": gp_access(short_icb), "10e_ae": ae_worst(nice),
            "10f_workforce_picture": workforce_picture(lookup, nice)}


# ---------------------------------------------------------------------------
# The readable version of the new sections
# ---------------------------------------------------------------------------

def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def to_markdown(w):
    out = ["## 10. What's new this month (new sources)", "",
           "### 10a. Latest periods", "",
           _table(["Source", "Status", "Latest period"],
                  [[p["source"] + (" (sensitive)" if p["sensitive"] else ""), p["status"], p["last_period"] or "-"]
                   for p in w["10a_published"]]), ""]
    a = w["10b_asi"]
    out += ["### 10b. Where GPs most often can't book a first appointment", "",
            f"Appointment slot issues (ASIs) per 100 bookings through the e-Referral Service, {month_label(a['month'])}. "
            f"England: {a['england_per_100_bookings']}. Providers with 1,000+ bookings; {a['left_out_flagged']} flagged "
            "providers left out. The rate is per booking, so it can be over 100.", "",
            _table(["Provider", "ASIs", "Bookings", "ASIs per 100 bookings"],
                   [[t["name"], f"{t['asis']:,}", f"{t['bookings']:,}", t["asi_per_100_bookings"]] for t in a["highest"]]), ""]
    c = w["10c_cancer"]
    out += ["### 10c. Cancer waiting times (sensitive: gentle copy required)", "",
            f"{month_label(c['month'])}. These are people waiting to find out if they have cancer, or to start treatment. "
            "Write about them with care: \"furthest from the standard\", not \"worst\".", ""]
    for s in c["standards"]:
        out += [f"**{s['standard']}** - {s['meaning']}. Standard {s['target_pct']}%. England {s['england_pct']}%. "
                f"{s['trusts_meeting']} of {s['trusts_listed']} trusts listed meet it.", "",
                _table(["Closest to or above", "%", "Furthest from", "%"],
                       [[h["name"], h["pct_within"], l["name"], l["pct_within"]]
                        for h, l in zip(s["closest_to_or_above"], s["furthest_from"])]), ""]
    g = w["10d_gp_access"]
    out += ["### 10d. GP access by area", "",
            f"{month_label(g['month'])}: {g['measure']}. Booking-to-appointment time isn't the whole wait - it starts when "
            f"the appointment is booked. {g['practices_left_out_flagged']} practices flagged \"check before using\" are left out.", "",
            _table(["Best ICBs", "% >28 days", "% same day", "Worst ICBs", "% >28 days", "% same day"],
                   [[b["name"], b["pct_over_28_days"], b["pct_same_day"], x["name"], x["pct_over_28_days"], x["pct_same_day"]]
                    for b, x in zip(g["icb_best"], g["icb_worst"])]), "",
            _table(["Best local authorities", "% >28 days", "Worst local authorities", "% >28 days"],
                   [[b["name"], b["pct_over_28_days"], x["name"], x["pct_over_28_days"]]
                    for b, x in zip(g["la_best"], g["la_worst"])]), ""]
    e = w["10e_ae"]
    out += ["### 10e. A&E", "",
            f"{month_label(e['month'])}. England: {e['england_pct_within_4_hours']}% within 4 hours "
            f"(major A&Es: {e['england_type1_pct']}%). Trusts with 3,000+ major A&E attendances.", "",
            _table(["Furthest from four hours (major A&E)", "% within 4 hours", "Attendances", "12+ hrs from decision to admit"],
                   [[t["name"], t["type1_pct_within_4_hours"], f"{t['type1_attendances']:,}", f"{t['dta_over_12_hours']:,}"]
                    for t in e["furthest_from_four_hours"]]), ""]
    f = w["10f_workforce_picture"]
    out += ["### 10f. Staffing and waits: a picture", "", f["note"], "",
            f"{f['trusts']} acute and specialist trusts with 10,000+ waiting: sickness absence ({month_label(f['sickness_month'])}) "
            f"against % within 18 weeks ({month_label(f['rtt_month'])}). Correlation: {f['correlation_sickness_vs_pct_18']}.", "",
            _table(["Sickness quarter", "Trusts", "Sickness absence", "Median % within 18 weeks"],
                   [[q["quarter"], q["trusts"], q["sickness_range"], q["median_pct_within_18_weeks"]] for q in f["by_sickness_quarter"]]), "",
            f"Regions: acute vacancy rate ({f['vacancy_quarter']}) against % within 18 weeks at their acute and specialist trusts.", "",
            _table(["Region", "Acute vacancy rate %", "% within 18 weeks", "Waiting"],
                   [[r["region"], r["acute_vacancy_rate_pct"], r["pct_within_18_weeks"], f"{r['waiting']:,}"] for r in f["regions"]]), ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 2. questions.md
# ---------------------------------------------------------------------------

def questions(f, w, lookup, nice, short_icb):
    """[(audience, question, source, grain, example answer)], worked out from the latest data."""
    H = HOME
    # Names: the RTT list first, then the new sources (community and mental health trusts aren't all on it).
    other_names = {}
    for path, code, label in (("talking_therapies/provider_month.csv", "provider_code", "provider_name"),
                              ("community/waits.csv", "org_code", "org_name"),
                              ("workforce/sickness_trust_month.csv", "org_code", "org_name")):
        t = read(path, dtype=str, usecols=[code, label]).dropna().drop_duplicates(code)
        other_names.update(dict(zip(t[code], t[label])))
    name = lambda code: nice(lookup["providers"].get(code) or other_names.get(code, code))
    trust = name(H["trust"])
    history = read("rtt/history.csv", dtype={"provider_code": str})
    now_month = history["month"].max()
    rtt_now = history[history["month"] == now_month]
    tf = lambda code: lookup["treatment_functions"].get(code, code)

    def rtt(code, treatment, part="Incomplete Pathways"):
        r = rtt_now[(rtt_now["provider_code"] == code) & (rtt_now["treatment_function_code"] == treatment)
                    & (rtt_now["rtt_part"] == part)]
        return r.iloc[0] if len(r) else None

    out = []
    add = lambda *row: out.append(row)

    # --- Patients -------------------------------------------------------
    t = rtt(H["trust"], "C_110", "Completed Pathways For Admitted Patients")
    add("patient", "How long will I wait for an operation at my hospital?", "RTT (rtt)", "trust x treatment, monthly",
        f"Trauma and orthopaedics at {trust}, {month_label(now_month)}: half of people who had their operation had "
        f"waited {t['median_weeks']:.0f} weeks or less." if t is not None else "n/a")
    ortho = rtt_now[(rtt_now["treatment_function_code"] == "C_110") & (rtt_now["rtt_part"] == "Incomplete Pathways")
                    & rtt_now["provider_code"].map(lookup["provider_types"]).isin(LEAGUE_TYPES)
                    & (rtt_now["total_patients"] >= 1000)]
    best = ortho.sort_values("pct_within_18_weeks", ascending=False).iloc[0]
    add("patient", "Which hospital is quickest for my treatment?", "RTT + ODS locations (rtt, ods)",
        "trust x treatment; trust locations", f"For trauma and orthopaedics, {name(best.provider_code)} had the highest share "
        f"seen within 18 weeks among acute and specialist trusts with 1,000+ waiting: {best.pct_within_18_weeks}%. The Lab can compare hospitals near the one you'd go to.")
    dm01 = latest(read("dm01/dm01.csv", dtype={"provider_code": str}))
    mri = dm01[(dm01["provider_code"] == H["trust"]) & (dm01["test"] == "MRI")]
    scan = (f"MRI at {trust}, {month_label(mri.iloc[0]['month'])}: {mri.iloc[0]['pct_6_weeks_plus']:.0f}% of "
            f"{int(mri.iloc[0]['total_waiting']):,} people waiting had waited 6 weeks or more (the standard is 1%)."
            if len(mri) else "See the Lab's scans view (DM01, 15 tests by trust).")
    add("patient", "How long will I wait for a scan or test?", "Diagnostic waiting times (dm01)", "trust x test, monthly", scan)
    fds = read("cancer/provider_standards.csv", dtype={"provider_code": str})
    fds = latest(fds)
    fds = fds[(fds["provider_code"] == H["trust"]) & (fds["standard"] == "FDS")]
    add("patient", "If I'm referred urgently with suspected cancer, how soon will I find out?", "Cancer waiting times (cancer) - sensitive",
        "trust x standard, monthly", f"At {trust} in {month_label(fds.iloc[0]['month'])}, {fds.iloc[0]['pct_within']}% of people were "
        "told whether or not they had cancer within 28 days (the standard is 75%)." if len(fds) else "n/a")
    gp_la = next((x for x in w["10d_gp_access"]["la_best"] + w["10d_gp_access"]["la_worst"]
                  if x["name"] == H["local_authority"]), None)
    practices = latest(read("gpad/practice_month.csv", dtype={"practice_code": str}))
    where = read("gp_practices/practices.csv", dtype=str)
    home_practices = practices[practices["practice_code"].isin(where[where["local_authority"] == H["local_authority"]]["practice_code"])]
    known = home_practices[["same_day", "day_1", "days_2_7", "days_8_14", "days_15_21", "days_22_28", "over_28"]].sum().sum()
    add("patient", "How long might I wait for a GP appointment at my practice?", "GP appointments (gpad) + practice list (gp_practices)",
        "practice, monthly", f"In {H['local_authority']} ({len(home_practices)} practices, {month_label(practices['month'].iloc[0])}): "
        f"{home_practices['same_day'].sum() / known * 100:.0f}% of appointments were the same day as booking and "
        f"{home_practices['over_28'].sum() / known * 100:.1f}% more than 28 days later.")
    ae = latest(read("ae/provider_month.csv", dtype={"provider_code": str}))
    a = ae[ae["provider_code"] == H["trust"]]
    add("patient", "How busy is A&E at my hospital?", "A&E (ae)", "trust, monthly",
        f"{trust}, {month_label(a.iloc[0]['month'])}: {a.iloc[0]['pct_within_4_hours']}% seen within 4 hours "
        f"({a.iloc[0]['type1_pct_within_4_hours']}% in the main A&E)." if len(a) else "n/a")
    tt = latest(read("talking_therapies/provider_month.csv", dtype={"provider_code": str}))
    x = tt[tt["provider_code"] == H["community_trust"]]
    add("patient", "How long will I wait for talking therapy for anxiety or depression?", "NHS Talking Therapies (talking_therapies)",
        "provider, monthly", f"{name(H['community_trust'])}, {month_label(x.iloc[0]['month'])}: {x.iloc[0]['pct_within_6_weeks']:.0f}% of "
        "people who finished a course had started within 6 weeks." if len(x) and pd.notna(x.iloc[0]["pct_within_6_weeks"]) else "n/a")
    cw = latest(read("community/waits.csv", dtype={"org_code": str}))
    paeds = cw[(cw["org_code"] == H["community_trust"]) & cw["service"].str.contains("Community paediatric")]
    eng_paeds = cw[(cw["org_type"] == "National") & cw["service"].str.contains("Community paediatric")]
    add("patient", "How long will my child wait for community paediatrics or speech therapy?", "Community health services (community)",
        "provider x service, monthly", f"England, {month_label(cw['month'].iloc[0])}: {int(eng_paeds.iloc[0]['total_waiting']):,} children "
        f"waiting for community paediatrics, {int(eng_paeds.iloc[0]['over_52_weeks']):,} for over a year"
        + (f"; at {name(H['community_trust'])}, {int(paeds.iloc[0]['total_waiting']):,} waiting." if len(paeds) and pd.notna(paeds.iloc[0]['total_waiting']) else "."))
    mh = latest(read("mhsds/provider_month.csv", dtype={"provider_code": str}))
    m = mh[mh["provider_code"] == H["community_trust"]]
    add("patient", "How long do children and young people wait for mental health support?", "Mental health services (mhsds)",
        "provider, monthly (3-month rolling)", f"{name(H['community_trust'])}, 3 months to {month_label(m.iloc[0]['month'])}: half of "
        f"children and young people had a first contact within {m.iloc[0]['cyp_median_days_to_first']:.0f} days of referral."
        if len(m) and pd.notna(m.iloc[0]["cyp_median_days_to_first"]) else "n/a")
    amb = read("ambulance/response_month.csv")
    lr = latest(amb)
    lr = lr[lr["org_code"] == H["ambulance"]]
    add("patient", "How fast will an ambulance come?", "Ambulance response times (ambulance)", "ambulance trust / region, monthly",
        f"London Ambulance Service, {month_label(lr.iloc[0]['month'])}: category 2 (e.g. stroke, heart attack) mean "
        f"{lr.iloc[0]['cat2_mean_minutes']} minutes against an 18-minute standard." if len(lr) else "n/a")
    dental = latest(read("dental/icb_month.csv"))
    pop = read("population/icb.csv")
    d = dental[dental["icb_code"] == H["icb"]]
    add("patient", "Can I get an NHS dentist near me?", "NHS dental activity (dental) + ONS population (population)",
        "dental contract / ICB, monthly", f"North East London ICB, {month_label(d.iloc[0]['month'])}: {int(d.iloc[0]['adults_seen_24m']):,} "
        f"adults seen by an NHS dentist in the last 24 months, across {int(d.iloc[0]['contracts'])} contracts." if len(d) else "n/a")
    add("patient", "What do other patients think of my hospital, and what did inspectors say?",
        "Friends and Family Test (fft), CQC ratings (cqc)", "trust / site", "See the trust page in the Lab: share rating care "
        "good or very good, and the CQC rating.")

    # --- GPs -----------------------------------------------------------
    asi = latest(read("ers/asi_specialty.csv", dtype={"provider_code": str}))
    s = asi[(asi["provider_code"] == H["trust"]) & (asi["dbs_bookings"] >= 50)].sort_values("asi_rate_pct", ascending=False)
    add("GP", "When I refer, how often will there be no slot to book?", "e-RS appointment slot issues (ers)",
        "provider x specialty, monthly", f"{trust}, {month_label(s.iloc[0]['month'])}: {s.iloc[0]['specialty']} had "
        f"{s.iloc[0]['asi_rate_pct']:.0f} slot issues per 100 bookings, the highest of its specialties with 50+ bookings."
        if len(s) else "n/a")
    add("GP", "Which nearby hospital has the shortest wait for this specialty?", "RTT (rtt) + ODS (ods)", "trust x treatment",
        "Use the Lab's Explore view with 'near' set to your practice postcode.")
    icb = latest(read("gpad/icb_month.csv"))
    i = icb[icb["icb_code"] == H["icb"]]
    add("GP", "How does my practice's booking-to-appointment time compare with my ICB?", "GP appointments (gpad)",
        "practice and ICB, monthly", f"North East London ICB, {month_label(i.iloc[0]['month'])}: {i.iloc[0]['pct_same_day']}% same day, "
        f"{i.iloc[0]['pct_within_14_days']}% within 14 days, {i.iloc[0]['pct_over_28_days']}% over 28 days." if len(i) else "n/a")
    add("GP", "What's my practice's did-not-attend rate?", "GP appointments (gpad)", "practice, monthly",
        f"North East London ICB, {month_label(i.iloc[0]['month'])}: {i.iloc[0]['pct_dna']}% of appointments with a known outcome were missed."
        if len(i) else "n/a")
    c62 = next(s for s in w["10c_cancer"]["standards"] if s["standard"] == "62D")
    add("GP", "Which trusts are meeting the cancer standards?", "Cancer waiting times (cancer) - sensitive", "trust x standard, monthly",
        f"{month_label(w['10c_cancer']['month'])}: {c62['trusts_meeting']} of {c62['trusts_listed']} trusts met the 62-day standard "
        f"of {c62['target_pct']}%; England {c62['england_pct']}%.")
    second = read("talking_therapies/second_appointment_latest.csv", dtype={"provider_code": str})
    sec = second[second["provider_code"] == H["community_trust"]]
    add("GP", "Do patients wait again between their first and second talking therapy session?", "NHS Talking Therapies (talking_therapies)",
        "provider, latest month", f"{name(H['community_trust'])}: {sec.iloc[0]['pct_second_over_90_days']:.0f}% waited over 90 days for a "
        "second appointment." if len(sec) and pd.notna(sec.iloc[0]["pct_second_over_90_days"]) else
        "Latest month only, by provider (many small providers are suppressed).")
    msk = cw[(cw["org_code"] == H["community_trust"]) & cw["service"].str.contains("Musculoskeletal")]
    add("GP", "How long are waits for community services like MSK or podiatry?", "Community health services (community)",
        "provider x service, monthly", f"{name(H['community_trust'])}, {month_label(cw['month'].iloc[0])}: "
        f"{int(msk.iloc[0]['total_waiting']):,} waiting for adult MSK, {msk.iloc[0]['pct_over_18_weeks']:.0f}% over 18 weeks."
        if len(msk) and pd.notna(msk.iloc[0]["pct_over_18_weeks"]) else "n/a")
    add("GP", "How long are adult community mental health waits?", "Mental health services (mhsds)", "provider, 3-month rolling",
        f"{name(H['community_trust'])}: half of adults with serious mental illness had a second contact within "
        f"{m.iloc[0]['adult_median_days_to_second']:.0f} days." if len(m) and pd.notna(m.iloc[0]["adult_median_days_to_second"]) else "n/a")

    # --- NHS insiders ---------------------------------------------------
    most = f["1_trusts_most_improved"][0]
    add("NHS insider", "Which trusts improved most on 18 weeks this year?", "RTT (rtt)", "trust, monthly",
        f"{most['name']}: {most['pct_18_then']}% to {most['pct_18_now']}% within 18 weeks ({most['change_points']:+.1f} points).")
    top_long = f["4_over_52_trusts"][0]
    add("NHS insider", "Where are the year-long waits?", "RTT (rtt)", "trust x treatment, monthly",
        f"{top_long['name']} has {top_long['over_52_now']:,} people waiting over a year, {top_long['share_of_england']}% of England's.")
    wl = read("wlmds/national_weekly.csv")
    add("NHS insider", "What has the waiting list done since the last official month?", "WLMDS weekly (wlmds)",
        "England by week; provider monthly snapshot", f"Week ending {wl.iloc[-1]['week_ending']}: {int(wl.iloc[-1]['total_waiting']):,} "
        f"pathways from {int(wl.iloc[-1]['providers_submitting'])} providers ({wl.iloc[-1]['pct_within_18']}% within 18 weeks). "
        "Management information; RTT stays the official count.")
    hi = w["10b_asi"]["highest"][0]
    add("NHS insider", "Where is the front door blocked - referrals with no slot to book?", "e-RS (ers)", "provider x specialty, monthly",
        f"{hi['name']}: {hi['asi_per_100_bookings']} slot issues per 100 bookings in {month_label(w['10b_asi']['month'])} "
        f"(England {w['10b_asi']['england_per_100_bookings']}).")
    winter = read("uec_sitreps/trust_winter.csv", dtype={"provider_code": str})
    last = winter[winter["winter"] == winter["winter"].max()]
    add("NHS insider", "How full were hospitals last winter, and how long did ambulance handovers take?", "UEC daily sitreps (uec_sitreps)",
        "trust x day, winter", f"Winter {last['winter'].iloc[0]}: general and acute beds {last['beds_occupied'].sum() / last['beds_open'].sum() * 100:.1f}% "
        f"occupied; {last['handovers_over_30'].sum() / last['handovers_known'].sum() * 100:.0f}% of handovers took over 30 minutes.")
    wp = w["10f_workforce_picture"]
    add("NHS insider", "Do trusts with more sickness absence have longer waits?", "Sickness absence (workforce) + RTT (rtt)",
        "trust, monthly", f"Across {wp['trusts']} large acute trusts, correlation {wp['correlation_sickness_vs_pct_18']} - a picture, not a cause.")
    lon = next((r for r in wp["regions"] if r["region"] == H["region"]), None)
    add("NHS insider", "What are vacancy rates in my region?", "NHS vacancy statistics (workforce)", "region x sector, quarterly",
        f"{H['region']}, acute trusts, {wp['vacancy_quarter']}: {lon['acute_vacancy_rate_pct']}% of posts vacant." if lon else "n/a")
    total_flags = sum(len(flags(s)) for s in ("ers", "wlmds", "cancer", "gpad", "talking_therapies", "mhsds", "community", "ae"))
    add("NHS insider", "Which figures should I check before using?", "every source's check_before_using.json", "provider / practice",
        f"{len(f['check_before_using'])} RTT providers and {total_flags:,} flags across the new sources moved 15+ points in a month "
        "(50+ for ASI rates) or are listed by NHS England with data issues.")

    # --- Journalists -----------------------------------------------------
    e = f["england"]
    add("journalist", "How many people are waiting, and is it going down?", "RTT (rtt)", "England, monthly",
        f"{e['waiting_now']:,} in {month_label(f['month'])}, down from {e['waiting_then']:,} a year earlier; "
        f"{e['pct_18_now']}% within 18 weeks (the aim is 92%).")
    lot = f["7_postcode_lottery"][0]
    add("journalist", "Where's the biggest postcode lottery for an operation?", "RTT (rtt)", "trust x treatment, 3 months",
        f"{lot['name']}: typical operation wait {lot['fastest_weeks']} weeks at {lot['fastest']} vs {lot['slowest_weeks']} at {lot['slowest']}.")
    worst_gp = w["10d_gp_access"]["icb_worst"][0]
    add("journalist", "Where is it hardest to get a GP appointment soon?", "GP appointments (gpad)", "practice / ICB / local authority, monthly",
        f"{worst_gp['name']}: {worst_gp['pct_over_28_days']}% of appointments more than 28 days after booking ({month_label(w['10d_gp_access']['month'])}).")
    aw = w["10e_ae"]["furthest_from_four_hours"][0]
    add("journalist", "Which A&Es are furthest from the four-hour standard?", "A&E (ae)", "trust, monthly",
        f"{aw['name']}: {aw['type1_pct_within_4_hours']}% of major A&E patients seen within 4 hours in {month_label(w['10e_ae']['month'])} "
        f"(England {w['10e_ae']['england_type1_pct']}%).")
    priv = next((t for t in f["8_private_share"] if t["code"] == "C_999"), f["8_private_share"][0])
    add("journalist", "How much NHS surgery is done in private hospitals?", "RTT (rtt)", "provider, 3 months",
        f"{priv['private_pct_now']}% of completed operations, across all treatments, were at independent providers "
        f"({priv['change_points']:+.1f} points on a year ago).")
    nations = read("uk_nations/headline.csv")
    wales = latest(nations[nations["nation"] == "Wales"], "period")
    add("journalist", "How do Scotland, Wales and Northern Ireland compare?", "Devolved headline waits (uk_nations)", "nation",
        f"They don't compare directly (different standards and counting). Wales, {month_label(wales.iloc[0]['period'])}: "
        f"{int(wales.iloc[0]['waiting']):,} pathways waiting, {wales.iloc[0]['pct_within_standard']}% within 26 weeks.")
    dental_all = latest(read("dental/icb_month.csv"))
    add("journalist", "How many adults are seeing an NHS dentist?", "NHS dental activity (dental)", "contract / ICB, monthly",
        f"{int(dental_all['adults_seen_24m'].sum()):,} adults seen in the 24 months to {month_label(dental_all['month'].iloc[0])}.")
    # Deprivation against area waits: Fingertips' ICBs are the pre-2026 ones, so only ICBs that didn't merge match by name.
    fp = read("fingertips/icb.csv")
    fp["icb"] = fp["area_name"].str.replace(r"\s*-\s*Q\w\w\s*$", "", regex=True).str.upper()
    areas = read("rtt/area_history.csv")
    areas = areas[(areas["month"] == areas["month"].max()) & (areas["treatment_function_code"] == "C_999")]
    both = fp.merge(areas, on="icb")
    corr = np.corrcoef(both["deprivation_score_imd2025"], both["pct_within_18_weeks"])[0, 1]
    add("journalist", "Are waits longer in more deprived areas?", "Fingertips (fingertips) + RTT areas (rtt)", "ICB",
        f"Across the {len(both)} ICBs whose boundaries didn't change in 2026, the correlation between deprivation (IMD 2025) "
        f"and % within 18 weeks is {corr:.2f} - a picture, not a cause.")
    eng = latest(amb[amb["level"] == "England"])
    add("journalist", "Are ambulances meeting their targets?", "Ambulance response times (ambulance)", "ambulance trust / region, monthly",
        f"England, {month_label(eng.iloc[0]['month'])}: category 2 mean {eng.iloc[0]['cat2_mean_minutes']} minutes (standard 18, interim aim 30).")
    add("journalist", "How many children wait over a year for community services?", "Community health services (community)",
        "provider x service, monthly", f"Community paediatrics alone: {int(eng_paeds.iloc[0]['over_52_weeks']):,} waiting over 52 weeks "
        f"in {month_label(cw['month'].iloc[0])}.")
    # --- Research -------------------------------------------------------
    if "11_research" in f:
        r = f["11_research"]
        studies, sites = research_data()
        live = studies[studies["status"] == "recruiting"]
        home_live = sites[(sites["provider_code"] == H["trust"]) & sites["study_id"].isin(live["study_id"])]
        add("research", "Which studies are recruiting at my hospital?", "Trials (trials: ClinicalTrials.gov + ISRCTN)",
            "study x site", f"{trust}: {home_live['study_id'].nunique():,} UK studies recruiting with a site matched to the "
            "trust. Each links to its registry page and a Be Part of Research search.")
        ortho = next((t for t in r["11c_departments"] if t["code"] == "C_110"), None)
        add("research", "Are there trials for my condition - say, a knee or hip problem?", "Trials (trials)",
            "study, mapped to treatment functions", f"{ortho['recruiting_studies']:,} UK studies recruiting now map to trauma and "
            "orthopaedics (by their conditions)." if ortho else "n/a")
        add("research", "Which trusts run the most research?", "Trials (trials)", "trust",
            f"{r['11b_trusts']['top'][0]['name']}: {r['11b_trusts']['top'][0]['recruiting_studies']:,} studies recruiting now. "
            "By participants: not available (NIHR doesn't openly publish it by trust).")
        top = r["11a_per_100k"]["highest"][0]
        add("research", "Where in England is research most within reach?", "Trials (trials) + ONS population (population)",
            "local authority", f"{top['area']}: {top['per_100k']} recruiting studies per 100,000 people "
            f"(England {r['11a_per_100k']['england_per_100k']}). A study counts everywhere it has a site.")
        longest = r["11c_departments"][0]
        add("research", "Do departments with long waits have much research?", "Trials (trials) + RTT (rtt)",
            "treatment function", f"{longest['name']} has the longest typical wait ({longest['median_wait_weeks']} weeks) and "
            f"{longest['recruiting_studies']:,} recruiting studies ({longest['recruiting_per_10k_waiting']} per 10,000 waiting).")
        ind = r["11d_industry_share"][0]
        add("research", "Is research in a department mostly industry or academic?", "Trials (trials)",
            "treatment function", f"{ind['name']}: {ind['industry_pct']}% of UK studies are industry-sponsored.")
        add("research", "Do hospitals that do more research have shorter waits?", "Trials (trials) + RTT (rtt)",
            "acute trust", f"Across {r['11e_scatter']['trusts']} large acute trusts, correlation {r['11e_scatter']['correlation']} "
            "between recruiting studies and % within 18 weeks - a picture, not a cause.")
        add("research", "Is a study on both registries?", "Trials (trials)", "study",
            f"{r['registries']['in_both']:,} of {r['registries']['studies']:,} UK studies are on both ClinicalTrials.gov "
            "and ISRCTN (linked by ISRCTN, IRAS or NCT number).")
    return out


def questions_md(f, w, lookup, nice, short_icb):
    rows = questions(f, w, lookup, nice, short_icb)
    out = ["# What the Wait Watcher kitchen can answer", "",
           f"Built by kitchen/make_findings.py from the data to {month_label(f['month'])}. Each question says which source "
           "answers it (the name in kitchen/registry.json), the grain (what one row describes) and an example answer "
           f"from the latest data. Patient examples use {HOME['place']} as the example place.", "",
           "Cancer answers are sensitive: write them gently. Figures from Scotland, Wales and Northern Ireland are not "
           "comparable with England's.", ""]
    for audience, title in (("patient", "Patients"), ("GP", "GPs"), ("NHS insider", "NHS insiders"),
                            ("journalist", "Journalists"), ("research", "Research")):
        out += [f"## {title}", ""]
        for _, question, source, grain, answer in [r for r in rows if r[0] == audience]:
            out += [f"### {question}", f"- Source: {source}", f"- Grain: {grain}", f"- Example: {answer}", ""]
    return "\n".join(out), rows
