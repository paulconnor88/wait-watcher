"""
kitchen/sources/ae.py - A&E attendances and four-hour waits, by trust, monthly.

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    Each financial year has a page listing a small CSV per month
           ("Monthly A&E September 2026 (CSV)"). Downloads every month from
           April 2024 into data/raw/ae/. Months are often revised later; a
           revised month has a new file name, so it's downloaded afresh.
  CLEAN    One row per organisation per month:
             attendances (all A&E types, and type 1 - major A&E - alone)
             seen within four hours (all types, and type 1)
             waits of 4-12 hours and 12+ hours from decision to admit
             emergency admissions via A&E
           The % seen within 4 hours is worked out the way NHS England does:
           1 - (over 4 hours / attendances), booked appointments included.
           The "TOTAL" row is dropped. Columns are picked by name because
           some months carry extra empty columns.
  WRITE    data/processed/ae/provider_month.csv
           data/processed/ae/check_before_using.json  (4-hour % moving 15+
                                                      points in a month)
  REPORT   A coverage summary.

Note: "12 hours from arrival" isn't in these files - only 12 hours from the
decision to admit, which understates long waits.

Run it with:   python kitchen/sources/ae.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, page_links,  # noqa: E402
                    processed_dir, raw_dir, stop_source, update_registry)

SOURCE = "ae"
BASE = "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/"
LICENCE_PAGE = "https://www.england.nhs.uk/terms-and-conditions/"
FIRST_YEAR = 2024
LINK_TEXT = re.compile(r"(?i)^Monthly A&E (\w+) (\d{4})\b.*\bCSV\b")
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

ATTEND = ["A&E attendances Type 1", "A&E attendances Type 2", "A&E attendances Other A&E Department",
          "A&E attendances Booked Appointments Type 1", "A&E attendances Booked Appointments Type 2",
          "A&E attendances Booked Appointments Other Department"]
OVER_4 = ["Attendances over 4hrs Type 1", "Attendances over 4hrs Type 2", "Attendances over 4hrs Other Department",
          "Attendances over 4hrs Booked Appointments Type 1", "Attendances over 4hrs Booked Appointments Type 2",
          "Attendances over 4hrs Booked Appointments Other Department"]
ADMISSIONS = ["Emergency admissions via A&E - Type 1", "Emergency admissions via A&E - Type 2",
              "Emergency admissions via A&E - Other A&E department"]


def year_pages():
    """One page per financial year from FIRST_YEAR to this one."""
    this_year = pd.Timestamp.today()
    last = this_year.year if this_year.month >= 4 else this_year.year - 1
    return [f"{BASE}ae-attendances-and-emergency-admissions-{y}-{(y + 1) % 100:02d}/" for y in range(FIRST_YEAR, last + 1)]


def monthly_files():
    """{"YYYY-MM": url} - the first (newest) CSV listed for each month."""
    found = {}
    for page in year_pages():
        for text, url in page_links(page, allow_missing=True):
            match = LINK_TEXT.search(text)
            if match and url.lower().endswith(".csv"):
                month = pd.to_datetime(f"1 {match.group(1)} {match.group(2)}").strftime("%Y-%m")
                found.setdefault(month, url)
    return found


def read_month(path, month):
    raw = pd.read_csv(path, dtype={"Org Code": str})
    raw.columns = [c.strip() for c in raw.columns]
    raw = raw[~raw["Org Code"].str.strip().str.upper().eq("TOTAL")]
    numbers = raw[ATTEND + OVER_4 + ADMISSIONS + ["Patients who have waited 4-12 hs from DTA to admission",
                                                   "Patients who have waited 12+ hrs from DTA to admission"]] \
        .apply(pd.to_numeric, errors="coerce").fillna(0)
    table = pd.DataFrame({
        "month": month, "provider_code": raw["Org Code"].str.strip(), "provider_name": raw["Org name"].str.strip(),
        "region": raw["Parent Org"].str.strip(),
        "attendances": numbers[ATTEND].sum(axis=1), "over_4_hours": numbers[OVER_4].sum(axis=1),
        "type1_attendances": numbers[ATTEND[0]] + numbers[ATTEND[3]],
        "type1_over_4_hours": numbers[OVER_4[0]] + numbers[OVER_4[3]],
        "dta_4_to_12_hours": numbers["Patients who have waited 4-12 hs from DTA to admission"],
        "dta_over_12_hours": numbers["Patients who have waited 12+ hrs from DTA to admission"],
        "emergency_admissions_via_ae": numbers[ADMISSIONS].sum(axis=1)})
    table["pct_within_4_hours"] = ((1 - table["over_4_hours"] / table["attendances"]) * 100).round(1) \
        .where(table["attendances"] > 0)
    table["type1_pct_within_4_hours"] = ((1 - table["type1_over_4_hours"] / table["type1_attendances"]) * 100) \
        .round(1).where(table["type1_attendances"] > 0)
    return table


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    files = monthly_files()
    print(f"  {len(files)} monthly CSVs from April {FIRST_YEAR}")
    months = [read_month(download(url, RAW), month) for month, url in sorted(files.items())]

    print("CLEAN")
    table = pd.concat(months, ignore_index=True).sort_values(["provider_code", "month"])
    big = table[table["type1_attendances"] >= 1000]
    flags = jump_flags(big, "provider_code", "month", "type1_pct_within_4_hours", label="type 1 four-hour %")
    table.to_csv(OUT / "provider_month.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/ae/provider_month.csv")

    month_list = sorted(files)
    missing = [m for m in pd.period_range(month_list[0], month_list[-1], freq="M").astype(str) if m not in files]
    update_registry(SOURCE, url=BASE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=month_list[0], last_period=month_list[-1],
                    note="Four-hour standard 95%, interim aim 78% by March 2026. 12-hour figures here are from "
                         "decision to admit, not arrival. Months are revised; revised files are re-downloaded.")
    latest = table[table["month"] == month_list[-1]]
    england = (1 - latest["over_4_hours"].sum() / latest["attendances"].sum()) * 100
    type1 = (1 - latest["type1_over_4_hours"].sum() / latest["type1_attendances"].sum()) * 100
    coverage_summary(SOURCE, len(table), month_list, table["provider_code"].unique(), notes=[
        f"with type 1 A&E:     {(latest['type1_attendances'] > 0).sum()} trusts in {month_list[-1]}",
        f"England, {month_list[-1]}: {england:.1f}% within 4 hours (type 1 {type1:.1f}%), "
        f"{int(latest['dta_over_12_hours'].sum()):,} waited 12+ hours from decision to admit",
        f"months missing:      {', '.join(missing) if missing else 'none'}",
        "unmatched codes:     mostly walk-in centres and urgent treatment centres (5-6 character codes)",
        f"check before using:  {len(flags)} trusts"])


if __name__ == "__main__":
    main()
