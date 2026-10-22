"""
kitchen/sources/rtt.py - referral to treatment (RTT) waiting times.

What this script does, in plain English:
  FETCH  Opens NHS England's RTT pages (one per financial year, from April
         2024 to now), finds every "Full CSV data file" link and downloads
         any month we don't already have into data/raw/rtt/, then unzips it.
  CLEAN  Reads every monthly CSV, one at a time, and keeps three kinds of
         rows: people still waiting ("Incomplete Pathways") and people who
         finished waiting, with or without a hospital admission. Adds up the
         rows two ways:
           - by provider: month + provider + treatment function + part
           - by area: people still waiting, month + ICB (the integrated
             care board that commissions care, i.e. where patients live) +
             treatment function
         and works out, from the weekly counts, the typical wait (median),
         the 80th and 92nd percentile waits, % within 18 weeks and the
         number waiting over 52 weeks.
         ICBs have merged over time (42 in 2025, 36 in 2026). So areas
         compare like with like, every row is put under the ICB its local
         commissioner belongs to in the latest month. The mapping is saved
         as icb_mapping.json.
  WRITE  data/processed/rtt/:
           history.csv              every provider group, every month
           area_history.csv         every ICB + treatment, every month
           icb_mapping.json         old commissioners and ICBs -> today's ICB
           by_treatment/<code>.json one file per treatment, for the website
           summary.json             the latest month only
           england_basis.csv        England each month: all rows, the NONC part, and NHS
                                    England's commissioner basis (for the reconciliation gate)
           lookup.json              code -> name (provider types are added
                                    by ods.py and kept when this re-runs)
         and copies the website's files to site/data/.
  REPORT A coverage summary and a sanity check for one trust.

Run it with:   python kitchen/sources/rtt.py
"""

import json
import re
import shutil
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (SITE_DATA_DIR, coverage_summary, download, page_links,  # noqa: E402
                    processed_dir, raw_dir, update_registry)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

FIRST_FINANCIAL_YEAR = 2024
PAGE_URL = ("https://www.england.nhs.uk/statistics/statistical-work-areas/"
            "rtt-waiting-times/rtt-data-{start}-{end:02d}/")
LINK_TEXT = "Full CSV data file"
MONTH_NUMBERS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                 "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

RAW = raw_dir("rtt")
OUT = processed_dir("rtt")
BY_TREATMENT = OUT / "by_treatment"

WAITING = "Incomplete Pathways"
PARTS_TO_KEEP = [WAITING, "Completed Pathways For Admitted Patients",
                 "Completed Pathways For Non-Admitted Patients"]
PROVIDER_KEYS = ["Period", "Provider Org Code", "Treatment Function Code", "RTT Part Description"]

CHECK_PROVIDER = "RJ2"        # Lewisham and Greenwich
CHECK_TREATMENT = "C_110"     # Trauma and orthopaedics


# ---------------------------------------------------------------------------
# FETCH
# ---------------------------------------------------------------------------

def financial_year_start(today):
    """NHS financial years run April to March: Oct 2026 is in 2026-27."""
    return today.year if today.month >= 4 else today.year - 1


def find_months():
    """{month: url} for every "Full CSV data file" link, newest first."""
    found = {}
    for year in range(financial_year_start(date.today()), FIRST_FINANCIAL_YEAR - 1, -1):
        url = PAGE_URL.format(start=year, end=(year + 1) % 100)
        for text, href in page_links(url, allow_missing=True):
            if LINK_TEXT not in text:
                continue
            # Link text looks like "Full CSV data file Aug26 (ZIP, 3M)".
            match = re.search(r"([A-Z][a-z]{2})(\d{2})\b", text)
            if match and match.group(1) in MONTH_NUMBERS:
                month = f"{2000 + int(match.group(2))}-{MONTH_NUMBERS[match.group(1)]:02d}"
                found.setdefault(month, href)
    return dict(sorted(found.items(), reverse=True))


