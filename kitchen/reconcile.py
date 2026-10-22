"""
kitchen/reconcile.py - the reconciliation gate: our England figures against NHS England's published ones.

Wait Watcher's numbers must match the official figures exactly, or differ only for a reason that is
written down and computed from the data. This runs after every source and before anything is
published (site_data.py, make_findings.py, lab_data.py). It fails the run loudly if any figure is off.

What it does, in plain English:
  For each source with a published England figure, every month we hold:
    ours       our England total, added up from our processed data
    published  NHS England's (or the publisher's) own England figure, from a separate published file
               where one exists (otherwise the England row the publisher prints in the same file)
    explained  a documented difference, worked out from the data - never a fixed allowance
    residual   ours - published - explained. Must be exactly 0.
  Prints a reconciliation table, writes data/processed/reconciliation.json and .md, and exits with an
  error if any residual isn't 0. Sources with no published England figure to check are listed as
  "not checked", with the reason.

The documented differences (see kitchen/DEFINITIONS.md):
  RTT, DM01    NHS England's England series leaves out patients at English providers who aren't
               commissioned by an English ICB (commissioner code "NONC" - mostly people from Wales at
               border hospitals). Our trust figures include them.
  Sitreps      The ambulance handover sheets have an "Unknown" row (handovers not assigned to a
               trust), counted in England's total but not under any trust.
  Community    Three services are published for England only, never by provider (adult
               safeguarding, children's safeguarding, looked after children teams).

Run it with:   python kitchen/reconcile.py
"""

import glob
import importlib.util
import json
import re
import sys
from pathlib import Path

import pandas as pd
import xlrd   # NHS England's DM01 timeseries is a legacy .xls file

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED_DIR, RAW_DIR, download, page_links, read_xlsx_rows, xlsx_sheet_names  # noqa: E402

KITCHEN = Path(__file__).resolve().parent
PUBLISHED = RAW_DIR / "published"
STATS = "https://www.england.nhs.uk/statistics/statistical-work-areas/"
RTT_PAGE = STATS + "rtt-waiting-times/rtt-data-{start}-{end:02d}/"
CANCER_PAGE = STATS + "cancer-waiting-times/"
GPAD_PAGE = "https://digital.nhs.uk/data-and-information/publications/statistical/appointments-in-general-practice/{month}"
DM01_PAGE = STATS + ("diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/"
                     "monthly-diagnostics-data-{start}-{end:02d}/")
# DM01 test codes in the order of the timeseries' "Diagnostic ID" (1-15).
DM01_TESTS = ["MRI", "CT", "NON_OBSTETRIC_ULTRASOUND", "BARIUM_ENEMA", "DEXA_SCAN", "AUDIOLOGY_ASSESSMENTS",
              "ECHOCARDIOGRAPHY", "ELECTROPHYSIOLOGY", "PERIPHERAL_NEUROPHYS", "SLEEP_STUDIES", "URODYNAMICS",
              "COLONOSCOPY", "FLEXI_SIGMOIDOSCOPY", "CYSTOSCOPY", "GASTROSCOPY"]
NATIONAL_ONLY_COMMUNITY = {"(A) Adult safeguarding", "(CYP) Safeguarding", "(CYP) Looked after children teams"}


