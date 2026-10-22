"""
kitchen/sources/cqc.py - add CQC inspection ratings to the hospitals on the site.

What this script does, in plain English:
  1. Opens CQC's "Using CQC data" page and finds this month's files:
       - "Care directory with ratings": every rating, including ratings
         for core services such as Surgery and Outpatients.
       - "Care directory with filters" (HSCA Active Locations): every
         registered location, with its ODS code, postcode and overall
         rating.
  2. Downloads them into data/raw/cqc/ and reads them. They're .ods
     spreadsheets; we read them directly (it's much faster than pandas).
  3. Matches each provider to CQC's provider-level rating by its ODS
     provider code (e.g. RN5 for Hampshire Hospitals) - never by name. CQC
     often leaves the ODS code blank for NHS trusts, but for them CQC's own
     Provider ID is the ODS code, so that's used instead.
     Then matches CQC locations to our providers' likely treatment sites
     (from data/processed/ods/locations.json):
       - by the location's own ODS code where CQC has one (most
         independent hospitals), else
       - by postcode, preferring a CQC location run by the same provider.
         "Same provider" is exact: CQC's Providers sheet gives each CQC
         Provider ID its ODS code, and every location names its Provider ID.
     A trust with no rating either way falls back to its most recently
     rated hospital, found the same exact way.
  4. Saves site/data/cqc.json (and a copy in data/processed/cqc/), keyed by
     provider code, with each matched site's overall rating, its Surgery
     and Outpatients ratings where available, the publication dates and a
     link to its CQC page.
  5. Prints how many providers and sites were matched, and every NHS trust
     with no match at all.

If the ratings file can't be downloaded (CQC's link was broken in October
2026), the script carries on with overall ratings from the active
locations file, and says so. Surgery and Outpatients ratings then show
as unavailable on the site.

Contains CQC information, used under the Open Government Licence.

Run it with:   python kitchen/sources/cqc.py   (after ods.py)
"""

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from pathlib import Path

import sys

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import PROJECT_DIR, coverage_summary, processed_dir, raw_dir, update_registry  # noqa: E402


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

CQC_DATA_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"
RATINGS_LINK_TEXT = "Care directory with ratings"
LOCATIONS_LINK_TEXT = "Care directory with filters"
LOCATION_PAGE = "https://www.cqc.org.uk/location/{location_id}"

RAW_DIR = raw_dir("cqc")
LOCATIONS_PATH = PROJECT_DIR / "data" / "processed" / "ods" / "locations.json"
LOOKUP_PATH = PROJECT_DIR / "data" / "processed" / "rtt" / "lookup.json"
SUMMARY_PATH = PROJECT_DIR / "data" / "processed" / "rtt" / "summary.json"
OUTPUT_PATHS = [PROJECT_DIR / "site" / "data" / "cqc.json",
                processed_dir("cqc") / "cqc.json"]

# Core services we keep. CQC used "Outpatients and diagnostic imaging"
# before 2018, so that counts as Outpatients too.
CORE_SERVICES = {
    "Surgery": "Surgery",
    "Outpatients": "Outpatients",
    "Outpatients and diagnostic imaging": "Outpatients",
}

# Words too common to help when comparing names.
COMMON_WORDS = {"THE", "AND", "OF", "NHS", "TRUST", "FOUNDATION", "LIMITED", "LTD", "PLC", "UK",
                "HOSPITAL", "HOSPITALS", "GROUP", "HEALTH", "HEALTHCARE", "CARE", "SERVICES"}

# CQC locations that are offices, not places people are treated.
OFFICE_WORDS = ["HEADQUARTERS", "HEAD OFFICE", "OFFICES", "ADMINISTRATION"]
# Words that make a name look like somewhere people are treated.
TREATMENT_PLACE_WORDS = ["HOSPITAL", "INFIRMARY", "MEDICAL CENTRE", "CLINIC", "TREATMENT CENTRE"]

# CQC values that mean "no rating to show".
UNRATED = {"", "No Approved Rating", "Not Rated", "Not rated"}

HEADERS = {"User-Agent": "Wait-Watcher/0.2 (personal data project)"}


