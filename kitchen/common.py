"""
kitchen/common.py - small helpers every source script shares.

  - where things live (raw downloads, processed data, the website's data)
  - downloading a file once, and finding links on a publisher's page
  - reading .xlsx / .xlsm spreadsheets with nothing but Python's own zip and
    XML readers (so we only need requests, beautifulsoup4 and pandas)
  - our provider codes, for matching other sources to the waiting lists
  - the registry (kitchen/registry.json): when each source was last fetched
  - the coverage summary every source prints at the end
"""

import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------

KITCHEN_DIR = Path(__file__).resolve().parent
PROJECT_DIR = KITCHEN_DIR.parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
SITE_DATA_DIR = PROJECT_DIR / "site" / "data"
REGISTRY_PATH = KITCHEN_DIR / "registry.json"

HEADERS = {"User-Agent": "Wait-Watcher/0.3 (personal data project)"}

MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december"]


def raw_dir(source):
    path = RAW_DIR / source
    path.mkdir(parents=True, exist_ok=True)
    return path


def processed_dir(source):
    path = PROCESSED_DIR / source
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_url(url, timeout=60, tries=4):
    """requests.get with a few retries: publishers' sites sometimes drop a
    connection, return a temporary server error, or say "too many requests"
    (429, e.g. ONS) - in which case we wait as long as they ask."""
    for attempt in range(1, tries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            if (response.status_code < 500 and response.status_code != 429) or attempt == tries:
                return response
            if response.status_code == 429:
                wait = response.headers.get("Retry-After", "")
                time.sleep(min(int(wait), 120) if wait.isdigit() else 20 * attempt)
                continue
        except requests.exceptions.RequestException:
            if attempt == tries:
                raise
        time.sleep(5 * attempt)


def post_json(url, payload, timeout=60, tries=4):
    """requests.post of some JSON, with the same retries as fetch_url (postcodes.io
    sometimes drops a connection part-way through a long run)."""
    for attempt in range(1, tries + 1):
        try:
            response = requests.post(url, json=payload, headers=HEADERS, timeout=timeout)
            if response.status_code < 500 or attempt == tries:
                response.raise_for_status()
                return response
        except requests.exceptions.RequestException:
            if attempt == tries:
                raise
        time.sleep(5 * attempt)


def get_page(url, allow_missing=False):
    """The HTML of a page, or None if it doesn't exist (and that's allowed)."""
    response = fetch_url(url)
    if allow_missing and response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def page_links(url, allow_missing=False):
    """Every link on a page, as (text, absolute url) pairs."""
    html = get_page(url, allow_missing)
    if html is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [(a.get_text(" ", strip=True), requests.compat.urljoin(url, a["href"]))
            for a in soup.find_all("a", href=True)]


def download(url, folder, name=None):
    """Download a file into `folder` unless it's already there. Returns its path.

    Publishers revise old months by posting a new file at a new address (e.g. "...-revised-2.zip"),
    while some scripts save files under a fixed name (e.g. "rtt-2025-08.zip"). So each folder keeps
    _sources.json, recording the address every file came from: if a name's address changes, the file
    is downloaded again. (A file saved before the manifest existed is assumed current and recorded.)"""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name or url.split("?")[0].rsplit("/", 1)[-1])
    manifest_path = folder / "_sources.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if path.exists() and path.stat().st_size > 0:
        if manifest.get(path.name, url) == url:
            if path.name not in manifest:
                manifest[path.name] = url
                manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
            return path
        print(f"  {path.name} has been revised at the source - downloading the new version")
    else:
        print(f"  downloading {path.name}")
    response = fetch_url(url, timeout=300)
    response.raise_for_status()
    path.write_bytes(response.content)
    manifest[path.name] = url
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return path


def month_key(year, month):
    return f"{year}-{month:02d}"


def months_back_to(first, last=None):
    """Every month from `last` (default: this month) back to `first`, newest
    first, as (year, month) pairs."""
    today = datetime.now()
    year, month = (today.year, today.month) if last is None else map(int, last.split("-"))
    first_year, first_month = map(int, first.split("-"))
    out = []
    while (year, month) >= (first_year, first_month):
        out.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out