def source_module(name):
    spec = importlib.util.spec_from_file_location(name, KITCHEN / "sources" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(source, measure, period, ours, published, explained=0, reason="", against=""):
    residual = round(float(ours) - float(published) - float(explained), 6)
    return {"source": source, "measure": measure, "period": period, "ours": ours, "published": published,
            "explained": explained, "reason": reason, "residual": residual, "against": against,
            "status": "PASS" if residual == 0 else "FAIL"}


def newest_link(pages, pattern):
    """(text, url) of the first link on the first page that has one whose text matches."""
    for page in pages:
        for text, url in page_links(page, allow_missing=True):
            if re.search(pattern, text, re.I):
                return text, url
    raise SystemExit(f"reconcile: no link matching {pattern!r} on {pages}")


# ---------------------------------------------------------------------------
# RTT: people waiting and year-long waits, against the RTT Overview Timeseries (reported only)
# ---------------------------------------------------------------------------

def rtt():
    year = pd.Timestamp.today().year if pd.Timestamp.today().month >= 4 else pd.Timestamp.today().year - 1
    pages = [RTT_PAGE.format(start=y, end=(y + 1) % 100) for y in (year, year - 1)]
    text, url = newest_link(pages, r"^RTT Overview Timeseries")
    path = download(url, PUBLISHED)
    rows = read_xlsx_rows(path, "Full Time Series")
    header = rows[11]
    col = lambda name: header.index(name)
    within, over18, over52 = col("No. within 18 weeks"), col("No. > 18 weeks"), col("No. > 52 weeks")
    published = {}
    for r in rows[12:]:
        if len(r) > over52 and isinstance(r[2], (int, float)) and isinstance(r[within], (int, float)):
            month = (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(r[2]))).strftime("%Y-%m")
            published[month] = (r[within] + r[over18], r[over52])
    ours = pd.read_csv(PROCESSED_DIR / "rtt" / "england_basis.csv").set_index("month")
    reason = "NONC: patients not commissioned by an English ICB (NHS England's England series is commissioner basis)"
    out = []
    for month, r in ours.iterrows():
        if month not in published:
            out.append({"source": "rtt", "measure": "people waiting", "period": month, "status": "NOT CHECKED",
                        "reason": "month not in the published timeseries"})
            continue
        out.append(row("rtt", "people waiting", month, int(r.waiting_all), published[month][0], int(r.waiting_nonc), reason, path.name))
        out.append(row("rtt", "waiting over 52 weeks", month, int(r.over_52_all), published[month][1], int(r.over_52_nonc), reason, path.name))
    return out


# ---------------------------------------------------------------------------
# Cancer: each standard, all cancers, against the national Monthly Time Series with Revisions
# ---------------------------------------------------------------------------

def cancer():
    links = [(t, u) for t, u in page_links(CANCER_PAGE) if re.match(r"^\w+ \d{4} Monthly Time Series with Revisions", t)]
    if not links:
        raise SystemExit("reconcile: no cancer Monthly Time Series with Revisions on " + CANCER_PAGE)
    # Newest publication first, so each month is checked against its latest revision.
    links.sort(key=lambda tu: pd.to_datetime(re.match(r"^(\w+ \d{4})", tu[0]).group(1), format="%B %Y"), reverse=True)
    published = {}
    for text, url in links:
        path = download(url, PUBLISHED)
        sheet = next(s for s in xlsx_sheet_names(path) if s.startswith("Provider"))
        rows = read_xlsx_rows(path, sheet)
        months = {j: pd.to_datetime(m, format="%b-%Y").strftime("%Y-%m") for j, m in enumerate(rows[13])
                  if isinstance(m, str) and re.match(r"[A-Z][a-z]{2}-\d{4}$", m)}
        for r in rows[15:]:
            if len(r) > 6 and r[1] == "Total" and r[5] == "ALL CANCERS":
                for j, month in months.items():
                    published.setdefault((r[4], month), (r[j], r[j + 1], path.name))
    ours = pd.read_csv(PROCESSED_DIR / "cancer" / "provider_standards.csv").groupby(["standard", "month"])[["total", "within"]].sum()
    out = []
    for (standard, month), r in ours.iterrows():
        if (standard, month) not in published:
            out.append({"source": "cancer", "measure": f"{standard} patients", "period": month, "status": "NOT CHECKED",
                        "reason": "month not in a published national time series"})
            continue
        total, within, name = published[(standard, month)]
        out.append(row("cancer", f"{standard} patients", month, r.total, total, against=name))
        out.append(row("cancer", f"{standard} within standard", month, r.within, within, against=name))
    return out


# ---------------------------------------------------------------------------
# A&E, e-RS, ambulance, WLMDS, community, population: the publisher's own England row
# ---------------------------------------------------------------------------

