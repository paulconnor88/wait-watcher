"""
kitchen/sources/ambulance.py - ambulance response times (AmbSYS), by ambulance trust and region.

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    The Ambulance Quality Indicators page has one CSV holding the whole
           monthly series since 2017 (about 1.5 MB), replaced each month with
           a new name ("AmbSYS ... to September 2026"). Downloads the newest
           into data/raw/ambulance/.
  CLEAN    From April 2024, for England, each region and each of the 11
           ambulance trusts, per month:
             Category 1 (life-threatening, e.g. cardiac arrest): incidents,
               mean and 90th centile response time
             Category 2 (emergency, e.g. stroke, heart attack): the same
           Times arrive in seconds; we keep seconds and add minutes.
           "." means not applicable and becomes blank.
  WRITE    data/processed/ambulance/response_month.csv
  REPORT   A coverage summary.

Standards: Category 1 mean 7 minutes, 90th centile 15 minutes. Category 2 mean
18 minutes (interim aim 30 minutes), 90th centile 40 minutes.

Run it with:   python kitchen/sources/ambulance.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, page_links, processed_dir,  # noqa: E402
                    raw_dir, stop_source, update_registry)

SOURCE = "ambulance"
PAGE = "https://www.england.nhs.uk/statistics/statistical-work-areas/ambulance-quality-indicators/"
LICENCE_PAGE = "https://www.england.nhs.uk/terms-and-conditions/"
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

# AmbSYS indicator codes -> our names (definitions: NHS England's AmbSYS indicator list).
INDICATORS = {"A8": "cat1_incidents", "A25": "cat1_mean_seconds", "A26": "cat1_p90_seconds",
              "A10": "cat2_incidents", "A31": "cat2_mean_seconds", "A32": "cat2_p90_seconds"}


def latest_file():
    for text, url in page_links(PAGE):
        if re.match(r"^AmbSYS .* to \w+ \d{4}$", text) and url.endswith(".csv") and "Old" not in text:
            return url
    raise SystemExit("couldn't find the AmbSYS CSV on " + PAGE)


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    path = download(latest_file(), RAW)

    print("CLEAN")
    raw = pd.read_csv(path, dtype=str)
    raw["month"] = raw["Year"] + "-" + raw["Month"].str.zfill(2)
    raw = raw[raw["month"] >= FIRST_MONTH]
    table = raw[["month", "Org Code", "Org Name", "Region"]].rename(
        columns={"Org Code": "org_code", "Org Name": "org_name", "Region": "region"})
    table["level"] = table["org_code"].map(lambda c: "England" if c == "Eng" else
                                           "Region" if re.match(r"Y\d\d$", c) else "Trust")
    for code, name in INDICATORS.items():
        table[name] = pd.to_numeric(raw[code], errors="coerce")        # "." -> blank
    for cat in ("cat1", "cat2"):
        for stat in ("mean", "p90"):
            table[f"{cat}_{stat}_minutes"] = (table[f"{cat}_{stat}_seconds"] / 60).round(1)
    table = table.sort_values(["level", "org_code", "month"])
    table.to_csv(OUT / "response_month.csv", index=False)
    print("  saved data/processed/ambulance/response_month.csv")

    months = sorted(table["month"].unique())
    update_registry(SOURCE, url=PAGE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=months[0], last_period=months[-1],
                    note="Standards: C1 mean 7 min / 90th 15 min; C2 mean 18 min (interim 30) / 90th 40 min. "
                         "Earlier months are revised each month. 90th centiles can't be added up across trusts.")
    trusts = table[table["level"] == "Trust"]
    england = table[(table["level"] == "England") & (table["month"] == months[-1])].iloc[0]
    coverage_summary(SOURCE, len(trusts), months, trusts["org_code"].unique(), notes=[
        f"regions:             {table.loc[table['level'] == 'Region', 'org_code'].nunique()}",
        f"England, {months[-1]}: category 2 mean {england['cat2_mean_minutes']} min, "
        f"category 1 mean {england['cat1_mean_minutes']} min",
        "unmatched codes:     ambulance trusts aren't on the RTT list"])


if __name__ == "__main__":
    main()
