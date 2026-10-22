"""
kitchen/sources/ods.py - find where each provider and its sites are, for the map.

What this script does, in plain English:
  1. Downloads five lists from the NHS Organisation Data Service (ODS) and
     keeps copies in data/raw/ods/:
       - etr       NHS trusts
       - ect       NHS care trusts (a handful of trusts that also run social care)
       - ephp      independent sector healthcare providers (companies)
       - ephpsite  independent sector sites (individual clinics/hospitals)
       - ets       NHS trust sites (hospitals, clinics, health centres)
  2. For every provider code in history.csv, finds its name and postcode,
     trying the first four lists in that order and using the first record
     that has a postcode. (Independent providers often report waiting times
     per site, e.g. "NVC20" is The Yorkshire Clinic, a site of Ramsay Health
     Care "NVC", so many codes are only found in the site list.)
  3. Finds each provider's open sites: NHS trust sites from ets, and
     independent company sites from ephpsite. Sites that share a postcode
     (e.g. "LGT ENT AT QUEEN ELIZABETH HOSPITAL" and "QUEEN ELIZABETH
     HOSPITAL") are merged into one. A provider with no listed sites gets its
     own address as its only site. Two kinds of site are skipped, because
     they're someone else's hospital where this provider only runs a service:
       - a site at another NHS trust's main address (e.g. Lewisham and
         Greenwich lists King's College Hospital)
       - an NHS trust site that is also listed as an independent site AND is
         more than 30 miles from the trust's main address (e.g. Royal
         Berkshire lists The Wellington Hospital in London). Nearby ones are
         kept, because independent companies often run clinics inside a
         trust's own hospitals.
     Each site is then marked as a likely "treatment site" if it's within
     30 miles of the provider's main address and either:
       - it IS an NHS trust's main address, or
       - its name contains "HOSPITAL" or "TREATMENT CENTRE", it isn't a
         department at someone else's hospital ("GSTT @ LONDON BRIDGE
         HOSPITAL"), it doesn't look like a private hospital (listed as an independent site under
         the same name, or a private brand like Bupa, Nuffield or Spire in
         its name - unless the trust has several entries there, as owners
         do, e.g. Andover War Memorial Hospital also hosts an independent
         clinic of the same name), and - if any other NHS trust lists the
         same address - this trust has more entries there than any other.
         (The trust that owns a hospital lists dozens of departments at it;
         a visiting trust lists one or two. So Wexham Park counts for Frimley
         Health, not Royal Berkshire. A hospital that several trusts list
         equally, like Broadmoor or Skipton General, counts for none of them.)
     A provider with no such site has its main address marked instead.
     Other sites (clinics, health centres) are kept so the website can
     mention them.
  4. Looks up the latitude and longitude of every postcode using the free
     postcodes.io service (100 postcodes per request).
  5. Saves data/processed/locations.json, keyed by provider code, with each
     provider's sites. Each site keeps its town, so the website can search
     by place ("Winchester", "Andover").
  6. Reports how many provider codes have no location, and what share of
     the people waiting that represents.

Note: the ODS site lists include every place a trust runs services from,
including community clinics and health centres, not just hospitals.


Also (step 6): every provider in the waiting lists gets a type - "acute",
"specialist", "community", "mental health" or "independent" - added to
lookup.json. Independent means a provider that isn't in the ODS NHS trust
or care trust lists. NHS trusts are typed from their names, except the
trusts with 10,000+ waiting, which were checked by hand and are listed in
kitchen/provider_types.json (those always win).

Downloads are reused if they're less than a week old.

Run it with:   python kitchen/sources/ods.py   (after rtt.py)
"""

import json
import math
import re
import shutil
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (KITCHEN_DIR, PROJECT_DIR, SITE_DATA_DIR, coverage_summary, post_json,  # noqa: E402
                    processed_dir, raw_dir, update_registry)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

