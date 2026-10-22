"""
kitchen/sources/gpad.py - Appointments in General Practice (GPAD), by practice.

How long people wait for a GP appointment: the time from booking to the
appointment itself, for every practice in England, every month.

What this script does, in plain English:
  LICENCE  Prints NHS England's licence statement (Open Government Licence).
  FETCH    Each monthly publication has a "Practice Level CSV" zip (about 20 MB,
           about 570 MB unzipped) holding that month and the two before. NHS
           England revises a month in each later publication that includes it, so
           every month is read from the LAST publication that has it: month M from
           the zip published for M+2 (or the newest zip, for the latest months).
           That's one zip per month from April 2024, in data/raw/gpad/. The
           England totals then match NHS England's National Overview (checked
           by kitchen/reconcile.py).
  CLEAN    Reads each month's CSV (about a million rows) straight out of the
           zip, without unzipping to disk, and adds it up to one row per
           practice per month:
             - appointments, attended, did not attend (DNA), status unknown
             - time from booking: same day, 1 day, 2-7, 8-14, 15-21, 22-28,
               more than 28 days, unknown
             - mode: face to face, telephone, video/online, home visit, unknown
             - appointments with a GP (rather than another member of staff)
           Percentages are of appointments with a known booking time (waits)
           or a known outcome (DNAs). Also adds up to ICB.
  WRITE    data/processed/gpad/practice_month.csv
           data/processed/gpad/month_sources.json  (the publication each month came from)
           data/processed/gpad/icb_month.csv
           data/processed/gpad/check_before_using.json  (same-day share moving
                                                        15+ points in a month)
  REPORT   A coverage summary.

Practice codes join to data/processed/gp_practices/practices.csv for postcode,
location and local authority.

Run it with:   python kitchen/sources/gpad.py
"""

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, download, jump_flags, months_back_to,  # noqa: E402
                    page_links, processed_dir, raw_dir, stop_source, update_registry)

SOURCE = "gpad"
INDEX = "https://digital.nhs.uk/data-and-information/publications/statistical/appointments-in-general-practice"
LICENCE_PAGE = "https://digital.nhs.uk/about-nhs-digital/terms-and-conditions"
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december"]
FIRST_MONTH = "2024-04"
RAW = raw_dir(SOURCE)
OUT = processed_dir(SOURCE)

WAITS = {"Same Day": "same_day", "1 Day": "day_1", "2 to 7 Days": "days_2_7", "8  to 14 Days": "days_8_14",
         "15  to 21 Days": "days_15_21", "22  to 28 Days": "days_22_28", "More than 28 Days": "over_28",
         "Unknown / Data Issue": "wait_unknown"}
KNOWN_WAITS = [w for w in WAITS.values() if w != "wait_unknown"]
MODES = {"Face-to-Face": "face_to_face", "Telephone": "telephone", "Video Conference/Online": "video_online",
         "Home Visit": "home_visit", "Unknown": "mode_unknown"}
STATUSES = {"Attended": "attended", "DNA": "dna", "Unknown": "status_unknown"}


def zip_for(year, month):
    """The Practice Level CSV zip on a month's publication page (or None)."""
    page = f"{INDEX}/{MONTH_NAMES[month - 1]}-{year}"
    for _, url in page_links(page, allow_missing=True):
        if re.search(r"Practice_Level_Crosstab_[A-Za-z]{3}_\d{2}\.zip$", url):
            return url
    return None


def month_of(name):
    """"Practice_Level_Crosstab_Aug_26.csv" -> "2026-08". Some months come in two
    regional halves, e.g. "..._London_East_South_Oct_25.csv" and "..._Oct_24_Midlands_and_North.csv"."""
    month, year = re.search(r"_([A-Z][a-z]{2})_(\d{2})(?=_|\.csv$)", name).groups()
    return f"20{year}-{MONTH_NAMES.index(next(m for m in MONTH_NAMES if m.startswith(month.lower()))) + 1:02d}"


def add_up(raw):
    """One row per practice from one month's raw rows."""
    raw = raw.rename(columns={"GP_CODE": "practice_code"})
    count = "COUNT_OF_APPOINTMENTS"
    parts = [raw.groupby("practice_code")[count].sum().rename("appointments")]
    for column, names in (("APPT_STATUS", STATUSES), ("TIME_BETWEEN_BOOK_AND_APPT", WAITS), ("APPT_MODE", MODES)):
        wide = raw.pivot_table(index="practice_code", columns=column, values=count, aggfunc="sum", fill_value=0)
        parts.append(wide.rename(columns=names).reindex(columns=list(names.values()), fill_value=0))
    parts.append(raw[raw["HCP_TYPE"] == "GP"].groupby("practice_code")[count].sum().rename("with_gp"))
    table = pd.concat(parts, axis=1).fillna(0).astype(int).reset_index()
    sub_icb = raw.drop_duplicates("practice_code").set_index("practice_code")["SUB_ICB_LOCATION_CODE"]
    table.insert(1, "sub_icb_code", table["practice_code"].map(sub_icb))
    return table


