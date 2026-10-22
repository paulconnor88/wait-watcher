"""
kitchen/sources/trials.py - UK clinical studies from both registries, de-duplicated, with sites matched to providers.

Builds on clinicaltrials.py and isrctn.py (run those first). Nothing is
downloaded except postcode lookups (postcodes.io, Open Government Licence),
cached in data/raw/trials/postcodes.json.

What this script does, in plain English:
  1. DE-DUPLICATE  A study registered on both ClinicalTrials.gov and ISRCTN
     becomes one row. Records are linked when they share an ISRCTN number, an
     IRAS number, or when the ISRCTN record names the NCT number. Linked
     records are grouped (a chain of links counts), and the group keeps every
     ID, a "sources" column, and fields from ClinicalTrials.gov first, filled
     in from ISRCTN. (Summaries stay in each registry's own studies.csv, to
     keep this file well under GitHub's 100 MB limit.) study_id is the NCT number if there is one, else the
     ISRCTN number.
  2. SITES  One row per study and UK site (both registries, same site listed
     twice in one study counted once), matched to ODS codes, in this order,
     never guessing:
       override      kitchen/trial_site_overrides.json (hand-mapped)
       exact         facility name = an ODS site or trust name, and same postcode
                     (an NHS entry wins over an independent one with the same name)
       postcode      the postcode is an NHS trust's headquarters (that trust), or
                     belongs to just one NHS trust's sites in the ODS lists (and to
                     one of its sites, if there's a site to name)
       trust name    the name is exactly an NHS trust's name, give or take "NHS
                     (Foundation) Trust" - trust names are unique (confidence 0.95).
                     Checked before "postcode", so a named trust is never overruled
                     by whatever else shares its postcode.
       fuzzy         a very close name (similarity 0.9+, clearly better than any
                     rival) among ODS names in the same town. Independent providers
                     often have sites inside NHS hospitals with the same name, so an
                     NHS winner is only compared with NHS rivals. Names are compared
                     with and without "NHS (Foundation) Trust". ODS also lists one
                     trust's services at another trust's hospital under the same name;
                     such a tie is only broken if exactly one tied trust has its HQ
                     in the facility's postcode district, or is itself the named
                     match, or has its HQ at that hospital.
     Sites whose postcode is in Scotland, Wales or Northern Ireland are marked
     "outside England" (the ODS lists and our providers are England only).
     Placeholder names ("Research Site", "GSK Investigational Site", blank)
     are only matched by postcode, never by name.
     Each match has a method and a confidence (1.0, 0.95, 0.85 or 0.8, and
     for fuzzy 0.9 x similarity). Unmatched sites stay unmatched.
     ODS lists used: NHS trusts and trust sites (etr, ets), independent
     providers and sites (ephp, ephpsite) - the files ods.py downloads.
     Each site also gets its local authority from its postcode.
  3. CONDITIONS  Each study's MeSH terms (or condition text and disease class
     for ISRCTN-only studies) mapped to our treatment functions using the
     rules in kitchen/trial_condition_rules.json. Every distinct term and what
     it mapped to (or "unmapped") goes to condition_mapping.json for review.
  WRITE    data/processed/trials/studies.csv
           data/processed/trials/sites.csv
           data/processed/trials/condition_mapping.json
           data/processed/trials/unmatched_sites.csv  (most common first, for hand-mapping)
  REPORT   A coverage summary: studies in one registry or both, match rates
           by method, and the 30 most common unmatched facility names.

Run it with:   python kitchen/sources/trials.py
"""

import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (KITCHEN_DIR, PROCESSED_DIR, RAW_DIR, coverage_summary, our_provider_codes,  # noqa: E402
                    post_json, processed_dir, raw_dir, update_registry)

