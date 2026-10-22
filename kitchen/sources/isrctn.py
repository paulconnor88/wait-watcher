"""
kitchen/sources/isrctn.py - the ISRCTN registry: every study recruiting, or that recruited, in the UK.

Contains information from the ISRCTN registry, licensed CC BY.

PRIVACY: contact names, emails and phone numbers are never stored. Each
trial arrives as XML with its contacts alongside; we pick out only the fields
below, so contacts never reach the disk. The plain English summary ends with
"Who is the main contact?" (a name and email): that part is cut, and any
email or phone number left anywhere (addresses, funders) is removed, as is
"c/o <name>" in addresses (common.redact_all). Free-text protocol numbers (which
sometimes include a person's name) are dropped too; only typed identifiers
(IRAS, NCT, CPMS, NIHR, EudraCT/CTIS) are kept.

What this script does, in plain English:
  LICENCE  Prints the ISRCTN FAQ's statement that study details can be used
           under a CC BY licence.
  FETCH    The public XML API, query: recruitment country is the United
           Kingdom, England, Scotland, Wales or Northern Ireland. The API has a
           "limit" but no paging, so the query is split by "last edited" date
           into windows small enough to come back whole (a window that's too
           big is halved). A full fetch happens if the last was 28+ days ago;
           otherwise only trials edited since the last run, merged in.
           Kept in data/raw/isrctn/trials.jsonl (already stripped).
  CLEAN    One row per study, the same fields as ClinicalTrials.gov where they
           exist: ISRCTN, IRAS and NCT numbers, titles, plain English summary,
           conditions (and disease class), interventions and type, phase,
           study type, status (worked out from the recruitment dates), dates,
           target enrolment, sponsor and whether commercial, funders, last
           update, and UK nations. One row per UK trial centre: name, address,
           city, postcode, nation.
  WRITE    data/processed/isrctn/studies.csv
           data/processed/isrctn/sites.csv
  REPORT   A coverage summary.

Run it with:   python kitchen/sources/isrctn.py        (add --full to force a full fetch)
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (check_licence, coverage_summary, fetch_url, processed_dir, raw_dir,  # noqa: E402
                    redact_all, stop_source, update_registry)

SOURCE = "isrctn"
API = "https://www.isrctn.com/api/query/format/default?q={q}&limit={limit}"
LICENCE_PAGE = "https://www.isrctn.com/page/faqs"
ATTRIBUTION = "Contains information from the ISRCTN registry, licensed CC BY"
NATIONS = ["England", "Scotland", "Wales", "Northern Ireland"]
UK = "(" + " OR ".join(f'recruitmentCountry:"{c}"' for c in ["United Kingdom"] + NATIONS) + ")"
LIMIT = 2000
FULL_EVERY_DAYS = 28
NS = {"i": "http://www.67bricks.com/isrctn"}
KEEP_NUMBER_TYPES = {"iras", "nct", "cpms", "nihr", "euctr", "ctis", "eudract"}
RAW = raw_dir(SOURCE)
STORE = RAW / "trials.jsonl"
STATE = RAW / "state.json"
OUT = processed_dir(SOURCE)


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def stamp(day):
    return f"{day.isoformat()}T00:00:00.000Z"


def query(extra=""):
    q = UK + (f" AND {extra}" if extra else "")
    response = fetch_url(API.format(q=quote(q), limit=LIMIT), timeout=300)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    return int(root.get("totalCount", 0)), [parse(t) for t in root.findall("i:fullTrial", NS)]


def fetch_window(start, end):
    """Every trial last edited in [start, end), halving the window if it's too big."""
    total, trials = query(f"lastEdited GE {stamp(start)} AND lastEdited LT {stamp(end)}")
    if total <= len(trials):
        return trials
    if (end - start).days <= 1:
        raise SystemExit(f"more than {LIMIT} trials edited on {start} - raise LIMIT")
    middle = start + (end - start) / 2
    return fetch_window(start, middle) + fetch_window(middle, end)


def text(element, path):
    found = element.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else None


def texts(element, path):
    return [(e.text or "").strip() for e in element.findall(path, NS) if e.text and e.text.strip()]


