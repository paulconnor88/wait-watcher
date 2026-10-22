"""
kitchen/sources/gp_practices.py - every GP practice, with where it is.

What this script does, in plain English:
  LICENCE  Prints the ODS licence statement (Open Government Licence) first.
  FETCH    Downloads NHS England's ODS "epraccur" list of GP practices
           (a CSV with no header row) into data/raw/gp_practices/, unless
           today's copy is already there.
  CLEAN    Keeps GP practices only (prescribing setting RO76), with code,
           name, postcode, status, open and close dates, the sub-ICB that
           commissions it and the ICB its postcode is in. Looks up each
           active practice's postcode with postcodes.io (100 at a time) to get
           its latitude and longitude, and its local authority.
  WRITE    data/processed/gp_practices/practices.csv
  REPORT   A coverage summary.

Practices are joined to other GP data (appointments, patient survey) by the
practice code, e.g. "F84017".

Run it with:   python kitchen/sources/gp_practices.py
"""

import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, post_json, processed_dir,  # noqa: E402
                    raw_dir, stop_source, update_registry)

SOURCE = "gp_practices"
URL = "https://www.odsdatasearchandexport.nhs.uk/api/getReport?report=epraccur"
LICENCE_PAGE = "https://digital.nhs.uk/services/organisation-data-service"
POSTCODES_URL = "https://api.postcodes.io/postcodes"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

# epraccur has no header row; these are its column positions (counting from 0).
COLUMNS = {0: "practice_code", 1: "name", 2: "region_code", 3: "icb_geography_code", 9: "postcode",
           10: "open_date", 11: "close_date", 12: "status", 14: "sub_icb_code", 25: "prescribing_setting"}
GP_PRACTICE = "RO76"


def coordinates(postcodes):
    """{postcode: (latitude, longitude, local authority)} from postcodes.io."""
    found = {}
    postcodes = sorted(set(p for p in postcodes if p))
    for start in range(0, len(postcodes), 100):
        batch = postcodes[start:start + 100]
        response = post_json(POSTCODES_URL, {"postcodes": batch})
        for item in response.json()["result"]:
            r = item["result"]
            if r:
                found[item["query"]] = (r["latitude"], r["longitude"], r.get("admin_district"))
    return found


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on the ODS page", "not open")

    print("FETCH")
    path = download(URL, RAW, name=f"epraccur-{date.today():%Y-%m-%d}.csv")
    raw = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)

    print("CLEAN")
    table = raw[list(COLUMNS)].rename(columns=COLUMNS)
    table = table[table["prescribing_setting"] == GP_PRACTICE].drop(columns="prescribing_setting")
    table["postcode"] = table["postcode"].str.strip()
    active = table["status"] == "ACTIVE"
    found = coordinates(table.loc[active, "postcode"])
    table["latitude"] = table["postcode"].map(lambda p: found.get(p, (None,))[0])
    table["longitude"] = table["postcode"].map(lambda p: found.get(p, (None, None))[1])
    table["local_authority"] = table["postcode"].map(lambda p: found.get(p, (None, None, None))[2])
    table = table.sort_values("practice_code")

    table.to_csv(OUT / "practices.csv", index=False)
    print("  saved data/processed/gp_practices/practices.csv")
    update_registry(SOURCE, url=URL, status="ingested", licence="Open Government Licence v3.0",
                    lag="updated weekly", first_period="current", last_period=date.today().isoformat())
    located = table.loc[active, "latitude"].notna().sum()
    coverage_summary(SOURCE, len(table), [date.today().isoformat()], table["practice_code"], match=False, notes=[
        f"active practices:    {active.sum():,}",
        f"active and located:  {located:,} ({active.sum() - located} postcodes not found by postcodes.io)",
        f"with a sub-ICB:      {(table['sub_icb_code'] != '').sum():,}"])


if __name__ == "__main__":
    main()