# The ODS lists to search for providers, in order of preference. URLs are
# linked from NHS England Digital's ODS download pages:
#   etr, ect, ets:  .../csv-downloads/other-nhs-organisations
#   ephp, ephpsite: .../csv-downloads/non-nhs-organisations
# (https://digital.nhs.uk/services/organisation-data-service/data-search-and-export/csv-downloads)
ODS_REPORT_URL = "https://www.odsdatasearchandexport.nhs.uk/api/getReport?report={name}"
PROVIDER_LISTS = {
    "etr": "NHS trust",
    "ect": "NHS care trust",
    "ephp": "independent provider",
    "ephpsite": "independent site",
}

# The ODS lists of sites. Each site row names its parent provider.
SITE_LISTS = ["ets", "ephpsite"]

# postcodes.io accepts up to 100 postcodes per request.
POSTCODES_URL = "https://api.postcodes.io/postcodes"
TERMINATED_POSTCODES_URL = "https://api.postcodes.io/terminated_postcodes"
BATCH_SIZE = 100

ODS_DIR = raw_dir("ods")
HISTORY_PATH = PROJECT_DIR / "data" / "processed" / "rtt" / "history.csv"
LOOKUP_PATH = PROJECT_DIR / "data" / "processed" / "rtt" / "lookup.json"
LOCATIONS_PATH = processed_dir("ods") / "locations.json"
HAND_CHECKED_TYPES = KITCHEN_DIR / "provider_types.json"
REUSE_DAYS = 7      # re-download the ODS lists if they're older than this

# Provider types from NHS trust names (hand-checked trusts override these).
MENTAL_HEALTH_WORDS = r"MENTAL HEALTH|PSYCHIATR|TAVISTOCK|LEARNING DISABIL|BRADFORD DISTRICT CARE"
COMMUNITY_WORDS = r"COMMUNITY|PARTNERSHIP|SOCIAL CARE"
SPECIALIST_WORDS = (r"ORTHOPAEDIC|CHILDREN|WOMEN|\bEYE\b|CANCER|CHRISTIE|CLATTERBRIDGE|MARSDEN|PAPWORTH|"
                    r"HEART AND CHEST|WALTON CENTRE|QUEEN VICTORIA HOSPITAL|GREAT ORMOND|ROYAL NATIONAL")

# The ODS files have no header row. These are the positions of the columns
# we need (counting from 0), from the ODS file specification. All five
# files share this layout.
CODE_COLUMN = 0
NAME_COLUMN = 1
TOWN_COLUMN = 7
POSTCODE_COLUMN = 9
CLOSE_DATE_COLUMN = 11
PARENT_COLUMN = 14   # site files only: the provider the site belongs to

# See step 3 in the description at the top.
FAR_FROM_HOME_MILES = 30
TREATMENT_SITE_WORDS = ["HOSPITAL", "TREATMENT CENTRE"]

# Words that mark a private hospital an NHS trust uses, rather than its own.
PRIVATE_HOSPITAL_WORDS = ["BUPA", "NUFFIELD", "SPIRE", "CAPIO", "CIRCLE", "RAMSAY",
                          "HCA", "BMI", "PRIVATE", "INDEPENDENT"]

HEADERS = {"User-Agent": "NHS-Wait-Watcher/0.1 (personal data project)"}


# ---------------------------------------------------------------------------
# Step 1: download the ODS lists
# ---------------------------------------------------------------------------

def download_ods_lists():
    """Download every list we need. Returns {report name: table}."""
    ODS_DIR.mkdir(parents=True, exist_ok=True)
    tables = {}

    for report in list(PROVIDER_LISTS) + [r for r in SITE_LISTS if r not in PROVIDER_LISTS]:
        url = ODS_REPORT_URL.format(name=report)
        path = ODS_DIR / f"{report}.csv"
        if path.exists() and time.time() - path.stat().st_mtime < REUSE_DAYS * 86400:
            print(f"Using {path.name} (downloaded in the last {REUSE_DAYS} days)")
        else:
            print(f"Downloading {url}")
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            path.write_bytes(response.content)

        # Read every column as text so codes like "R0A" stay as they are.
        table = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
        table[POSTCODE_COLUMN] = table[POSTCODE_COLUMN].str.strip()
        print(f"  {len(table):,} records")
        tables[report] = table

    return tables


