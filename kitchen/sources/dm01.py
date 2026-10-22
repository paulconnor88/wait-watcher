"""
kitchen/sources/dm01.py - diagnostic waiting times (DM01), NHS England.

What this script does, in plain English:
  FETCH  Opens NHS England's monthly diagnostics pages (one per financial
         year, from 2024-25 to now) and finds each month's "full extract"
         zip. Some months were re-published later; we take the newest
         upload of each month. Downloads anything new into data/raw/dm01/.
  CLEAN  Each extract has one row per provider + commissioner + test, with
         the number of people waiting in weekly bands (0-1 weeks ... 12-13
         weeks, then 13+ weeks). We add up the commissioner rows so there's
         one row per month + provider + test, for the 15 tests and the total.
         Then work out the total waiting and the share waiting 6 weeks or
         more (the NHS standard is that under 1% should) and 13 weeks or more.
  WRITE  data/processed/dm01/dm01.csv
  REPORT A coverage summary.

Run it with:   python kitchen/sources/dm01.py
"""

import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import coverage_summary, download, page_links, processed_dir, raw_dir, update_registry  # noqa: E402


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

FIRST_FINANCIAL_YEAR = 2024
PAGE_URL = ("https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/"
            "monthly-diagnostics-waiting-times-and-activity/monthly-diagnostics-data-{start}-{end:02d}/")
RAW = raw_dir("dm01")
OUT = processed_dir("dm01")

KEYS = ["Period", "Provider Org Code", "Diagnostic Tests"]
SIX_WEEKS_OR_MORE = ["06 < 07 Weeks", "07 < 08 Weeks", "08 < 09 Weeks", "09 < 10 Weeks", "10 < 11 Weeks",
                     "11 < 12 Weeks", "12 < 13 Weeks", "13+ Weeks"]


# ---------------------------------------------------------------------------
# FETCH
# ---------------------------------------------------------------------------

def find_extracts():
    """{month: url} for each month's full extract, the newest upload of each."""
    today = date.today()
    first_page = today.year if today.month >= 4 else today.year - 1
    found = {}
    for year in range(first_page, FIRST_FINANCIAL_YEAR - 1, -1):
        for _, url in page_links(PAGE_URL.format(start=year, end=(year + 1) % 100), allow_missing=True):
            match = re.search(r"DM01-([A-Z]+)-(\d{4})-full-extract[^/]*\.zip$", url, re.I)
            if not match:
                continue
            month = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%B %Y").strftime("%Y-%m")
            # Uploads live under .../uploads/sites/2/YYYY/MM/ - a later folder is a later upload.
            uploaded = re.search(r"/uploads/sites/\d+/(\d{4}/\d{2})/", url).group(1)
            if month not in found or uploaded > found[month][0]:
                found[month] = (uploaded, url)
    return {month: url for month, (_, url) in sorted(found.items())
            if month >= f"{FIRST_FINANCIAL_YEAR}-04"}


# ---------------------------------------------------------------------------
# CLEAN
# ---------------------------------------------------------------------------

def read_extract(path):
    """One month's extract, added up to provider + test."""
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        header = pd.read_csv(archive.open(name), nrows=0).columns
        bands = [c for c in header if re.match(r"\d\d(\+| < \d\d) Weeks?$", c)]
        table = pd.read_csv(archive.open(name), usecols=KEYS + bands + ["Total WL"], low_memory=False)
    table[bands + ["Total WL"]] = table[bands + ["Total WL"]].fillna(0)
    grouped = table.groupby(KEYS, as_index=False)[bands + ["Total WL"]].sum()
    total = grouped[bands].sum(axis=1)
    if (total - grouped["Total WL"]).abs().max() > 0:
        raise SystemExit(f"{path.name}: the weekly bands don't add up to the total waiting list.")
    out = pd.DataFrame({
        "month": grouped["Period"].map(lambda p: datetime.strptime(p.split("-", 1)[1], "%B-%Y").strftime("%Y-%m")),
        "provider_code": grouped["Provider Org Code"],
        "test": grouped["Diagnostic Tests"],
    })
    for band in bands:
        out["wk_" + band.replace(" < ", "_").replace(" Weeks", "").replace(" Week", "").replace("+", "_plus")] = grouped[band].astype(int)
    out["total_waiting"] = total.astype(int)
    six = [b for b in bands if b in SIX_WEEKS_OR_MORE]
    out["pct_6_weeks_plus"] = (grouped[six].sum(axis=1) / total * 100).round(1).where(total > 0)
    out["pct_13_weeks_plus"] = (grouped["13+ Weeks"] / total * 100).round(1).where(total > 0)
    return out


def main():
    print("FETCH")
    extracts = find_extracts()
    print(f"  {len(extracts)} months listed ({min(extracts)} to {max(extracts)})")
    paths = {month: download(url, RAW) for month, url in extracts.items()}

    print("CLEAN")
    tables = []
    for month, path in paths.items():
        table = read_extract(path)
        if set(table["month"]) != {month}:
            raise SystemExit(f"{path.name} doesn't contain {month}.")
        tables.append(table)
    dm01 = pd.concat(tables, ignore_index=True).sort_values(["provider_code", "test", "month"])

    dm01.to_csv(OUT / "dm01.csv", index=False)
    print(f"  saved data/processed/dm01/dm01.csv")
    update_registry("dm01", latest_month=dm01["month"].max())

    latest = dm01[(dm01["month"] == dm01["month"].max()) & (dm01["test"] == "TOTAL")]
    england = latest[[c for c in dm01.columns if c.startswith("wk_")]].sum()
    six = england[[c for c in england.index if c in ("wk_06_07", "wk_07_08", "wk_08_09", "wk_09_10",
                                                     "wk_10_11", "wk_11_12", "wk_12_13", "wk_13_plus")]].sum()
    coverage_summary("dm01", len(dm01), dm01["month"].unique(), dm01["provider_code"].unique(), notes=[
        f"tests:               {dm01['test'].nunique() - 1} plus TOTAL",
        f"England, {dm01['month'].max()}: {int(england.sum()):,} waiting, "
        f"{six / england.sum() * 100:.1f}% for 6+ weeks, {england['wk_13_plus'] / england.sum() * 100:.1f}% for 13+ weeks"])


if __name__ == "__main__":
    main()
