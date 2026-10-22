"""
kitchen/sources/dental.py - NHS dental activity, by contract and by ICB (NHSBSA).

Not a waiting list - NHS dentistry doesn't have one - but the closest open
measure of access: how many people an NHS dental contract has seen, and how
much of the work it's paid for it actually delivers.

What this script does, in plain English:
  LICENCE  Prints the licence on NHSBSA's open data portal page for the
           dataset (Open Government Licence).
  FETCH    Asks the portal (CKAN) for the list of monthly files
           "UDA_CONTRACTOR_YYYYMM" and downloads each one from April 2024 into
           data/raw/dental/ (about 1.3 MB each).
  CLEAN    One row per contract per month: commissioner (ICB), postcode, the
           year's target units of dental activity (UDAs), UDAs delivered that
           month, courses of treatment by band (1, 2, 3, urgent), and the
           number of children seen in the last 12 months and adults seen in
           the last 24 months. Column names changed in April 2026
           (BAND_URGENT became BAND_UNSCHEDULED; YEAR_MONTH became "2026-04"),
           so both spellings are accepted. Also adds up to ICB.
  WRITE    data/processed/dental/contract_month.csv
           data/processed/dental/icb_month.csv
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/dental.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, fetch_url, processed_dir,  # noqa: E402
                    raw_dir, stop_source, update_registry)

SOURCE = "dental"
DATASET = "english-contractor-monthly-general-dental-activity"
PAGE = f"https://opendata.nhsbsa.net/dataset/{DATASET}"
API = f"https://opendata.nhsbsa.net/api/3/action/package_show?id={DATASET}"
FIRST_MONTH = "202404"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

COLUMNS = {"YEAR_MONTH": "month", "COMMISSIONER_CODE": "icb_code", "COMMISSIONER_NAME": "icb_name",
           "CONTRACT_NUMBER": "contract_number", "PROVIDER_NAME": "provider_name",
           "LATEST_PPC_ADDRESS_POSTCODE": "postcode", "UDA_PERF_TARGET": "uda_target_year",
           "UDA_DELIVERED": "uda_delivered", "BAND_1_DELIVERED": "band_1", "BAND_2A_DELIVERED": "band_2a",
           "BAND_2B_DELIVERED": "band_2b", "BAND_2C_DELIVERED": "band_2c", "BAND_3_DELIVERED": "band_3",
           "BAND_URGENT_DELIVERED": "band_urgent", "BAND_UNSCHEDULED_DELIVERED": "band_urgent",
           "CHILD_12M_COUNT": "children_seen_12m", "ADULT_24M_COUNT": "adults_seen_24m"}
COUNTS = ["uda_target_year", "uda_delivered", "band_1", "band_2a", "band_2b", "band_2c", "band_3", "band_urgent",
          "children_seen_12m", "adults_seen_24m"]


def monthly_files():
    """{"YYYYMM": url} for every monthly file the portal lists."""
    resources = fetch_url(API).json()["result"]["resources"]
    return {r["name"][-6:]: r["url"] for r in resources if r["name"].startswith("UDA_CONTRACTOR_")}


def main():
    is_open, _ = check_licence(SOURCE, PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on the NHSBSA dataset page", "not open")

    print("FETCH")
    files = {m: u for m, u in monthly_files().items() if m >= FIRST_MONTH}
    print(f"  {len(files)} monthly files from {FIRST_MONTH}")
    months = []
    for month, url in sorted(files.items()):
        path = download(url, RAW, name=f"uda_contractor_{month}.csv")
        try:
            raw = pd.read_csv(path, dtype=str)
        except UnicodeDecodeError:          # some months are saved as Windows (Latin-1) text
            raw = pd.read_csv(path, dtype=str, encoding="latin-1")
        table = raw[[c for c in COLUMNS if c in raw.columns]].rename(columns=COLUMNS)
        table["month"] = f"{month[:4]}-{month[4:]}"
        months.append(table)

    print("CLEAN")
    contracts = pd.concat(months, ignore_index=True)
    for column in COUNTS:
        contracts[column] = pd.to_numeric(contracts[column], errors="coerce")
    contracts = contracts.sort_values(["contract_number", "month"])
    icb = contracts.groupby(["month", "icb_code"], as_index=False).agg(
        icb_name=("icb_name", "last"), contracts=("contract_number", "nunique"),
        **{c: (c, "sum") for c in COUNTS})
    contracts.to_csv(OUT / "contract_month.csv", index=False)
    icb.to_csv(OUT / "icb_month.csv", index=False)
    print("  saved data/processed/dental/contract_month.csv and icb_month.csv")

    month_list = sorted(contracts["month"].unique())
    update_registry(SOURCE, url=PAGE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=month_list[0], last_period=month_list[-1],
                    note="Contract-level activity, not waits: NHS dentistry has no waiting list. 'Seen' counts are "
                         "rolling (children 12 months, adults 24 months). Commissioner codes follow the ICB "
                         "changes of the time.")
    latest = contracts[contracts["month"] == month_list[-1]]
    coverage_summary(SOURCE, len(contracts), month_list, contracts["contract_number"], match=False, notes=[
        f"contracts, latest:   {len(latest):,} across {latest['icb_code'].nunique()} commissioners",
        f"England, {month_list[-1]}: {int(latest['adults_seen_24m'].sum()):,} adults seen in 24 months, "
        f"{int(latest['children_seen_12m'].sum()):,} children seen in 12 months"])


if __name__ == "__main__":
    main()