def fetch():
    print("FETCH")
    months = find_months()
    print(f"  {len(months)} months listed ({min(months)} to {max(months)})")
    for month, url in months.items():
        zip_path = download(url, RAW, name=f"rtt-{month}.zip")
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                extracted = RAW / name
                # A revised zip (newer than what was extracted from it) replaces that month's CSV,
                # including one with a different name ("...-full-extract.csv" -> "...-revised.csv").
                if extracted.exists() and extracted.stat().st_mtime >= zip_path.stat().st_mtime:
                    continue
                label = re.search(r"RTT-\w+-\d{4}", name)
                for old_csv in (RAW.glob(f"*{label.group(0)}-*.csv") if label else []):
                    old_csv.unlink()
                archive.extract(name, RAW)
    return months


# ---------------------------------------------------------------------------
# CLEAN: weekly bands and measures
# ---------------------------------------------------------------------------

def band_upper_weeks(columns):
    """The weekly band columns and the upper week of each one. "Gt 17 To 18
    Weeks SUM 1" (more than 17 and up to 18 weeks) counts as week 18; the
    last band, "Gt 104 Weeks SUM 1", counts as week 105 ("over 104")."""
    bands = {}
    for column in columns:
        closed_band = re.match(r"Gt (\d+) To (\d+) Weeks", column)
        open_band = re.match(r"Gt (\d+) Weeks", column)
        if closed_band:
            bands[column] = int(closed_band.group(2))
        elif open_band:
            bands[column] = int(open_band.group(1)) + 1
    return bands


def period_to_month(period):
    """"RTT-August-2026" -> "2026-08"."""
    return datetime.strptime(period, "RTT-%B-%Y").strftime("%Y-%m")


def week_when_share_reached(cumulative, totals, upper_weeks, percent):
    """For each group, the first week band by which at least `percent`% of
    patients are counted (the band's top week)."""
    reached = cumulative.mul(100).ge(totals.mul(percent), axis=0)
    weeks = reached.idxmax(axis=1).map(upper_weeks)
    return weeks.where(totals > 0)


def measures(bands_table):
    """Total, median, 80th and 92nd percentile waits, % within 18 weeks and
    over 52 weeks for each row of a table of weekly band counts."""
    upper_weeks = band_upper_weeks(bands_table.columns)
    band_columns = list(upper_weeks)
    bands = bands_table[band_columns]
    cumulative = bands.cumsum(axis=1)
    totals = bands.sum(axis=1)
    within_18 = [c for c in band_columns if upper_weeks[c] <= 18]
    over_52 = [c for c in band_columns if upper_weeks[c] > 52]
    out = pd.DataFrame({
        "total_patients": totals,
        "median_weeks": week_when_share_reached(cumulative, totals, upper_weeks, 50),
        "p80_weeks": week_when_share_reached(cumulative, totals, upper_weeks, 80),
        "p92_weeks": week_when_share_reached(cumulative, totals, upper_weeks, 92),
        "pct_within_18_weeks": (bands[within_18].sum(axis=1) / totals * 100).round(1),
        "over_52_weeks": bands[over_52].sum(axis=1),
    })
    for column in ["median_weeks", "p80_weeks", "p92_weeks"]:
        out[column] = out[column].astype("Int64")
    return out


# ---------------------------------------------------------------------------
# CLEAN: ICBs, mapped to today's
# ---------------------------------------------------------------------------

