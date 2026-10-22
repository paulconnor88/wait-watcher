"""
kitchen/make_findings.py - the month's headline numbers, ready to write up.

What this script does, in plain English:
  1. Finds the latest month in data/processed/rtt/history.csv (e.g. August
     2026) and the same month a year earlier (August 2025).
  2. Reads just the raw monthly files it needs from data/raw/rtt/: those two
     months, plus the two months before each (for "last 3 months" figures
     about people who had an operation). It keeps the weekly band counts,
     because a typical wait for a whole trust, area or England has to be
     worked out from the counts - it can't be averaged from smaller groups.
  3. Works out nine findings (listed in main() below), comparing now with a
     year ago.
  4. Saves data/processed/findings-<month>.json and a readable
     data/processed/findings-<month>.md, and prints the .md.
  5. Saves a short data/processed/report-facts-<month>.json: England in
     three numbers, the five most and least improved trusts and areas, the
     trust with the most year-long waits, the biggest postcode lottery, and
     whether the 65% and 92% milestones are met.
  6. "What's new this month" from the phase 3 sources (kitchen/whats_new.py):
     biggest appointment slot issue rates, cancer standards most and least
     met (gently), GP access best and worst by area, A&E furthest from four
     hours, and staffing against waits as a picture. Added to the findings
     as section 10, with a few headlines in report facts.
  7. UK clinical research (whats_new.research_findings), as pictures, never
     causal claims: recruiting studies per 100,000 people by council area,
     trusts by recruiting studies, departments' waits against their studies,
     industry and academic shares, and research against waits for acute
     trusts. Section 11.
  8. Writes data/processed/questions.md: every question the kitchen can
     answer, by audience (and a Research section), with its source, grain and
     an example answer from the latest data (it feeds the Lab's home screen).

How the numbers are worked out:
  - "Waiting" means incomplete pathways (people still waiting).
  - England totals are on NHS England's commissioner basis (its "reported only" figure): every row
    except patients whose commissioner is NONC (not an English ICB - mostly people from Wales at
    border hospitals). Trust and department figures use every row. See kitchen/DEFINITIONS.md.
  - "Within 18 weeks" is the share of people waiting 18 weeks or less.
  - "Over 52 weeks" counts people waiting more than 52 weeks.
  - The typical wait is the median, interpolated within the weekly band where
    half of people are reached. The bands are the same as build_history.py
    ("more than 17 and up to 18 weeks" is the band from 17 to 18). Note that
    build_history.py itself rounds up to the band's top week, so its medians
    can be up to a week higher than these.
  - "Typical operation wait" is the median for completed admitted pathways,
    with the last three months' counts added together.
  - Whole-trust and whole-England figures use the "Total" treatment function
    (C_999). NHS trusts are provider codes starting with R; the independent
    sector is every other provider code.
  - The league table, the most/least improved trusts and the turnarounds
    only include acute and specialist trusts (provider types from
    lookup.json, set by kitchen/sources/ods.py) - not community or mental
    health trusts, whose waiting lists are a different kind of service.
  - Areas are the integrated care boards (ICBs) that commission care, i.e.
    where patients live. Several ICBs merged between the two years, so both
    years are put under today's ICBs using data/processed/rtt/icb_mapping.json.
  - "Check before using": a provider is flagged if its % within 18 weeks
    moved more than 15 points from one month to the next in the last year.
    Flagged providers are left out of "most improved" and "fastest" lists,
    and listed at the end so they can be checked. Separately, a trust's
    figure for one treatment is left out of the postcode lottery if its
    typical operation wait is under 5 weeks. (That rule isn't applied to
    whole trusts: a trust doing a lot of quick day-case work can have a
    short typical wait overall without anything being wrong.)

Run it with:   python kitchen/make_findings.py   (after kitchen/sources/rtt.py and ods.py)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "kitchen" / "sources"))
from rtt import band_upper_weeks, today_icb  # noqa: E402  (same weekly bands, same ICB mapping)
sys.path.insert(0, str(PROJECT_DIR / "kitchen"))
import whats_new  # noqa: E402  (section 10 and questions.md)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

RAW_DIR = PROJECT_DIR / "data" / "raw" / "rtt"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
HISTORY_PATH = PROCESSED_DIR / "rtt" / "history.csv"
LOOKUP_PATH = PROCESSED_DIR / "rtt" / "lookup.json"
ICB_MAPPING_PATH = PROCESSED_DIR / "rtt" / "icb_mapping.json"

WAITING = "Incomplete Pathways"
OPERATION = "Completed Pathways For Admitted Patients"
TOTAL = "C_999"                       # the "Total" treatment function
NONC = "NONC"                         # commissioner code: not commissioned by an English ICB

BIG_TRUST = 10_000                    # trusts with at least this many waiting
MIN_OPERATIONS = 150                  # for the postcode lottery
NHS_AIM = 92.0                        # % within 18 weeks the NHS aims for
TOP = 10                              # how many to show at each end
SURGICAL = ["C_100", "C_101", "C_110", "C_120", "C_130", "C_140",
            "C_150", "C_160", "C_170", "C_502"]   # surgical specialties
SURGICAL_SHOWN = 6
LEAGUE_TYPES = {"acute", "specialist"}   # trust types in the league table
LOW_OPERATION_WAIT = 5                # typical operation wait under this: check
BIG_MONTHLY_MOVE = 15                 # % within 18 weeks moving more than this in a month: check
MILESTONES = (65.0, 92.0)             # % within 18 weeks: the interim aim and the standard
FACTS_SHOWN = 5


# ---------------------------------------------------------------------------
# Months and files
# ---------------------------------------------------------------------------

def add_months(month, n):
    """"2026-08" plus -2 -> "2026-06"."""
    year, number = map(int, month.split("-"))
    index = year * 12 + number - 1 + n
    return f"{index // 12}-{index % 12 + 1:02d}"


def month_name(month):
    """"2026-08" -> "August 2026"."""
    return datetime.strptime(month, "%Y-%m").strftime("%B %Y")


def raw_file_for(month):
    """The raw CSV for one month, e.g. "...RTT-August-2026-full-extract.csv"."""
    label = datetime.strptime(month, "%Y-%m").strftime("RTT-%B-%Y")
    matches = sorted(RAW_DIR.glob(f"*{label}*.csv"))
    if not matches:
        raise SystemExit(f"No raw file for {month_name(month)} in {RAW_DIR} - run kitchen/sources/rtt.py.")
    return matches[-1]


# ---------------------------------------------------------------------------
# Reading the raw files: weekly band counts, added up
# ---------------------------------------------------------------------------

def read_month(month, with_areas):
    """Band counts for one month, added up two ways:
         providers: one row per provider + treatment function + part
         areas:     (if with_areas) people waiting, all treatments, one row
                    per local commissioner, with its ICB
    Only the columns we need are read, to keep memory down."""
    path = raw_file_for(month)
    print(f"Reading {path.name}")
    header = pd.read_csv(path, nrows=0).columns
    bands = list(band_upper_weeks(header))
    keys = ["Provider Org Code", "Treatment Function Code", "RTT Part Description",
            "Commissioner Org Code", "Commissioner Parent Name"]
    table = pd.read_csv(path, usecols=keys + bands, low_memory=False)
    table = table[table["RTT Part Description"].isin([WAITING, OPERATION])]
    table[bands] = table[bands].fillna(0).astype(np.int64)

    providers = table.groupby(["Provider Org Code", "Treatment Function Code", "RTT Part Description"])[bands].sum()
    # England on NHS England's commissioner basis: every row except NONC (patients not commissioned by an
    # English ICB). This is the England figure Wait Watcher quotes (kitchen/DEFINITIONS.md).
    england = table[table["Commissioner Org Code"] != NONC].groupby(["Treatment Function Code", "RTT Part Description"])[bands].sum()
    areas = None
    if with_areas:
        rows = table[(table["RTT Part Description"] == WAITING) & (table["Treatment Function Code"] == TOTAL)]
        areas = rows.groupby(["Commissioner Org Code", "Commissioner Parent Name"])[bands].sum()
    return providers, areas, bands, england


# ---------------------------------------------------------------------------
# Measures from band counts
# ---------------------------------------------------------------------------

UPPER = None   # upper week of each band, in order (set in main)


def interpolated_median(counts):
    """The week by which half of people are counted, interpolated within the
    band where that happens. The band "up to week w" runs from w-1 to w; the
    last band ("over 104") is treated as 104 to 105."""
    counts = np.asarray(counts, dtype=float)
    total = counts.sum()
    if total == 0:
        return None
    cumulative = counts.cumsum()
    i = int(np.searchsorted(cumulative, total / 2))       # first band reaching half
    before = cumulative[i - 1] if i > 0 else 0.0
    lower = UPPER[i - 1] if i > 0 else 0
    return lower + (total / 2 - before) / counts[i] * (UPPER[i] - lower)


def measures(counts):
    """Waiting, % within 18 weeks, over 52 weeks and typical wait for one row
    of band counts."""
    counts = np.asarray(counts, dtype=float)
    total = counts.sum()
    if total == 0:
        return None
    return {
        "waiting": int(total),
        "pct_18": counts[UPPER <= 18].sum() / total * 100,
        "over_52": int(counts[UPPER > 52].sum()),
        "pct_over_52": counts[UPPER > 52].sum() / total * 100,
        "median": interpolated_median(counts),
    }


def rows_of(table, part, treatment=None):
    """{provider code (or treatment): band counts} for one part of a table."""
    sub = table.xs(part, level="RTT Part Description")
    if treatment is not None:
        sub = sub.xs(treatment, level="Treatment Function Code")
    return sub


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

KEEP_CAPITALS = {"NHS", "ICB", "UK", "ENT", "II", "III"}
SMALL_WORDS = {"and", "of", "the", "for", "in", "at", "on", "upon", "to", "with", "by"}


def nice(name):
    """"LEWISHAM AND GREENWICH NHS TRUST" -> "Lewisham and Greenwich NHS Trust"."""
    words = []
    for i, word in enumerate(str(name).split()):
        bare = re.sub(r"[^A-Za-z]", "", word)
        if bare in KEEP_CAPITALS:
            words.append(word)
        elif i > 0 and word.lower() in SMALL_WORDS:
            words.append(word.lower())
        else:
            words.append(re.sub(r"(^|[-(])([a-z])", lambda m: m.group(1) + m.group(2).upper(), word.lower()))
    return " ".join(words)


def short_icb(name):
    """"NHS SOUTH EAST LONDON INTEGRATED CARE BOARD" -> "South East London"."""
    return nice(re.sub(r"^NHS |INTEGRATED CARE BOARD$", "", name).strip())


def treatment_name(code, lookup):
    """"Trauma and Orthopaedic Service" -> "Trauma and Orthopaedic";
    "Other - Surgical Services" -> "Other surgical"."""
    if code == TOTAL:
        return "All treatments"
    name = re.sub(r"\s+Services?$", "", lookup["treatment_functions"].get(code, code)).strip()
    other = re.match(r"^Other - (.+)$", name)
    if other:
        return "Other" if other.group(1) == "Other" else f"Other {other.group(1).lower()}"
    return name


# ---------------------------------------------------------------------------
# Rounding for the outputs
# ---------------------------------------------------------------------------

def r1(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 1)


def then_now(then, now):
    """Then and now measures side by side, with the change in points."""
    return {
        "waiting_then": then["waiting"], "waiting_now": now["waiting"],
        "pct_18_then": r1(then["pct_18"]), "pct_18_now": r1(now["pct_18"]),
        "change_points": r1(now["pct_18"] - then["pct_18"]),
        "median_then": r1(then["median"]), "median_now": r1(now["median"]),
        "over_52_then": then["over_52"], "over_52_now": now["over_52"],
        "pct_over_52_then": r1(then["pct_over_52"]), "pct_over_52_now": r1(now["pct_over_52"]),
    }


# ---------------------------------------------------------------------------
# The findings
# ---------------------------------------------------------------------------

def trust_table(now_rows, then_rows, lookup, min_waiting=BIG_TRUST):
    """Acute and specialist trusts with at least `min_waiting` waiting now,
    then and now."""
    types = lookup.get("provider_types", {})
    if not types:
        raise SystemExit("lookup.json has no provider types - run kitchen/sources/ods.py first.")
    out = []
    for code, counts in now_rows.iterrows():
        if types.get(code) not in LEAGUE_TYPES:
            continue
        now = measures(counts.values)
        if not now or now["waiting"] < min_waiting or code not in then_rows.index:
            continue
        then = measures(then_rows.loc[code].values)
        out.append({"code": code, "name": nice(lookup["providers"].get(code, code)), **then_now(then, now)})
    return out


def operation_counts(tables, part=OPERATION):
    """Admitted band counts for several months added together, one row per
    provider + treatment function."""
    added = None
    for table in tables:
        sub = table.xs(part, level="RTT Part Description")
        added = sub if added is None else added.add(sub, fill_value=0)
    return added


def provider_flags(history, latest):
    """{provider code: reason} for providers to check before using: % within
    18 weeks (all treatments, people waiting) moving more than
    BIG_MONTHLY_MOVE points between months in the last year. (The under-5-
    weeks operation wait check is only for single treatments - see the
    postcode lottery.)"""
    flags = {}
    first = add_months(latest, -12)
    rows = history[(history["rtt_part"] == WAITING) & (history["treatment_function_code"] == TOTAL)
                   & (history["month"] >= first) & (history["month"] <= latest)].sort_values(["provider_code", "month"])
    for code, group in rows.groupby("provider_code"):
        moves = group["pct_within_18_weeks"].diff().abs()
        if moves.max() > BIG_MONTHLY_MOVE:
            at = group.loc[moves.idxmax()]
            flags[code] = f"% within 18 weeks moved {moves.max():.0f} points in a month (to {month_name(at['month'])})"
    return flags


def report_facts(f):
    """The short list of facts a monthly report is built around."""
    e = f["england"]
    pick = lambda t: {k: t[k] for k in ("name", "waiting_now", "pct_18_then", "pct_18_now", "change_points") if k in t}
    areas = f["3_areas"]
    lottery = f["7_postcode_lottery"][0] if f["7_postcode_lottery"] else None
    top_long = f["4_over_52_trusts"][0] if f["4_over_52_trusts"] else None
    return {
        "month": f["month"], "compared_with": f["year_ago"],
        "england": {
            "waiting": {"then": e["waiting_then"], "now": e["waiting_now"]},
            "pct_within_18_weeks": {"then": e["pct_18_then"], "now": e["pct_18_now"], "change_points": e["change_points"]},
            "over_52_weeks": {"then": e["over_52_then"], "now": e["over_52_now"]},
        },
        "most_improved_trusts": [pick(t) for t in f["1_trusts_most_improved"][:FACTS_SHOWN]],
        "least_improved_trusts": [pick(t) for t in f["1_trusts_least_improved"][:FACTS_SHOWN]],
        "trust_types_included": sorted(LEAGUE_TYPES),
        "most_improved_areas": [pick(a) for a in areas[:FACTS_SHOWN]],
        "least_improved_areas": [pick(a) for a in areas[-FACTS_SHOWN:][::-1]],
        "most_year_long_waits": top_long and {"name": top_long["name"], "over_52_weeks": top_long["over_52_now"],
                                              "share_of_england_pct": top_long["share_of_england"]},
        "biggest_postcode_lottery": lottery and {k: lottery[k] for k in (
            "name", "gap_weeks", "fastest", "fastest_weeks", "slowest", "slowest_weeks")},
        "milestones": {f"{m:g}_pct_within_18_weeks_met": e["pct_18_now"] >= m for m in MILESTONES},
        "check_before_using": len(f["check_before_using"]),
        "whats_new": whats_new_facts(f.get("10_whats_new")),
    }


def whats_new_facts(w):
    """A few headlines from section 10 for the report."""
    if not w:
        return None
    a, c, g, e = w["10b_asi"], w["10c_cancer"], w["10d_gp_access"], w["10e_ae"]
    return {
        "asi_per_100_bookings_england": a["england_per_100_bookings"],
        "highest_asi_rate": a["highest"][0] if a["highest"] else None,
        "cancer_sensitive": "gentle copy required",
        "cancer": {s["standard"]: {"england_pct": s["england_pct"], "target_pct": s["target_pct"],
                                   "trusts_meeting": s["trusts_meeting"], "trusts_listed": s["trusts_listed"]}
                   for s in c["standards"]},
        "gp_access_best_icb": g["icb_best"][0], "gp_access_worst_icb": g["icb_worst"][0],
        "ae_england_pct_within_4_hours": e["england_pct_within_4_hours"],
        "ae_furthest_from_four_hours": e["furthest_from_four_hours"][0],
    }


def main():
    global UPPER
    history = pd.read_csv(HISTORY_PATH, usecols=["month"])
    latest = history["month"].max()
    year_ago = add_months(latest, -12)
    lookup = json.loads(LOOKUP_PATH.read_text())
    print(f"Comparing {month_name(latest)} with {month_name(year_ago)}\n")

    # The six months we need: the two Augusts (with areas) and the two
    # months before each.
    now_tables, then_tables = [], []
    now_areas = then_areas = england_now_table = england_then_table = None
    for offset in (-2, -1, 0):
        providers, areas, bands, england = read_month(add_months(latest, offset), with_areas=offset == 0)
        now_tables.append(providers)
        if offset == 0:
            now_areas, england_now_table = areas, england
        providers, areas, bands, england = read_month(add_months(year_ago, offset), with_areas=offset == 0)
        then_tables.append(providers)
        if offset == 0:
            then_areas, england_then_table = areas, england
    UPPER = np.array([band_upper_weeks([b])[b] for b in bands])
    now, then = now_tables[-1], then_tables[-1]
    ops_now, ops_then = operation_counts(now_tables), operation_counts(then_tables)
    three_now = f"{month_name(add_months(latest, -2)).split()[0]} to {month_name(latest)}"
    three_then = f"{month_name(add_months(year_ago, -2)).split()[0]} to {month_name(year_ago)}"

    # England totals are on the commissioner basis (NHS England's reported-only figure). Two checks:
    # all rows must match history.csv, and the commissioner basis must match rtt/england_basis.csv,
    # which kitchen/reconcile.py has checked against NHS England's timeseries.
    history_full = pd.read_csv(HISTORY_PATH)
    check = history_full[(history_full["month"] == latest) & (history_full["rtt_part"] == WAITING)
                         & (history_full["treatment_function_code"] == TOTAL)]["total_patients"].sum()
    waiting_total_now = rows_of(now, WAITING, TOTAL)
    all_rows_now = measures(waiting_total_now.sum().values)
    england_now = measures(england_now_table.loc[(TOTAL, WAITING)].values)
    england_then = measures(england_then_table.loc[(TOTAL, WAITING)].values)
    if int(check) != all_rows_now["waiting"]:
        raise SystemExit(f"England total {all_rows_now['waiting']} doesn't match history.csv ({int(check)}).")
    basis = pd.read_csv(PROCESSED_DIR / "rtt" / "england_basis.csv").set_index("month")
    for month, m in ((latest, england_now), (year_ago, england_then)):
        expected = (basis.loc[month, "waiting_commissioner_basis"], basis.loc[month, "over_52_commissioner_basis"])
        if (m["waiting"], m["over_52"]) != expected:
            raise SystemExit(f"England {month} on the commissioner basis ({m['waiting']}, {m['over_52']}) doesn't match "
                             f"rtt/england_basis.csv {expected}.")

    findings = {"month": latest, "year_ago": year_ago,
                "england": then_now(england_then, england_now),
                "england_basis": "commissioner basis: NHS England's reported-only figure (all rows less NONC)",
                "england_all_rows_now": {"waiting": all_rows_now["waiting"], "over_52": all_rows_now["over_52"]}}

    # Check before using: providers whose figures jump about.
    flags = provider_flags(history_full, latest)
    findings["check_before_using"] = [{"code": code, "name": nice(lookup["providers"].get(code, code)), "reason": reason}
                                      for code, reason in sorted(flags.items())]

    # 1. Trusts, most and least improved (acute and specialist; flagged ones
    # left out of "most improved").
    trusts = trust_table(rows_of(now, WAITING, TOTAL), rows_of(then, WAITING, TOTAL), lookup)
    for t in trusts:
        t["check_before_using"] = t["code"] in flags
    trusts.sort(key=lambda t: t["change_points"], reverse=True)
    findings["1_trusts_most_improved"] = [t for t in trusts if not t["check_before_using"]][:TOP]
    findings["1_trusts_least_improved"] = trusts[-TOP:][::-1]

    # 2. Treatments, most and least improved, across England.
    waiting_now_tf = rows_of(now, WAITING).groupby(level="Treatment Function Code").sum()
    waiting_then_tf = rows_of(then, WAITING).groupby(level="Treatment Function Code").sum()
    ops_now_tf = ops_now.groupby(level="Treatment Function Code").sum()
    ops_then_tf = ops_then.groupby(level="Treatment Function Code").sum()
    treatments = []
    for code in waiting_now_tf.index:
        if code == TOTAL or code not in waiting_then_tf.index:
            continue
        row = {"code": code, "name": treatment_name(code, lookup),
               **then_now(measures(waiting_then_tf.loc[code].values), measures(waiting_now_tf.loc[code].values)),
               "operation_median_then": r1(interpolated_median(ops_then_tf.loc[code].values)) if code in ops_then_tf.index else None,
               "operation_median_now": r1(interpolated_median(ops_now_tf.loc[code].values)) if code in ops_now_tf.index else None}
        treatments.append(row)
    treatments.sort(key=lambda t: t["change_points"], reverse=True)
    findings["2_treatments"] = treatments

    # 3. Areas (ICBs). Both years go under today's ICBs, using the same
    # mapping as the area history, so merged ICBs compare like with like.
    mapping = json.loads(ICB_MAPPING_PATH.read_text())
    def by_today_icb(areas_table):
        frame = areas_table.reset_index()
        frame["icb"] = today_icb(frame, mapping)
        return frame.groupby("icb")[[c for c in frame.columns if c.startswith("Gt ")]].sum()
    now_by_icb, then_by_icb = by_today_icb(now_areas), by_today_icb(then_areas)
    known_icbs = set(mapping["by_commissioner_code"].values())
    unmatched = int(then_by_icb[~then_by_icb.index.isin(known_icbs)].values.sum())
    areas = []
    for icb, counts in now_by_icb.iterrows():
        if icb not in known_icbs or icb not in then_by_icb.index:
            continue   # leaves out NHS England's own specialised commissioning
        areas.append({"name": short_icb(icb), **then_now(measures(then_by_icb.loc[icb].values), measures(counts.values))})
    areas.sort(key=lambda a: a["change_points"], reverse=True)
    findings["3_areas"] = areas
    findings["3_areas_note"] = {
        "icbs_then": int(then_areas.index.get_level_values(1).nunique()),
        "icbs_now": int(now_areas.index.get_level_values(1).nunique()),
        "year_ago_people_not_matched": unmatched}

    # 4. Year-long waits: where they are. The England total quoted is the commissioner basis; trust and
    # department shares are worked out on all rows, so they add up to 100%.
    england_over_52 = all_rows_now["over_52"]
    long_trusts = []
    for code, counts in waiting_total_now.iterrows():
        if code.startswith("R"):
            m = measures(counts.values)
            if m and m["over_52"]:
                long_trusts.append({"code": code, "name": nice(lookup["providers"].get(code, code)),
                                    "over_52_now": m["over_52"], "waiting_now": m["waiting"],
                                    "share_of_england": r1(m["over_52"] / england_over_52 * 100)})
    long_trusts.sort(key=lambda t: t["over_52_now"], reverse=True)
    findings["4_over_52_trusts"] = long_trusts[:TOP]
    long_tfs = [{"code": t["code"], "name": t["name"], "over_52_now": t["over_52_now"],
                 "share_of_england": r1(t["over_52_now"] / england_over_52 * 100)} for t in treatments]
    long_tfs.sort(key=lambda t: t["over_52_now"], reverse=True)
    findings["4_over_52_treatments"] = long_tfs[:5]
    findings["4_england_over_52_now"] = england_now["over_52"]

    # 5. League table: NHS trusts with 10,000+ waiting, by % within 18 weeks now.
    league = sorted(trusts, key=lambda t: t["pct_18_now"], reverse=True)
    for rank, t in enumerate(league, 1):
        t["rank_now"] = rank
        t["meets_aim"] = t["pct_18_now"] >= NHS_AIM
    findings["5_league_table"] = league

    # 6. If you were referred today: England's typical operation wait, last
    # three months, for the biggest surgical specialties.
    biggest = sorted((c for c in SURGICAL if c in ops_now_tf.index),
                     key=lambda c: ops_now_tf.loc[c].sum(), reverse=True)[:SURGICAL_SHOWN]
    findings["6_operation_waits"] = [{
        "code": c, "name": treatment_name(c, lookup),
        "operations_now": int(ops_now_tf.loc[c].sum()),
        "median_then": r1(interpolated_median(ops_then_tf.loc[c].values)),
        "median_now": r1(interpolated_median(ops_now_tf.loc[c].values)),
    } for c in biggest]
    for row in findings["6_operation_waits"]:
        row["change_weeks"] = r1(row["median_now"] - row["median_then"])

    # 7. Postcode lottery: fastest and slowest NHS trust for each treatment.
    lottery = []
    for code in ops_now_tf.index:
        if code == TOTAL:
            continue
        trusts_here, skipped = [], []
        for provider, counts in ops_now.xs(code, level="Treatment Function Code").iterrows():
            if provider.startswith("R") and counts.sum() >= MIN_OPERATIONS:
                median = interpolated_median(counts.values)
                if median < LOW_OPERATION_WAIT or provider in flags:
                    skipped.append({"code": provider, "name": nice(lookup["providers"].get(provider, provider)),
                                    "weeks": r1(median)})
                else:
                    trusts_here.append((median, provider, int(counts.sum())))
        findings.setdefault("check_before_using_by_treatment", []).extend(
            {**s_, "treatment": treatment_name(code, lookup),
             "reason": f"typical operation wait {s_['weeks']} weeks" if s_["weeks"] < LOW_OPERATION_WAIT else flags.get(s_["code"])}
            for s_ in skipped)
        if len(trusts_here) < 2:
            continue
        trusts_here.sort()
        (fast, fast_code, fast_n), (slow, slow_code, slow_n) = trusts_here[0], trusts_here[-1]
        lottery.append({"code": code, "name": treatment_name(code, lookup), "trusts_compared": len(trusts_here),
                        "fastest": nice(lookup["providers"].get(fast_code, fast_code)), "fastest_weeks": r1(fast),
                        "slowest": nice(lookup["providers"].get(slow_code, slow_code)), "slowest_weeks": r1(slow),
                        "gap_weeks": r1(slow - fast), "left_out_to_check": len(skipped)})
    lottery.sort(key=lambda t: t["gap_weeks"], reverse=True)
    findings["7_postcode_lottery"] = lottery

    # 8. Private share of operations, now and a year ago.
    def private_share(ops):
        shares = {}
        for code in ops.index.get_level_values("Treatment Function Code").unique():
            per_provider = ops.xs(code, level="Treatment Function Code").sum(axis=1)
            total = per_provider.sum()
            private = per_provider[~per_provider.index.str.startswith("R")].sum()
            shares[code] = (private / total * 100 if total else None, int(total))
        return shares
    share_now, share_then = private_share(ops_now), private_share(ops_then)
    private = [{"code": c, "name": treatment_name(c, lookup), "operations_now": share_now[c][1],
                "private_pct_then": r1(share_then.get(c, (None, 0))[0]), "private_pct_now": r1(share_now[c][0])}
               for c in share_now]
    for row in private:
        row["change_points"] = r1(row["private_pct_now"] - row["private_pct_then"]) if row["private_pct_then"] is not None else None
    private.sort(key=lambda t: (t["code"] != TOTAL, -(t["private_pct_now"] or 0)))
    findings["8_private_share"] = private

    # 9. Turnarounds: bottom quarter a year ago, top half now.
    then_big = []
    for code, counts in rows_of(then, WAITING, TOTAL).iterrows():
        m = measures(counts.values)
        if lookup["provider_types"].get(code) in LEAGUE_TYPES and m and m["waiting"] >= BIG_TRUST:
            then_big.append((m["pct_18"], code))
    then_big.sort()
    bottom_quarter = {code for _, code in then_big[:len(then_big) // 4]}
    top_half = {t["code"] for t in league[:len(league) // 2]}
    findings["9_turnarounds"] = [t for t in league if t["code"] in bottom_quarter and t["code"] in top_half]
    findings["9_note"] = {"trusts_in_league_then": len(then_big), "bottom_quarter_then": len(bottom_quarter),
                          "trusts_in_league_now": len(league), "top_half_now": len(top_half)}

    findings["meta"] = {"three_months_now": three_now, "three_months_then": three_then}

    # 10. What's new this month, from the phase 3 sources.
    findings["10_whats_new"] = whats_new.findings(lookup, nice, short_icb)
    # 11. UK clinical research (kitchen/sources/trials.py), as pictures.
    findings["11_research"] = whats_new.research_findings(lookup, nice, findings)

    # Save and print.
    json_path = PROCESSED_DIR / f"findings-{latest}.json"
    md_path = PROCESSED_DIR / f"findings-{latest}.md"
    json_path.write_text(json.dumps(findings, indent=1, default=str))
    markdown = (to_markdown(findings) + "\n" + whats_new.to_markdown(findings["10_whats_new"]) + "\n"
                + whats_new.research_markdown(findings["11_research"]))
    md_path.write_text(markdown)
    facts_path = PROCESSED_DIR / f"report-facts-{latest}.json"
    facts_path.write_text(json.dumps(report_facts(findings), indent=1, default=str))
    questions, question_rows = whats_new.questions_md(findings, findings["10_whats_new"], lookup, nice, short_icb)
    questions_path = PROCESSED_DIR / "questions.md"
    questions_path.write_text(questions)
    (PROCESSED_DIR / "questions.json").write_text(json.dumps(   # the same, for the Lab's home screen
        [dict(zip(("audience", "question", "source", "grain", "example"), row)) for row in question_rows], indent=1))
    print(f"\nSaved {json_path.relative_to(PROJECT_DIR)}, {md_path.relative_to(PROJECT_DIR)}, "
          f"{facts_path.relative_to(PROJECT_DIR)} and {questions_path.relative_to(PROJECT_DIR)}\n")
    print(markdown)


# ---------------------------------------------------------------------------
# The readable version
# ---------------------------------------------------------------------------

def n(x):
    return "-" if x is None else f"{x:,}"


def p(x, signed=False):
    if x is None:
        return "-"
    return f"{x:+.1f}" if signed else f"{x:.1f}"


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def to_markdown(f):
    now, then = month_name(f["month"]), month_name(f["year_ago"])
    e = f["england"]
    meta = f["meta"]
    out = [f"# Wait Watcher findings - {now}",
           "",
           f"Comparing {now} with {then}. Source: NHS England referral to treatment (RTT) statistics.",
           "Within 18 weeks = share of people still waiting who have waited 18 weeks or less. "
           "Typical wait = interpolated median. Points = percentage points.",
           "",
           "## England",
           "",
           "NHS England's reported-only figure (commissioner basis: every patient commissioned by an English ICB). "
           f"All rows of the file, including {n(f['england_all_rows_now']['waiting'] - e['waiting_now'])} patients not "
           f"commissioned by an English ICB, come to {n(f['england_all_rows_now']['waiting'])}.",
           "",
           f"- Waiting: {n(e['waiting_then'])} then, {n(e['waiting_now'])} now.",
           f"- Within 18 weeks: {p(e['pct_18_then'])}% then, {p(e['pct_18_now'])}% now ({p(e['change_points'], True)} points). The NHS aims for 92%.",
           f"- Typical wait: {p(e['median_then'])} weeks then, {p(e['median_now'])} weeks now.",
           f"- Over 52 weeks: {n(e['over_52_then'])} then, {n(e['over_52_now'])} now.",
           ""]

    trust_headers = ["Trust", "Waiting now", "% <18w then", "% <18w now", "Change (pts)", "Typical wait then (wks)", "Typical wait now (wks)"]
    trust_row = lambda t: [t["name"], n(t["waiting_now"]), p(t["pct_18_then"]), p(t["pct_18_now"]),
                           p(t["change_points"], True), p(t["median_then"]), p(t["median_now"])]
    out += ["## 1. Trusts: most and least improved", "",
            f"Acute and specialist NHS trusts with {BIG_TRUST:,}+ people waiting now. Change in % within 18 weeks over 12 months. "
            "Trusts flagged \"check before using\" are left out of the most improved list.", "",
            "**Most improved**", "", table(trust_headers, [trust_row(t) for t in f["1_trusts_most_improved"]]), "",
            "**Least improved**", "", table(trust_headers, [trust_row(t) for t in f["1_trusts_least_improved"]]), ""]

    out += ["## 2. Treatments: most and least improved", "",
            f"England, by treatment function, ranked by change in % within 18 weeks. "
            f"Typical operation wait = admitted median, {meta['three_months_then']} vs {meta['three_months_now']}.", "",
            table(["Treatment", "Waiting now", "% <18w then", "% <18w now", "Change (pts)", "Typical wait then", "Typical wait now",
                   "Op wait then", "Op wait now"],
                  [[t["name"], n(t["waiting_now"]), p(t["pct_18_then"]), p(t["pct_18_now"]), p(t["change_points"], True),
                    p(t["median_then"]), p(t["median_now"]), p(t["operation_median_then"]), p(t["operation_median_now"])]
                   for t in f["2_treatments"]]), ""]

    note = f["3_areas_note"]
    out += ["## 3. Areas (ICBs, where patients live): most and least improved", "",
            f"People waiting, by the ICB that commissions their care. There were {note['icbs_then']} ICBs a year ago and "
            f"{note['icbs_now']} now; year-ago figures are grouped under today's ICBs so mergers compare like with like "
            f"({n(note['year_ago_people_not_matched'])} people a year ago couldn't be matched). "
            "NHS England's own specialised commissioning is left out.", "",
            table(["Area", "Waiting now", "% <18w then", "% <18w now", "Change (pts)", "Typical wait then", "Typical wait now",
                   "% >52w then", "% >52w now"],
                  [[a["name"], n(a["waiting_now"]), p(a["pct_18_then"]), p(a["pct_18_now"]), p(a["change_points"], True),
                    p(a["median_then"]), p(a["median_now"]), p(a["pct_over_52_then"]), p(a["pct_over_52_now"])]
                   for a in f["3_areas"]]), ""]

    out += ["## 4. Year-long waits: where they are", "",
            f"England: {n(f['4_england_over_52_now'])} people waiting over 52 weeks in {now}.", "",
            "**Trusts with the most**", "",
            table(["Trust", "Over 52 weeks", "Share of England", "Waiting now"],
                  [[t["name"], n(t["over_52_now"]), p(t["share_of_england"]) + "%", n(t["waiting_now"])] for t in f["4_over_52_trusts"]]), "",
            "**Treatments with the most**", "",
            table(["Treatment", "Over 52 weeks", "Share of England"],
                  [[t["name"], n(t["over_52_now"]), p(t["share_of_england"]) + "%"] for t in f["4_over_52_treatments"]]), ""]

    met = sum(1 for t in f["5_league_table"] if t["meets_aim"])
    out += ["## 5. League table", "",
            f"All {len(f['5_league_table'])} acute and specialist NHS trusts with {BIG_TRUST:,}+ waiting, by % within 18 weeks now. "
            f"✓ = at or above the 92% aim ({met} trusts).", "",
            table(["#", "Trust", "Waiting now", "% <18w now", "Change (pts)", "92%+"],
                  [[t["rank_now"], t["name"] + (" (check before using)" if t.get("check_before_using") else ""),
                    n(t["waiting_now"]), p(t["pct_18_now"]), p(t["change_points"], True),
                    "✓" if t["meets_aim"] else ""] for t in f["5_league_table"]]), ""]

    out += ["## 6. If you were referred today", "",
            f"England's typical operation wait (admitted median) for the {SURGICAL_SHOWN} surgical specialties with the most operations, "
            f"{meta['three_months_now']} vs {meta['three_months_then']}.", "",
            table(["Treatment", "Operations (3 months)", "Typical wait then (wks)", "Typical wait now (wks)", "Change (wks)"],
                  [[t["name"], n(t["operations_now"]), p(t["median_then"]), p(t["median_now"]), p(t["change_weeks"], True)]
                   for t in f["6_operation_waits"]]), ""]

    out += ["## 7. Postcode lottery", "",
            f"Gap between the fastest and slowest NHS trust's typical operation wait, {meta['three_months_now']}, "
            f"trusts with {MIN_OPERATIONS}+ operations. Trusts with a typical operation wait under {LOW_OPERATION_WAIT} weeks, "
            "or flagged \"check before using\", are left out of fastest and slowest.", "",
            table(["Treatment", "Gap (wks)", "Fastest", "Wks", "Slowest", "Wks", "Trusts compared"],
                  [[t["name"], p(t["gap_weeks"]), t["fastest"], p(t["fastest_weeks"]), t["slowest"], p(t["slowest_weeks"]),
                    t["trusts_compared"]] for t in f["7_postcode_lottery"]]), ""]

    out += ["## 8. Private share of operations", "",
            f"Share of completed admitted pathways at independent-sector providers (codes not starting with R), "
            f"{meta['three_months_then']} vs {meta['three_months_now']}.", "",
            table(["Treatment", "Operations now (3 months)", "% private then", "% private now", "Change (pts)"],
                  [[t["name"], n(t["operations_now"]), p(t["private_pct_then"]), p(t["private_pct_now"]), p(t["change_points"], True)]
                   for t in f["8_private_share"]]), ""]

    nine = f["9_note"]
    out += ["## 9. Turnarounds", "",
            f"In the bottom quarter of the league table a year ago ({nine['bottom_quarter_then']} of {nine['trusts_in_league_then']} trusts) "
            f"and in the top half now ({nine['top_half_now']} of {nine['trusts_in_league_now']}).", ""]
    out += [table(["Trust", "% <18w then", "% <18w now", "Change (pts)", "Rank now"],
                  [[t["name"], p(t["pct_18_then"]), p(t["pct_18_now"]), p(t["change_points"], True), t["rank_now"]]
                   for t in f["9_turnarounds"]]) if f["9_turnarounds"] else "None this month.", ""]

    out += ["## Check before using", "",
            f"Providers whose % within 18 weeks moved more than {BIG_MONTHLY_MOVE} points in a month in the last year. "
            "Left out of most improved and fastest lists.", ""]
    out += [table(["Provider", "Reason"], [[c["name"], c["reason"]] for c in f["check_before_using"]])
            if f["check_before_using"] else "None this month.", ""]
    by_treatment = f.get("check_before_using_by_treatment", [])
    out += [f"Also left out of the postcode lottery: {len(by_treatment)} trust and treatment pairs with a typical "
            f"operation wait under {LOW_OPERATION_WAIT} weeks, or from a flagged provider "
            f"(listed in the JSON under check_before_using_by_treatment).", ""]
    return "\n".join(out)


if __name__ == "__main__":
    main()
