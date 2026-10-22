"""
kitchen/sources/population.py - ONS mid-year population estimates, by local authority and by ICB.

So waits and appointments can be put "per head", and areas with more older
people can be spotted.

What this script does, in plain English:
  LICENCE  Prints the ONS licence statement (Open Government Licence).
  FETCH    For each of two ONS datasets, asks ONS which edition is newest
           (adding "/data" to a dataset page returns its list of editions as
           JSON) and downloads that edition's spreadsheet into data/raw/population/:
             local authorities: "Population estimates for the UK ..." (mid-2025)
             ICBs: "Clinical commissioning group / ICB mid-year estimates" (mid-2024)
  CLEAN    Local authorities: sheet "MYE2 - Persons", one row per area with
           all ages, and people aged 65 and over (and the %). Only English
           areas (codes starting E).
           ICBs: the newest "Mid-YYYY ICB" sheet is by sub-ICB and single year
           of age, for women and men; added up to total and 65+, per sub-ICB
           and per ICB. The sub-ICB ODS code (e.g. "02P") comes from the end of
           its name, so it joins to GP data.
  WRITE    data/processed/population/local_authority.csv
           data/processed/population/sub_icb.csv
           data/processed/population/icb.csv
  REPORT   A coverage summary.

Note: the ICB file uses April 2024 boundaries (42 ICBs), before the 2026
mergers; ONS area codes (E54...) are kept so it joins to Fingertips.

Run it with:   python kitchen/sources/population.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, fetch_url, processed_dir,  # noqa: E402
                    raw_dir, read_xlsx_rows, stop_source, update_registry, xlsx_sheet_names)

SOURCE = "population"
ONS = "https://www.ons.gov.uk"
DATASETS = "/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/"
LA_DATASET = DATASETS + "populationestimatesforukenglandandwalesscotlandandnorthernireland"
ICB_DATASET = DATASETS + "clinicalcommissioninggroupmidyearpopulationestimates"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)


def newest_file(dataset, skip=r"tomid"):
    """(edition label, url) of the newest single-year edition's spreadsheet."""
    editions = fetch_url(ONS + dataset + "/data").json()["datasets"]
    for edition in editions:
        if re.search(skip, edition["uri"].rsplit("/", 1)[-1]) and len(editions) > 1 and dataset == LA_DATASET:
            continue          # "mid2011tomid2025" is a back series; we want the single year
        info = fetch_url(ONS + edition["uri"] + "/data").json()
        files = [d["file"] for d in info.get("downloads", []) if d["file"].endswith(".xlsx")]
        if files:
            return info["description"]["edition"], f"{ONS}/file?uri={edition['uri']}/{files[0]}"
    raise SystemExit(f"no spreadsheet found for {dataset}")


def local_authorities(path):
    rows = read_xlsx_rows(path, "MYE2 - Persons")
    at = next(i for i, r in enumerate(rows) if r[:4] == ["Code", "Name", "Geography", "All ages"])
    header = [str(h) for h in rows[at]]
    table = pd.DataFrame([r[:len(header)] for r in rows[at + 1:] if r and r[0]], columns=header)
    ages = [h for h in header[4:] if re.match(r"\d+", h) and int(re.match(r"\d+", h).group()) >= 65]
    table = table[table["Code"].str.startswith("E")]
    out = pd.DataFrame({"area_code": table["Code"], "area_name": table["Name"], "geography": table["Geography"],
                        "population": pd.to_numeric(table["All ages"]),
                        "aged_65_plus": table[ages].apply(pd.to_numeric).sum(axis=1)})
    out["pct_65_plus"] = (out["aged_65_plus"] / out["population"] * 100).round(1)
    return out


def sub_icbs(path):
    sheet = max(s for s in xlsx_sheet_names(path) if re.match(r"Mid-\d{4} ICB", s))
    rows = read_xlsx_rows(path, sheet)
    at = next(i for i, r in enumerate(rows) if r and r[0] and str(r[0]).startswith("SICBL"))
    header = [str(h) for h in rows[at]]
    table = pd.DataFrame([r[:len(header)] for r in rows[at + 1:] if r and r[0]], columns=header)
    older = [h for h in header if re.match(r"[FM](\d+)$", h) and int(h[1:]) >= 65]
    out = pd.DataFrame({
        "sub_icb_area_code": table[header[0]], "sub_icb_code": table[header[1]].str.extract(r"- (\w{3})\s*$")[0],
        "sub_icb_name": table[header[1]], "icb_area_code": table[header[2]], "icb_name": table[header[3]],
        "region": table[header[5]], "population": pd.to_numeric(table["Total"]),
        "aged_65_plus": table[older].apply(pd.to_numeric).sum(axis=1)})
    return sheet, out


def main():
    is_open, _ = check_licence(SOURCE, ONS + LA_DATASET)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on the ONS dataset page", "not open")

    print("FETCH")
    la_edition, la_url = newest_file(LA_DATASET)
    icb_edition, icb_url = newest_file(ICB_DATASET)
    la = local_authorities(download(la_url, RAW, name=f"la-{re.sub(r'[^A-Za-z0-9]+', '-', la_edition)}.xlsx"))
    sheet, sub = sub_icbs(download(icb_url, RAW, name=f"icb-{re.sub(r'[^A-Za-z0-9]+', '-', icb_edition)}.xlsx"))

    print("CLEAN")
    icb = sub.groupby(["icb_area_code", "icb_name", "region"], as_index=False)[["population", "aged_65_plus"]].sum()
    for table in (sub, icb):
        table["pct_65_plus"] = (table["aged_65_plus"] / table["population"] * 100).round(1)
    la.to_csv(OUT / "local_authority.csv", index=False)
    sub.to_csv(OUT / "sub_icb.csv", index=False)
    icb.to_csv(OUT / "icb.csv", index=False)
    print("  saved data/processed/population/local_authority.csv, sub_icb.csv and icb.csv")

    update_registry(SOURCE, url=ONS + LA_DATASET, status="ingested", licence="Open Government Licence v3.0",
                    first_period=sheet.split(" ")[0], last_period=la_edition,
                    note=f"Local authorities: {la_edition}. ICBs: {sheet} (April 2024 boundaries, 42 ICBs). "
                         "Annual; LA and ICB editions don't reconcile exactly (LA figures were revised Oct 2026).")
    england = la[la["geography"] == "Country"]["population"]
    coverage_summary(SOURCE, len(la) + len(sub), [la_edition, sheet], list(la["area_code"]) + list(sub["sub_icb_code"]),
                     match=False, notes=[
        f"local authority rows: {len(la)} ({la['geography'].nunique()} kinds of area), England "
        f"{int(england.iloc[0]):,}" if len(england) else f"local authority rows: {len(la)}",
        f"sub-ICBs:            {len(sub)} -> {len(icb)} ICBs ({sheet})"])


if __name__ == "__main__":
    main()
