"""
kitchen/sources/talking_therapies.py - NHS Talking Therapies (anxiety and depression), by provider.

What this script does, in plain English:
  LICENCE  Prints the publication's licence statement (Open Government Licence).
  FETCH    Each monthly publication page has a "Monthly Time Series for Key
           Measures" CSV covering 13 months (about 29 MB). Working back from
           the newest page, it downloads just enough of them to reach April
           2024 (about three files) - far less than the 45 MB-a-month full
           files. It also downloads the newest full "Monthly Activity Data
           File", once, for the measures the time series leaves out: the wait
           between first and second appointment (the "hidden wait").
           Pages marked "upcoming" have no files yet and are skipped.
  CLEAN    Provider rows only (the provider code is in ORG_CODE2). Per month:
             referrals received, people starting treatment, % of those who
             finished treatment who'd started within 6 and 18 weeks, people who
             finished a course, % recovered and % reliably recovered.
           From the latest full file: % waiting over 28 and over 90 days
           between first and second appointment.
           "*" means suppressed (small numbers) and becomes blank. Measures
           are matched by ID (M001 etc.), because names have changed over time.
  WRITE    data/processed/talking_therapies/provider_month.csv
           data/processed/talking_therapies/england_month.csv
           data/processed/talking_therapies/second_appointment_latest.csv
           data/processed/talking_therapies/check_before_using.json
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/talking_therapies.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, page_links,  # noqa: E402
                    processed_dir, raw_dir, stop_source, update_registry)

SOURCE = "talking_therapies"
INDEX = ("https://digital.nhs.uk/data-and-information/publications/statistical/"
         "nhs-talking-therapies-monthly-statistics-including-employment-advisors")
LICENCE_PAGE = "https://digital.nhs.uk/about-nhs-digital/terms-and-conditions"
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

KEY_MEASURES = {"M001": "referrals", "M031": "entered_treatment", "M053": "pct_within_6_weeks",
                "M055": "pct_within_18_weeks", "M076": "finished_treatment", "M192": "pct_recovery",
                "M195": "pct_reliable_recovery"}
SECOND_APPOINTMENT = {"M184": "had_second_appointment", "M123": "pct_second_within_28_days",
                      "M124": "pct_second_over_28_days", "M126": "pct_second_over_90_days"}


def publication_pages():
    """Monthly publication pages, newest first (as the index lists them)."""
    pages = []
    for _, url in page_links(INDEX):
        if re.search(r"/performance-[a-z]+-\d{4}", url) and url not in pages:
            pages.append(url)
    return pages


def files_on(page):
    """(time series url, its first month, full activity file url) on one page."""
    series = first = activity = None
    for text, url in page_links(page, allow_missing=True):
        match = re.search(r"Time Series for Key Measures - (\w+) (\d{4}) -", text)
        if match and url.endswith(".csv"):
            series, first = url, pd.to_datetime(f"1 {match.group(1)} {match.group(2)}").strftime("%Y-%m")
        if re.search(r"_month_[a-z]{3}_\d{4}_activity_(performance|final)\.csv$", url):
            activity = url
    return series, first, activity


def provider_rows(path, measures):
    """Provider-level rows for some measures, one column per measure."""
    raw = pd.read_csv(path, dtype=str)
    value = next(c for c in raw.columns if c.startswith("MEASURE_VALUE"))
    raw = raw[raw["GROUP_TYPE"].isin(["Provider", "England"]) & raw["MEASURE_ID"].isin(measures)]
    start = raw["REPORTING_PERIOD_START"]
    raw = raw.assign(month=start.map(lambda d: f"{d[6:10]}-{d[3:5]}" if "/" in d else d[:7]),
                     value=pd.to_numeric(raw[value], errors="coerce"),     # "*" -> blank
                     provider_code=raw["ORG_CODE2"].where(raw["GROUP_TYPE"] == "Provider", "ENGLAND"))
    wide = raw.pivot_table(index=["month", "provider_code"], columns="MEASURE_ID", values="value", aggfunc="first")
    names = raw.drop_duplicates("provider_code").set_index("provider_code")["ORG_NAME2"]
    wide = wide.rename(columns=measures).reset_index()
    wide.insert(2, "provider_name", wide["provider_code"].map(names))
    return wide


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    found, latest_activity = {}, None
    for page in publication_pages():
        series, first, activity = files_on(page)
        if not series:
            continue                       # "upcoming" - nothing published yet
        if latest_activity is None:
            latest_activity = activity
        last = (pd.Period(first, "M") + 12).strftime("%Y-%m")
        if found and last >= min(found):
            continue                       # overlaps what we have; the next one back that doesn't will do
        path = download(series, RAW)
        for month, rows in provider_rows(path, KEY_MEASURES).groupby("month"):
            found.setdefault(month, rows)  # newer files win
        if min(found) <= FIRST_MONTH:
            break
    second = provider_rows(download(latest_activity, RAW), SECOND_APPOINTMENT)

    print("CLEAN")
    table = pd.concat([found[m] for m in sorted(found) if m >= FIRST_MONTH], ignore_index=True)
    england = table[table["provider_code"] == "ENGLAND"].drop(columns=["provider_code", "provider_name"])
    providers = table[table["provider_code"] != "ENGLAND"].sort_values(["provider_code", "month"])
    second = second[second["provider_code"] != "ENGLAND"]
    flags = jump_flags(providers[providers["entered_treatment"] >= 50], "provider_code", "month",
                       "pct_within_6_weeks", label="6-week share")

    providers.to_csv(OUT / "provider_month.csv", index=False)
    england.to_csv(OUT / "england_month.csv", index=False)
    second.to_csv(OUT / "second_appointment_latest.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/talking_therapies/provider_month.csv, england_month.csv, "
          "second_appointment_latest.csv")

    months = sorted(providers["month"].unique())
    update_registry(SOURCE, url=INDEX, status="ingested", licence="Open Government Licence v3.0",
                    first_period=months[0], last_period=months[-1],
                    note="6- and 18-week figures are for people who finished a course of treatment that month "
                         "(the national standard is 75% and 95%). Small numbers are suppressed; sub-national "
                         "percentages are whole numbers. The second-appointment wait is the latest month only.")
    last = england.iloc[-1]
    coverage_summary(SOURCE, len(providers), months, providers["provider_code"].unique(), notes=[
        f"England, {months[-1]}: {int(last['referrals']):,} referrals, {last['pct_within_6_weeks']:.1f}% within "
        f"6 weeks, {last['pct_recovery']:.1f}% recovered",
        f"second appointment:  {second['pct_second_over_90_days'].notna().sum()} providers with a 90-day figure "
        f"({second['month'].iloc[0]})",
        "not on our list:     most talking therapies services are independent or community providers "
        "outside the RTT list",
        f"check before using:  {len(flags)} providers"])


if __name__ == "__main__":
    main()
