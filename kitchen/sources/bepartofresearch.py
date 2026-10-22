"""
kitchen/sources/bepartofresearch.py - Be Part of Research: link patterns only. Nothing is scraped.

Be Part of Research (NIHR) is where the public finds studies to join. We
don't copy anything from it (its terms ask you to contact them before
copying any material); we only want to link to it.

What this script does, in plain English:
  TERMS    Fetches and prints the site's terms about linking ("You may link to
           the Be Part of Research website...").
  CHECK    Fetches the search page once to confirm it's there.
  WRITE    data/processed/bepartofresearch/link_patterns.json:
             - a study page is .../trial-details/trial-detail?trialId=<N>, but
               N is Be Part of Research's own number, not an NCT, ISRCTN, IRAS
               or CPMS ID - so we can't build it from the IDs we hold.
             - a search link works for any study ID we hold:
               .../results/search-results?query=<study ID>
           kitchen/sources/trials.py adds that search link to every study
           (column bepartofresearch_search).

Run it with:   python kitchen/sources/bepartofresearch.py
"""

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import fetch_url, get_page, processed_dir, update_registry  # noqa: E402

SOURCE = "bepartofresearch"
SITE = "https://bepartofresearch.nihr.ac.uk"
TERMS = SITE + "/site-policies/terms-and-conditions/"
SEARCH = SITE + "/results/search-results?query={study_id}"
OUT = processed_dir(SOURCE)


def main():
    text = re.sub(r"\s+", " ", BeautifulSoup(get_page(TERMS), "html.parser").get_text(" "))
    print(f"\nTERMS: {SOURCE}\n  {TERMS}")
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\blink|copy or use|owned by", sentence, re.I):
            print(f"  - {sentence.strip()[:300]}")
    search_ok = fetch_url(SEARCH.format(study_id="ISRCTN")).status_code == 200
    patterns = {
        "study_page": {"exists_for_public_ids": False,
                       "pattern": SITE + "/trial-details/trial-detail?trialId={internal_id}",
                       "note": "trialId is Be Part of Research's own number (e.g. 25051 shows 'CPMS 53995'); "
                               "it can't be built from NCT, ISRCTN, IRAS or CPMS IDs."},
        "search": {"pattern": SEARCH, "keyed_by": "NCT, ISRCTN or IRAS ID (any study_id in trials/studies.csv)",
                   "checked": search_ok},
        "terms": "Linking allowed, fairly and without implying endorsement; copying any material needs permission "
                 "(bepartofresearch@nihr.ac.uk). Nothing is scraped or stored from the site.",
    }
    (OUT / "link_patterns.json").write_text(json.dumps(patterns, indent=1))
    print("  saved data/processed/bepartofresearch/link_patterns.json")
    update_registry(SOURCE, status="links only", licence="linking permitted (site terms); no content copied",
                    note="No public-ID URL for study pages; a search link per study ID is used instead.")
    print(f"\nCOVERAGE: {SOURCE}\n  links only - study-page URLs use an internal ID; search link "
          f"{'checked' if search_ok else 'NOT reachable'}")


if __name__ == "__main__":
    main()
