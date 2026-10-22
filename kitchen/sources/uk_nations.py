"""
kitchen/sources/uk_nations.py - headline waiting lists in Scotland, Wales and Northern Ireland.

NOT COMPARABLE with England. Each nation counts differently:
  England           referral to treatment, 18-week standard, one pathway per patient
  Scotland          each stage separately (new outpatient; inpatient/day case),
                    12-week standard
  Wales             referral to treatment pathways, 26- and 36-week targets
  Northern Ireland  each stage separately, quarterly; 9/13-week targets
So every row carries comparable_with_england = False. These are here for
context ("the lists are long everywhere"), never for a league table.

What this script does, in plain English:
  LICENCE  Prints each nation's licence statement (all Open Government Licence).
  FETCH    Scotland: Public Health Scotland's open data portal (CKAN) - the
             "Ongoing and Completed Waits - Monthly" CSV.
           Wales: the Welsh Government's statistics API, asking only for the
             all-Wales total (the full dataset is 177 MB).
           Northern Ireland: the latest quarterly outpatient and inpatient
             spreadsheets from the Department of Health.
           All saved in data/raw/uk_nations/.
  CLEAN    One row per nation, measure and period: number waiting, and the
           share within that nation's own standard where it can be worked out
           (Scotland: 12 weeks; Wales: 26 weeks), or the median wait (NI).
  WRITE    data/processed/uk_nations/headline.csv
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/uk_nations.py
"""

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, fetch_url, page_links,  # noqa: E402
                    processed_dir, raw_dir, read_xlsx_rows, stop_source, update_registry)

SOURCE = "uk_nations"
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

SCOTLAND_LICENCE = "https://www.opendata.nhs.scot/about"
SCOTLAND_API = "https://www.opendata.nhs.scot/api/3/action/package_show?id=stage-of-treatment-waiting-times"
WALES_LICENCE = "https://www.gov.wales/copyright-statement"
WALES_DATASET = "3ef3a1d8-1467-4afe-ad60-4fc3d92228a1"   # pathways waiting 26 / 36 weeks, one and two years
WALES_FILTER = [{"columnName": "local health board provider", "values": ["All Wales LHB (Provider)"]},
                {"columnName": "specialty", "values": ["Total"]},
                {"columnName": "stage of pathway", "values": ["All Stages of Pathway"]},
                {"columnName": "age group", "values": ["Total"]}]
NI_LICENCE = "https://www.health-ni.gov.uk/articles/crown-copyright-health"
NI_ARTICLES = {"outpatient": "https://www.health-ni.gov.uk/articles/outpatient-waiting-times",
               "inpatient and day case": "https://www.health-ni.gov.uk/articles/inpatient-waiting-times"}


def scotland():
    resources = fetch_url(SCOTLAND_API).json()["result"]["resources"]
    url = next(r["url"] for r in resources if re.match(r"Ongoing and Completed Waits\W+Monthly", r["name"]))
    raw = pd.read_csv(download(url, RAW), dtype={"MonthEnding": str})
    raw = raw[(raw["HBT"] == "S92000003") & (raw["Specialty"] == "Z9") & (raw["WaitType"] == "Ongoing")]
    return pd.DataFrame({
        "nation": "Scotland", "measure": raw["PatientType"].str.lower() + " (stage of treatment)",
        "period": raw["MonthEnding"].str[:4] + "-" + raw["MonthEnding"].str[4:6],
        "waiting": raw["Waits"], "standard": "12 weeks",
        "pct_within_standard": ((1 - raw["WaitsOver12Weeks"] / raw["Waits"]) * 100).round(1),
        "median_weeks": (raw["Median"] / 7).round(1)})


