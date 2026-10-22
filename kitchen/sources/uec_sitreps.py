"""
kitchen/sources/uec_sitreps.py - winter daily situation reports: beds and ambulance handovers, by trust.

Published weekly in winter only (roughly December to March). Outside winter
this script finds nothing new and just re-reads what it has.

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    Each winter has a page ("...daily-situation-reports-2025-26") with a
           time-series spreadsheet for the UEC sitrep and one for ambulance
           handovers (file names end in a random code, so they're found by
           their start). Downloads winters from 2024-25 into data/raw/uec_sitreps/.
  CLEAN    Both sheets are wide: one block of columns per day.
             Beds ("Total G&A beds"): general and acute beds open and
               occupied, and occupancy %, per trust per day.
             Handovers: ambulance handovers, how many took over 30 and over
               60 minutes, as a % of those with a known handover time.
           England total rows are dropped.
  WRITE    data/processed/uec_sitreps/trust_day.csv
           data/processed/uec_sitreps/trust_winter.csv  (each trust's winter average)
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/uec_sitreps.py
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, page_links, processed_dir,  # noqa: E402
                    raw_dir, read_xlsx_rows, stop_source, update_registry, xlsx_sheet_names)

SOURCE = "uec_sitreps"
BASE = "https://www.england.nhs.uk/statistics/statistical-work-areas/uec-sitrep/"
LICENCE_PAGE = "https://www.england.nhs.uk/terms-and-conditions/"
FIRST_WINTER = 2024
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)


def excel_day(serial):
    return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()


def winter_files():
    """{winter "2025-26": (sitrep url, ambulance url)} for every winter published."""
    today = date.today()
    found = {}
    for year in range(FIRST_WINTER, today.year + 1):
        label = f"{year}-{(year + 1) % 100:02d}"
        links = page_links(f"{BASE}urgent-and-emergency-care-daily-situation-reports-{label}/", allow_missing=True)
        sitrep = next((u for _, u in links if re.search(r"Web-File-Timeseries-UEC-Daily-SitRep[^/]*\.xlsx$", u)), None)
        ambulance = next((u for _, u in links if re.search(r"Web-File-Timeseries-Ambulance-Collection[^/]*\.xlsx$", u)), None)
        if sitrep or ambulance:
            found[label] = (sitrep, ambulance)
    return found


def day_blocks(dates_row, start):
    """[(date, first column, last column + 1)] from a row with a date on the first column of each block."""
    columns = [c for c in range(start, len(dates_row)) if isinstance(dates_row[c], (int, float))]
    return [(excel_day(dates_row[c]), c, columns[i + 1] if i + 1 < len(columns) else len(dates_row))
            for i, c in enumerate(columns)]


def read_beds(path):
    rows = read_xlsx_rows(path, "Total G&A beds")
    at = next(i for i, r in enumerate(rows) if len(r) > 4 and r[3] == "Code" and r[4] == "Name")
    header, out = rows[at], []
    for day, first, last in day_blocks(rows[at - 1], 5):
        cols = {header[c]: c for c in range(first, last) if c < len(header) and header[c]}
        open_col = next((c for h, c in cols.items() if h.startswith("Total G&A Beds Open")), None)
        occ_col = next((c for h, c in cols.items() if "occ" in h.lower()), None)
        if open_col is None or occ_col is None:
            continue           # a stray date with no block under it
        for r in rows[at + 1:]:
            if len(r) > 4 and r[3] and r[3] != "-" and occ_col < len(r):
                out.append({"date": day, "provider_code": r[3], "provider_name": r[4],
                            "beds_open": r[open_col], "beds_occupied": r[occ_col]})
    return pd.DataFrame(out)


def read_handovers(path):
    sheet = next(s for s in xlsx_sheet_names(path) if "andovers" in s)   # "Handovers" or "All handovers"
    rows = read_xlsx_rows(path, sheet)
    at = next(i for i, r in enumerate(rows) if r and r[0] == "Region")
    dates_row = next(r for r in rows[:at] if any(isinstance(x, (int, float)) for x in r[3:]))
    header, out = rows[at], []
    for day, first, last in day_blocks(dates_row, 3):
        cols = {}
        for c in range(first, last):       # first mention of each heading is the count, the second the %
            if c < len(header) and header[c] and header[c] not in cols:
                cols[header[c]] = c
        for r in rows[at + 1:]:
            if len(r) > 2 and r[1] and isinstance(r[1], str) and len(r[1]) <= 5:
                get = (lambda h: r[cols[h]] if cols.get(h) is not None and cols[h] < len(r) else None)
                out.append({"date": day, "provider_code": r[1], "handovers": get("All handovers"),
                            "handovers_known": get("Handover time known"),
                            "handovers_over_30": get("Over 30 minutes"), "handovers_over_60": get("Over 60 minutes")})
    return pd.DataFrame(out)


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    winters = winter_files()
    print(f"  winters published: {', '.join(winters) if winters else 'none'}")
    days = []
    for winter, (sitrep, ambulance) in sorted(winters.items()):
        # Some winters reuse the same file name, so each is saved under its winter.
        beds = read_beds(download(sitrep, RAW, name=f"sitrep-{winter}.xlsx")) if sitrep \
            else pd.DataFrame(columns=["date", "provider_code"])
        handovers = read_handovers(download(ambulance, RAW, name=f"ambulance-{winter}.xlsx")) if ambulance \
            else pd.DataFrame(columns=["date", "provider_code"])
        both = beds.merge(handovers, on=["date", "provider_code"], how="outer")
        both.insert(0, "winter", winter)
        days.append(both)

    print("CLEAN")
    table = pd.concat(days, ignore_index=True)
    for column in ("beds_open", "beds_occupied", "handovers", "handovers_known", "handovers_over_30", "handovers_over_60"):
        table[column] = pd.to_numeric(table[column], errors="coerce")
    table["occupancy_pct"] = (table["beds_occupied"] / table["beds_open"] * 100).round(1)
    table["pct_handovers_over_30"] = (table["handovers_over_30"] / table["handovers_known"] * 100).round(1)
    table = table.sort_values(["provider_code", "date"])
    sums = table.groupby(["winter", "provider_code"], as_index=False).agg(
        provider_name=("provider_name", "first"), days=("date", "nunique"),
        beds_open=("beds_open", "sum"), beds_occupied=("beds_occupied", "sum"),
        handovers_known=("handovers_known", "sum"), handovers_over_30=("handovers_over_30", "sum"),
        handovers_over_60=("handovers_over_60", "sum"))
    sums["occupancy_pct"] = (sums["beds_occupied"] / sums["beds_open"] * 100).round(1)
    sums["pct_handovers_over_30"] = (sums["handovers_over_30"] / sums["handovers_known"] * 100).round(1)
    sums["pct_handovers_over_60"] = (sums["handovers_over_60"] / sums["handovers_known"] * 100).round(1)
    table.to_csv(OUT / "trust_day.csv", index=False)
    sums.to_csv(OUT / "trust_winter.csv", index=False)
    print("  saved data/processed/uec_sitreps/trust_day.csv and trust_winter.csv")

    dates = sorted(table["date"].dropna().unique())
    update_registry(SOURCE, url=BASE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=dates[0], last_period=dates[-1],
                    note="Winter only (about December to March), published weekly on Thursdays. Unvalidated "
                         "management information. 2026-27 not yet published (expected early December 2026).")
    last = sums[sums["winter"] == max(winters)]
    occupancy = last["beds_occupied"].sum() / last["beds_open"].sum() * 100
    over_30 = last["handovers_over_30"].sum() / last["handovers_known"].sum() * 100
    coverage_summary(SOURCE, len(table), dates, table["provider_code"].dropna().unique(), notes=[
        f"winters:             {', '.join(sorted(winters))}",
        f"winter {max(winters)}:      bed occupancy {occupancy:.1f}%, {over_30:.1f}% of handovers over 30 minutes"])


if __name__ == "__main__":
    main()
