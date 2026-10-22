"""
kitchen/sources/mhsds.py - Mental Health Services Monthly Statistics: waits, by provider.

How long people wait for community mental health care once referred.
Two different measures, because that's what's published by provider:
  Children and young people (under 18): referral to FIRST contact.
  Adults with serious mental illness (community mental health teams):
    referral to SECOND contact - the point where care has really started.
    Referral-to-first-contact for adults isn't published by provider.

What this script does, in plain English:
  LICENCE  Prints the licence statement (Open Government Licence).
  FETCH    For each month from April 2024, finds the publication page's
           "MHSDS Data File" and "Referral Spells" file (zips, about 4 MB and
           1 MB; links are found by their text because file names vary) and
           downloads them into data/raw/mhsds/.
  CLEAN    Provider rows only. From the main file (3-month rolling periods,
           labelled by the month they end):
             CYP:    first contacts (count), median and 90th percentile days
             adults: second contacts (count), median and 90th percentile days
           From the referral spells file:
             % of referrals with a "clock stop" within 4 weeks (adults, CYP)
             median days still waiting (adults for 2nd, CYP for 1st contact)
           "*" means suppressed and becomes blank.
  WRITE    data/processed/mhsds/provider_month.csv
           data/processed/mhsds/check_before_using.json  (4-week share moving
                                                         15+ points in a month)
  REPORT   A coverage summary.

Note: the referral-spell method changed from November 2024, so early and
late figures don't compare cleanly - the jump check helps catch this.

Run it with:   python kitchen/sources/mhsds.py
"""

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, months_back_to,  # noqa: E402
                    page_links, processed_dir, raw_dir, stop_source, update_registry)

SOURCE = "mhsds"
INDEX = "https://digital.nhs.uk/data-and-information/publications/statistical/mental-health-services-monthly-statistics"
LICENCE_PAGE = "https://digital.nhs.uk/about-nhs-digital/terms-and-conditions"
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december"]
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

MAIN = {"MHS130": "cyp_first_contacts", "MHS131": "cyp_median_days_to_first", "MHS132": "cyp_p90_days_to_first",
        "MHS124": "adult_second_contacts", "MHS125": "adult_median_days_to_second",
        "MHS126": "adult_p90_days_to_second"}
SPELLS = {"MRS01b": "adult_pct_within_4_weeks", "MRS08b": "cyp_pct_within_4_weeks",
          "MRS03a": "adult_median_days_still_waiting", "MRS10a": "cyp_median_days_still_waiting"}


def files_for(year, month):
    """(main file url, referral spells url) on one month's page, or Nones."""
    page = f"{INDEX}/performance-{MONTH_NAMES[month - 1]}-{year}"
    main = spells = None
    for text, url in page_links(page, allow_missing=True):
        if re.match(r"MHSDS Monthly: Performance \w+ \d{4} MHSDS Data File", text):
            main = main or url
        if re.match(r"MHSDS Monthly: Performance \w+ \d{4} Referral Spells", text):
            spells = spells or url
    return main, spells


def read_any(path):
    """A CSV, or the CSV inside a zip."""
    if path.suffix.lower() != ".zip":
        return pd.read_csv(path, dtype=str)
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        return pd.read_csv(io.TextIOWrapper(archive.open(name), encoding="latin-1"), dtype=str)


def provider_measures(raw, measures, month):
    rows = raw[(raw["BREAKDOWN"] == "Provider") & raw["MEASURE_ID"].isin(measures)
               & (raw["REPORTING_PERIOD_END"].str[3:5] == month[5:]) & (raw["REPORTING_PERIOD_END"].str[6:10] == month[:4])]
    # A measure can appear for more than one period ending this month (e.g. 3 and 12 months):
    # keep the shortest, which is the one with the latest start.
    rows = rows.assign(start=pd.to_datetime(rows["REPORTING_PERIOD_START"], dayfirst=True))
    rows = rows.sort_values("start").drop_duplicates(["PRIMARY_LEVEL", "MEASURE_ID"], keep="last")
    wide = rows.assign(value=pd.to_numeric(rows["MEASURE_VALUE"], errors="coerce")) \
        .pivot_table(index="PRIMARY_LEVEL", columns="MEASURE_ID", values="value", aggfunc="first")
    names = rows.drop_duplicates("PRIMARY_LEVEL").set_index("PRIMARY_LEVEL")["PRIMARY_LEVEL_DESCRIPTION"]
    wide = wide.rename(columns=measures)
    wide.insert(0, "provider_name", names)
    return wide


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    months, gaps = [], []
    for year, month in months_back_to(FIRST_MONTH):
        key = f"{year}-{month:02d}"
        main_url, spells_url = files_for(year, month)
        if not main_url:
            continue                                   # not published yet
        main_table = provider_measures(read_any(download(main_url, RAW, name=f"main-{key}{Path(main_url).suffix}")),
                                       MAIN, key)
        if spells_url:
            spells = provider_measures(read_any(download(spells_url, RAW, name=f"spells-{key}{Path(spells_url).suffix}")),
                                       SPELLS, key).drop(columns="provider_name")
            main_table = main_table.join(spells, how="outer")
        else:
            gaps.append(key)
        main_table.insert(0, "month", key)
        months.append(main_table.rename_axis("provider_code").reset_index())

    print("CLEAN")
    table = pd.concat(months, ignore_index=True)
    columns = ["month", "provider_code", "provider_name"] + list(MAIN.values()) + list(SPELLS.values())
    table = table.reindex(columns=columns).sort_values(["provider_code", "month"])
    flags = {}
    for column in ("cyp_pct_within_4_weeks", "adult_pct_within_4_weeks"):
        for code, reason in jump_flags(table.dropna(subset=[column]), "provider_code", "month", column,
                                       label=column.replace("_", " ")).items():
            flags.setdefault(code, reason)
    table.to_csv(OUT / "provider_month.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/mhsds/provider_month.csv")

    month_list = sorted(table["month"].unique())
    update_registry(SOURCE, url=INDEX, status="ingested", licence="Open Government Licence v3.0",
                    first_period=month_list[0], last_period=month_list[-1],
                    note="CYP: referral to first contact. Adults (community mental health, serious mental "
                         "illness): referral to SECOND contact - adult first-contact waits aren't published by "
                         "provider. Median and 90th percentile are 3-month rolling. Referral-spell method changed "
                         "Nov 2024." + (f" No referral spells file for {', '.join(gaps)}." if gaps else ""))
    latest = table[table["month"] == month_list[-1]]
    coverage_summary(SOURCE, len(table), month_list, table["provider_code"].unique(), notes=[
        f"latest, providers:   {latest['cyp_median_days_to_first'].notna().sum()} with a CYP median, "
        f"{latest['adult_median_days_to_second'].notna().sum()} with an adult median",
        f"no spells file:      {', '.join(gaps) if gaps else 'none'}",
        f"check before using:  {len(flags)} providers"])


if __name__ == "__main__":
    main()
