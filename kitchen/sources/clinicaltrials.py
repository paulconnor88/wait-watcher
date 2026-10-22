"""
kitchen/sources/clinicaltrials.py - ClinicalTrials.gov: every study with a site in the United Kingdom.

PRIVACY: contact names, emails and phone numbers are dropped as each page
arrives, before anything is saved. We never ask for the central contacts or
the overall officials; each location's "contacts" list and the sponsor's
"responsible party" (a named investigator) are deleted; and any email or
phone number left in free text (facility names, summaries) is removed.

What this script does, in plain English:
  LICENCE  Prints ClinicalTrials.gov's terms. They're not the Open Government
           Licence, but they allow free use and distribution of the data at no
           charge, on conditions much like attribution: say it's from
           ClinicalTrials.gov, keep it current, show the date it was processed,
           and say how it was changed. We treat that as equivalent (the
           conditions are recorded in kitchen/registry.json). The terms page
           is built by JavaScript, so the script finds the text in the page's
           script files; if it can't find it, it stops.
  FETCH    The API v2 (no key), 1,000 studies a page, following nextPageToken:
           every study with at least one location in the United Kingdom, any
           status. A full fetch happens if the last one was 28+ days ago (so
           the monthly run is always full); otherwise only studies updated
           since the last run (LastUpdatePostDate), merged into what we have.
           Kept in data/raw/clinicaltrials/studies.jsonl, one study a line,
           already stripped of contact details.
  CLEAN    One row per study: NCT ID, titles, brief summary, conditions and
           MeSH terms, interventions and their types, phase, study type,
           status, dates, enrolment target, lead sponsor and its class
           (industry / NIH / other...), collaborators, secondary IDs (with any
           ISRCTN and IRAS numbers picked out, for de-duplication), last
           update. One row per UK site: facility, city, postcode, site status.
  WRITE    data/processed/clinicaltrials/studies.csv
           data/processed/clinicaltrials/sites.csv
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/clinicaltrials.py        (add --full to force a full fetch)
"""

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (coverage_summary, fetch_url, get_page, processed_dir, raw_dir,  # noqa: E402
                    redact_all, stop_source, update_registry)

SOURCE = "clinicaltrials"
API = "https://clinicaltrials.gov/api/v2/studies"
TERMS_PAGE = "https://clinicaltrials.gov/about-site/terms-conditions"
TERMS_PHRASE = "Terms and Conditions apply for use of ClinicalTrials.gov data"
UK = 'AREA[LocationCountry]"United Kingdom"'
FIELDS = ",".join([
    "protocolSection.identificationModule", "protocolSection.statusModule",
    "protocolSection.sponsorCollaboratorsModule", "protocolSection.descriptionModule.briefSummary",
    "protocolSection.conditionsModule", "protocolSection.designModule.phases",
    "protocolSection.designModule.studyType", "protocolSection.designModule.enrollmentInfo",
    "protocolSection.armsInterventionsModule.interventions", "protocolSection.contactsLocationsModule.locations",
    "derivedSection.conditionBrowseModule.meshes", "derivedSection.conditionBrowseModule.ancestors"])
FULL_EVERY_DAYS = 28
RAW = raw_dir(SOURCE)
STORE = RAW / "studies.jsonl"
STATE = RAW / "state.json"
OUT = processed_dir(SOURCE)


# ---------------------------------------------------------------------------
# Licence
# ---------------------------------------------------------------------------

def terms_text():
    """The terms, from whichever of the page's script files holds them."""
    html = get_page(TERMS_PAGE)
    scripts = re.findall(r'src="([^"]+\.js)"', html)
    seen, queue = set(), [requests_url(s) for s in scripts]
    while queue and len(seen) < 120:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        text = fetch_url(url).text
        if TERMS_PHRASE in text:
            # The page text sits in the script as quoted strings: keep just those.
            start = text.index(TERMS_PHRASE)
            strings = re.findall(r'"([^"]{12,})"', text[start - 5:start + 6000])
            return re.sub(r"\s+", " ", " ".join(strings))
        queue += [requests_url(c) for c in re.findall(r'["(./]+(chunk-[A-Z0-9]+\.js)', text)]
    return None


