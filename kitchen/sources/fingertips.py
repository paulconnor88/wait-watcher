"""
kitchen/sources/fingertips.py - area context from OHID's Fingertips: deprivation, older people, healthy life expectancy.

Not about waits - it's the backdrop. An area with more older people and
more deprivation will have more need, so waits there are best read
alongside these.

What this script does, in plain English:
  LICENCE  Prints the Fingertips site's licence statement (Open Government Licence).
  FETCH    One call to the Fingertips API per geography, for four indicators,
           saved as CSVs in data/raw/fingertips/ (re-fetched each month, as
           a whole, because it's small - 2-4 MB):
             94240  deprivation score (IMD 2025)
             92310  % of the population aged 65 and over
             90362  healthy life expectancy at birth (men and women separately)
             93505  healthy life expectancy at 65 (men and women separately)
           Geographies: ICBs (area type 221) and upper-tier local authorities (502).
  CLEAN    Keeps the main value for each area (no deprivation-decile
           breakdowns), the latest period for each indicator, and turns it
           into one row per area. For ICBs, the ODS code (e.g. QYG) is taken
           from the end of the area name so it joins to our ICB data.
  WRITE    data/processed/fingertips/icb.csv
           data/processed/fingertips/local_authority.csv
  REPORT   A coverage summary.

Note: Fingertips' ICB areas are the 42 ICBs that existed before the 2026
mergers, so some don't match today's 36. Fingertips is being replaced by
"Find public health data"; if the API moves, this script will fail loudly.

Run it with:   python kitchen/sources/fingertips.py
"""

import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, fetch_url, processed_dir, raw_dir,  # noqa: E402
                    stop_source, update_registry)

SOURCE = "fingertips"
SITE = "https://fingertips.phe.org.uk/"
API = SITE + "api/all_data/csv/by_indicator_id?indicator_ids={ids}&child_area_type_id={area}&parent_area_type_id=15"
INDICATORS = {94240: "deprivation_score_imd2025", 92310: "pct_aged_65_plus",
              90362: "healthy_life_expectancy_birth", 93505: "healthy_life_expectancy_65"}
GEOGRAPHIES = {"icb": 221, "local_authority": 502}
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)


def fetch(area_type):
    """The API's CSV for our indicators, saved under today's date (so it's fetched once a day at most)."""
    path = RAW / f"fingertips-{area_type}-{date.today():%Y-%m-%d}.csv"
    if not path.exists():
        print(f"  downloading {path.name}")
        url = API.format(ids=",".join(map(str, INDICATORS)), area=area_type)
        response = fetch_url(url, timeout=120)
        response.raise_for_status()
        path.write_bytes(response.content)
    return pd.read_csv(path, dtype={"Area Code": str})


def tidy(raw, area_type):
    """One row per area: the latest value of each indicator (men and women kept apart where given)."""
    raw = raw[(raw["Area Type"] != "England") & raw["Category Type"].isna()]
    latest = raw["Time period Sortable"] == raw.groupby("Indicator ID")["Time period Sortable"].transform("max")
    raw = raw[latest].copy()
    raw["column"] = raw["Indicator ID"].map(INDICATORS) + raw["Sex"].map(
        lambda s: "" if s == "Persons" else "_" + s.lower())
    wide = raw.pivot_table(index=["Area Code", "Area Name"], columns="column", values="Value", aggfunc="first")
    wide = wide.round(1).reset_index().rename(columns={"Area Code": "area_code", "Area Name": "area_name"})
    periods = raw.drop_duplicates("Indicator ID").set_index("Indicator ID")["Time period"]
    if area_type == GEOGRAPHIES["icb"]:
        wide.insert(1, "icb_code", wide["area_name"].str.extract(r"- (Q\w\w)\s*$")[0])
    return wide, {INDICATORS[i]: p for i, p in periods.items()}


def main():
    is_open, _ = check_licence(SOURCE, SITE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on the Fingertips site", "not open")

    print("FETCH")
    tables, periods = {}, {}
    for name, area_type in GEOGRAPHIES.items():
        tables[name], periods = tidy(fetch(area_type), area_type)

    print("CLEAN")
    for name, table in tables.items():
        table.to_csv(OUT / f"{name}.csv", index=False)
    print("  saved data/processed/fingertips/icb.csv and local_authority.csv")

    update_registry(SOURCE, url=SITE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=min(periods.values()), last_period=max(periods.values()),
                    note="Latest period per indicator: " + "; ".join(f"{k} {v}" for k, v in periods.items()) +
                         ". ICB geography is the pre-2026 42 ICBs.")
    icb, la = tables["icb"], tables["local_authority"]
    coverage_summary(SOURCE, len(icb) + len(la), sorted(set(periods.values())),
                     list(icb["area_code"]) + list(la["area_code"]), match=False, notes=[
        f"ICBs:                {len(icb)} ({icb['icb_code'].notna().sum()} with an ODS code)",
        f"local authorities:   {len(la)}",
        f"indicators:          {', '.join(f'{k} ({v})' for k, v in periods.items())}"])


if __name__ == "__main__":
    main()