def build_icb_mapping(pairs, newest_month):
    """From (month, local commissioner code, ICB name) seen in the files:
    each local commissioner -> its ICB in the newest month, and each older
    ICB name -> the ICBs its commissioners belong to today."""
    newest = pairs[pairs["month"] == newest_month]
    by_code = dict(newest.drop_duplicates("Commissioner Org Code")[["Commissioner Org Code", "Commissioner Parent Name"]].values)
    old_to_today = {}
    for code, parent in pairs[pairs["month"] != newest_month][["Commissioner Org Code", "Commissioner Parent Name"]].values:
        if code in by_code and parent not in by_code.values():
            old_to_today.setdefault(parent, set()).add(by_code[code])
    return {
        "_about": "Rows are put under the ICB their local commissioner belongs to in the latest month. "
                  "An old ICB that split is listed with every ICB its commissioners now belong to.",
        "latest_month": newest_month,
        "by_commissioner_code": dict(sorted(by_code.items())),
        "old_icb_to_today": {old: sorted(today) for old, today in sorted(old_to_today.items())},
    }


def today_icb(table, mapping):
    """Today's ICB for each row: by local commissioner code, or by the old ICB
    name if it maps to exactly one ICB today, or the name as given (e.g. NHS
    England's specialised commissioning, which isn't an ICB)."""
    by_code = table["Commissioner Org Code"].map(mapping["by_commissioner_code"])
    single = {old: today[0] for old, today in mapping["old_icb_to_today"].items() if len(today) == 1}
    by_name = table["Commissioner Parent Name"].map(single)
    return by_code.fillna(by_name).fillna(table["Commissioner Parent Name"]).fillna("Unknown")


# ---------------------------------------------------------------------------
# CLEAN: read every file
# ---------------------------------------------------------------------------

def read_raw_files():
    csv_paths = sorted(RAW.glob("*RTT*full-extract*.csv"),
                       key=lambda p: datetime.strptime(re.search(r"RTT-(\w+-\d{4})", p.name).group(1), "%B-%Y"))
    if not csv_paths:
        raise SystemExit(f"No RTT CSV files in {RAW}.")
    provider_tables, commissioner_tables, name_tables, months_seen = [], [], [], set()
    for path in csv_paths:
        print(f"  reading {path.name}")
        table = pd.read_csv(path, low_memory=False)
        table = table[table["RTT Part Description"].isin(PARTS_TO_KEEP)].copy()
        for month in table["Period"].map(period_to_month).unique():
            if month in months_seen:
                raise SystemExit(f"{month} appears in more than one file in {RAW}.")
            months_seen.add(month)
        bands = list(band_upper_weeks(table.columns))
        # Blank weekly counts mean zero patients. (Rebuilt in one go, which
        # pandas prefers to changing 105 columns one by one.)
        table = pd.concat([table.drop(columns=bands), table[bands].fillna(0).astype(int)], axis=1)
        provider_tables.append(table.groupby(PROVIDER_KEYS, as_index=False)[bands].sum())
        # People waiting by local commissioner; mapped to today's ICB below.
        waiting = table[table["RTT Part Description"] == WAITING]
        commissioner_tables.append(waiting.groupby(
            ["Period", "Commissioner Org Code", "Commissioner Parent Name", "Treatment Function Code"],
            as_index=False, dropna=False)[bands].sum())
        name_tables.append(table[["Period", "Provider Org Code", "Provider Org Name",
                                  "Treatment Function Code", "Treatment Function Name"]].drop_duplicates())

    commissioners = pd.concat(commissioner_tables, ignore_index=True)
    commissioners["month"] = commissioners["Period"].map(period_to_month)
    write_england_basis(commissioners)
    mapping = build_icb_mapping(commissioners.dropna(subset=["Commissioner Org Code", "Commissioner Parent Name"])
                                [["month", "Commissioner Org Code", "Commissioner Parent Name"]].drop_duplicates(),
                                commissioners["month"].max())
    commissioners["icb"] = today_icb(commissioners, mapping)
    bands = list(band_upper_weeks(commissioners.columns))
    areas = commissioners.groupby(["Period", "icb", "Treatment Function Code"], as_index=False)[bands].sum()
    return (pd.concat(provider_tables, ignore_index=True), areas,
            pd.concat(name_tables, ignore_index=True), mapping)