def parse(full):
    """One trial as a dict of the fields we keep - contacts are simply never read."""
    trial = full.find("i:trial", NS)
    refs = trial.find("i:externalRefs", NS)
    numbers = {}
    for n in (refs.findall("i:secondaryNumbers/i:secondaryNumber", NS) if refs is not None else []):
        kind = (n.get("numberType") or "").lower()
        if kind in KEEP_NUMBER_TYPES and n.text:
            numbers.setdefault(kind, n.text.strip())
    centres = [{"name": text(c, "i:name"), "address": re.sub(r"\s+", " ", text(c, "i:address") or "") or None,
                "city": text(c, "i:city"), "postcode": (text(c, "i:zip") or "").upper() or None,
                "country": text(c, "i:country")}
               for c in trial.findall("i:participants/i:trialCentres/i:trialCentre", NS)]
    sponsor = full.find("i:sponsor", NS)
    return redact_all({
        "isrctn": "ISRCTN" + text(trial, "i:isrctn"),
        "iras": (text(refs, "i:irasNumber") if refs is not None else None) or numbers.get("iras"),
        "nct_id": (text(refs, "i:clinicalTrialsGovNumber") if refs is not None else None) or numbers.get("nct"),
        "other_ids": "; ".join(f"{k.upper()} {v}" for k, v in numbers.items() if k not in ("iras", "nct")),
        "title": text(trial, "i:trialDescription/i:title"),
        "scientific_title": text(trial, "i:trialDescription/i:scientificTitle"),
        "summary": text(trial, "i:trialDescription/i:plainEnglishSummary"),
        "conditions": texts(trial, "i:conditions/i:condition/i:description"),
        "disease_classes": texts(trial, "i:conditions/i:condition/i:diseaseClass1"),
        "interventions": texts(trial, "i:interventions/i:intervention/i:drugNames"),
        "intervention_types": sorted(set(texts(trial, "i:interventions/i:intervention/i:interventionType"))),
        "phases": sorted(set(texts(trial, "i:interventions/i:intervention/i:phase"))),
        "study_type": text(trial, "i:trialDesign/i:primaryStudyDesign"),
        "recruitment_start": text(trial, "i:participants/i:recruitmentStart"),
        "recruitment_end": text(trial, "i:participants/i:recruitmentEnd"),
        "overall_end": text(trial, "i:trialDesign/i:overallEndDate"),
        "status_override": text(trial, "i:participants/i:recruitmentStatusOverride"),
        "target_enrolment": text(trial, "i:participants/i:targetEnrolment"),
        "countries": texts(trial, "i:participants/i:recruitmentCountries/i:country"),
        "centres": centres,
        "sponsor": text(sponsor, "i:organisation") if sponsor is not None else None,
        "commercial": text(sponsor, "i:commercialStatus") if sponsor is not None else None,
        "funders": texts(full, "i:funder/i:name"),
        "last_update": trial.get("lastUpdated"),
    })


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

def status_of(t, today):
    """Recruiting / not yet recruiting / completed, from the recruitment dates (as ISRCTN shows it)."""
    if t["status_override"]:
        return t["status_override"]
    start, end, overall = (t[k][:10] if t[k] else None for k in ("recruitment_start", "recruitment_end", "overall_end"))
    if start and start > today:
        return "Not yet recruiting"
    if end and end >= today:
        return "Recruiting"
    if overall and overall >= today:
        return "Active, recruitment completed"
    return "Completed"


def study_row(t, today):
    nations = [c for c in t["countries"] if c in NATIONS]
    return {
        "isrctn": t["isrctn"], "iras": t["iras"], "nct_id": t["nct_id"], "other_ids": t["other_ids"],
        "title": t["title"], "scientific_title": t["scientific_title"], "summary": t["summary"],
        "conditions": "; ".join(t["conditions"]), "disease_classes": "; ".join(sorted(set(t["disease_classes"]))),
        "interventions": "; ".join(t["interventions"]), "intervention_types": "; ".join(t["intervention_types"]),
        "phase": "; ".join(t["phases"]), "study_type": t["study_type"], "overall_status": status_of(t, today),
        "start_date": (t["recruitment_start"] or "")[:10] or None, "recruitment_end": (t["recruitment_end"] or "")[:10] or None,
        "completion_date": (t["overall_end"] or "")[:10] or None, "enrolment_target": t["target_enrolment"],
        "lead_sponsor": t["sponsor"], "sponsor_class": {"Commercial": "INDUSTRY", "Non-commercial": "OTHER"}.get(t["commercial"]),
        "funders": "; ".join(t["funders"]), "uk_nations": "; ".join(nations) or ("United Kingdom" if "United Kingdom" in t["countries"] else None),
        "last_update": (t["last_update"] or "")[:10],
    }