# ---------------------------------------------------------------------------
# Step 1 & 2: find, download and read the files
# ---------------------------------------------------------------------------

def find_file_links():
    """Returns {link text we look for: url} from CQC's data page."""
    response = requests.get(CQC_DATA_PAGE, headers=HEADERS, timeout=60)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    links = {}
    for link in soup.find_all("a"):
        text = link.get_text(" ", strip=True)
        for wanted in (RATINGS_LINK_TEXT, LOCATIONS_LINK_TEXT):
            if text.startswith(wanted) and link.get("href", "").endswith(".ods") and wanted not in links:
                links[wanted] = link["href"]
    return links


def download(url):
    """Saves the file in data/raw/cqc/ and returns its path, or None if
    CQC's server doesn't have it."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / url.rsplit("/", 1)[-1]
    if path.exists():
        print(f"  {path.name}: already downloaded")
        return path
    print(f"  downloading {url}")
    response = requests.get(url, headers=HEADERS, timeout=300)
    if response.status_code != 200 or not response.content.startswith(b"PK"):
        print(f"  !! not available (HTTP {response.status_code})")
        return None
    path.write_bytes(response.content)
    return path


def read_ods_sheet(path, header_first_cell):
    """Reads the sheet whose header row starts with `header_first_cell`
    (e.g. "Location ID") and returns it as a table of text.

    An .ods file is a zip containing content.xml; we walk through it row by
    row with Python's built-in XML reader."""
    table_tag = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
    rows, header = [], None
    with zipfile.ZipFile(path) as archive, archive.open("content.xml") as content:
        for event, element in ET.iterparse(content, events=("end",)):
            if element.tag == table_tag + "table-row":
                row = []
                for cell in element:
                    if cell.tag in (table_tag + "table-cell", table_tag + "covered-table-cell"):
                        # Repeated empty cells are stored once with a count.
                        repeat = min(int(cell.get(table_tag + "number-columns-repeated", "1")), 500)
                        row.extend(["".join(cell.itertext()).strip()] * repeat)
                if header is None and row and row[0] == header_first_cell:
                    # Trim the empty columns that repeated cells add at the end.
                    while row and row[-1] == "":
                        row.pop()
                    header = row
                elif header is not None:
                    rows.append(row[:len(header)])
                element.clear()
            elif element.tag == table_tag + "table":
                if header is not None:
                    break  # finished the sheet we wanted
                element.clear()
    if header is None:
        raise SystemExit(f"Couldn't find a sheet starting with '{header_first_cell}' in {path.name}.")
    # Pad short rows so every row has a value for every column.
    return pd.DataFrame([row + [""] * (len(header) - len(row)) for row in rows], columns=header)


def iso_date(text):
    """'24/01/2024' -> '2024-01-24'. Blank if it isn't a date."""
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ""


def read_active_locations(path):
    table = read_ods_sheet(path, "Location ID")
    table = table[table["Location ID"] != ""]
    return pd.DataFrame({
        "location_id": table["Location ID"],
        "name": table["Location Name"],
        "ods_code": table["Location ODS Code"],
        "postcode": table["Location Postal Code"].str.upper().str.strip(),
        "provider_name": table["Provider Name"],
        "provider_id": table["Provider ID"],
        "overall": table["Location Latest Overall Rating"],
        "overall_date": table["Publication Date"].map(iso_date),
    })


def read_core_service_ratings(path):
    """From the ratings file: {location id: {"Surgery": {rating, date}, ...}}.
    Returns None if the file isn't laid out as expected."""
    table = read_ods_sheet(path, "Location ID")
    needed = ["Location ID", "Service / Population Group", "Domain", "Latest Rating", "Publication Date"]
    missing = [column for column in needed if column not in table.columns]
    if missing:
        print(f"  !! the ratings file has changed layout (missing {missing}); skipping core services")
        return None
    overall_domain = table[table["Domain"] == "Overall"]
    services = {}
    for location_id, group, rating, published in zip(
            overall_domain["Location ID"], overall_domain["Service / Population Group"],
            overall_domain["Latest Rating"], overall_domain["Publication Date"]):
        service = CORE_SERVICES.get(group)
        if service:
            services.setdefault(location_id, {})[service] = {"rating": rating, "date": iso_date(published)}
    return services