# ---------------------------------------------------------------------------
# Step 2: match the provider codes from history.csv
# ---------------------------------------------------------------------------

def match_providers(tables, provider_codes):
    """Return one row per provider code that we found a postcode for.
    If a code appears in more than one list, the earlier list wins."""
    rows = []
    for report, source in PROVIDER_LISTS.items():
        table = tables[report]
        rows.append(pd.DataFrame({
            "code": table[CODE_COLUMN],
            "name": table[NAME_COLUMN],
            "postcode": table[POSTCODE_COLUMN],
            "town": table[TOWN_COLUMN],
            "source": source,
        }))
    providers = pd.concat(rows, ignore_index=True)

    providers = providers[(providers["postcode"] != "") & providers["code"].isin(provider_codes)]
    # Rows are already in order of preference, so keep the first per code.
    return providers.drop_duplicates("code", keep="first")


# ---------------------------------------------------------------------------
# Step 3: find each provider's sites
# ---------------------------------------------------------------------------

def site_name_preference(name):
    """When several sites share a postcode, we keep one name. Prefer names
    that look like a whole hospital ("QUEEN ELIZABETH HOSPITAL") over a
    department within one ("LGT ENT AT QUEEN ELIZABETH HOSPITAL"), then the
    shortest. Lower is better."""
    return (0 if looks_like_hospital(name) else 1, len(name))


def looks_like_hospital(name):
    """A whole hospital, not a department ("... AT ...", "... - A&E") or a
    made-up record ("P RBH VIRTUAL HOSPITAL")."""
    return ("HOSPITAL" in name and " AT " not in name and " @ " not in name
            and " - " not in name and "VIRTUAL" not in name)


def plain_name(name):
    """For comparing names: "THE PRINCESS MARGARET HOSPITAL" and
    "PRINCESS MARGARET HOSPITAL" should count as the same."""
    words = "".join(c if c.isalnum() else " " for c in name.upper()).split()
    return " ".join(word for word in words if word != "THE")


def find_sites(tables, matched):
    """Returns a table of open sites for the matched providers, one per
    postcode, with columns parent, name, postcode and two flags:
      also_independent  an NHS trust site also listed as an independent site
      visiting          this trust doesn't have more entries at this address
                        than every other NHS trust, so it's probably someone
                        else's building, or shared
    save_locations uses the flags to decide what to keep."""
    rows = []
    for report in SITE_LISTS:
        table = tables[report]
        is_open = table[CLOSE_DATE_COLUMN] == ""
        rows.append(pd.DataFrame({
            "parent": table.loc[is_open, PARENT_COLUMN],
            "name": table.loc[is_open, NAME_COLUMN],
            "postcode": table.loc[is_open, POSTCODE_COLUMN],
            "town": table.loc[is_open, TOWN_COLUMN],
            "list": report,
        }))
    sites = pd.concat(rows, ignore_index=True)

    sites = sites[(sites["postcode"] != "") & sites["parent"].isin(matched["code"])].copy()

    # How many entries each NHS trust has at each address, and the most any
    # trust has there. This counts every trust in the list, including ones
    # that don't report waiting times (e.g. West London NHS Trust, which runs
    # Broadmoor Hospital).
    all_trust_sites = tables["ets"][tables["ets"][CLOSE_DATE_COLUMN] == ""]
    entries = all_trust_sites.groupby([POSTCODE_COLUMN, PARENT_COLUMN]).size()
    most_entries = entries.groupby(level=0).max()
    # How many trusts share that top count at each address.
    trusts_at_top = entries[entries == entries.groupby(level=0).transform("max")].groupby(level=0).size()

    # Skip sites at another NHS trust's main address.
    main_address = dict(zip(matched["code"], matched["postcode"]))
    owner_of_postcode = {}
    for provider in matched[matched["source"].str.startswith("NHS")].itertuples():
        owner_of_postcode.setdefault(provider.postcode, set()).add(provider.code)
    at_someone_elses = sites.apply(
        lambda site: bool(owner_of_postcode.get(site["postcode"], set()) - {site["parent"]})
        and main_address.get(site["parent"]) != site["postcode"],
        axis=1,
    )
    print(f"Skipping {at_someone_elses.sum()} sites at another NHS trust's main address")
    sites = sites[~at_someone_elses].copy()

    # One site per postcode per provider, keeping the most hospital-like name.
    sites["preference"] = sites["name"].map(site_name_preference)
    sites = sites.sort_values(["parent", "postcode", "preference"])
    sites = sites.drop_duplicates(["parent", "postcode"])

    # Mark NHS trust sites with the same name and postcode as an independent site.
    independent = tables["ephpsite"]
    independent_places = set(zip(independent[NAME_COLUMN].map(plain_name), independent[POSTCODE_COLUMN]))
    sites["also_independent"] = (sites["list"] == "ets") & [
        (plain_name(name), postcode) in independent_places
        for name, postcode in zip(sites["name"], sites["postcode"])
    ]

    # How many entries this trust itself has at each site's address.
    sites["entries"] = [
        int(entries.get((postcode, parent), 0)) if listed == "ets" else 0
        for listed, parent, postcode in zip(sites["list"], sites["parent"], sites["postcode"])
    ]

    # Mark NHS trust sites where this trust isn't clearly the owner.
    sites["visiting"] = [
        listed == "ets"
        and not (entries.get((postcode, parent), 0) == most_entries.get(postcode, 0)
                 and trusts_at_top.get(postcode, 0) == 1)
        for listed, parent, postcode in zip(sites["list"], sites["parent"], sites["postcode"])
    ]
    return sites.drop(columns=["preference", "list"])


