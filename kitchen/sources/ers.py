"""
kitchen/sources/ers.py - NHS e-Referral Service: appointment slot issues (ASIs).

An ASI is when a GP tries to book a patient's first hospital appointment
through the e-Referral Service and there's no slot to book. It's the queue
before the waiting list.

What this script does, in plain English:
  LICENCE  Prints the licence statement (Open Government Licence) first.
  FETCH    Finds the monthly ASI report (one .xlsx per month) on NHS
           England's e-RS reports page. The page only lists recent months, so
           earlier ones (back to April 2024) come from the UK Government Web
           Archive's copies of the same page. Downloads anything new into
           data/raw/ers/.
  CLEAN    Each report's own "Reporting period" says which month it is.
           Table 1: by provider - ASIs (no slots, slot unavailable, system
           unavailable), "directly bookable service" (DBS) bookings, and ASIs
           per 100 bookings. Table 3: by provider, site and specialty - ASIs and
           bookings; added up to provider and specialty.
  WRITE    data/processed/ers/asi_provider.csv
           data/processed/ers/asi_specialty.csv
           data/processed/ers/check_before_using.json  (ASI rate moving 50+
                                                        points in a month)
  REPORT   A coverage summary.

Note: the ASI rate is ASIs per DBS booking, not per referral, so it can be
over 100%. Open referral counts by provider aren't published (the e-RS "open
data" is by referring area and stopped in September 2025). This is
management information: "may be incomplete ... not quality assured".

Run it with:   python kitchen/sources/ers.py
"""

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, page_links,  # noqa: E402
                    processed_dir, raw_dir, read_xlsx_rows, stop_source, update_registry)

SOURCE = "ers"
PAGE = "https://digital.nhs.uk/services/e-referral-service/reports-and-statistics/appointment-slot-issue-reports"
ARCHIVED_PAGES = [   # the same page as it was, for months no longer listed
    "https://webarchive.nationalarchives.gov.uk/ukgwa/20250129165147mp_/" + PAGE,
    "https://webarchive.nationalarchives.gov.uk/ukgwa/20260505194417mp_/" + PAGE,
]
LICENCE_PAGE = ("https://digital.nhs.uk/data-and-information/publications/statistical/"
                "mi-nhs-e-referral-service-open-data/current/author-copyright-licence")
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)


def report_links():
    """{file name: url} for every monthly report we can find, newest copy first."""
    found = {}
    for page in [PAGE] + ARCHIVED_PAGES:
        for _, url in page_links(page, allow_missing=True):
            if not re.search(r"/asi-reports/[^/]+\.xlsx$", url):
                continue
            if "webarchive" in url:
                # "/ukgwa/<time>mp_/https://..." is the page view; "id_" is the raw file.
                url = re.sub(r"(/ukgwa/\d+)mp_/", r"\1id_/", url)
            found.setdefault(url.rsplit("/", 1)[-1], url)
    return found


def excel_date(serial):
    return (date(1899, 12, 30) + timedelta(days=int(serial))).strftime("%Y-%m")


def heading(text):
    """One spelling for each column heading: July 2026's report says "ORG_CODE",
    "No_Slots" and so on where every other month says "Provider Code", "No Slots"."""
    text = str(text).replace("_", " ").strip().lower()
    text = re.sub(r"^org ", "provider ", text)
    words = {"asis": "ASIs", "dbs": "DBS"}
    return " ".join(words.get(word, word.capitalize()) for word in text.split())


def table(rows):
    """A sheet's rows below its header row, as a DataFrame."""
    at = next(i for i, r in enumerate(rows) if r and heading(r[0]) == "Provider Code")
    header = [heading(h) for h in rows[at]]
    body = [r + [None] * (len(header) - len(r)) for r in rows[at + 1:] if r and r[0] not in (None, "ENGLAND")]
    return pd.DataFrame([r[:len(header)] for r in body], columns=header)


def read_report(path):
    rows1 = read_xlsx_rows(path, "Table 1")
    month = excel_date(next(r[1] for r in rows1 if r and r[0] == "Reporting period:"))
    t1 = table(rows1)
    provider = pd.DataFrame({
        "month": month, "provider_code": t1["Provider Code"].astype(str).str.strip(), "provider_name": t1["Provider Name"],
        "no_slots": t1["No Slots"], "slot_unavailable": t1["Slot Unavailable"], "system_unavailable": t1["System Unavailable"],
        "total_asis": t1["Total ASIs"], "dbs_bookings": t1["DBS Bookings"]})
    t3 = table(read_xlsx_rows(path, "Table 3"))
    specialty = (t3.groupby(["Provider Code", "Specialty Name"], as_index=False)[["Total ASIs", "DBS Bookings"]].sum()
                 .rename(columns={"Provider Code": "provider_code", "Specialty Name": "specialty",
                                  "Total ASIs": "total_asis", "DBS Bookings": "dbs_bookings"}))
    specialty.insert(0, "month", month)
    for t in (provider, specialty):
        t["asi_rate_pct"] = (t["total_asis"] / t["dbs_bookings"] * 100).round(1).where(t["dbs_bookings"] > 0)
    return month, provider, specialty


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found for the e-RS reports", "not open")

    print("FETCH")
    links = report_links()
    print(f"  {len(links)} monthly reports listed (live page plus web archive)")
    providers, specialties = {}, {}
    for name, url in links.items():
        try:
            path = download(url, RAW, name=name)
        except Exception as error:      # an archived copy that's gone missing
            print(f"  !! couldn't download {name}: {error}")
            continue
        month, provider, specialty = read_report(path)
        if month < FIRST_MONTH or month in providers:
            continue
        providers[month], specialties[month] = provider, specialty

    print("CLEAN")
    asi = pd.concat(providers.values(), ignore_index=True).sort_values(["provider_code", "month"])
    by_specialty = pd.concat(specialties.values(), ignore_index=True).sort_values(["provider_code", "specialty", "month"])
    # ASI rates run into the hundreds, so a 15-point move is ordinary; flag 50+.
    flags = jump_flags(asi[asi["dbs_bookings"] >= 100], "provider_code", "month", "asi_rate_pct",
                       threshold=50, label="ASI rate")
    asi.to_csv(OUT / "asi_provider.csv", index=False)
    by_specialty.to_csv(OUT / "asi_specialty.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/ers/asi_provider.csv and asi_specialty.csv")

    months = sorted(providers)
    all_months = pd.period_range(FIRST_MONTH, months[-1], freq="M").astype(str)
    missing = [m for m in all_months if m not in providers]
    update_registry(SOURCE, url=PAGE, status="ingested", licence="Open Government Licence v3.0",
                    cadence="monthly", lag="about 2 weeks after month end", first_period=months[0], last_period=months[-1],
                    note="Management information. ASI rate = ASIs per directly bookable service booking (can exceed 100%). "
                         "Referral counts by provider aren't openly published.")
    latest = asi[asi["month"] == months[-1]]
    england = latest["total_asis"].sum() / latest["dbs_bookings"].sum() * 100
    coverage_summary(SOURCE, len(asi), months, asi["provider_code"].unique(), notes=[
        f"specialty rows:      {len(by_specialty):,} ({by_specialty['specialty'].nunique()} specialties)",
        f"months missing:      {', '.join(missing) if missing else 'none'}",
        f"England, {months[-1]}: {int(latest['total_asis'].sum()):,} ASIs for {int(latest['dbs_bookings'].sum()):,} bookings ({england:.1f} per 100)",
        f"check before using:  {len(flags)} providers (ASI rate moved 50+ points in a month)"])


if __name__ == "__main__":
    main()