def read_provider_ratings(path):
    """From the ratings file's Providers sheet: each provider's overall rating,
    as {ODS code: {cqc_name, rating, date, url}}, and {CQC Provider ID: ODS
    code} for every provider listed. (None, {}) if the layout changed."""
    # (Locations whose provider isn't on this sheet - providers CQC hasn't
    # rated at provider level - fall back to the Provider ID itself below.)
    table = read_ods_sheet(path, "Provider ID")
    needed = ["Provider ID", "Provider ODS Code", "Provider Name", "Service / Population Group",
              "Domain", "Latest Rating", "Publication Date", "URL"]
    missing = [column for column in needed if column not in table.columns]
    if missing:
        print(f"  !! the Providers sheet has changed layout (missing {missing}); skipping provider ratings")
        return None, {}
    # The ODS code is often blank for NHS trusts - but for them CQC's own
    # Provider ID is the ODS code (R0A is Manchester University, RAE is
    # Bradford Teaching Hospitals), so use that when the ODS code is blank.
    table["ods"] = table["Provider ODS Code"].str.strip().str.upper()
    table["ods"] = table["ods"].where(table["ods"] != "", table["Provider ID"].str.strip().str.upper())
    id_to_ods = dict(zip(table["Provider ID"], table["ods"]))
    overall = table[(table["Service / Population Group"] == "Overall") & (table["Domain"] == "Overall")]
    by_code = {}
    for row in overall.to_dict("records"):
        by_code[row["ods"]] = {
            "cqc_name": row["Provider Name"], "rating": row["Latest Rating"] or "Not yet rated",
            "date": iso_date(row["Publication Date"]),
            "url": row["URL"] or f"https://www.cqc.org.uk/provider/{row['Provider ID']}"}
    return by_code, id_to_ods


def match_provider_ratings(locations, by_code):
    """Provider-level ratings, by ODS provider code only."""
    return {code: {**by_code[code], "matched_by": "ODS code"} for code in locations if code in by_code}


# ---------------------------------------------------------------------------
# Step 3: match CQC locations to our sites
# ---------------------------------------------------------------------------

def name_words(name):
    words = re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split()
    return {word for word in words if word not in COMMON_WORDS}


