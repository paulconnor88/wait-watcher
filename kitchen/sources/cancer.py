"""
kitchen/sources/cancer.py - cancer waiting times by trust, monthly.

SENSITIVE: these figures are about people waiting to find out whether they
have cancer, or waiting to start treatment. Any copy built on them needs to
be gentle: no league-table glee, no "worst trust" headlines, and always say
what the standard means for a person.

The three standards:
  FDS  Faster Diagnosis Standard: told whether or not you have cancer within
       28 days of an urgent referral. Standard 75% (interim aim 80% by March 2026).
  31D  31 days from deciding to treat to starting treatment. Standard 96%.
  62D  62 days from urgent referral to first treatment. Standard 85%
       (interim aim 75% by March 2026).

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    Downloads the "Monthly Combined CSV" for each financial year from
           2024-25 (25-60 MB each) into data/raw/cancer/.
  CLEAN    Keeps trust (provider) rows. For each month, trust and standard:
           patients seen or treated (Total), within the standard (Within),
           after it (After), and the % within. One table for all cancers
           together, one by cancer type (all routes / all stages, all
           treatments). If a month appears in two files, the newer file wins.
  WRITE    data/processed/cancer/provider_standards.csv
           data/processed/cancer/provider_by_cancer_type.csv
           data/processed/cancer/check_before_using.json  (% within moving
                                                          15+ points in a month)
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/cancer.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, page_links,  # noqa: E402
                    processed_dir, raw_dir, stop_source, update_registry)

SOURCE = "cancer"
PAGE = "https://www.england.nhs.uk/statistics/statistical-work-areas/cancer-waiting-times/"
LICENCE_PAGE = "https://www.england.nhs.uk/terms-and-conditions/"
LINK_TEXT = re.compile(r"^(\d{4})-(\d{2}) Apr\W+\w+ Monthly Combined CSV")
FIRST_YEAR = 2024
STANDARDS = {"FDS": 75, "31D": 96, "62D": 85}
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)
KEEP = ["Period", "Basis", "Org_Code", "Org_Name", "Standard_or_Item", "Cancer_Type",
        "Referral_Route_or_Stage", "Treatment_Modality", "Total", "Within", "After"]


def yearly_files():
    """{financial year start: url}, e.g. {2025: ".../2025-26-Apr-Mar-...csv"}."""
    found = {}
    for text, url in page_links(PAGE):
        match = LINK_TEXT.search(text)
        if match and url.endswith(".csv") and int(match.group(1)) >= FIRST_YEAR:
            found.setdefault(int(match.group(1)), url)
    return found


def read_year(path):
    """Trust rows for every standard, at "all routes / all stages, all treatments"."""
    table = pd.read_csv(path, usecols=KEEP, dtype={"Org_Code": str}, low_memory=False)
    table = table[(table["Basis"] == "Provider")
                  & table["Standard_or_Item"].isin(STANDARDS)
                  & table["Referral_Route_or_Stage"].isin(["ALL ROUTES", "ALL STAGES"])
                  & (table["Treatment_Modality"].isna() | (table["Treatment_Modality"] == "ALL MODALITIES"))
                  & (table["Org_Code"] != "Total")]
    # Periods are "2024-04-01" in some files and "01/04/2025" in others.
    period = table["Period"].map(lambda p: f"{p[6:10]}-{p[3:5]}" if "/" in p else p[:7])
    return pd.DataFrame({
        "month": period, "provider_code": table["Org_Code"].str.strip(),
        "provider_name": table["Org_Name"], "standard": table["Standard_or_Item"],
        "cancer_type": table["Cancer_Type"], "total": table["Total"], "within": table["Within"],
        "after": table["After"]})


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    files = yearly_files()
    print(f"  {len(files)} yearly files from {FIRST_YEAR}-{(FIRST_YEAR + 1) % 100:02d}")
    months = {}
    for year in sorted(files):   # newer files overwrite any month they share with older ones
        path = download(files[year], RAW)
        for month, rows in read_year(path).groupby("month"):
            months[month] = rows

    print("CLEAN")
    rows = pd.concat(months.values(), ignore_index=True)
    rows["pct_within"] = (rows["within"] / rows["total"] * 100).round(1).where(rows["total"] > 0)
    rows["standard_pct"] = rows["standard"].map(STANDARDS)
    everything = rows[rows["cancer_type"] == "ALL CANCERS"].drop(columns="cancer_type")
    everything = everything.sort_values(["provider_code", "standard", "month"])
    by_type = rows[rows["cancer_type"] != "ALL CANCERS"].sort_values(["provider_code", "standard", "cancer_type", "month"])

    flags = {}
    for standard in STANDARDS:
        some = everything[(everything["standard"] == standard) & (everything["total"] >= 20)]
        for code, reason in jump_flags(some, "provider_code", "month", "pct_within", label=f"{standard} %").items():
            flags.setdefault(code, reason)

    everything.to_csv(OUT / "provider_standards.csv", index=False)
    by_type.to_csv(OUT / "provider_by_cancer_type.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/cancer/provider_standards.csv and provider_by_cancer_type.csv")

    month_list = sorted(months)
    update_registry(SOURCE, url=PAGE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=month_list[0], last_period=month_list[-1],
                    sensitive="sensitive: gentle copy required",
                    note="Standards: FDS 75% (28 days to diagnosis or all-clear), 31D 96%, 62D 85%. "
                         "Latest months are provisional and revised in the next year's Final file.")
    latest = everything[everything["month"] == month_list[-1]]
    national = latest.groupby("standard")[["within", "total"]].sum()
    national = ", ".join(f"{s} {national.loc[s, 'within'] / national.loc[s, 'total'] * 100:.1f}%"
                         for s in STANDARDS if s in national.index)
    met = latest[latest["total"] >= 20].assign(met=lambda t: t["pct_within"] >= t["standard_pct"])
    coverage_summary(SOURCE, len(everything), month_list, everything["provider_code"].unique(), notes=[
        f"by cancer type:      {len(by_type):,} rows ({by_type['cancer_type'].nunique()} types)",
        f"England, {month_list[-1]}: {national}",
        "trusts meeting it:   " + ", ".join(f"{s} {int(g['met'].sum())} of {len(g)}" for s, g in met.groupby("standard")),
        f"check before using:  {len(flags)} trusts",
        "SENSITIVE:           gentle copy required"])


if __name__ == "__main__":
    main()