def wales():
    url = (f"https://api.stats.gov.wales/v1/{WALES_DATASET}/download/csv?filter="
           + quote(json.dumps(WALES_FILTER)))
    path = RAW / f"wales-{date.today():%Y-%m}.csv"
    if not path.exists():
        print(f"  downloading {path.name}")
        response = fetch_url(url, timeout=120)
        response.raise_for_status()
        path.write_bytes(response.content)
    raw = pd.read_csv(path)
    wide = raw.pivot_table(index="Date", columns="Data description", values="Data values", aggfunc="first")
    wide = wide.reset_index()
    return pd.DataFrame({
        "nation": "Wales", "measure": "patient pathways (referral to treatment)",
        "period": pd.to_datetime(wide["Date"], format="%B %Y").dt.strftime("%Y-%m"),
        "waiting": wide["Total pathways waiting"], "standard": "26 weeks",
        "pct_within_standard": (wide["Pathways waiting less than 26 weeks"] / wide["Total pathways waiting"] * 100).round(1),
        "median_weeks": None})


def northern_ireland():
    out = []
    for measure, article in NI_ARTICLES.items():
        publication = next(u for _, u in page_links(article)
                           if re.search(r"/publications/northern-ireland-waiting-time-statistics-", u))
        table_url = next(u for _, u in page_links(publication) if re.search(r"hs-niwts-tables-[^/]+\.xlsx$", u))
        rows = read_xlsx_rows(download(table_url, RAW), "Table 3")
        header = rows[0]
        q, n, m = header.index("Quarter Ending"), header.index("No. of Patients Waiting"), header.index("Median (Weeks)")
        for r in rows[1:]:
            if len(r) > max(q, n, m) and isinstance(r[q], (int, float)) and isinstance(r[n], (int, float)):
                out.append({"nation": "Northern Ireland", "measure": f"{measure} (stage of treatment, quarterly)",
                            "period": (date(1899, 12, 30) + timedelta(days=int(r[q]))).strftime("%Y-%m"),
                            "waiting": r[n], "standard": "9 weeks (outpatient) / 13 weeks (inpatient)",
                            "pct_within_standard": None,
                            "median_weeks": round(r[m], 1) if isinstance(r[m], (int, float)) else None})
    # The inpatient table repeats quarters across old and new systems (PAS, encompass): keep the latest row.
    return pd.DataFrame(out).drop_duplicates(["measure", "period"], keep="last")


def main():
    nations = {"Scotland": (SCOTLAND_LICENCE, scotland), "Wales": (WALES_LICENCE, wales),
               "Northern Ireland": (NI_LICENCE, northern_ireland)}
    tables, stopped = [], []
    for nation, (licence_page, fetch) in nations.items():
        is_open, _ = check_licence(f"{SOURCE} ({nation})", licence_page)
        if not is_open:
            stopped.append(nation)
            continue
        print(f"FETCH {nation}")
        tables.append(fetch())
    if not tables:
        return stop_source(SOURCE, "no open licence found for any nation", "not open")

    print("CLEAN")
    table = pd.concat(tables, ignore_index=True)
    table = table[table["period"] >= FIRST_MONTH].sort_values(["nation", "measure", "period"])
    table["comparable_with_england"] = False
    table.to_csv(OUT / "headline.csv", index=False)
    print("  saved data/processed/uk_nations/headline.csv")

    periods = sorted(table["period"].unique())
    update_registry(SOURCE, status="ingested", licence="Open Government Licence v3.0",
                    first_period=periods[0], last_period=periods[-1],
                    note="NOT COMPARABLE with England: different standards (12 / 26 / 9-13 weeks), stage-of-"
                         "treatment vs pathway counting, different cadence. Context only." +
                         (f" Not ingested (no licence found): {', '.join(stopped)}." if stopped else ""))
    latest = table.sort_values("period").groupby(["nation", "measure"]).tail(1)
    coverage_summary(SOURCE, len(table), periods, table["nation"], match=False, notes=[
        f"{r['nation']}, {r['measure']}, {r['period']}: {int(r['waiting']):,} waiting"
        + (f", {r['pct_within_standard']}% within {r['standard']}" if pd.notna(r["pct_within_standard"]) else "")
        for _, r in latest.iterrows()] + ["comparable_with_england: False on every row"])


if __name__ == "__main__":
    main()