def write_england_basis(commissioners):
    """England's people waiting and year-long waits each month, two ways (england_basis.csv):
      all       every row in the file - what our trust and department figures add up to
      NONC      patients at English providers not commissioned by an English ICB (code "NONC":
                mostly people from Wales at border hospitals)
      commissioner basis = all minus NONC - NHS England's own England figure ("reported only",
                in the RTT Overview Timeseries). kitchen/reconcile.py checks it to the unit."""
    total = commissioners[commissioners["Treatment Function Code"] == "C_999"]
    upper = band_upper_weeks(total.columns)
    over_52 = [b for b, week in upper.items() if week > 52]
    total = total.assign(waiting=total[list(upper)].sum(axis=1), over_52=total[over_52].sum(axis=1),
                         nonc=total["Commissioner Org Code"].eq("NONC"))
    all_ = total.groupby("month")[["waiting", "over_52"]].sum()
    nonc = total[total["nonc"]].groupby("month")[["waiting", "over_52"]].sum().reindex(all_.index, fill_value=0)
    out = pd.DataFrame({"waiting_all": all_["waiting"], "over_52_all": all_["over_52"],
                        "waiting_nonc": nonc["waiting"], "over_52_nonc": nonc["over_52"]})
    out["waiting_commissioner_basis"] = out["waiting_all"] - out["waiting_nonc"]
    out["over_52_commissioner_basis"] = out["over_52_all"] - out["over_52_nonc"]
    out.astype(int).reset_index().to_csv(OUT / "england_basis.csv", index=False)


def provider_history(grouped):
    out = pd.concat([pd.DataFrame({
        "month": grouped["Period"].map(period_to_month),
        "provider_code": grouped["Provider Org Code"],
        "treatment_function_code": grouped["Treatment Function Code"],
        "rtt_part": grouped["RTT Part Description"],
    }), measures(grouped)], axis=1)
    return out.sort_values(["provider_code", "treatment_function_code", "rtt_part", "month"]).reset_index(drop=True)


def area_history(grouped):
    out = pd.concat([pd.DataFrame({
        "month": grouped["Period"].map(period_to_month),
        "icb": grouped["icb"],
        "treatment_function_code": grouped["Treatment Function Code"],
    }), measures(grouped)], axis=1)
    return out.sort_values(["icb", "treatment_function_code", "month"]).reset_index(drop=True)


def latest_waiting_counts(grouped):
    """{(provider, treatment): weekly counts} for the latest month's waiting
    list, so the website can say how someone's wait compares."""
    bands = list(band_upper_weeks(grouped.columns))
    months = grouped["Period"].map(period_to_month)
    latest = grouped[(months == months.max()) & (grouped["RTT Part Description"] == WAITING)]
    counts = {}
    for row in latest[["Provider Org Code", "Treatment Function Code"] + bands].itertuples(index=False):
        weekly = [int(n) for n in row[2:]]
        while weekly and weekly[-1] == 0:
            weekly.pop()
        counts[(row[0], row[1])] = weekly
    return counts


def build_lookup(names):
    """Code -> name; the newest month's name wins. Provider types (added by
    ods.py) are kept from the last run."""
    latest_first = names.assign(month=names["Period"].map(period_to_month)).sort_values("month", ascending=False)
    providers = latest_first.drop_duplicates("Provider Org Code")
    treatments = latest_first.drop_duplicates("Treatment Function Code")
    lookup = {
        "providers": dict(sorted(zip(providers["Provider Org Code"], providers["Provider Org Name"]))),
        "treatment_functions": dict(sorted(zip(treatments["Treatment Function Code"], treatments["Treatment Function Name"]))),
    }
    old = OUT / "lookup.json"
    if old.exists():
        previous = json.loads(old.read_text())
        if "provider_types" in previous:
            lookup["provider_types"] = {c: t for c, t in previous["provider_types"].items() if c in lookup["providers"]}
    return lookup


# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------

