"""
kitchen/sources/wlmds.py - Waiting List Minimum Data Set (WLMDS): the weekly waiting list.

The monthly RTT statistics (rtt.py) are the official count. WLMDS is NHS
England's weekly management-information count of the same waiting list, built
from patient-level submissions. It's quicker (about 5 weeks behind rather
than 6-7) and weekly, but rougher: not every provider submits every week, it
includes pathways with an unknown start date, and it isn't quality assured.

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    Downloads each monthly "WLMDS Summary" spreadsheet (the current one
           and the archive back to April 2024) into data/raw/wlmds/.
  CLEAN    From the newest file: the national weekly series (every week since
           September 2021) and the latest week by treatment function.
           From every file: its provider table, which is a snapshot of each
           provider's list in the file's last week - so one snapshot a month.
           Columns are matched by their heading text, not position, because
           the layout has shifted (April 2024 had extra columns).
  WRITE    data/processed/wlmds/national_weekly.csv
           data/processed/wlmds/treatment_function_latest.csv
           data/processed/wlmds/provider_snapshots.csv
           data/processed/wlmds/check_before_using.json  (18-week share moving
                                                         15+ points between snapshots,
                                                         plus providers NHS England
                                                         lists with data issues)
  REPORT   A coverage summary.

There is no provider-by-treatment-function table in the published summary,
so "provider x treatment for the latest week" isn't available openly.

Run it with:   python kitchen/sources/wlmds.py
"""

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, page_links,  # noqa: E402
                    processed_dir, raw_dir, read_xlsx_rows, stop_source, update_registry)

SOURCE = "wlmds"
PAGE = "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/wlmds/"
ARCHIVE = PAGE + "wlmds-summary-archive/"
LICENCE_PAGE = "https://www.england.nhs.uk/terms-and-conditions/"
FILE_NAME = re.compile(r"WLMDS-Summary-to-(\d{1,2})-([A-Za-z]+)-(\d{4})[^/]*\.xlsx$")
FIRST_WEEK = "2024-04-01"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

# Heading text -> our column name. Matched case-insensitively.
COLUMNS = {
    "week ending": "week_ending",
    "organisation code": "provider_code", "organisation name": "provider_name", "organisation type": "provider_type",
    "treatment function code": "treatment_function_code", "treatment function name": "treatment_function",
    "number of acute providers submitting": "acute_providers_submitting",
    "total number of providers submitting": "providers_submitting",
    "total waiting list": "total_waiting",
    "up to 18 weeks": "w0_18", "over 18 and up to 26 weeks": "w18_26", "over 26 and up to 40 weeks": "w26_40",
    "over 40 and up to 52 weeks": "w40_52", "over 52 and up to 65 weeks": "w52_65", "over 65 and up to 78 weeks": "w65_78",
    "over 78 and up to 104 weeks": "w78_104", "over 104 weeks": "w104_plus", "unknown clock start date": "unknown_start",
}
OVER_52 = ["w52_65", "w65_78", "w78_104", "w104_plus"]


def excel_day(serial):
    return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()


def file_links():
    """{week ending (YYYY-MM-DD): url} for every summary file listed."""
    found = {}
    for page in (PAGE, ARCHIVE):
        for _, url in page_links(page):
            match = FILE_NAME.search(url)
            if match and "Demographics" not in url:
                day, month, year = match.groups()
                week = pd.to_datetime(f"{day} {month[:3]} {year}").date().isoformat()
                found.setdefault(week, url)
    return found