# ---------------------------------------------------------------------------
# Step 4: look up the postcodes
# ---------------------------------------------------------------------------

def look_up_postcodes(postcodes):
    """Returns {postcode: (latitude, longitude)} for every postcode that
    postcodes.io recognises."""
    unique = sorted(set(postcodes))
    found = {}

    for start in range(0, len(unique), BATCH_SIZE):
        batch = unique[start:start + BATCH_SIZE]
        if start % 2000 == 0:
            print(f"Looking up postcodes {start + 1:,}+ of {len(unique):,}")
        response = post_json(POSTCODES_URL, {"postcodes": batch})

        # Each answer has the postcode we asked about ("query") and either
        # the details or null if it wasn't recognised.
        for answer in response.json()["result"]:
            details = answer["result"]
            if details and details["latitude"] is not None:
                found[answer["query"]] = (details["latitude"], details["longitude"])

    # Postcodes that have been retired (e.g. when a building is redeveloped)
    # aren't in the main lookup, but postcodes.io still knows where they were.
    missing = [postcode for postcode in unique if postcode not in found]
    print(f"Checking {len(missing)} unrecognised postcodes against retired postcodes")
    for postcode in missing:
        response = requests.get(f"{TERMINATED_POSTCODES_URL}/{postcode}",
                                headers=HEADERS, timeout=30)
        if response.status_code == 200:
            details = response.json()["result"]
            found[postcode] = (details["latitude"], details["longitude"])

    return found


# ---------------------------------------------------------------------------
# Steps 5 & 6: save and report gaps
# ---------------------------------------------------------------------------

