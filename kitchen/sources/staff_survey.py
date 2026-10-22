"""
kitchen/sources/staff_survey.py - NHS Staff Survey, by trust.

What this script does, in plain English:
  FETCH  Opens the NHS Staff Survey national results page, finds the
         "detailed spreadsheets" zip for the latest year (e.g.
         NSS25-Detailed-spreadsheets.zip for the 2025 survey) and downloads
         it into data/raw/staff_survey/ unless we have it.
  CLEAN  Reads the organisational results spreadsheet, sheet "YOUR
         ORGANISATION Q25-26", and keeps two questions for each organisation:
           Q25c  "I would recommend my organisation as a place to work."
           Q25d  "If a friend or relative needed treatment I would be happy
                  with the standard of care provided by this organisation."
                 (often described as "recommend as a place to receive
                 treatment")
         as the share who agree or strongly agree, with the number of
         responses. NHS organisations only - private hospitals don't take part.
  WRITE  data/processed/staff_survey/staff_survey.csv. Each run adds the
         latest year and keeps earlier years already in the file, so the
         file builds up a history as new surveys come out.
  REPORT A coverage summary.

Run it with:   python kitchen/sources/staff_survey.py
"""

import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (coverage_summary, download, page_links, processed_dir, raw_dir,  # noqa: E402
                    read_xlsx_rows, update_registry, xlsx_sheet_names)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

PAGE_URL = "https://www.nhsstaffsurveys.com/results/national-results/"
RAW = raw_dir("staff_survey")
OUT = processed_dir("staff_survey")
QUESTIONS = {"Q25c": "recommend_place_to_work_pct", "Q25d": "recommend_place_for_treatment_pct"}


# ---------------------------------------------------------------------------
# FETCH
# ---------------------------------------------------------------------------

def fetch():
    """The organisational results spreadsheet and the survey year."""
    url = next((url for _, url in page_links(PAGE_URL) if re.search(r"Detailed-spreadsheets\.zip$", url, re.I)), None)
    if url is None:
        raise SystemExit(f"Couldn't find the detailed spreadsheets zip on {PAGE_URL}.")
    zipped = download(url, RAW)
    year = 2000 + int(re.search(r"NSS(\d\d)", zipped.name, re.I).group(1))
    with zipfile.ZipFile(zipped) as archive:
        name = next(n for n in archive.namelist() if "organisational results" in n.lower())
        target = RAW / "unzipped" / name
        if not target.exists():
            archive.extract(name, RAW / "unzipped")
    return target, year


# ---------------------------------------------------------------------------
# CLEAN
# ---------------------------------------------------------------------------

def read_questions(path, year):
    """One row per organisation: Q25c and Q25d as % agree or strongly agree.
    Each question has six columns: five answer percentages, then responses."""
    sheet = next(n for n in xlsx_sheet_names(path) if "Q25" in n)
    rows = read_xlsx_rows(path, sheet)
    titles = rows[0]
    header_at = next(i for i, row in enumerate(rows) if row and row[0] == "ODS code")
    starts = {q: next(i for i, t in enumerate(titles) if isinstance(t, str) and t.startswith(q)) for q in QUESTIONS}
    out = []
    for row in rows[header_at + 1:]:
        if not row or not isinstance(row[0], str) or not re.fullmatch(r"[A-Z0-9]{3,6}", row[0].strip()):
            continue
        record = {"year": year, "provider_code": row[0].strip(), "name": row[1], "benchmarking_group": row[2]}
        for question, column in QUESTIONS.items():
            start = starts[question]
            values = row[start + 3:start + 6] if len(row) >= start + 6 else [None] * 3
            try:
                agree, strongly, responses = float(values[0]), float(values[1]), int(float(values[2]))
                record[column] = round(agree + strongly, 1)
                record[column.replace("_pct", "_responses")] = responses
            except (TypeError, ValueError):
                record[column] = None            # suppressed or missing
                record[column.replace("_pct", "_responses")] = None
        out.append(record)
    return pd.DataFrame(out)


def main():
    print("FETCH")
    path, year = fetch()
    print(f"  {path.name} ({year} survey)")
    print("CLEAN")
    latest = read_questions(path, year)
    csv_path = OUT / "staff_survey.csv"
    if csv_path.exists():
        earlier = pd.read_csv(csv_path)
        latest = pd.concat([earlier[earlier["year"] != year], latest], ignore_index=True)
    latest = latest.sort_values(["provider_code", "year"])
    latest.to_csv(csv_path, index=False)
    print("  saved data/processed/staff_survey/staff_survey.csv")
    update_registry("staff_survey", latest_year=int(year))

    this_year = latest[latest["year"] == year]
    coverage_summary("staff_survey", len(latest), [str(y) for y in latest["year"].unique()],
                     latest["provider_code"].unique(), notes=[
                         f"organisations in {year}: {len(this_year)}",
                         f"with a 'place for treatment' figure: {this_year['recommend_place_for_treatment_pct'].notna().sum()}",
                         f"England median, {year}: place for treatment "
                         f"{this_year['recommend_place_for_treatment_pct'].median():.1f}%, place to work "
                         f"{this_year['recommend_place_to_work_pct'].median():.1f}%",
                         "years are survey years, not months"])


if __name__ == "__main__":
    main()
