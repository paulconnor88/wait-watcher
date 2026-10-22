"""
kitchen/sources/community.py - community health services waiting lists, by provider and service.

Waits for things like children's speech and language therapy, community
paediatrics, wheelchairs, podiatry and adult physiotherapy - none of which
are in the hospital RTT figures.

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    Downloads the monthly spreadsheet (about 1.4 MB) for every month
           from April 2024 into data/raw/community/. File names use the
           financial year: "2025-26-January" is January 2026.
  CLEAN    Table 4 is the total waiting list by service; Tables 4a-4h are
           the same broken down by how long people have waited. Sheets are
           matched by their title, not their name, because the bands changed
           (until 2025 the last band was "over 52 weeks"; now it's split into
           52-104 and over 104). For each month, organisation (provider, ICB,
           England) and service: total waiting, waiting over 18 weeks, over
           52 weeks, and the % over 18 weeks. A blank means no submission for
           that service - not zero.
           Table 1 says how many organisations didn't submit that month.
  WRITE    data/processed/community/waits.csv
           data/processed/community/non_submitters.csv  (the gaps, by month)
           data/processed/community/check_before_using.json
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/community.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, page_links, processed_dir,  # noqa: E402
                    raw_dir, read_xlsx_rows, stop_source, update_registry, xlsx_sheet_names)

SOURCE = "community"
PAGE = "https://www.england.nhs.uk/statistics/statistical-work-areas/community-health-services-waiting-lists/"
LICENCE_PAGE = "https://www.england.nhs.uk/terms-and-conditions/"
FILE_NAME = re.compile(r"Community-health-services-waiting-lists-(\d{4})-(\d{2})-([A-Za-z]+)[^/]*\.xlsx$")
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)


def monthly_files():
    """{"YYYY-MM": url}; the year in the name is the financial year."""
    found = {}
    for _, url in page_links(PAGE):
        match = FILE_NAME.search(url)
        if not match:
            continue
        start_year, month_name = int(match.group(1)), match.group(3)
        month = pd.to_datetime(f"1 {month_name[:3]} 2000").month
        year = start_year if month >= 4 else start_year + 1
        found.setdefault(f"{year}-{month:02d}", url)
    return found


def sheet_table(rows):
    """Rows under the "Organisation Type" header, in long form: one row per organisation and service."""
    at = next(i for i, r in enumerate(rows) if r and r[0] == "Organisation Type")
    header = rows[at]
    out = []
    for r in rows[at + 1:]:
        if not r or not r[0]:
            if out and (not r or not any(r)):
                break
            if not r or len(r) < 3 or r[2] != "England":
                continue
        for col in range(3, len(header)):
            value = r[col] if col < len(r) else None
            if isinstance(value, (int, float)):
                out.append({"org_type": r[0] or "National", "org_code": r[1] or "ENGLAND", "org_name": r[2],
                            "service": header[col], "value": value})
    return pd.DataFrame(out)


def band_of(title):
    """Which bucket a breakdown sheet belongs to, from its title."""
    if re.search(r"over 52 weeks|>52-104 weeks|over 104 weeks", title):
        return "over_52"
    if re.search(r">18-52 weeks", title):
        return "w18_52"
    return None


def read_month(path):
    totals, bands = None, []
    for sheet in xlsx_sheet_names(path):
        rows = read_xlsx_rows(path, sheet)
        title = (rows[0][0] if rows and rows[0] else "") or ""
        if title.startswith("Total waiting list by service"):
            totals = sheet_table(rows).rename(columns={"value": "total_waiting"})
        elif title.startswith("Number waiting") and band_of(title):
            bands.append(sheet_table(rows).assign(band=band_of(title)))
    keys = ["org_type", "org_code", "org_name", "service"]
    long = pd.concat(bands).groupby(keys + ["band"], as_index=False)["value"].sum()
    wide = long.pivot_table(index=keys, columns="band", values="value", aggfunc="sum").reset_index()
    table = totals.merge(wide, on=keys, how="left")
    table["over_18_weeks"] = table[["w18_52", "over_52"]].sum(axis=1, min_count=1)
    table = table.rename(columns={"over_52": "over_52_weeks"}).drop(columns="w18_52")
    table["pct_over_18_weeks"] = (table["over_18_weeks"] / table["total_waiting"] * 100).round(1)
    return table


def non_submitters(path):
    """{month label: number of organisations that didn't submit}, England row of Table 1."""
    rows = read_xlsx_rows(path, "Table 1")
    header = next(r for r in rows if r and r[0] == "Organisation Type")
    england = next(r for r in rows if len(r) > 1 and r[1] == "England")
    return {pd.to_datetime(h, format="%b-%y").strftime("%Y-%m"): england[i]
            for i, h in enumerate(header) if i >= 2 and i < len(england) and isinstance(england[i], (int, float))}


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    files = {m: u for m, u in monthly_files().items() if m >= FIRST_MONTH}
    print(f"  {len(files)} monthly files from {FIRST_MONTH}")
    months, gaps = [], {}
    for month, url in sorted(files.items()):
        path = download(url, RAW, name=f"community-{month}.xlsx")
        table = read_month(path)
        table.insert(0, "month", month)
        months.append(table)
        gaps.update(non_submitters(path))

    print("CLEAN")
    waits = pd.concat(months, ignore_index=True).sort_values(["org_code", "service", "month"])
    providers = waits[waits["org_type"] == "Provider"]
    big = providers[providers["total_waiting"] >= 100].assign(key=lambda t: t["org_code"] + " | " + t["service"])
    flags = jump_flags(big, "key", "month", "pct_over_18_weeks", label="share over 18 weeks")
    gaps = pd.DataFrame(sorted(gaps.items()), columns=["month", "organisations_not_submitting"])
    waits.to_csv(OUT / "waits.csv", index=False)
    gaps.to_csv(OUT / "non_submitters.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/community/waits.csv and non_submitters.csv")

    month_list = sorted(files)
    missing = [m for m in pd.period_range(FIRST_MONTH, month_list[-1], freq="M").astype(str) if m not in files]
    update_registry(SOURCE, url=PAGE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=month_list[0], last_period=month_list[-1],
                    note="Unvalidated management information (community health services SitRep). Only counts by "
                         "wait band, no medians. A blank is no submission, not zero. Safeguarding and looked-after "
                         "children lines are national only. Non-submitters each month are in non_submitters.csv.")
    latest = waits[(waits["month"] == month_list[-1]) & (waits["org_type"] == "National")]
    longest = latest.sort_values("over_52_weeks", ascending=False).iloc[0]
    coverage_summary(SOURCE, len(providers), month_list, providers["org_code"].unique(), notes=[
        f"all rows:            {len(waits):,} (providers, ICBs, regions, England)",
        f"services:            {waits['service'].nunique()}",
        f"England, {month_list[-1]}: {int(latest['total_waiting'].sum()):,} waiting; most over a year: "
        f"{longest['service']} ({int(longest['over_52_weeks']):,})",
        f"months missing:      {', '.join(missing) if missing else 'none'}",
        f"non-submitters:      {int(gaps['organisations_not_submitting'].max())} at most in a month",
        f"check before using:  {len(flags)} provider-service lines"])


if __name__ == "__main__":
    main()