SOURCE = "trials"
OUT = processed_dir(SOURCE)
RAW = raw_dir(SOURCE)
POSTCODE_CACHE = RAW / "postcodes.json"
OVERRIDES = KITCHEN_DIR / "trial_site_overrides.json"
RULES = KITCHEN_DIR / "trial_condition_rules.json"
ODS_FILES = {"etr": "trust", "ets": "trust site", "ephp": "independent provider", "ephpsite": "independent site"}
CODE, NAME, TOWN, POSTCODE, CLOSED, PARENT = 0, 1, 7, 9, 11, 14     # ODS file columns (no header row)
FUZZY_MIN, FUZZY_CLEAR = 0.90, 0.04
NHS_KINDS = {"trust", "trust site"}
# Placeholder facility names that say nothing about where the site is (the postcode can still place them).
PLACEHOLDER = re.compile(r"^$|^(RESEARCH|CLINICAL|STUDY|TRIAL|INVESTIGATIONAL|INVESTIGATIVE|LOCAL)( \w+)* (SITE|INSTITUTION|CENTRE)( \d+)?$|"
                         r"INVESTIGATIONAL SITE|INVESTIGATIVE SITE|CLINICAL TRIAL SITE|RESEARCH SITE|LOCAL INSTITUTION|"
                         r"^FOR ADDITIONAL INFORMATION|^SITE \d+|^\d+$")