def requests_url(path):
    return path if path.startswith("http") else "https://clinicaltrials.gov/" + path.lstrip("./")


def check_terms():
    print(f"\nLICENCE CHECK: {SOURCE}\n  {TERMS_PAGE}")
    text = terms_text()
    if not text:
        print("  => terms text not found")
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"no charge|attribute|current at all times|date the data|modifications|copyright|email",
                     sentence, re.I):
            print(f"  - {sentence.strip()[:300]}")
    is_free = "at no charge" in text and "Attribute the source" in text
    print("  => free use and distribution with attribution-style conditions - treated as equivalent to an open licence"
          if is_free else "  => terms changed - not ingesting")
    return is_free


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def strip_contacts(study):
    """Delete every contact's name, email and phone before the study is kept. Also keep only
    the UK locations (counting the rest), which keeps the store a tenth of the size."""
    module = study.get("protocolSection", {}).get("contactsLocationsModule", {})
    for key in ("centralContacts", "overallOfficials"):
        module.pop(key, None)
    study.get("protocolSection", {}).get("sponsorCollaboratorsModule", {}).pop("responsibleParty", None)  # a named person
    locations = module.get("locations", [])
    for location in locations:
        location.pop("contacts", None)
    if locations:
        module["locations"] = [loc for loc in locations if loc.get("country") == "United Kingdom"]
        module["locationsElsewhere"] = len(locations) - len(module["locations"])
    return redact_all(study)          # emails and phone numbers left in any free text


def fetch(query):
    """Every study matching the query, page by page."""
    studies, token, page = [], None, 0
    while True:
        url = f"{API}?filter.advanced={quote(query)}&pageSize=1000&fields={FIELDS}&countTotal=true"
        if token:
            url += f"&pageToken={token}"
        response = fetch_url(url, timeout=180)
        response.raise_for_status()
        data = response.json()
        if page == 0:
            print(f"  {data.get('totalCount', '?'):,} studies to fetch" if isinstance(data.get("totalCount"), int)
                  else "  fetching")
        studies += [strip_contacts(s) for s in data.get("studies", [])]
        page += 1
        token = data.get("nextPageToken")
        if not token:
            return studies


def nct(study):
    return study["protocolSection"]["identificationModule"]["nctId"]


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

def secondary_numbers(ids):
    """(ISRCTN, IRAS) picked out of the secondary IDs, if any."""
    isrctn = iras = None
    for item in ids:
        text = f"{item.get('id', '')} {item.get('domain', '')} {item.get('type', '')}"
        found = re.search(r"ISRCTN\s*(\d{8})", text, re.I)
        if found:
            isrctn = isrctn or f"ISRCTN{found.group(1)}"
        if re.search(r"\bIRAS\b", text, re.I):
            number = re.search(r"\b(\d{5,7})\b", item.get("id", ""))
            if number:
                iras = iras or number.group(1)
    return isrctn, iras


def study_row(study):
    p = study["protocolSection"]
    ident, status, sponsors = p["identificationModule"], p.get("statusModule", {}), p.get("sponsorCollaboratorsModule", {})
    design, derived = p.get("designModule", {}), study.get("derivedSection", {}).get("conditionBrowseModule", {})
    interventions = p.get("armsInterventionsModule", {}).get("interventions", [])
    secondary = ident.get("secondaryIdInfos", [])
    isrctn, iras = secondary_numbers(secondary)
    lead = sponsors.get("leadSponsor", {})
    return {
        "nct_id": ident["nctId"], "isrctn": isrctn, "iras": iras,
        "title": ident.get("briefTitle"), "official_title": ident.get("officialTitle"),
        "brief_summary": p.get("descriptionModule", {}).get("briefSummary"),
        "conditions": "; ".join(p.get("conditionsModule", {}).get("conditions", [])),
        "mesh_terms": "; ".join(m["term"] for m in derived.get("meshes", [])),
        "mesh_ancestors": "; ".join(m["term"] for m in derived.get("ancestors", [])),
        "interventions": "; ".join(i.get("name", "") for i in interventions),
        "intervention_types": "; ".join(sorted({i.get("type", "") for i in interventions if i.get("type")})),
        "phase": "; ".join(design.get("phases", [])), "study_type": design.get("studyType"),
        "overall_status": status.get("overallStatus"),
        "start_date": status.get("startDateStruct", {}).get("date"),
        "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
        "completion_date": status.get("completionDateStruct", {}).get("date"),
        "enrolment_target": design.get("enrollmentInfo", {}).get("count"),
        "enrolment_type": design.get("enrollmentInfo", {}).get("type"),
        "lead_sponsor": lead.get("name"), "sponsor_class": lead.get("class"),
        "collaborators": "; ".join(c.get("name", "") for c in sponsors.get("collaborators", [])),
        # Typed registry IDs only: free-text "OTHER" IDs can include a person's name.
        "secondary_ids": "; ".join(f"{s.get('id')} ({s.get('domain') or s.get('type')})" for s in secondary
                                   if s.get("type") != "OTHER" or re.search(r"IRAS|ISRCTN", str(s), re.I)),
        "last_update": status.get("lastUpdatePostDateStruct", {}).get("date"),
        "sites_outside_uk": p.get("contactsLocationsModule", {}).get("locationsElsewhere"),
    }