# ---------------------------------------------------------------------------
# Reading .xlsx / .xlsm spreadsheets without extra libraries
# ---------------------------------------------------------------------------

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def xlsx_sheet_names(path):
    with zipfile.ZipFile(path) as z:
        book = ET.fromstring(z.read("xl/workbook.xml"))
    return [s.get("name") for s in book.find("m:sheets", _NS)]


def _column_index(reference):
    """"C12" -> 2 (columns counted from 0)."""
    letters = re.match(r"[A-Z]+", reference).group(0)
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def read_xlsx_rows(path, sheet):
    """All rows of one sheet as lists of values (text or numbers, None for
    blanks). An .xlsx is a zip of XML files: the workbook lists the sheets,
    each sheet is an XML file, and most text lives in a shared list."""
    with zipfile.ZipFile(path) as z:
        book = ET.fromstring(z.read("xl/workbook.xml"))
        target_id = next(s.get(f"{{{_NS['r']}}}id") for s in book.find("m:sheets", _NS) if s.get("name") == sheet)
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == target_id)
        sheet_path = "xl/" + target.lstrip("/").replace("xl/", "", 1)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for item in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in item.iter(f"{{{_NS['m']}}}t")))
        rows = []
        with z.open(sheet_path) as handle:
            for _, element in ET.iterparse(handle):
                if element.tag != f"{{{_NS['m']}}}row":
                    continue
                values = {}
                for cell in element.findall("m:c", _NS):
                    kind, raw = cell.get("t"), cell.find("m:v", _NS)
                    if kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t"))
                    elif raw is None:
                        continue
                    elif kind == "s":
                        value = shared[int(raw.text)]
                    elif kind in ("str", "e"):
                        value = raw.text
                    else:
                        try:
                            number = float(raw.text)
                            value = int(number) if number.is_integer() else number
                        except (TypeError, ValueError):
                            value = raw.text
                    values[_column_index(cell.get("r"))] = value
                if values:
                    rows.append([values.get(i) for i in range(max(values) + 1)])
                else:
                    rows.append([])
                element.clear()
    return rows


# ---------------------------------------------------------------------------
# Our provider codes (from the RTT waiting lists)
# ---------------------------------------------------------------------------

def our_provider_codes():
    """Every provider code in the RTT data, for matching other sources."""
    lookup = PROCESSED_DIR / "rtt" / "lookup.json"
    if not lookup.exists():
        raise SystemExit("data/processed/rtt/lookup.json is missing - run kitchen/sources/rtt.py first.")
    return set(json.loads(lookup.read_text())["providers"])


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def load_registry():
    return json.loads(REGISTRY_PATH.read_text())


def update_registry(source, **fields):
    """Record when a source was fetched (and anything else worth noting, e.g.
    first_period and last_period)."""
    registry = load_registry()
    entry = next(s for s in registry["sources"] if s["name"] == source)
    entry.update(fields)
    entry["last_fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")


def stop_source(source, reason, licence):
    """Record why a source isn't ingested, print it, and leave cleanly (so
    run_all.py carries on with the next source)."""
    update_registry(source, status="not ingested", licence=licence, reason=reason)
    print("\n" + "=" * 70)
    print(f"COVERAGE: {source}")
    print("=" * 70)
    print(f"  not ingested - {reason}")


# ---------------------------------------------------------------------------
# Privacy: free text from research registries
# ---------------------------------------------------------------------------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w-])(\+\d{1,3}[\s.-]?(\(0\))?\s?|\(?0)\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?![\w-])")
# A line that's just a "main contact" heading ("Who is the main contact?", "Main contact:",
# even "Whi is the main contact?"): everything from there to the end is cut.
MAIN_CONTACT = re.compile(r"^[ \t]*(wh\w*\s+(is|was|are|were)\s+(the\s+)?)?main\s+contacts?[ \t]*[?:]*[ \t]*$.*",
                          re.I | re.S | re.M)
CARE_OF = re.compile(r"\bc/o\s+[^,;\n]+[,;]?\s*", re.I)     # "C/O Jane Smith, ..." in addresses