RECRUITING = {"RECRUITING", "Recruiting", "ENROLLING_BY_INVITATION"}
# Words too common to tell two places apart, ignored when finding fuzzy candidates.
GENERIC = {"THE", "OF", "AND", "NHS", "TRUST", "FOUNDATION", "HOSPITAL", "HOSPITALS", "UNIVERSITY", "ROYAL",
           "GENERAL", "DISTRICT", "COUNTY", "CENTRE", "CENTER", "HEALTH", "CARE", "HEALTHCARE", "SERVICES",
           "SERVICE", "INFIRMARY", "MEDICAL", "CLINIC", "ST", "SAINT", "NATIONAL", "COMMUNITY", "PARTNERSHIP",
           "TEACHING", "SITE", "RESEARCH", "UK", "LTD", "LIMITED", "UNIT", "DEPARTMENT", "PRACTICE"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def norm(name):
    """A facility name in one spelling: upper case, '&' as AND, no punctuation, common abbreviations spelt out."""
    name = str(name or "").upper().replace("&", " AND ")
    name = re.sub(r"[’'`]", "", name)
    name = re.sub(r"[^A-Z0-9 ]+", " ", name)
    for short, full in ((r"\bHOSP\b", "HOSPITAL"), (r"\bUNIV\b", "UNIVERSITY"), (r"\bSAINT\b", "ST"),
                        (r"\bNHS FT\b", "NHS FOUNDATION TRUST"), (r"\bCTR\b", "CENTRE"), (r"\bCENTER\b", "CENTRE")):
        name = re.sub(short, full, name)
    return re.sub(r"\s+", " ", name).strip()


def core(name):
    """A normalised name without the organisational suffix: "KINGS COLLEGE HOSPITAL NHS FOUNDATION TRUST"
    and "KINGS COLLEGE HOSPITAL" share the core "KINGS COLLEGE HOSPITAL"."""
    return " ".join(w for w in name.split() if w not in ("THE", "NHS", "FOUNDATION", "TRUST"))


def district(postcode):
    """The outward part of a postcode ("CB22QQ" -> "CB2")."""
    return postcode[:-3] if postcode else None


def norm_postcode(postcode):
    postcode = re.sub(r"\s+", "", str(postcode or "")).upper()
    return postcode if re.match(r"^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$", postcode) else None


def split(value):
    return [v.strip() for v in str(value).split(";") if v.strip()] if isinstance(value, str) else []


# ---------------------------------------------------------------------------
# 1. De-duplicate
# ---------------------------------------------------------------------------

def group_records(ct, isr):
    """Union-find over records linked by a shared ISRCTN, IRAS or NCT number."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a, b):
        parent[find(a)] = find(b)

    links = Counter()
    ct_keys = {f"CT:{r.nct_id}": r for r in ct.itertuples()}
    isr_keys = {f"IS:{r.isrctn}": r for r in isr.itertuples()}
    by_isrctn = {r.isrctn: k for k, r in isr_keys.items()}
    by_iras = defaultdict(list)
    for k, r in list(ct_keys.items()) + list(isr_keys.items()):
        find(k)
        if isinstance(r.iras, str) and r.iras.strip():
            by_iras[r.iras.strip()].append(k)
    for k, r in ct_keys.items():
        if isinstance(r.isrctn, str) and r.isrctn in by_isrctn:
            join(k, by_isrctn[r.isrctn])
            links["ISRCTN number"] += 1
    nct_keys = {r.nct_id: k for k, r in ct_keys.items()}
    for k, r in isr_keys.items():
        if isinstance(r.nct_id, str) and r.nct_id in nct_keys:
            join(k, nct_keys[r.nct_id])
            links["NCT number (in the ISRCTN record)"] += 1
    for keys in by_iras.values():
        if any(k.startswith("CT:") for k in keys) and any(k.startswith("IS:") for k in keys):
            links["IRAS number"] += 1
        for k in keys[1:]:
            join(k, keys[0])
    groups = defaultdict(list)
    for k in list(ct_keys) + list(isr_keys):
        groups[find(k)].append(k)
    return list(groups.values()), ct_keys, isr_keys, links


def first(*values):
    for v in values:
        if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip():
            return v
    return None


def status_group(status):
    status = str(status or "").upper().replace(" ", "_").replace(",", "")
    if status in ("RECRUITING", "ENROLLING_BY_INVITATION"):
        return "recruiting"
    if status in ("NOT_YET_RECRUITING",):
        return "not yet recruiting"
    if status in ("ACTIVE_NOT_RECRUITING", "ACTIVE_RECRUITMENT_COMPLETED"):
        return "active, not recruiting"
    if status in ("COMPLETED",):
        return "completed"
    if status in ("TERMINATED", "WITHDRAWN", "SUSPENDED", "STOPPED"):
        return "stopped"
    return "unknown"


def merged_rows(groups, ct_keys, isr_keys):
    rows, record_to_study = [], {}
    for keys in groups:
        cts = sorted((ct_keys[k] for k in keys if k.startswith("CT:")), key=lambda r: r.nct_id)
        iss = sorted((isr_keys[k] for k in keys if k.startswith("IS:")), key=lambda r: r.isrctn)
        c, i = (cts[0] if cts else None), (iss[0] if iss else None)
        g = lambda r, f: getattr(r, f, None) if r is not None else None
        study_id = c.nct_id if c is not None else i.isrctn
        # Status: from whichever record was updated most recently.
        newer = c if (c is not None and (i is None or str(g(c, "last_update")) >= str(g(i, "last_update")))) else i
        sponsor_class = first(g(c, "sponsor_class"), g(i, "sponsor_class"))
        rows.append({
            "study_id": study_id,
            "nct_id": "; ".join(r.nct_id for r in cts) or first(g(i, "nct_id")),
            "isrctn": "; ".join(r.isrctn for r in iss) or first(g(c, "isrctn")),
            "iras": first(g(c, "iras"), g(i, "iras")),
            "sources": "; ".join(s for s, rs in (("clinicaltrials.gov", cts), ("isrctn", iss)) if rs),
            "title": first(g(c, "title"), g(i, "title")),
            "conditions": first(g(c, "conditions"), g(i, "conditions")),
            "mesh_terms": g(c, "mesh_terms"), "mesh_ancestors": g(c, "mesh_ancestors"),
            "disease_classes": g(i, "disease_classes"),
            "interventions": first(g(c, "interventions"), g(i, "interventions")),
            "intervention_types": first(g(c, "intervention_types"), g(i, "intervention_types")),
            "phase": first(g(c, "phase"), g(i, "phase")),
            "study_type": first(g(c, "study_type"), g(i, "study_type")),
            "status": status_group(g(newer, "overall_status")), "status_as_registered": g(newer, "overall_status"),
            "start_date": first(g(c, "start_date"), g(i, "start_date")),
            "primary_completion_date": g(c, "primary_completion_date"),
            "completion_date": first(g(c, "completion_date"), g(i, "completion_date")),
            "enrolment_target": first(g(c, "enrolment_target"), g(i, "enrolment_target")),
            "lead_sponsor": first(g(c, "lead_sponsor"), g(i, "lead_sponsor")),
            "sponsor_class": sponsor_class,
            "industry_or_academic": "industry" if sponsor_class == "INDUSTRY" else "academic and other" if sponsor_class else None,
            "collaborators": first(g(c, "collaborators"), g(i, "funders")),
            "uk_nations": g(i, "uk_nations"),
            "last_update": max(str(g(r, "last_update") or "") for r in cts + iss),
        })
        for k in keys:
            record_to_study[k] = study_id
    return pd.DataFrame(rows), record_to_study


# ---------------------------------------------------------------------------
# 2. Sites
# ---------------------------------------------------------------------------

def ods_reference():
    """Every open ODS trust, trust site, independent provider and independent site - plus NHS trusts
    closed since April 2024 (e.g. North Bristol, merged in June 2026), so studies at recently merged
    trusts still match the trust our waiting-time history uses. Open entries come first, so they win ties."""
    rows = []
    for name, kind in ODS_FILES.items():
        table = pd.read_csv(RAW_DIR / "ods" / f"{name}.csv", header=None, dtype=str, keep_default_na=False)
        recently_closed = (table[CLOSED] >= "20240401") if kind == "trust" else False
        table = table[(table[CLOSED] == "") | recently_closed]
        for r in table.itertuples(index=False):
            trust = r[PARENT] if kind.endswith("site") else r[CODE]
            rows.append({"code": r[CODE], "trust_code": trust, "kind": kind, "name": r[NAME], "norm": norm(r[NAME]),
                         "town": norm(r[TOWN]), "postcode": norm_postcode(r[POSTCODE]), "closed": r[CLOSED] or None})
    table = pd.DataFrame(rows)
    return table.sort_values("closed", na_position="first", kind="stable").reset_index(drop=True)


class Matcher:
    """Matches one facility to an ODS code, in the agreed order, or not at all."""

    def __init__(self, ods, overrides):
        self.overrides = overrides
        self.ods = ods.set_index("code")
        self.exact = {}
        for r in ods.itertuples():                       # NHS lists come first, so they win
            if r.postcode:
                self.exact.setdefault((r.norm, r.postcode), r.code)
        self.hq_at = defaultdict(set)                    # postcode -> trusts headquartered there
        self.hq_district, self.hq_postcode, self.trust_names = {}, {}, defaultdict(set)
        for r in ods.itertuples():
            if r.kind == "trust":
                self.trust_names[core(r.norm)].add(r.code)
                if r.postcode:
                    self.hq_at[r.postcode].add(r.code)
                    self.hq_district[r.code] = district(r.postcode)
                    self.hq_postcode[r.code] = r.postcode
        self.by_postcode = defaultdict(list)
        for r in ods.itertuples():
            if r.postcode and r.kind in NHS_KINDS:
                self.by_postcode[r.postcode].append(r)
        self.by_town_token = defaultdict(set)
        self.rows = list(ods.itertuples())
        for i, r in enumerate(self.rows):
            for token in set(r.norm.split()) - GENERIC:
                self.by_town_token[(r.town, token)].add(i)

    def match(self, facility, city, postcode, nation=None):
        name, pc, town = norm(facility), norm_postcode(postcode), norm(city)
        if nation in ("Scotland", "Wales", "Northern Ireland"):
            return None, "outside England", None
        placeholder = bool(PLACEHOLDER.search(name))
        for key in (f"{name} | {pc}", name):
            if key in self.overrides:
                code = self.overrides[key]
                return (code, "override", 1.0) if code else (None, "override: unmatched", None)
        if not placeholder and pc and (name, pc) in self.exact:
            return self.exact[(name, pc)], "exact", 1.0
        # A facility named as an NHS trust is that trust, whatever else is at its postcode.
        named = self.trust_names.get(core(name), set()) if not placeholder else set()
        if len(named) == 1:
            return next(iter(named)), "trust name", 0.95
        if pc and len(self.hq_at.get(pc, ())) == 1:
            return next(iter(self.hq_at[pc])), "postcode", 0.85
        if pc and self.by_postcode.get(pc):
            here = self.by_postcode[pc]
            trusts = {r.trust_code for r in here}
            if len(trusts) == 1:
                sites = [r for r in here if r.kind.endswith("site")]
                if len(sites) == 1:
                    return sites[0].code, "postcode", 0.85
                if not sites:
                    return here[0].code, "postcode", 0.8
        if placeholder:
            return None, "unmatched: placeholder name", None
        if town and name:
            candidates = set()
            for token in set(name.split()) - GENERIC:
                candidates |= self.by_town_token.get((town, token), set())
            similar = lambda i: max(difflib.SequenceMatcher(None, name, self.rows[i].norm).ratio(),
                                    difflib.SequenceMatcher(None, core(name), core(self.rows[i].norm)).ratio())
            scored = sorted(((similar(i), i) for i in candidates), reverse=True)
            if scored and scored[0][0] >= FUZZY_MIN:
                top = scored[0][0]
                close = [(s, i) for s, i in scored if top - s < FUZZY_CLEAR]
                nhs_close = [(s, i) for s, i in close if self.rows[i].kind in NHS_KINDS]
                close = nhs_close or close                       # an NHS name wins over an independent one
                trusts = {self.rows[i].trust_code for _, i in close}
                # A tie between trusts (ODS lists services at another trust's hospital under its name):
                # broken only by one of these, in order, each picking exactly one trust.
                for keep in (
                        lambda t: pc and self.hq_district.get(t) == district(pc),          # HQ in the facility's district
                        lambda t: any(self.rows[i].code == t for _, i in close),           # the trust itself, by name
                        lambda t: any(self.rows[i].trust_code == t and self.rows[i].postcode == self.hq_postcode.get(t)
                                      for _, i in close)):                                  # the hospital is its HQ
                    if len(trusts) == 1:
                        break
                    chosen = {t for t in trusts if keep(t)}
                    if len(chosen) == 1:
                        trusts = chosen
                        close = [(s, i) for s, i in close if self.rows[i].trust_code in chosen]
                if len(trusts) == 1:
                    best_score, best = close[0]
                    return self.rows[best].code, "fuzzy", round(best_score * 0.9, 2)
        return None, "unmatched", None


SCOTLAND_AREAS = {"AB", "DD", "DG", "EH", "FK", "G", "HS", "IV", "KA", "KW", "KY", "ML", "PA", "PH", "ZE"}
WALES_AREAS = {"CF", "LD", "LL", "NP", "SA"}


def nation_from_area(postcode):
    area = re.match(r"^[A-Z]+", postcode or "")
    area = area.group(0) if area else None
    return ("Scotland" if area in SCOTLAND_AREAS else "Wales" if area in WALES_AREAS
            else "Northern Ireland" if area == "BT" else None)


def local_authorities(postcodes):
    """{postcode: local authority} from postcodes.io, cached between runs."""
    cache = json.loads(POSTCODE_CACHE.read_text()) if POSTCODE_CACHE.exists() else {}
    wanted = sorted({p for p in postcodes if p and p not in cache})
    for start in range(0, len(wanted), 100):
        batch = wanted[start:start + 100]
        for item in post_json("https://api.postcodes.io/postcodes", {"postcodes": batch}).json()["result"]:
            r = item["result"]
            cache[item["query"]] = [r.get("admin_district"), r.get("country")] if r else None
    POSTCODE_CACHE.write_text(json.dumps(cache))
    return cache


# ---------------------------------------------------------------------------
# 3. Conditions
# ---------------------------------------------------------------------------

def condition_mapper(treatment_names):
    rules = json.loads(RULES.read_text())
    compiled = [(re.compile(r["pattern"], re.I), r["tf"], r["pattern"]) for r in rules["rules"]]
    classes = {k: v for k, v in rules["disease_classes"].items() if not k.startswith("_")}
    seen = {}

    def map_term(term, field):
        key = (field, term)
        if key not in seen:
            hit = next(((tf, pattern) for rx, tf, pattern in compiled if rx.search(term)), None)
            if field == "disease class":
                hit = (classes[term], f"disease class '{term}'") if term in classes else None
            seen[key] = {"term": term, "field": field, "treatment_function": hit[0] if hit else None,
                         "treatment_function_name": treatment_names.get(hit[0]) if hit else None,
                         "method": f"{field} rule" if hit else "unmapped", "rule": hit[1] if hit else None,
                         "studies": 0}
        seen[key]["studies"] += 1
        return seen[key]["treatment_function"]

    def map_study(row):
        """Most specific evidence first: MeSH terms, then ancestors, then text, then disease class."""
        for field, terms in (("mesh term", split(row["mesh_terms"])), ("mesh ancestor", split(row["mesh_ancestors"])),
                             ("condition text", split(row["conditions"])), ("disease class", split(row["disease_classes"]))):
            found = {tf for tf in (map_term(t, field) for t in terms) if tf}
            if found:
                return "; ".join(sorted(found)), field
        return None, None

    return map_study, seen


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ct = pd.read_csv(PROCESSED_DIR / "clinicaltrials" / "studies.csv", dtype=str)
    isr = pd.read_csv(PROCESSED_DIR / "isrctn" / "studies.csv", dtype=str)
    ct_sites = pd.read_csv(PROCESSED_DIR / "clinicaltrials" / "sites.csv", dtype=str)
    isr_sites = pd.read_csv(PROCESSED_DIR / "isrctn" / "sites.csv", dtype=str)
    lookup = json.loads((PROCESSED_DIR / "rtt" / "lookup.json").read_text())

    print("DE-DUPLICATE")
    groups, ct_keys, isr_keys, links = group_records(ct, isr)
    studies, record_to_study = merged_rows(groups, ct_keys, isr_keys)
    both = studies["sources"].str.contains(";").sum()
    print(f"  {len(ct):,} ClinicalTrials.gov + {len(isr):,} ISRCTN records -> {len(studies):,} studies")

    print("CONDITIONS")
    map_study, mapping = condition_mapper(lookup["treatment_functions"])
    mapped = studies.apply(map_study, axis=1, result_type="expand")
    studies["treatment_functions"], studies["treatment_function_method"] = mapped[0], mapped[1]

    print("SITES")
    sites = pd.concat([
        ct_sites.assign(study_id=ct_sites["nct_id"].map(lambda n: record_to_study[f"CT:{n}"]), registry="clinicaltrials.gov"),
        isr_sites.assign(study_id=isr_sites["isrctn"].map(lambda n: record_to_study[f"IS:{n}"]), registry="isrctn"),
    ], ignore_index=True)
    sites["facility_norm"] = sites["facility"].map(norm)
    sites["postcode"] = sites["postcode"].map(norm_postcode)
    sites = (sites.sort_values("registry").groupby(["study_id", "facility_norm", sites["postcode"].fillna("")], as_index=False)
             .agg(facility=("facility", "first"), city=("city", "first"), postcode=("postcode", "first"),
                  site_status=("site_status", "first"), registries=("registry", lambda r: "; ".join(sorted(set(r))))))
    overrides = json.loads(OVERRIDES.read_text()).get("overrides", {})
    ods = ods_reference()
    matcher = Matcher(ods, overrides)
    places = local_authorities(sites["postcode"].dropna().unique())
    sites["local_authority"] = sites["postcode"].map(lambda p: (places.get(p) or [None])[0] if p else None)
    sites["nation"] = sites["postcode"].map(lambda p: (places.get(p) or [None, None])[1] if p else None)
    # Retired postcodes aren't found: fall back to postcode areas that lie wholly in one nation.
    sites["nation"] = sites["nation"].fillna(sites["postcode"].map(nation_from_area))
    unique = sites[["facility", "city", "postcode", "nation"]].drop_duplicates(["facility", "city", "postcode"])
    results = {(r.facility, r.city, r.postcode): matcher.match(r.facility, r.city, r.postcode, r.nation)
               for r in unique.itertuples()}
    matched = sites.apply(lambda r: results[(r["facility"], r["city"], r["postcode"])], axis=1, result_type="expand")
    sites["ods_code"], sites["match_method"], sites["match_confidence"] = matched[0], matched[1], matched[2]
    kinds = ods.set_index("code")
    sites["ods_kind"] = sites["ods_code"].map(kinds["kind"])
    sites["trust_code"] = sites["ods_code"].map(kinds["trust_code"])
    sites["ods_closed"] = sites["ods_code"].map(kinds["closed"])
    ours = our_provider_codes()
    sites["provider_code"] = sites["trust_code"].where(sites["trust_code"].isin(ours))
    sites = sites.drop(columns="facility_norm").merge(studies[["study_id", "status"]], on="study_id", how="left")

    # Where each study runs: recruiting UK site counts, matched providers.
    studies["uk_sites"] = studies["study_id"].map(sites.groupby("study_id").size()).fillna(0).astype(int)
    studies["providers"] = studies["study_id"].map(
        sites.dropna(subset=["provider_code"]).groupby("study_id")["provider_code"].agg(lambda c: "; ".join(sorted(set(c)))))
    studies["bepartofresearch_search"] = studies["study_id"].map(
        lambda s: f"https://bepartofresearch.nihr.ac.uk/results/search-results?query={s}")

    print("WRITE")
    studies.to_csv(OUT / "studies.csv", index=False)
    sites.to_csv(OUT / "sites.csv", index=False)
    review = sorted(mapping.values(), key=lambda m: (-m["studies"], m["term"]))
    (OUT / "condition_mapping.json").write_text(json.dumps(
        {"_about": "Every distinct condition term and the treatment function its rule gave it (kitchen/trial_condition_rules.json). "
                   "'studies' counts how often the term was looked at.", "terms": review}, indent=1))
    unmatched = sites[sites["match_method"] == "unmatched"]
    common = (unmatched.assign(name=unmatched["facility"].map(norm)).groupby("name")
              .agg(sites=("study_id", "size"), example_city=("city", "first"), example_postcode=("postcode", "first"))
              .sort_values("sites", ascending=False).reset_index())
    common.to_csv(OUT / "unmatched_sites.csv", index=False)
    print("  saved data/processed/trials/studies.csv, sites.csv, condition_mapping.json, unmatched_sites.csv")

    rates = sites["match_method"].value_counts()
    mapped_share = studies["treatment_functions"].notna().mean() * 100
    years = sorted(studies["start_date"].dropna().str[:4].unique())
    update_registry(SOURCE, status="built", licence="ClinicalTrials.gov terms; ISRCTN CC BY (see those sources)",
                    first_period=years[0], last_period=pd.Timestamp.today().strftime("%Y-%m-%d"),
                    note="Records linked by shared ISRCTN, IRAS or NCT number. Site matching never guesses: override, "
                         "exact name+postcode, single-trust postcode, then a close name in the same town.")
    coverage_summary(SOURCE, len(studies), years, sites["provider_code"].dropna().unique(), notes=[
        f"one registry only:   {(~studies['sources'].str.contains(';')).sum():,} "
        f"(ClinicalTrials.gov {(studies['sources'] == 'clinicaltrials.gov').sum():,}, ISRCTN {(studies['sources'] == 'isrctn').sum():,})",
        f"in both registries:  {both:,}  (links: " + ", ".join(f"{k} {v:,}" for k, v in links.items()) + ")",
        f"recruiting now:      {(studies['status'] == 'recruiting').sum():,}",
        f"study-sites:         {len(sites):,}",
        "matched, by method:  " + ", ".join(f"{m} {rates.get(m, 0):,} ({rates.get(m, 0) / len(sites) * 100:.1f}%)"
                                            for m in ("override", "exact", "postcode", "trust name", "fuzzy")),
        "not matched:         " + ", ".join(f"{m} {rates.get(m, 0):,} ({rates.get(m, 0) / len(sites) * 100:.1f}%)"
                                            for m in ("unmatched", "unmatched: placeholder name", "outside England",
                                                      "override: unmatched")),
        f"England match rate:  {sites['ods_code'].notna().sum() / (sites['match_method'] != 'outside England').sum() * 100:.0f}% "
        "of study-sites not outside England",
        f"matched to ours:     {sites['provider_code'].notna().sum():,} study-sites at {sites['provider_code'].nunique()} of our providers",
        f"with a local authority: {sites['local_authority'].notna().mean() * 100:.0f}% of study-sites",
        f"conditions mapped:   {mapped_share:.0f}% of studies have a treatment function",
        "30 most common unmatched facility names (for kitchen/trial_site_overrides.json):"]
        + [f"  {r.sites:>5,}  {r.name}  ({r.example_city}, {r.example_postcode or 'no postcode'})"
           for r in common.head(30).itertuples()])


if __name__ == "__main__":
    main()
