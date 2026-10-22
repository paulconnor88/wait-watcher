"""
kitchen/sources/hra_summaries.py - Health Research Authority research summaries: licence check, then stop.

The HRA publishes a summary of each research study given a research ethics
committee opinion (about 68,600 of them), each with its IRAS ID - which would
join neatly to our studies. But before ingesting anything, the licence:

What this script does, in plain English:
  LICENCE  Fetches the HRA's terms and conditions and prints them. At the last
           check (21 October 2026, terms "last updated 16 Aug 2018") the
           material is HRA copyright, reproducible free "for research or
           private study" and "must not be systematically reproduced and sold
           for commercial gain". That isn't the Open Government Licence or an
           equivalent, and there's no API or bulk download - getting the
           summaries would mean fetching ~68,600 pages.
  STOP     Records the reason in kitchen/registry.json and stops. If the HRA
           moves the summaries to the OGL (or gives permission), the plan is:
           read the two sitemap pages (sitemap.xml, sitemap.xml?p=2) for the
           summary URLs, fetch each politely, keep title, IRAS ID, date of REC
           opinion and the research summary - never "Contact name" or
           "Contact email" - and join to data/processed/trials/studies.csv by
           IRAS ID.

Run it with:   python kitchen/sources/hra_summaries.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import check_licence, stop_source  # noqa: E402

SOURCE = "hra_summaries"
TERMS = "https://www.hra.nhs.uk/about-us/governance/terms-and-conditions/"


def main():
    is_open, sentences = check_licence(SOURCE, TERMS)
    restricted = any("research or private study" in s for s in sentences)
    if is_open and not restricted:
        raise SystemExit("An open licence now appears on the HRA's terms - review it, then build the ingestion "
                         "described at the top of this script.")
    stop_source(SOURCE, "HRA copyright: free reproduction only 'for research or private study', not systematically "
                        "reproduced for commercial gain - not the OGL or equivalent; no API or bulk download "
                        "(~68,600 pages). Ask the HRA about OGL re-use before ingesting.",
                "HRA copyright (research or private study)")


if __name__ == "__main__":
    main()