def redact(text):
    """Free text with contact details taken out: ISRCTN summaries end with "Who is the main
    contact?" (a name and an email) - that section is cut - and any email address or phone
    number left anywhere is replaced with "[removed]"."""
    if not text:
        return text
    text = MAIN_CONTACT.sub("", text)
    text = CARE_OF.sub("", text)
    text = EMAIL.sub("[removed]", text)
    return PHONE.sub(lambda m: "[removed]" if 10 <= sum(ch.isdigit() for ch in m.group(0)) <= 13 else m.group(0), text)


def redact_all(value):
    """redact() applied to every piece of text in a nested dict / list."""
    if isinstance(value, dict):
        return {k: redact_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_all(v) for v in value]
    return redact(value) if isinstance(value, str) else value


# ---------------------------------------------------------------------------
# Licence check: every new source prints its licence before ingesting
# ---------------------------------------------------------------------------

OPEN_LICENCE = r"open government licen[cs]e|creative commons attribution|\bCC[ -]BY\b"


def check_licence(source, url, extra_open=None):
    """Fetch the page that states a source's licence, print the sentences
    about licensing, and say whether it's the Open Government Licence (or an
    equivalent open licence). Returns (is_open, the sentences found)."""
    from bs4 import BeautifulSoup
    html = get_page(url)
    text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" "))
    sentences = [s.strip()[:400] for s in re.split(r"(?<=[.!?])\s+", text)
                 if re.search(r"licen[cs]|copyright|re-?use|terms of use|attribution", s, re.I)]
    print(f"\nLICENCE CHECK: {source}\n  {url}")
    for sentence in sentences[:8]:
        print(f"  - {sentence}")
    pattern = OPEN_LICENCE + (f"|{extra_open}" if extra_open else "")
    is_open = bool(re.search(pattern, text, re.I))
    print(f"  => {'open licence found - ingesting' if is_open else 'NO open licence found'}")
    return is_open, sentences


# ---------------------------------------------------------------------------
# "Check before using": the 15-point jump rule, for any monthly percentage
# ---------------------------------------------------------------------------

def jump_flags(table, key, period, value, threshold=15, label="figure"):
    """{key: reason} for every key whose percentage `value` moved more than
    `threshold` points between consecutive periods, in the last 12 periods."""
    flags = {}
    periods = sorted(table[period].dropna().unique())[-13:]
    recent = table[table[period].isin(periods)].sort_values([key, period])
    for code, group in recent.groupby(key):
        moves = group[value].astype(float).diff().abs()
        if moves.max() > threshold:
            at = group.loc[moves.idxmax(), period]
            flags[code] = f"{label} moved {moves.max():.0f} points in a month (to {at})"
    return flags


# ---------------------------------------------------------------------------
# The coverage summary every source prints
# ---------------------------------------------------------------------------

def coverage_summary(source, rows, months, codes, notes=(), match=True):
    """Print rows, the period covered, and how many provider codes match ours
    (match=False for practices, areas or national figures)."""
    if not match:
        month_list = sorted(months)
        print()
        print("=" * 70)
        print(f"COVERAGE: {source}")
        print("=" * 70)
        print(f"  rows:                {rows:,}")
        print(f"  periods:             {len(month_list)}" + (f" ({month_list[0]} to {month_list[-1]})" if month_list else ""))
        print(f"  keys:                {len(set(codes)):,} (not provider codes, so not matched to ours)")
        for note in notes:
            print(f"  {note}")
        return {"rows": rows, "months": len(month_list), "codes": len(set(codes))}
    ours = our_provider_codes()
    codes = set(codes)
    matched, unmatched = codes & ours, codes - ours
    month_list = sorted(months)
    print()
    print("=" * 70)
    print(f"COVERAGE: {source}")
    print("=" * 70)
    print(f"  rows:                {rows:,}")
    print(f"  months:              {len(month_list)}" + (f" ({month_list[0]} to {month_list[-1]})" if month_list else ""))
    print(f"  provider codes:      {len(codes):,}")
    print(f"  matched to ours:     {len(matched):,} (of our {len(ours):,})")
    print(f"  unmatched:           {len(unmatched):,}" + (f"  e.g. {', '.join(sorted(unmatched)[:8])}" if unmatched else ""))
    for note in notes:
        print(f"  {note}")
    return {"rows": rows, "months": len(month_list), "codes": len(codes),
            "matched": len(matched), "unmatched": len(unmatched)}