def block(rows):
    """The first table on a sheet: find the row holding "Total Waiting List",
    take each column's heading from that row (or the row above, for the
    code/name/week columns) and read data rows until the first blank."""
    at = next(i for i, r in enumerate(rows) if "Total Waiting List" in r)
    above = rows[at - 1] + [None] * len(rows[at])
    names = {}
    for col, text in enumerate(rows[at]):
        text = text or above[col]
        if isinstance(text, str) and text.strip().lower() in COLUMNS and COLUMNS[text.strip().lower()] not in names.values():
            names[col] = COLUMNS[text.strip().lower()]
    body = []
    for r in rows[at + 1:]:
        if len(r) < 3 or r[1] in (None, ""):
            break
        body.append({name: (r[col] if col < len(r) else None) for col, name in names.items()})
    table = pd.DataFrame(body)
    for name in table.columns:
        if name.startswith("w") and name != "week_ending" or name in ("total_waiting", "unknown_start",
                                                                       "acute_providers_submitting", "providers_submitting"):
            table[name] = pd.to_numeric(table[name], errors="coerce")
    # Our own percentages, the way NHS England works them out: of pathways with a known start date.
    known = table["total_waiting"] - table["unknown_start"].fillna(0)
    table["pct_within_18"] = (table["w0_18"] / known * 100).round(1)
    table["pct_over_52"] = (table[OVER_52].sum(axis=1) / known * 100).round(2)
    return table


def data_issue_providers(rows):
    """Providers NHS England lists under "did not submit ... or data quality issues"."""
    at = next((i for i, r in enumerate(rows) if len(r) > 1 and r[1] == "Organisation Code"), None)
    out = {}
    if at is None:
        return out
    for r in rows[at + 1:]:
        if len(r) < 3 or not r[1]:
            break
        out[r[1]] = next((x for x in r[3:] if x), "listed")
    return out


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    links = file_links()
    print(f"  {len(links)} monthly summaries listed")
    snapshots = []
    for week, url in sorted(links.items()):
        if week < FIRST_WEEK:
            continue
        path = download(url, RAW, name=f"WLMDS-Summary-to-{week}.xlsx")
        providers = block(read_xlsx_rows(path, "Provider"))
        providers.insert(0, "week_ending", week)
        snapshots.append(providers)
    newest = RAW / f"WLMDS-Summary-to-{max(links)}.xlsx"

    print("CLEAN")
    national_rows = read_xlsx_rows(newest, "National-Time Series")
    national = block(national_rows)
    national["week_ending"] = national["week_ending"].map(excel_day)
    issues = data_issue_providers(national_rows)
    by_treatment = block(read_xlsx_rows(newest, "National-Treatment Function"))
    by_treatment.insert(0, "week_ending", max(links))
    snapshots = pd.concat(snapshots, ignore_index=True)
    snapshots["provider_code"] = snapshots["provider_code"].astype(str).str.strip()

    big = snapshots[snapshots["total_waiting"] >= 500]
    flags = jump_flags(big, "provider_code", "week_ending", "pct_within_18", label="18-week share")
    for code, issue in issues.items():
        flags[code] = f"NHS England lists this provider for the week ending {max(links)}: {issue}"

    national.to_csv(OUT / "national_weekly.csv", index=False)
    by_treatment.to_csv(OUT / "treatment_function_latest.csv", index=False)
    snapshots.to_csv(OUT / "provider_snapshots.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/wlmds/national_weekly.csv, treatment_function_latest.csv, provider_snapshots.csv")

    weeks = sorted(national["week_ending"])
    update_registry(SOURCE, url=PAGE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=weeks[0], last_period=weeks[-1],
                    note="Weekly management information from patient-level submissions. Differs from monthly RTT: "
                         "not quality assured, not every provider submits every week, includes pathways with an unknown "
                         "start, no adjustment for non-submitters (except one estimate for the latest week). Monthly RTT "
                         "stays the official count. Provider figures are one snapshot a month (each file's last week); "
                         "there's no open provider-by-treatment table.")
    latest = national.iloc[-1]
    coverage_summary(SOURCE, len(snapshots), sorted(snapshots["week_ending"].unique()),
                     snapshots["provider_code"].unique(), notes=[
        f"national weeks:      {len(national)} ({weeks[0]} to {weeks[-1]})",
        f"latest week:         {int(latest['total_waiting']):,} waiting from {int(latest['providers_submitting'])} providers "
        f"({latest['pct_within_18']}% within 18 weeks)",
        f"treatment functions: {len(by_treatment)} in the latest week",
        f"check before using:  {len(flags)} providers ({len(issues)} listed by NHS England with data issues)"])


if __name__ == "__main__":
    main()