def percentages(table):
    known = table[KNOWN_WAITS].sum(axis=1)
    table["pct_same_day"] = (table["same_day"] / known * 100).round(1)
    table["pct_within_14_days"] = (table[["same_day", "day_1", "days_2_7", "days_8_14"]].sum(axis=1) / known * 100).round(1)
    table["pct_over_28_days"] = (table["over_28"] / known * 100).round(1)
    table["pct_face_to_face"] = (table["face_to_face"] / table["appointments"] * 100).round(1)
    table["pct_dna"] = (table["dna"] / (table["attended"] + table["dna"]) * 100).round(1)
    return table


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no open licence found on NHS England's terms page", "not open")

    print("FETCH")
    # The newest publication, then which publication each month is read from: the last one that
    # includes it (month M is in the zips for M, M+1 and M+2, revised each time).
    publications = {}
    for year, month in months_back_to(FIRST_MONTH):
        url = zip_for(year, month)
        if url:
            publications[f"{year}-{month:02d}"] = url
    newest = max(publications)
    plus_two = lambda m: (pd.Period(m, "M") + 2).strftime("%Y-%m")
    source_of = {m: min(plus_two(m), newest) for m in publications}
    wanted = set(source_of)
    found, icbs = {}, {}
    for publication in sorted(set(source_of.values()), reverse=True):      # newest first
        months_here = {m for m, p in source_of.items() if p == publication}
        url = publications.get(publication)
        if not url:
            raise SystemExit(f"No Practice Level CSV for the {publication} publication, needed for {sorted(months_here)}")
        path = download(url, RAW)
        with zipfile.ZipFile(path) as archive:
            # Sub-ICB -> ICB. Zips are read newest first, so the newest mapping wins: every month is
            # put under today's ICBs (several merged in 2026), as the RTT area figures are.
            mapping = pd.read_csv(archive.open("Mapping.csv"), dtype=str)
            for sub_icb, icb in (mapping.drop_duplicates("SUB_ICB_LOCATION_CODE")
                                 .set_index("SUB_ICB_LOCATION_CODE")[["ICB_CODE", "ICB_NAME"]].to_dict("index").items()):
                icbs.setdefault(sub_icb, icb)
            files = {}   # month -> its file(s) in this zip
            for name in archive.namelist():
                if name.endswith(".csv") and name != "Mapping.csv":
                    files.setdefault(month_of(name), []).append(name)
            for this_month, names in files.items():
                if this_month in found or this_month not in months_here:
                    continue
                print(f"  reading {', '.join(names)}")
                raw = pd.concat([pd.read_csv(io.TextIOWrapper(archive.open(name)), dtype=str,
                                             usecols=["GP_CODE", "SUB_ICB_LOCATION_CODE", "HCP_TYPE", "APPT_MODE",
                                                      "TIME_BETWEEN_BOOK_AND_APPT", "COUNT_OF_APPOINTMENTS",
                                                      "APPT_STATUS"])
                                 for name in names], ignore_index=True)
                raw["COUNT_OF_APPOINTMENTS"] = pd.to_numeric(raw["COUNT_OF_APPOINTMENTS"])
                table = add_up(raw)
                table.insert(0, "month", this_month)
                found[this_month] = table

    print("CLEAN")
    practices = pd.concat(found.values(), ignore_index=True)
    practices["icb_code"] = practices["sub_icb_code"].map(lambda c: icbs.get(c, {}).get("ICB_CODE"))
    counts = [c for c in practices.columns if c not in ("month", "practice_code", "sub_icb_code", "icb_code")]
    icb = practices.groupby(["month", "icb_code"], as_index=False)[counts].sum()
    icb.insert(2, "icb_name", icb["icb_code"].map({v["ICB_CODE"]: v["ICB_NAME"] for v in icbs.values()}))
    practices = percentages(practices).sort_values(["practice_code", "month"])
    icb = percentages(icb).sort_values(["icb_code", "month"])

    flags = jump_flags(practices[practices["appointments"] >= 500], "practice_code", "month",
                       "pct_same_day", label="same-day share")
    practices.to_csv(OUT / "practice_month.csv", index=False)
    # Which publication each month was read from - the reconciliation gate checks each month against
    # NHS England's National Overview in that same publication.
    (OUT / "month_sources.json").write_text(json.dumps(
        {m: {"publication": source_of[m], "url": publications[source_of[m]]} for m in sorted(found)}, indent=1))
    icb.to_csv(OUT / "icb_month.csv", index=False)
    (OUT / "check_before_using.json").write_text(json.dumps(flags, indent=1))
    print("  saved data/processed/gpad/practice_month.csv and icb_month.csv")

    months = sorted(found)
    update_registry(SOURCE, url=INDEX, status="ingested", licence="Open Government Licence v3.0",
                    first_period=months[0], last_period=months[-1],
                    note="Booking-to-appointment time is not the same as how long a patient waited from first "
                         "asking: it starts when the appointment is booked. Management information from GP "
                         "systems; some practices map appointments differently.")
    latest = practices[practices["month"] == months[-1]]
    england = percentages(latest[counts].sum().to_frame().T)
    on_list = set(pd.read_csv(Path(OUT).parent / "gp_practices" / "practices.csv", dtype=str)["practice_code"]) \
        if (Path(OUT).parent / "gp_practices" / "practices.csv").exists() else set()
    coverage_summary(SOURCE, len(practices), months, practices["practice_code"], match=False, notes=[
        f"practices, latest:   {len(latest):,} ({len(set(latest['practice_code']) - on_list)} not in the practice list)",
        f"ICBs:                {icb['icb_code'].nunique()}",
        f"England, {months[-1]}: {int(england['appointments'].iloc[0]):,} appointments; "
        f"{england['pct_same_day'].iloc[0]}% same day, {england['pct_over_28_days'].iloc[0]}% over 28 days, "
        f"{england['pct_dna'].iloc[0]}% DNA",
        f"check before using:  {len(flags):,} practices (same-day share moved 15+ points in a month)"])


if __name__ == "__main__":
    main()