def ae():
    module = source_module("ae")
    out = []
    files = {}
    for path in Path(RAW_DIR / "ae").glob("*.csv"):
        raw = pd.read_csv(path, dtype={"Org Code": str})
        raw.columns = [c.strip() for c in raw.columns]
        month = pd.to_datetime(raw["Period"].iloc[0].replace("MSitAE-", ""), format="%B-%Y").strftime("%Y-%m")
        files.setdefault(month, []).append((path, raw))
    ours = pd.read_csv(PROCESSED_DIR / "ae" / "provider_month.csv").groupby("month").sum(numeric_only=True)
    for month in ours.index:
        if month not in files:
            continue
        path, raw = max(files[month], key=lambda pr: pr[0].stat().st_mtime)       # the file ae.py read
        total = raw[raw["Org Code"].str.strip().str.upper() == "TOTAL"]
        num = lambda cols: float(total[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum().sum())
        for measure, cols, ours_col in (("attendances", module.ATTEND, "attendances"),
                                        ("over 4 hours", module.OVER_4, "over_4_hours"),
                                        ("12+ hours from decision to admit",
                                         ["Patients who have waited 12+ hrs from DTA to admission"], "dta_over_12_hours")):
            out.append(row("ae", measure, month, ours.loc[month, ours_col], num(cols), against=f"{path.name} (TOTAL row)"))
    return out


def ers():
    module = source_module("ers")
    ours = pd.read_csv(PROCESSED_DIR / "ers" / "asi_provider.csv").groupby("month")[["total_asis", "dbs_bookings"]].sum()
    out = []
    for path in sorted(Path(RAW_DIR / "ers").glob("*.xlsx")):
        rows = read_xlsx_rows(path, "Table 1")
        month = module.excel_date(next(r[1] for r in rows if r and r[0] == "Reporting period:"))
        if month not in ours.index:
            continue
        at = next(i for i, r in enumerate(rows) if r and module.heading(r[0]) == "Provider Code")
        header = [module.heading(h) for h in rows[at]]
        england = next(r for r in rows[at + 1:] if r and r[0] == "ENGLAND")
        for measure, col, ours_col in (("slot issues", "Total ASIs", "total_asis"), ("bookings", "DBS Bookings", "dbs_bookings")):
            out.append(row("ers", measure, month, ours.loc[month, ours_col], england[header.index(col)],
                           against=f"{path.name} (ENGLAND row)"))
    return out


def ambulance():
    path = sorted(Path(RAW_DIR / "ambulance").glob("*.csv"), key=lambda p: p.stat().st_mtime)[-1]
    raw = pd.read_csv(path, dtype=str)
    raw["month"] = raw["Year"] + "-" + raw["Month"].str.zfill(2)
    ours = pd.read_csv(PROCESSED_DIR / "ambulance" / "response_month.csv")
    trusts = ours[ours["level"] == "Trust"].groupby("month")[["cat1_incidents", "cat2_incidents"]].sum()
    out = []
    for month in trusts.index:
        england = raw[(raw["month"] == month) & (raw["Org Code"] == "Eng")]
        for measure, code, col in (("category 1 incidents", "A8", "cat1_incidents"), ("category 2 incidents", "A10", "cat2_incidents")):
            out.append(row("ambulance", measure, month, trusts.loc[month, col], pd.to_numeric(england[code]).sum(),
                           against=f"{path.name} (Eng row)"))
    return out


def wlmds():
    """Each month's provider snapshot against the national figure for the same week in the same file
    (exact). The newest file's national series revises older weeks; that difference is reported, not failed."""
    module = source_module("wlmds")
    national_now = pd.read_csv(PROCESSED_DIR / "wlmds" / "national_weekly.csv").set_index("week_ending")
    snapshots = pd.read_csv(PROCESSED_DIR / "wlmds" / "provider_snapshots.csv")
    over_52 = ["w52_65", "w65_78", "w78_104", "w104_plus"]
    out = []
    for week, g in snapshots.groupby("week_ending"):
        path = RAW_DIR / "wlmds" / f"WLMDS-Summary-to-{week}.xlsx"
        same_file = module.block(read_xlsx_rows(path, "National-Time Series"))
        same_file["week_ending"] = same_file["week_ending"].map(module.excel_day)
        n = same_file.set_index("week_ending").loc[week]
        for measure, ours_value, published in (("people waiting", g["total_waiting"].sum(), n["total_waiting"]),
                                               ("waiting over 52 weeks", g[over_52].sum().sum(), n[over_52].sum())):
            r = row("wlmds", measure, week, ours_value, published, against=f"{path.name} (National-Time Series)")
            if week in national_now.index:
                now = national_now.loc[week, "total_waiting"] if measure == "people waiting" else national_now.loc[week, over_52].sum()
                if now != published:
                    r["note"] = f"newest file revises this week to {now:,.0f} ({(now / published - 1) * 100:+.2f}%)"
            out.append(r)
    return out


def community():
    waits = pd.read_csv(PROCESSED_DIR / "community" / "waits.csv")
    out = []
    for month, g in waits.groupby("month"):
        national = g[g["org_type"] == "National"]
        providers = g[g["org_type"] == "Provider"]
        explained = national[national["service"].isin(NATIONAL_ONLY_COMMUNITY)]["total_waiting"].sum()
        out.append(row("community", "people waiting, all services", month, providers["total_waiting"].sum(),
                       national["total_waiting"].sum(), -explained,
                       "services published for England only (safeguarding, looked after children)",
                       "monthly spreadsheet, National row"))
    return out


def population():
    la = pd.read_csv(PROCESSED_DIR / "population" / "local_authority.csv")
    lower = la[la["geography"].isin(["Unitary Authority", "Non-metropolitan District", "Metropolitan District", "London Borough"])]
    england = la[la["geography"] == "Country"]["population"].sum()
    return [row("population", "people, all council areas", "latest", lower["population"].sum(), england,
                against="ONS mid-year estimates (ENGLAND row)")]


# ---------------------------------------------------------------------------
# GP appointments: practice totals against NHS England's National Overview
# ---------------------------------------------------------------------------

def gpad():
    """Each month against NHS England's National Overview from the same publication it was read from
    (exact), and - reported, not failed - how far the newest publication has since revised it."""
    ours = pd.read_csv(PROCESSED_DIR / "gpad" / "practice_month.csv").groupby("month")["appointments"].sum()
    sources = json.loads((PROCESSED_DIR / "gpad" / "month_sources.json").read_text())
    overviews = {}

    def overview(publication):
        if publication not in overviews:
            page = GPAD_PAGE.format(month=pd.Period(publication, "M").strftime("%B-%Y").lower())
            _, url = newest_link([page], r"National Overview")
            path = download(url, PUBLISHED, name=f"gpad-national-overview-{publication}.csv")
            n = pd.read_csv(path, dtype=str)
            n["month"] = pd.to_datetime(n["APPOINTMENT_MONTH"], format="%b%Y").dt.strftime("%Y-%m")
            overviews[publication] = (n.assign(a=pd.to_numeric(n["APPOINTMENTS"])).groupby("month")["a"].sum(), path.name)
        return overviews[publication]

    newest = max(s["publication"] for s in sources.values())
    latest_totals, latest_name = overview(newest)
    out = []
    for month, total in ours.items():
        totals, name = overview(sources[month]["publication"])
        r = row("gpad", "appointments", month, total, totals[month], against=name)
        revised = latest_totals.get(month)
        if revised is not None and revised != totals[month]:
            r["note"] = (f"since revised by NHS England to {revised:,.0f} ({(revised / totals[month] - 1) * 100:+.2f}%) "
                         f"in {latest_name}; practice-level figures aren't republished")
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# DM01: people waiting and 6+ week waits, every test, against the Monthly Diagnostics Timeseries
# ---------------------------------------------------------------------------

def dm01():
    year = pd.Timestamp.today().year if pd.Timestamp.today().month >= 4 else pd.Timestamp.today().year - 1
    pages = [DM01_PAGE.format(start=y, end=(y + 1) % 100) for y in (year, year - 1)]
    _, url = newest_link(pages, r"^Monthly Diagnostics\W+Time series")
    path = download(url, PUBLISHED)
    book = xlrd.open_workbook(str(path))

    def series(sheet_name):
        sheet = book.sheet_by_name(sheet_name)
        header = next(i for i in range(sheet.nrows) if sheet.row_values(i)[1] == "Diagnostic ID")
        months = {j: (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))).strftime("%Y-%m")
                  for j, v in enumerate(sheet.row_values(header)) if isinstance(v, float)}
        out = {}
        for i in range(header + 1, sheet.nrows):
            r = sheet.row_values(i)
            test = "TOTAL" if r[2] == "Total" else DM01_TESTS[int(r[1]) - 1] if isinstance(r[1], float) else None
            if test:
                out.update({(test, m): r[j] for j, m in months.items() if isinstance(r[j], float)})
        return out

    waiting, six = series("Total Waiting List"), series("6+ Week Waits")
    ours = pd.read_csv(PROCESSED_DIR / "dm01" / "england_basis.csv")
    reason = "NONC: patients not commissioned by an English ICB (NHS England's DM01 England series leaves them out)"
    out = []
    for r in ours.itertuples():
        for measure, published, all_rows, nonc in (("people waiting", waiting, r.waiting_all, r.waiting_nonc),
                                                   ("waiting 6+ weeks", six, r.six_weeks_plus_all, r.six_weeks_plus_nonc)):
            label = f"{measure}" if r.test == "TOTAL" else f"{measure} ({r.test})"
            if (r.test, r.month) not in published:
                out.append({"source": "dm01", "measure": label, "period": r.month, "status": "NOT CHECKED",
                            "reason": "month not in the published timeseries"})
                continue
            out.append(row("dm01", label, r.month, all_rows, round(published[(r.test, r.month)]), nonc, reason, path.name))
    return out