def to_records(table):
    return json.loads(table.to_json(orient="records"))


def write_json(path, data):
    path.write_text(json.dumps(data, separators=(",", ":")))


def write(history, areas, lookup, mapping, waiting_counts):
    history.to_csv(OUT / "history.csv", index=False)
    areas.to_csv(OUT / "area_history.csv", index=False)
    (OUT / "icb_mapping.json").write_text(json.dumps(mapping, indent=1))

    latest_month = history["month"].max()
    BY_TREATMENT.mkdir(exist_ok=True)
    for old_file in BY_TREATMENT.glob("*.json"):
        old_file.unlink()
    for code, rows in history.groupby("treatment_function_code"):
        by_provider = {}
        for record in to_records(rows.drop(columns="treatment_function_code")):
            provider = record.pop("provider_code")
            if record["month"] == latest_month and record["rtt_part"] == WAITING:
                record["waiting_by_week"] = waiting_counts.get((provider, code), [])
            by_provider.setdefault(provider, []).append(record)
        write_json(BY_TREATMENT / f"{code}.json", by_provider)

    providers = {}
    for record in to_records(history[history["month"] == latest_month].drop(columns="month")):
        provider = providers.setdefault(record.pop("provider_code"), {})
        provider.setdefault(record.pop("treatment_function_code"), {})[record.pop("rtt_part")] = record
    write_json(OUT / "summary.json", {"month": latest_month, "providers": providers})
    (OUT / "lookup.json").write_text(json.dumps(lookup, indent=2))

    # The website's copies.
    shutil.copy(OUT / "summary.json", SITE_DATA_DIR / "summary.json")
    shutil.copy(OUT / "lookup.json", SITE_DATA_DIR / "lookup.json")
    site_by_treatment = SITE_DATA_DIR / "by_treatment"
    site_by_treatment.mkdir(exist_ok=True)
    for old_file in site_by_treatment.glob("*.json"):
        old_file.unlink()
    for path in BY_TREATMENT.glob("*.json"):
        shutil.copy(path, site_by_treatment / path.name)


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------

def sanity_check(history, lookup):
    rows = history[(history["provider_code"] == CHECK_PROVIDER) & (history["treatment_function_code"] == CHECK_TREATMENT)
                   & (history["rtt_part"] == WAITING)].tail(3)
    print(f"\nSanity check: {lookup['providers'].get(CHECK_PROVIDER)}, {lookup['treatment_functions'].get(CHECK_TREATMENT)}, still waiting")
    print(rows.drop(columns=["provider_code", "treatment_function_code", "rtt_part"]).to_string(index=False))


def main():
    fetch()
    print("\nCLEAN")
    grouped, area_grouped, names, mapping = read_raw_files()
    history = provider_history(grouped)
    areas = area_history(area_grouped)
    lookup = build_lookup(names)
    missing = sorted(set(history["provider_code"]) - set(lookup["providers"]))
    if missing:
        raise SystemExit(f"Provider codes with no name: {missing[:20]}")
    write(history, areas, lookup, mapping, latest_waiting_counts(grouped))
    update_registry("rtt", latest_month=history["month"].max())

    latest = history["month"].max()
    icbs_now = areas[areas["month"] == latest]["icb"].nunique()
    coverage_summary("rtt (providers)", len(history), history["month"].unique(), history["provider_code"].unique(), notes=[
        f"area history rows:   {len(areas):,} ({icbs_now} ICBs in {latest}, all months under today's ICBs)",
        f"ICB mapping:         {len(mapping['by_commissioner_code'])} local commissioners, "
        f"{len(mapping['old_icb_to_today'])} older ICB names mapped",
        f"unmapped area rows:  {int((~areas['icb'].str.contains('INTEGRATED CARE BOARD')).sum()):,} "
        f"(NHS England specialised commissioning and unknown commissioners)"])
    sanity_check(history, lookup)


if __name__ == "__main__":
    main()