def site_rows(t):
    for c in t["centres"]:
        if c["country"] in NATIONS + ["United Kingdom", "UK"]:
            yield {"isrctn": t["isrctn"], "facility": c["name"], "address": c["address"], "city": c["city"],
                   "postcode": c["postcode"], "nation": c["country"]}


def main():
    is_open, _ = check_licence(SOURCE, LICENCE_PAGE)
    if not is_open:
        return stop_source(SOURCE, "no CC BY statement found on the ISRCTN FAQ", "not open")

    print("FETCH")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    store = {}
    if STORE.exists():
        for line in STORE.read_text().splitlines():
            trial = json.loads(line)
            store[trial["isrctn"]] = trial
    today = date.today()
    last_full = state.get("last_full")
    full = ("--full" in sys.argv or not store or not last_full
            or datetime.fromisoformat(last_full).date() < today - timedelta(days=FULL_EVERY_DAYS))
    if full:
        total, _ = query()
        print(f"  full fetch: {total:,} UK trials")
        store = {}
        for year in range(2000, today.year + 1):        # one window per year, halved as needed
            start, end = date(year, 1, 1), date(year + 1, 1, 1)
            for trial in fetch_window(start, end):
                store[trial["isrctn"]] = trial
        _, older = query(f"lastEdited LT {stamp(date(2000, 1, 1))}")
        store.update({t["isrctn"]: t for t in older})
        if len(store) < total:
            raise SystemExit(f"fetched {len(store):,} of {total:,} trials - windows missed some")
        state["last_full"] = today.isoformat()
    else:
        since = date.fromisoformat(state["last_run"])
        changed = fetch_window(since - timedelta(days=1), today + timedelta(days=1))
        print(f"  {len(changed):,} trials edited since {since}")
        store.update({t["isrctn"]: t for t in changed})
    state["last_run"] = today.isoformat()
    STORE.write_text("\n".join(json.dumps(t, separators=(",", ":")) for t in store.values()) + "\n")
    STATE.write_text(json.dumps(state, indent=1))

    print("CLEAN")
    iso = today.isoformat()
    studies = pd.DataFrame([study_row(t, iso) for t in store.values()]).sort_values("isrctn")
    sites = pd.DataFrame([row for t in store.values() for row in site_rows(t)])
    studies.to_csv(OUT / "studies.csv", index=False)
    sites.to_csv(OUT / "sites.csv", index=False)
    print("  saved data/processed/isrctn/studies.csv and sites.csv")

    years = sorted(studies["start_date"].dropna().str[:4].unique())
    update_registry(SOURCE, status="ingested", licence="CC BY (ISRCTN FAQ: study details usable under a CC-BY licence)",
                    first_period=years[0], last_period=iso,
                    note=f"Attribution: '{ATTRIBUTION}'. Contacts and free-text protocol numbers are never stored. "
                         "Status is worked out from recruitment dates, as on the ISRCTN site.")
    coverage_summary(SOURCE, len(studies), years, studies["isrctn"], match=False, notes=[
        f"UK centres:          {len(sites):,} ({sites['facility'].nunique():,} names, "
        f"{sites['postcode'].notna().mean() * 100:.0f}% with a postcode)",
        f"recruiting now:      {(studies['overall_status'] == 'Recruiting').sum():,}",
        f"with IRAS / NCT:     {studies['iras'].notna().sum():,} / {studies['nct_id'].notna().sum():,}",
        "nations:             " + ", ".join(f"{n} {studies['uk_nations'].fillna('').str.contains(n).sum():,}" for n in NATIONS),
        f"attribution:         {ATTRIBUTION}"])


if __name__ == "__main__":
    main()
