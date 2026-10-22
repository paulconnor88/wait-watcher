"""
kitchen/sources/njr.py - National Joint Registry (NJR): licence check first.

What this script does, in plain English:
  1. Fetches the NJR pages that say how its data may be used - the hospital
     profile site's disclaimer and copyright line, and the data access page -
     and prints the relevant wording.
  2. Looks for an open re-use licence (the Open Government Licence, or a
     plain statement that re-use is permitted).
  3. Only if one is found would it go on to ingest hip and knee replacement
     counts and outcome indicators by hospital. If not, it records the
     reason in kitchen/registry.json and stops without downloading any data.

As of October 2026 no open licence is published: the hospital profiles are
marked "Copyright NJR", and data beyond the public reports needs an NJR Data
Request Form, a signed Data Sharing Agreement and cost recovery. (Some old
annual-report datasets - 2011 and 2013 data - were released on data.gov.uk
under the Open Government Licence, but they're too old to be useful here.)
This script exits successfully either way, so run_all.py carries on.

Run it with:   python kitchen/sources/njr.py
"""

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import get_page, update_registry  # noqa: E402


PAGES = {
    "hospital profile disclaimer": "https://surgeonprofile.njrcentre.org.uk/Home/Disclaimer",
    "hospital profile home": "https://surgeonprofile.njrcentre.org.uk/",
    "data access requests": "https://www.njrcentre.org.uk/healthcare-providers/data-access-requests/",
}
OPEN_LICENCE = r"open government licen[cs]e|re-?use (of (this|the) data )?is permitted|creative commons"
WORTH_PRINTING = r"copyright|licen[cs]|re-?use|permission|data sharing agreement|data request form|cost recovery|not to be taken"


def plain_text(page):
    page = re.sub(r"(?s)<(script|style|nav).*?</\1>", " ", page)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))


def main():
    found_open_licence, quotes = False, []
    for label, url in PAGES.items():
        text = plain_text(get_page(url))
        print(f"\n== {label}: {url}")
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if re.search(WORTH_PRINTING, sentence, re.I):
                sentence = sentence.strip()[:400]
                print(f"  - {sentence}")
                quotes.append(sentence)
        if re.search(OPEN_LICENCE, text, re.I):
            found_open_licence = True

    if found_open_licence:
        print("\nAn open licence was found. Ingesting NJR data isn't written yet - "
              "review the licence wording above, then add the ingest step.")
        update_registry("njr", status="licence found - ingest not written yet",
                        licence="see wording printed by kitchen/sources/njr.py")
        return

    reason = ("Not ingested: no open re-use licence is published. The hospital profiles are marked "
              "'Copyright NJR', and data beyond the public reports needs an NJR Data Request Form, "
              "a signed Data Sharing Agreement and cost recovery.")
    print(f"\n{reason}")
    update_registry("njr", status="not ingested - no open licence",
                    licence="No open licence found (Copyright NJR; data by request under a Data Sharing Agreement)",
                    reason=reason)
    print("\n" + "=" * 70)
    print("COVERAGE: njr")
    print("=" * 70)
    print("  not ingested - licence does not permit re-use (reason recorded in kitchen/registry.json)")


if __name__ == "__main__":
    main()