def similarity(a, b):
    """Share of distinctive words two names have in common (0 to 1)."""
    a, b = name_words(a), name_words(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def best_match(candidates, provider_code, site_name):
    """Pick the CQC location at a postcode that's most likely our site.
    Prefer a location run by the same provider (by ODS code, via CQC's
    Provider ID); then the most similar site name. Offices never count, and
    a location sharing no words with our site's name only counts if it
    sounds like somewhere people are treated."""
    is_office = candidates["name"].str.upper().map(lambda n: any(w in n for w in OFFICE_WORDS))
    candidates = candidates[~is_office]
    if candidates.empty:
        return None
    scored = candidates.assign(
        same_provider=candidates["provider_ods"] == provider_code,
        name_score=candidates["name"].map(lambda n: similarity(n, site_name)),
    ).sort_values(["same_provider", "name_score"], ascending=False)
    top = scored.iloc[0]
    sounds_like_treatment = any(w in top["name"].upper() for w in TREATMENT_PLACE_WORDS)
    if top["name_score"] == 0 and not sounds_like_treatment:
        return None
    if top["same_provider"] or top["name_score"] >= 0.5:
        return top
    return None


def rating_entry(site, cqc, services, matched_by):
    return {
        "site_name": site["name"],
        "site_postcode": site["postcode"],
        "location_id": cqc["location_id"],
        "cqc_name": cqc["name"],
        "url": LOCATION_PAGE.format(location_id=cqc["location_id"]),
        "matched_by": matched_by,
        "overall": {"rating": cqc["overall"] if cqc["overall"] not in UNRATED else "Not yet rated",
                    "date": cqc["overall_date"]},
        "services": (services or {}).get(cqc["location_id"], {}),
    }


def match_all(locations, cqc, services):
    by_ods = {code: row for code, row in zip(cqc["ods_code"], cqc.to_dict("records")) if code}
    by_postcode = {postcode: rows for postcode, rows in cqc.groupby("postcode")}
    matched = {}

    for code, provider in locations.items():
        entries = []
        # Independent sites report under their own ODS code.
        if code in by_ods:
            site = next((s for s in provider["sites"] if s["treatment"]), provider["sites"][0])
            entries.append(rating_entry(site, by_ods[code], services, "ODS code"))
        else:
            for site in provider["sites"]:
                if not site["treatment"]:
                    continue
                cqc_row = best_match(by_postcode.get(site["postcode"], pd.DataFrame(columns=cqc.columns)),
                                     code, site["name"])
                if cqc_row is not None:
                    entries.append(rating_entry(site, cqc_row, services, "postcode and name"))
        if entries:
            matched[code] = entries
    return matched


def same_trust_fallback(locations, cqc, matched, trust_ratings, services):
    """Last resort for NHS trusts with no trust rating and no rated site
    match: use the most recently rated hospital CQC lists under that trust
    (by ODS code, via CQC's Provider ID). So a large trust rarely shows
    "No rating found"."""
    added = 0
    for code, provider in locations.items():
        if not provider["source"].startswith("NHS") or code in trust_ratings:
            continue
        if any(e["overall"]["rating"] != "Not yet rated" for e in matched.get(code, [])):
            continue
        theirs = cqc[cqc["provider_ods"] == code]
        rated = theirs[~theirs["overall"].isin(UNRATED)]
        if rated.empty:
            continue
        rated = rated.assign(is_hospital=rated["name"].str.upper().str.contains("HOSPITAL"))
        row = rated.sort_values(["is_hospital", "overall_date"], ascending=False).iloc[0]
        site = {"name": row["name"].upper(), "postcode": row["postcode"]}
        matched.setdefault(code, []).append(rating_entry(site, row, services, "same trust"))
        added += 1
    print(f"  same-trust fallback used for {added} NHS trusts")


# ---------------------------------------------------------------------------
# Steps 4 & 5: save and report
# ---------------------------------------------------------------------------

def report_trusts(trust_ratings, matched, locations):
    """NHS trusts reporting waits, and which have no CQC rating at all."""
    summary = json.loads(SUMMARY_PATH.read_text())
    nhs = sorted(c for c in summary["providers"] if locations.get(c, {}).get("source", "").startswith("NHS"))
    with_trust = [c for c in nhs if c in trust_ratings]
    print()
    print("=" * 70)
    print("CQC PROVIDER-LEVEL RATINGS")
    print("=" * 70)
    print(f"NHS trusts reporting waits:        {len(nhs)}")
    print(f"  with a trust-level CQC rating:   {len(with_trust)} "
          f"({sum(trust_ratings[c]['matched_by'] == 'ODS code' for c in with_trust)} by ODS code)")
    gaps = [c for c in nhs if c not in trust_ratings]
    print(f"  with no trust-level rating:      {len(gaps)} (CQC hasn't published an overall rating for")
    print(f"                                   these; the site falls back to a hospital rating)")
    rated_site = lambda c: any(e["overall"]["rating"] != "Not yet rated" for e in matched.get(c, []))
    none_at_all = [c for c in gaps if not rated_site(c)]
    print(f"\nNHS trusts with NO CQC match at any level: {len(none_at_all)}")
    for code in none_at_all:
        print(f"    {code:<5} {locations[code]['name']}")
    return none_at_all


def report(matched, locations, core_services_available):
    summary = json.loads(SUMMARY_PATH.read_text())
    reporting = set(summary["providers"])
    waiting = {code: (t.get("C_999", {}).get("Incomplete Pathways", {}) or {}).get("total_patients", 0)
               for code, t in summary["providers"].items()}

    def kind(code):
        return "independent" if locations.get(code, {}).get("source", "").startswith("independent") else "NHS"

    print()
    print("=" * 70)
    print("CQC MATCH COVERAGE")
    print("=" * 70)
    for group in ["NHS", "independent"]:
        codes = [c for c in reporting if kind(c) == group]
        found = [c for c in codes if c in matched]
        rated = [c for c in found if any(e["overall"]["rating"] != "Not yet rated" for e in matched[c])]
        print(f"{group + ' providers reporting waits:':<36} {len(codes)}")
        print(f"  with a matched CQC location:       {len(found)} ({len(found) / len(codes):.0%})")
        print(f"  with an overall rating:            {len(rated)} ({len(rated) / len(codes):.0%})")
    covered = sum(waiting[c] for c in reporting if c in matched)
    print(f"\nPeople waiting at providers with a CQC match: {covered / sum(waiting.values()):.1%}")
    sites = [e for entries in matched.values() for e in entries]
    print(f"Matched sites: {len(sites)} ({sum(e['matched_by'] == 'ODS code' for e in sites)} by ODS code, "
          f"{sum(e['matched_by'] != 'ODS code' for e in sites)} by postcode and name)")
    if core_services_available:
        with_surgery = sum("Surgery" in e["services"] for e in sites)
        with_outpatients = sum("Outpatients" in e["services"] for e in sites)
        print(f"Sites with a Surgery rating: {with_surgery}; with an Outpatients rating: {with_outpatients}")
    else:
        print("Core service ratings (Surgery, Outpatients): NOT AVAILABLE this run - "
              "the ratings file couldn't be downloaded.")


def main():
    print(f"Reading {CQC_DATA_PAGE}")
    links = find_file_links()
    for wanted in (LOCATIONS_LINK_TEXT, RATINGS_LINK_TEXT):
        print(f"  {wanted}: {links.get(wanted, 'NOT FOUND')}")
    if LOCATIONS_LINK_TEXT not in links:
        raise SystemExit("Couldn't find the care directory file on CQC's page.")

    print("\nDownloading")
    locations_file = download(links[LOCATIONS_LINK_TEXT])
    ratings_file = download(links[RATINGS_LINK_TEXT]) if RATINGS_LINK_TEXT in links else None
    if locations_file is None:
        raise SystemExit("Couldn't download the care directory file.")

    print("\nReading (this takes about 20 seconds per file)")
    cqc = read_active_locations(locations_file)
    print(f"  {len(cqc):,} CQC locations")
    services = read_core_service_ratings(ratings_file) if ratings_file else None
    if services is not None:
        print(f"  core service ratings for {len(services):,} locations")

    locations = json.loads(LOCATIONS_PATH.read_text())
    by_code, id_to_ods = read_provider_ratings(ratings_file) if ratings_file else (None, {})
    cqc["provider_ods"] = cqc["provider_id"].map(id_to_ods).fillna(cqc["provider_id"].str.strip().str.upper())
    print(f"  {(cqc['provider_ods'] != '').sum():,} CQC locations linked to an ODS provider code")
    trust_ratings = match_provider_ratings(locations, by_code) if by_code is not None else {}
    print(f"  provider-level ratings matched for {len(trust_ratings):,} of our providers")
    matched = match_all(locations, cqc, services)
    same_trust_fallback(locations, cqc, matched, trust_ratings, services)

    output = {
        "_about": "CQC ratings for our providers' likely treatment sites. Contains CQC information, "
                  "used under the Open Government Licence.",
        "made_on": date.today().isoformat(),
        "source_files": [p.name for p in (locations_file, ratings_file) if p],
        "core_services_available": services is not None,
        "trusts": trust_ratings,
        "providers": matched,
    }
    for path in OUTPUT_PATHS:
        path.write_text(json.dumps(output, separators=(",", ":")))
    print(f"\nSaved {OUTPUT_PATHS[0].relative_to(PROJECT_DIR)} and {OUTPUT_PATHS[1].relative_to(PROJECT_DIR)}")

    report(matched, locations, services is not None)
    no_match = report_trusts(trust_ratings, matched, locations)
    update_registry("cqc", source_files=output["source_files"])
    coverage_summary("cqc", sum(len(v) for v in matched.values()) + len(trust_ratings), [],
                     set(matched) | set(trust_ratings), notes=[
                         f"trust-level ratings: {len(trust_ratings)} (by ODS provider code)",
                         f"providers with a site rating: {len(matched)}",
                         f"NHS trusts with no match at all: {len(no_match)}"])


if __name__ == "__main__":
    main()
