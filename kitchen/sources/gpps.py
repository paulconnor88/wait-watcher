"""
kitchen/sources/gpps.py - GP Patient Survey (GPPS), by practice.

Would give, for each practice: how easy it is to get through on the phone,
overall experience, and confidence and trust in the healthcare professional.

What this script does, in plain English:
  LICENCE  Fetches the survey site's pages about using the data and prints
           anything they say about licensing. The survey is run by Ipsos for
           NHS England and its site says "© GP Patient Survey"; it doesn't
           state the Open Government Licence. So, under the kitchen's rule,
           this script records why in kitchen/registry.json and stops.
  FETCH / CLEAN / WRITE  Only if an open licence is found (see below).

If Ipsos or NHS England confirm the practice data is OGL (ask
GPPatientSurvey@ipsos.com), add the wording they give to LICENCE_PAGES, and
the script will go on to:
  FETCH    The weighted practice-level CSV (about 100 MB) for the latest year.
  CLEAN    Practice code plus three measures, as percentages:
             phone   - "easy to get through to on the phone"
             overall - "good overall experience"
             confidence - "had confidence and trust in the professional"
           (-97, -98, -99 mean "too few responses" and become blank.)
  WRITE    data/processed/gpps/practice_year.csv

Run it with:   python kitchen/sources/gpps.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, processed_dir,  # noqa: E402
                    raw_dir, stop_source, update_registry)

SOURCE = "gpps"
SITE = "https://www.gp-patient.co.uk"
LICENCE_PAGES = [SITE + "/why-use-the-data", SITE + "/uses-of-gpps"]
YEAR = 2026
CSV_URL = (SITE + "/FileDownload/Download?fileRedirect=" + str(YEAR) +
           "%2Fsurvey-results%2Fpractice-results%2Fpractice-data-csv%2FGPPS_" + str(YEAR) +
           "_Practice_data_(weighted)_(csv)_PUBLIC.csv")
MEASURES = {"localgpservicesphone.pcteval": "pct_phone_easy", "overallexp.pcteval": "pct_overall_good",
            "lastgpapptconf.pcteval": "pct_confidence_trust"}
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)


def main():
    is_open = False
    for page in LICENCE_PAGES:
        is_open = is_open or check_licence(SOURCE, page)[0]
    if not is_open:
        return stop_source(SOURCE, "the GP Patient Survey site (Ipsos, '© GP Patient Survey') doesn't state an "
                                   "open licence for the practice data. OGL is likely via NHS England but isn't "
                                   "stated - confirm with GPPatientSurvey@ipsos.com before ingesting.",
                           "not stated")

    print("FETCH")
    path = download(CSV_URL, RAW, name=f"GPPS_{YEAR}_practice_weighted.csv")

    print("CLEAN")
    raw = pd.read_csv(path, usecols=["ad_practicecode"] + list(MEASURES), dtype={"ad_practicecode": str})
    table = raw.rename(columns={"ad_practicecode": "practice_code", **MEASURES})
    for column in MEASURES.values():
        table[column] = (table[column].where(table[column] >= 0) * 100).round(1)   # -97/-98/-99 -> blank
    table.insert(1, "year", YEAR)
    table.to_csv(OUT / "practice_year.csv", index=False)
    update_registry(SOURCE, url=SITE, status="ingested", first_period=str(YEAR), last_period=str(YEAR))
    coverage_summary(SOURCE, len(table), [str(YEAR)], table["practice_code"], match=False, notes=[
        f"phone easy, median practice: {table['pct_phone_easy'].median():.0f}%"])


if __name__ == "__main__":
    main()
