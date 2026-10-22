"""
kitchen/sources/phin.py - Private Healthcare Information Network (PHIN): licence check only.

PHIN publishes figures on private hospitals (volumes, length of stay,
patient feedback). Before ingesting anything, the kitchen's rule is to fetch
and print the licence.

What this script does, in plain English:
  LICENCE  Fetches PHIN's terms and conditions and prints the lines about
           copyright and re-use. At the last check (October 2026) they say the
           site's content "may not be reproduced other than ... for individual
           private use, research, study or non-commercial use only" and not
           "made available on a network without the prior written consent of
           PHIN" - which rules out republishing it here.
  STOP     Unless an open licence appears, records the reason in
           kitchen/registry.json and stops. Nothing is downloaded.

To change this, PHIN would need to give written consent (or publish its data
under an open licence); then add the ingestion here.

Run it with:   python kitchen/sources/phin.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bs4 import BeautifulSoup  # noqa: E402
from common import check_licence, get_page, stop_source  # noqa: E402

SOURCE = "phin"
TERMS = "https://www.phin.org.uk/about/terms-and-conditions-of-use"


def main():
    is_open, _ = check_licence(SOURCE, TERMS)
    # The clause that matters, searched for in the whole page:
    text = re.sub(r"\s+", " ", BeautifulSoup(get_page(TERMS), "html.parser").get_text(" "))
    restrictive = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                   if re.search(r"may not be reproduced|prior written consent", s, re.I)]
    for sentence in restrictive:
        print(f"  ! {sentence[:400]}")
    if is_open and not restrictive:
        print("  An open licence now appears on PHIN's terms - review them, then add ingestion to this script.")
    stop_source(SOURCE, "PHIN's terms allow only private, research, study or non-commercial use and forbid "
                        "making content available on a network without PHIN's prior written consent. Not an open "
                        "licence; ask PHIN for written consent before ingesting.", "PHIN terms (not open)")


if __name__ == "__main__":
    main()