def site_rows(study):
    for location in study["protocolSection"].get("contactsLocationsModule", {}).get("locations", []):
        if location.get("country") == "United Kingdom":
            yield {"nct_id": nct(study), "facility": location.get("facility"), "city": location.get("city"),
                   "postcode": (location.get("zip") or "").upper().strip() or None, "site_status": location.get("status")}


def main():
    if not check_terms():
        return stop_source(SOURCE, "ClinicalTrials.gov terms not found or changed - check them by hand", "not checked")

    print("FETCH")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    store = {}
    if STORE.exists():
        for line in STORE.read_text().splitlines():
            study = json.loads(line)
            store[nct(study)] = study
    last_full = state.get("last_full")
    full = ("--full" in sys.argv or not store or not last_full
            or datetime.fromisoformat(last_full).date() < date.today() - timedelta(days=FULL_EVERY_DAYS))
    if full:
        print("  full fetch")
        store = {nct(s): s for s in fetch(UK)}
        state["last_full"] = date.today().isoformat()
    else:
        since = state["last_run"]
        print(f"  studies updated since {since}")
        for study in fetch(f"{UK} AND AREA[LastUpdatePostDate]RANGE[{since},MAX]"):
            store[nct(study)] = study
    state["last_run"] = date.today().isoformat()
    STORE.write_text("\n".join(json.dumps(s, separators=(",", ":")) for s in store.values()) + "\n")
    STATE.write_text(json.dumps(state, indent=1))

    print("CLEAN")
    studies = pd.DataFrame([study_row(s) for s in store.values()]).sort_values("nct_id")
    sites = pd.DataFrame([row for s in store.values() for row in site_rows(s)])
    studies.to_csv(OUT / "studies.csv", index=False)
    sites.to_csv(OUT / "sites.csv", index=False)
    print("  saved data/processed/clinicaltrials/studies.csv and sites.csv")

    years = sorted(studies["start_date"].dropna().str[:4].unique())
    update_registry(SOURCE, status="ingested", first_period=years[0], last_period=state["last_run"],
                    licence="ClinicalTrials.gov terms and conditions (free use; attribute ClinicalTrials.gov, keep "
                            "current, show the processing date, state modifications)",
                    note="Attribution: 'Source: ClinicalTrials.gov, processed <date>; reshaped by Wait Watcher (UK "
                         "sites only, contact details removed)'. Contact names, emails and phones are dropped at "
                         "fetch time. Weekly: updates since the last run; full fetch every 28 days.")
    recruiting = studies["overall_status"].eq("RECRUITING").sum()
    coverage_summary(SOURCE, len(studies), years, studies["nct_id"], match=False, notes=[
        f"UK sites:            {len(sites):,} ({sites['facility'].nunique():,} facility names)",
        f"recruiting now:      {recruiting:,} studies",
        f"with an ISRCTN:      {studies['isrctn'].notna().sum():,}; with an IRAS number: {studies['iras'].notna().sum():,}",
        f"sponsor classes:     " + ", ".join(f"{k} {v:,}" for k, v in studies["sponsor_class"].value_counts().items()),
        f"fetch:               {'full' if full else 'updates only'}; periods are study start years"])


if __name__ == "__main__":
    main()
