"""
kitchen/sources/workforce.py - NHS staffing: vacancies (by region and sector) and sickness absence (by trust).

Vacancy rates are NOT published by trust - only by NHS England region and
sector (acute, ambulance, community, mental health, specialist), each
quarter. Trust-level figures are "available on request". So this script
takes the regional vacancy rates, and, as the closest monthly trust-level
staffing measure, sickness absence.

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    Vacancies: finds the newest "NHS Vacancy Statistics ... Tables"
           spreadsheet (pages for future editions exist but have no files,
           so they're skipped) into data/raw/workforce/.
           Sickness: the small monthly "Sickness Absence Rates CSV" for every
           month from April 2024.
  CLEAN    Vacancies: sheet "Total 2018 onwards" has two blocks, vacancy FTE
           and vacancy rate, by region and sector, one column per quarter.
           Turned into one row per region, sector and quarter.
           Sickness: per organisation per month, days lost, days available
           and the sickness absence rate %.
  WRITE    data/processed/workforce/vacancy_region_quarter.csv
           data/processed/workforce/sickness_trust_month.csv
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/workforce.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, months_back_to, page_links,  # noqa: E402
                    processed_dir, raw_dir, read_xlsx_rows, stop_source, update_registry)

SOURCE = "workforce"
STATS = "https://digital.nhs.uk/data-and-information/publications/statistical/"
VACANCY_INDEX = STATS + "nhs-vacancies-survey"
SICKNESS_INDEX = STATS + "nhs-sickness-absence-rates"
LICENCE_PAGE = "https://digital.nhs.uk/about-nhs-digital/terms-and-conditions"
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december"]
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)


def newest_vacancy_tables():
    """The newest edition's tables spreadsheet: editions are named "april-2015---june-2026-...", so
    sort by their end month and take the first that has a file."""
    editions = []
    for _, url in page_links(VACANCY_INDEX):
        match = re.search(r"/april-2015---([a-z]+)-(\d{4})", url)
        if match and match.group(1) in MONTH_NAMES:
            editions.append(((int(match.group(2)), MONTH_NAMES.index(match.group(1))), url))
    for _, page in sorted(set(editions), reverse=True):
        tables = [u for t, u in page_links(page, allow_missing=True) if u.endswith("-eng-tables.xlsx")]
        if tables:
            return tables[0]
    raise SystemExit("no vacancy tables found")


def read_vacancies(path):
    rows = read_xlsx_rows(path, "Total 2018 onwards")
    out, measure = [], None
    for i, r in enumerate(rows):
        if len(r) == 1 and isinstance(r[0], str) and "vacancy" in r[0].lower():
            measure = "vacancy_rate_pct" if "rate" in r[0].lower() else "vacancy_fte"
        if r and r[0] == "Region" and measure:
            quarters = r[2:]
            region = None
            for row in rows[i + 1:]:
                if not row:
                    break
                # Region names appear once, on their first sector row; "<region> Total" rows have no
                # sector; "Grand Total" (or "National Total") is England.
                region = row[0] if row[0] and not str(row[0]).endswith("Total") else region
                sector = row[1] if len(row) > 1 and row[1] else "All sectors"
                place = "England" if str(row[0]) in ("Grand Total", "National Total") else region
                for q, value in zip(quarters, row[2:]):
                    if isinstance(value, (int, float)):
                        out.append({"region": place, "sector": sector, "quarter": q, "measure": measure,
                                    "value": value * 100 if measure == "vacancy_rate_pct" else value})
    table = pd.DataFrame(out).pivot_table(index=["region", "sector", "quarter"], columns="measure",
                                          values="value", aggfunc="first").reset_index()
    table["quarter_end"] = table["quarter"].str.extract(r"\((\w{3}-\d{2})\)")[0] \
        .map(lambda q: pd.to_datetime(q, format="%b-%y").strftime("%Y-%m") if isinstance(q, str) else None)
    table["vacancy_rate_pct"] = table["vacancy_rate_pct"].round(1)
    return table.sort_values(["region", "sector", "quarter_end"])


def sickness_file(year, month):
    page = f"{SICKNESS_INDEX}/{MONTH_NAMES[month - 1]}-{year}"
    for _, url in page_links(page, allow_missing=True):
        if re.search(r"Sickness%20Absence%20rates%20CSV", url, re.I):
            return url
    return None


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    vacancies = read_vacancies(download(newest_vacancy_tables(), RAW))
    months = []
    for year, month in months_back_to(FIRST_MONTH):
        url = sickness_file(year, month)
        if not url:
            continue                        # not published yet
        raw = pd.read_csv(download(url, RAW, name=f"sickness-{year}-{month:02d}.csv"), dtype=str)
        months.append(pd.DataFrame({
            "month": f"{year}-{month:02d}", "org_code": raw["ORG_CODE"], "org_name": raw["ORG_NAME"],
            "org_type": raw["ORG_TYPE"], "region": raw["NHSE_REGION_NAME"],
            "fte_days_lost": pd.to_numeric(raw["FTE_DAYS_LOST"]), "fte_days_available": pd.to_numeric(raw["FTE_DAYS_AVAILABLE"]),
            "sickness_rate_pct": pd.to_numeric(raw["SICKNESS_ABSENCE_RATE_PERCENT"])}))

    print("CLEAN")
    sickness = pd.concat(months, ignore_index=True).sort_values(["org_code", "month"])
    vacancies.to_csv(OUT / "vacancy_region_quarter.csv", index=False)
    sickness.to_csv(OUT / "sickness_trust_month.csv", index=False)
    print("  saved data/processed/workforce/vacancy_region_quarter.csv and sickness_trust_month.csv")

    month_list = sorted(sickness["month"].unique())
    quarters = sorted(vacancies["quarter_end"].dropna().unique())
    update_registry(SOURCE, url=VACANCY_INDEX, status="ingested", licence="Open Government Licence v3.0",
                    first_period=month_list[0], last_period=month_list[-1],
                    note="Vacancy rates are only published by region and sector (quarterly, experimental "
                         f"statistics; latest quarter {quarters[-1]}). Trust-level vacancies aren't open, so "
                         "sickness absence by trust (monthly, about 4 months behind) is the trust-level staffing "
                         "measure.")
    latest = vacancies[(vacancies["quarter_end"] == quarters[-1]) & (vacancies["sector"] == "All sectors")]
    england = latest[latest["region"] == "England"]["vacancy_rate_pct"]
    coverage_summary(SOURCE, len(sickness), month_list, sickness["org_code"].unique(), notes=[
        f"vacancy rows:        {len(vacancies):,} ({vacancies['region'].nunique()} regions incl. England, "
        f"quarters to {quarters[-1]})",
        f"England vacancy rate, {quarters[-1]}: {england.iloc[0] if len(england) else '?'}%",
        f"sickness, {month_list[-1]}: median trust {sickness[sickness['month'] == month_list[-1]]['sickness_rate_pct'].median():.1f}%"])


if __name__ == "__main__":
    main()