# ---------------------------------------------------------------------------
# Winter sitreps: trusts' beds and ambulance handovers against each file's ENGLAND rows
# ---------------------------------------------------------------------------

def uec_sitreps():
    module = source_module("uec_sitreps")
    ours = pd.read_csv(PROCESSED_DIR / "uec_sitreps" / "trust_day.csv")
    out = []
    for winter in sorted(ours["winter"].unique()):
        days = ours[ours["winter"] == winter].groupby("date").sum(numeric_only=True)
        # Beds: "ENGLAND (All Acute Trusts)" in the Total G&A beds sheet.
        path = RAW_DIR / "uec_sitreps" / f"sitrep-{winter}.xlsx"
        rows = read_xlsx_rows(path, "Total G&A beds")
        at = next(i for i, r in enumerate(rows) if len(r) > 4 and r[3] == "Code" and r[4] == "Name")
        header = rows[at]
        england = next(r for r in rows[at + 1:] if len(r) > 4 and str(r[4]).startswith("ENGLAND (All"))
        for day, first, last in module.day_blocks(rows[at - 1], 5):
            cols = {header[c]: c for c in range(first, last) if c < len(header) and header[c]}
            open_col = next((c for h, c in cols.items() if h.startswith("Total G&A Beds Open")), None)
            occ_col = next((c for h, c in cols.items() if "occ" in h.lower()), None)
            if open_col is None or occ_col is None or day not in days.index:
                continue
            out.append(row("uec_sitreps", "G&A beds open", day, days.loc[day, "beds_open"], england[open_col],
                           against=f"{path.name} (ENGLAND (All Acute Trusts) row)"))
            out.append(row("uec_sitreps", "G&A beds occupied", day, days.loc[day, "beds_occupied"], england[occ_col],
                           against=f"{path.name} (ENGLAND (All Acute Trusts) row)"))
        # Handovers: "ENGLAND (All Trusts)"; the "Unknown" row is in England's total but under no trust.
        path = RAW_DIR / "uec_sitreps" / f"ambulance-{winter}.xlsx"
        sheet = next(sh for sh in xlsx_sheet_names(path) if "andovers" in sh)
        rows = read_xlsx_rows(path, sheet)
        at = next(i for i, r in enumerate(rows) if r and r[0] == "Region")
        header = rows[at]
        dates_row = next(r for r in rows[:at] if any(isinstance(x, (int, float)) for x in r[3:]))
        england = next(r for r in rows if len(r) > 2 and str(r[2]).startswith("ENGLAND"))
        unknown = next((r for r in rows[at + 1:] if len(r) > 2 and str(r[2]).strip() == "Unknown"), [])
        for day, first, last in module.day_blocks(dates_row, 3):
            cols = {}
            for c in range(first, last):
                if c < len(header) and header[c] and header[c] not in cols:
                    cols[header[c]] = c
            if day not in days.index:
                continue
            for heading, col in (("Handover time known", "handovers_known"), ("Over 30 minutes", "handovers_over_30"),
                                 ("Over 60 minutes", "handovers_over_60")):
                c = cols.get(heading)
                if c is None or c >= len(england):
                    continue
                explained = unknown[c] if c < len(unknown) and isinstance(unknown[c], (int, float)) else 0
                out.append(row("uec_sitreps", f"handovers: {heading.lower()}", day, days.loc[day, col], england[c],
                               -explained, "the Unknown row: handovers not assigned to a trust",
                               f"{path.name} (ENGLAND (All Trusts) row)"))
    return out


