"""
kitchen/sources/fft.py - Friends and Family Test (FFT), NHS England.

What this script does, in plain English:
  FETCH  Opens NHS England's FFT publication page for every month from
         April 2024 to now, finds the inpatient, outpatient and A&E files
         (their names change from year to year, so we match on the service)
         and downloads anything new into data/raw/fft/.
  CLEAN  Reads each file's trust-level sheet ("Trusts", or "Orgs" for
         outpatients) by its column headings. For inpatients we also read the
         "Sites" sheet, because most private hospitals report there under
         their own code. Keeps, per month + service + provider: the number of
         responses and the share who were positive.
         Note on wording: since 2020 the FFT question is "Overall, how was
         your experience of our service?". NHS England's headline figure is
         the share answering "very good" or "good" ("percentage positive").
         It is NOT a "would recommend" figure any more, so we store it as
         pct_positive. Figures from fewer than MIN_RESPONSES people are kept
         but flagged.
  WRITE  data/processed/fft/fft.csv
  REPORT A coverage summary.

Run it with:   python kitchen/sources/fft.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (MONTH_NAMES, coverage_summary, download, month_key, months_back_to,  # noqa: E402
                    our_provider_codes, page_links, processed_dir, raw_dir, read_xlsx_rows,
                    update_registry, xlsx_sheet_names)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

FIRST_MONTH = "2024-04"
PAGE_URL = "https://www.england.nhs.uk/publication/friends-and-family-test-data-{month}-{year}/"
RAW = raw_dir("fft")
OUT = processed_dir("fft")
MIN_RESPONSES = 30

# How each service's file is named. They vary a lot: "FFT-inpatient-data",
# "fft-ip-sep-24", "FFT_IP_MacroWebfile_Dec-25", "fft-out-patient-data",
# "FFT-outpatients-data", "fft-accident-emergency-data", "ftt-ae-apr-26"...
SERVICES = {
    "inpatient": r"in-?patients?[-_]|[-_]ip[-_]",
    "outpatient": r"out-?patients?[-_]|[-_]op[-_]",
    "a_and_e": r"accident|[-_]ae[-_]",
}
# The sheets to read for each service, in order.
SHEETS = {"inpatient": ["Trusts", "Sites"], "outpatient": ["Orgs", "Trusts"], "a_and_e": ["Trusts"]}


# ---------------------------------------------------------------------------
# FETCH
# ---------------------------------------------------------------------------

def files_for(year, month):
    """{service: url} on one month's page ({} if there's no page yet)."""
    links = page_links(PAGE_URL.format(month=MONTH_NAMES[month - 1], year=year), allow_missing=True)
    found = {"_page": bool(links)}
    for _, url in links:
        name = url.rsplit("/", 1)[-1].lower()
        if not name.endswith((".xlsm", ".xlsx")) or "checker" in name:
            continue
        for service, pattern in SERVICES.items():
            if re.search(pattern, name) and service not in found:
                found[service] = url
    return found


# ---------------------------------------------------------------------------
# CLEAN
# ---------------------------------------------------------------------------

def read_sheet(path, sheet, code_heading):
    """Rows of (code, responses, eligible, share positive) from one sheet,
    found by its column headings."""
    rows = read_xlsx_rows(path, sheet)
    header_at = next((i for i, row in enumerate(rows)
                      if code_heading in row and "Total Responses" in row and "Percentage Positive" in row), None)
    if header_at is None:
        raise SystemExit(f"{path.name}, sheet {sheet}: couldn't find the '{code_heading}' heading row.")
    header = rows[header_at]
    code_col, responses_col = header.index(code_heading), header.index("Total Responses")
    eligible_col, positive_col = header.index("Total Eligible"), header.index("Percentage Positive")
    out = []
    for row in rows[header_at + 1:]:
        if len(row) <= positive_col:
            continue
        code, responses, positive = row[code_col], row[responses_col], row[positive_col]
        if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{3,6}", code.strip()) and isinstance(responses, (int, float)) \
                and isinstance(positive, (int, float)) and responses > 0:
            eligible = row[eligible_col] if isinstance(row[eligible_col], (int, float)) else None
            out.append((code.strip(), int(responses), eligible, float(positive)))
    return out


def read_file(path, service, month, ours):
    """One month's file for one service."""
    sheets = xlsx_sheet_names(path)
    rows = []
    for sheet in SHEETS[service]:
        if sheet not in sheets:
            continue
        heading = "Site Code" if sheet == "Sites" else "Trust Code"
        found = read_sheet(path, sheet, heading)
        if sheet == "Sites":
            # Only sites that are providers in their own right (most private hospitals).
            have = {r[0] for r in rows}
            found = [r for r in found if r[0] in ours and r[0] not in have]
        rows += found
    if not rows:
        raise SystemExit(f"{path.name}: no provider rows found in sheets {SHEETS[service]} (has {sheets}).")
    return pd.DataFrame([{"month": month, "service": service, "provider_code": code, "responses": responses,
                          "eligible": eligible, "pct_positive": round(positive * 100, 1),
                          "small_numbers": responses < MIN_RESPONSES}
                         for code, responses, eligible, positive in rows])


def main():
    ours = our_provider_codes()
    print("FETCH")
    tables, missing = [], []
    for year, month in months_back_to(FIRST_MONTH):
        files = files_for(year, month)
        key = month_key(year, month)
        if not files.pop("_page"):
            continue     # no page for this month yet
        for service in SERVICES:
            if service not in files:
                missing.append(f"{key} {service}")
                continue
            path = download(files[service], RAW)
            tables.append(read_file(path, service, key, ours))
    if not tables:
        raise SystemExit("No FFT files found.")

    fft = pd.concat(tables, ignore_index=True).sort_values(["provider_code", "service", "month"])
    fft.to_csv(OUT / "fft.csv", index=False)
    print("  saved data/processed/fft/fft.csv")
    update_registry("fft", latest_month=fft["month"].max())

    latest = fft[fft["month"] == fft["month"].max()]
    coverage_summary("fft", len(fft), fft["month"].unique(), fft["provider_code"].unique(), notes=[
        "by service, latest month: " + ", ".join(f"{s} {latest[latest['service'] == s]['provider_code'].nunique()} providers"
                                                  for s in SERVICES),
        f"files not published:  {', '.join(missing) if missing else 'none'}",
        "pct_positive = share answering 'very good' or 'good' (the FFT no longer asks 'would you recommend')"])


if __name__ == "__main__":
    main()