def miles_between(a, b):
    """Straight-line distance in miles between two (latitude, longitude) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def is_treatment_site(site, provider, home, place):
    """A likely treatment site - see step 3 at the top."""
    if home[0] is None or miles_between(home, place) > FAR_FROM_HOME_MILES:
        return False
    if provider.source.startswith("NHS") and site["postcode"] == provider.postcode:
        return True
    sounds_right = (any(word in site["name"] for word in TREATMENT_SITE_WORDS)
                    and " AT " not in site["name"] and " @ " not in site["name"])
    sounds_private = any(word in plain_name(site["name"]).split() for word in PRIVATE_HOSPITAL_WORDS)
    # Also listed as an independent site: only someone else's hospital if this
    # trust has just one entry there (an owner lists many departments).
    private_place = site["also_independent"] and site.get("entries", 0) <= 1
    return sounds_right and not sounds_private and not private_place and not site["visiting"]


def save_locations(matched, sites, coordinates):
    sites_by_provider = {parent: rows for parent, rows in sites.groupby("parent")}
    locations = {}
    skipped_far_independent = 0
    main_address_used = 0

    for provider in matched.sort_values("code").itertuples():
        latitude, longitude = coordinates.get(provider.postcode, (None, None))

        # The provider's own sites, or failing that its own address.
        if provider.code in sites_by_provider:
            site_rows = sites_by_provider[provider.code].to_dict("records")
        else:
            site_rows = [{"name": provider.name, "postcode": provider.postcode, "town": provider.town,
                          "also_independent": False, "visiting": False, "entries": 0}]

        provider_sites = []
        for site in site_rows:
            postcode = site["postcode"]
            if postcode not in coordinates:
                continue
            site_latitude, site_longitude = coordinates[postcode]
            # An independent hospital far from the trust's home isn't really its site.
            if (site["also_independent"] and latitude is not None
                    and miles_between((latitude, longitude), coordinates[postcode]) > FAR_FROM_HOME_MILES):
                skipped_far_independent += 1
                continue
            name = site["name"]
            # If an NHS trust's main address is only recorded as departments
            # (e.g. "P RBH AMU/HMU"), call it after the trust instead.
            if (provider.source.startswith("NHS") and postcode == provider.postcode
                    and not looks_like_hospital(name)):
                name = f"{provider.name} MAIN SITE"
            provider_sites.append({
                "name": name, "postcode": postcode, "town": site.get("town", ""),
                "latitude": site_latitude, "longitude": site_longitude,
                "treatment": is_treatment_site(site, provider, (latitude, longitude), coordinates[postcode]),
            })

        # No likely treatment site? Use the main address instead.
        if latitude is not None and not any(site["treatment"] for site in provider_sites):
            main_address_used += 1
            at_main_address = [site for site in provider_sites if site["postcode"] == provider.postcode]
            if at_main_address:
                at_main_address[0]["treatment"] = True
            else:
                provider_sites.append({"name": provider.name, "postcode": provider.postcode, "town": provider.town,
                                       "latitude": latitude, "longitude": longitude, "treatment": True})

        locations[provider.code] = {
            "name": provider.name,
            "postcode": provider.postcode,
            "town": provider.town,
            "latitude": latitude,
            "longitude": longitude,
            "source": provider.source,
            "sites": provider_sites,
        }

    # No spaces, to keep the file small for the website.
    LOCATIONS_PATH.write_text(json.dumps(locations, separators=(",", ":")))
    shutil.copy(LOCATIONS_PATH, SITE_DATA_DIR / "locations.json")
    print(f"Skipped {skipped_far_independent} NHS trust sites that are independent hospitals "
          f"over {FAR_FROM_HOME_MILES} miles from the trust")
    print(f"{main_address_used} providers have no hospital or treatment centre site within "
          f"{FAR_FROM_HOME_MILES} miles, so their main address is used")
    site_counts = pd.Series([len(l["sites"]) for l in locations.values()])
    print(f"\nSaved {len(locations)} providers to {LOCATIONS_PATH.relative_to(PROJECT_DIR)} "
          f"({LOCATIONS_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"  {site_counts.sum():,} sites in total; {(site_counts > 1).sum()} providers have more than one "
          f"(most: {site_counts.max()})")

    not_recognised = [code for code, l in locations.items() if l["latitude"] is None]
    if not_recognised:
        print(f"  Postcode not recognised by postcodes.io for: {', '.join(not_recognised)}")

    return locations


def report_gaps(history, locations):
    names = json.loads(LOOKUP_PATH.read_text())["providers"]

    located = {code for code, l in locations.items() if l["sites"]}
    all_codes = set(history["provider_code"])
    missing = sorted(all_codes - located)

    # Which providers are still reporting in the latest month?
    latest_month = history["month"].max()
    latest_codes = set(history.loc[history["month"] == latest_month, "provider_code"])
    missing_latest = [code for code in missing if code in latest_codes]

    # Where the located ones came from.
    sources = pd.Series([locations[code]["source"] for code in all_codes & located])

    print()
    print("=" * 70)
    print("LOCATION COVERAGE")
    print("=" * 70)
    print(f"Provider codes in history.csv:        {len(all_codes)}")
    print(f"  located:                            {len(all_codes) - len(missing)}")
    for source, count in sources.value_counts().items():
        print(f"    from {source + ':':<31} {count}")
    print(f"  NOT located:                        {len(missing)}")
    print(f"    of which still reporting in {latest_month}: {len(missing_latest)}")

    # What share of everyone waiting is at a provider we can't map?
    # (C_999 is the all-specialties total for each provider.)
    waiting = history[
        (history["month"] == latest_month)
        & (history["treatment_function_code"] == "C_999")
        & (history["rtt_part"] == "Incomplete Pathways")
    ]
    waiting_missing = waiting.loc[waiting["provider_code"].isin(missing), "total_patients"].sum()
    print(f"\nPeople waiting in {latest_month} at providers with no location: "
          f"{waiting_missing:,} of {waiting['total_patients'].sum():,} "
          f"({waiting_missing / waiting['total_patients'].sum():.2%})")

    if missing:
        print("\nProviders with no location:")
        for code in missing:
            note = "" if code in latest_codes else f"  (not reporting in {latest_month})"
            print(f"  {code:<7} {names.get(code, '')}{note}")


# ---------------------------------------------------------------------------
# Step 6: provider types, added to lookup.json
# ---------------------------------------------------------------------------

def provider_types(tables, provider_codes, names):
    """{code: type} for every provider in the waiting lists."""
    nhs = set(tables["etr"][CODE_COLUMN]) | set(tables["ect"][CODE_COLUMN])
    checked = json.loads(HAND_CHECKED_TYPES.read_text())["types"]
    types = {}
    for code in sorted(provider_codes):
        name = names.get(code, "").upper()
        if code in checked:
            types[code] = checked[code]["type"]
        elif code not in nhs:
            types[code] = "independent"
        elif re.search(MENTAL_HEALTH_WORDS, name):
            types[code] = "mental health"
        elif re.search(COMMUNITY_WORDS, name):
            types[code] = "community"
        elif re.search(SPECIALIST_WORDS, name):
            types[code] = "specialist"
        else:
            types[code] = "acute"
    return types


def save_types(types):
    lookup = json.loads(LOOKUP_PATH.read_text())
    lookup["provider_types"] = types
    LOOKUP_PATH.write_text(json.dumps(lookup, indent=2))
    shutil.copy(LOOKUP_PATH, SITE_DATA_DIR / "lookup.json")
    counts = pd.Series(list(types.values())).value_counts()
    print("\nProvider types added to lookup.json: " + ", ".join(f"{k} {v}" for k, v in counts.items()))


# ---------------------------------------------------------------------------
# Run everything
# ---------------------------------------------------------------------------

def main():
    if not HISTORY_PATH.exists():
        raise SystemExit("No history.csv yet - run kitchen/sources/rtt.py first.")
    history = pd.read_csv(HISTORY_PATH)
    provider_codes = set(history["provider_code"])
    names = json.loads(LOOKUP_PATH.read_text())["providers"]

    tables = download_ods_lists()
    matched = match_providers(tables, provider_codes)
    sites = find_sites(tables, matched)
    coordinates = look_up_postcodes(list(matched["postcode"]) + list(sites["postcode"]))
    locations = save_locations(matched, sites, coordinates)
    report_gaps(history, locations)
    save_types(provider_types(tables, provider_codes, names))
    update_registry("ods")
    coverage_summary("ods (locations)", sum(len(l["sites"]) for l in locations.values()), [],
                     [c for c, l in locations.items() if l["sites"]],
                     notes=[f"providers located:   {sum(1 for l in locations.values() if l['sites'])} "
                            f"(rows above are sites; ODS lists are current, not monthly)"])


if __name__ == "__main__":
    main()