# ---------------------------------------------------------------------------
# Not checked, with the reason
# ---------------------------------------------------------------------------

NOT_CHECKED = {
    "talking_therapies": "the England figures are NHS England's own England row, used as published (nothing re-added)",
    "mhsds": "no England figure is quoted; provider figures only",
    "fft": "no England figure is quoted",
    "dental": "no monthly England headline is published to check against (NHSBSA official statistics are annual)",
    "workforce": "England figures are read directly from the published tables",
    "trials": "no published England total exists for clinical studies",
}


CHECKS = {"rtt": rtt, "dm01": dm01, "cancer": cancer, "ae": ae, "ers": ers, "ambulance": ambulance, "wlmds": wlmds,
          "community": community, "gpad": gpad, "uec_sitreps": uec_sitreps, "population": population}


def main():
    results = []
    for name, check in CHECKS.items():
        try:
            results += check()
        except FileNotFoundError as error:
            results.append({"source": name, "measure": "-", "period": "-", "status": "FAIL",
                            "reason": f"missing input: {error}"})
    for name, reason in NOT_CHECKED.items():
        results.append({"source": name, "measure": "-", "period": "-", "status": "NOT CHECKED", "reason": reason})

    table = pd.DataFrame(results)
    (PROCESSED_DIR / "reconciliation.json").write_text(json.dumps(results, indent=1, default=str))

    # The printed table: one line per source and measure, with the latest period in full.
    checked = table[table["status"].isin(["PASS", "FAIL"]) & table["measure"].ne("-")]
    lines = ["| Source | Measure | Periods | Exact | Latest | Ours | Published | Explained gap | Residual |",
             "|---|---|---|---|---|---|---|---|---|"]
    # Per-test DM01 lines are grouped under their measure; the latest line shown is the all-tests total.
    checked = checked.assign(group=checked["measure"].str.replace(r" \(.*\)$", "", regex=True))
    for (source, measure), g in checked.groupby(["source", "group"], sort=False):
        headline = g[g["measure"] == measure] if (g["measure"] == measure).any() else g
        latest = headline.sort_values("period").iloc[-1]
        label = measure + (" (each test and the total)" if len(g) > len(headline) else "")
        lines.append(f"| {source} | {label} | {len(g)} | {(g['status'] == 'PASS').sum()} | {latest['period']} | "
                     f"{latest['ours']:,.0f} | {latest['published']:,.0f} | {latest['explained']:+,.0f} | {latest['residual']:+,.0f} |")
    failures = table[table["status"] == "FAIL"]
    not_checked = table[(table["status"] == "NOT CHECKED") & table["measure"].eq("-")]
    report = ["# Reconciliation", "", f"{len(checked):,} checks: {(checked['status'] == 'PASS').sum():,} exact, "
              f"{len(failures):,} failed.", "", *lines, ""]
    if len(failures):
        report += ["## Failures", "", "| Source | Measure | Period | Ours | Published | Explained | Residual | Note |", "|---|---|---|---|---|---|---|---|"]
        report += [f"| {r.source} | {r.measure} | {r.period} | {r.ours} | {r.published} | {r.explained} | {r.residual} | {r.reason} |"
                   for r in failures.itertuples()]
        report.append("")
    noted = checked[checked.get("note", pd.Series(dtype=str)).notna()] if "note" in checked else checked.iloc[0:0]
    if len(noted):
        report += ["## Later revisions by the publisher (reported, not failed)", "",
                   "These figures match the publication they came from exactly; the publisher has since revised them.", "",
                   "| Source | Measure | Period | Ours (= published then) | Note |", "|---|---|---|---|---|"]
        report += [f"| {r.source} | {r.measure} | {r.period} | {r.ours:,.0f} | {r.note} |" for r in noted.itertuples()]
        report.append("")
    report += ["## Explained gaps", "",
               "- RTT: NONC - patients at English providers not commissioned by an English ICB. NHS England's England "
               "series is commissioner basis and leaves them out; our trust figures include them.",
               "- DM01: the same NONC patients; NHS England's DM01 England series leaves them out too.",
               "- Community services: three services are published for England only (adult safeguarding, children's "
               "safeguarding, looked after children teams).",
               "- Winter sitreps: the handover sheets' Unknown row (handovers not assigned to a trust) is in England's "
               "total but under no trust.", "",
               "## Not checked", ""] + [f"- {r.source}: {r.reason}" for r in not_checked.itertuples()]
    (PROCESSED_DIR / "reconciliation.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    if len(failures):
        print(f"\n!! RECONCILIATION FAILED: {len(failures)} figure(s) don't match the published England figures. "
              "Nothing should be published until they do.", file=sys.stderr)
        sys.exit(1)
    print("\nReconciliation passed: every checked England figure matches the published one exactly, or differs only "
          "by a documented, computed gap.")


if __name__ == "__main__":
    main()
