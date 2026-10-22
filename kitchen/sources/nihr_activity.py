"""
kitchen/sources/nihr_activity.py - NIHR research activity by trust (league table): checks, and stops if it can't.

The NIHR research activity league table (studies recruiting and participants
recruited, per NHS trust, by year) was published by the NIHR Clinical
Research Network until 2018/19. Since then NIHR (now the Research Delivery
Network, RDN) publishes "RDN portfolio data" by region and specialty only;
trust-level figures sit in an interactive tool, not a file.

What this script does, in plain English:
  LICENCE  Fetches NIHR's portfolio data pages and prints any licence or
           copyright statement. At the last check (21 October 2026) the site
           couldn't be reached at all, and earlier copies show only "© NIHR" -
           no open licence.
  FIND     Looks on those pages for a downloadable trust-level table (a
           spreadsheet or CSV link mentioning trusts or organisations).
  INGEST   Only if both an open licence and a trust-level file are found:
           then this script needs finishing (columns: trust, year, studies,
           participants, trust group, matched to our provider codes). Until
           then it records the reason in kitchen/registry.json and stops, so
           run_all.py carries on.

Run it with:   python kitchen/sources/nihr_activity.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import check_licence, page_links, stop_source  # noqa: E402

SOURCE = "nihr_activity"
PAGES = ["https://www.nihr.ac.uk/about-us/who-we-are/reports-and-performance/rdn-portfolio-data",
         "https://www.nihr.ac.uk/about-us/who-we-are/reports-and-performance/rdn-portfolio-historical-data"]
TRUST_FILE = re.compile(r"\.(xlsx|xls|csv)(\?|$)", re.I)


def main():
    is_open, files = False, []
    for page in PAGES:
        try:
            is_open = check_licence(SOURCE, page, extra_open=r"open government licence")[0] or is_open
            files += [(t, u) for t, u in page_links(page, allow_missing=True)
                      if TRUST_FILE.search(u) and re.search(r"trust|organisation|provider|league", t + u, re.I)]
        except Exception as error:          # the site was unreachable on 21 Oct 2026
            print(f"  !! couldn't fetch {page}: {type(error).__name__}")
    for text, url in files:
        print(f"  trust-level file? {text} | {url}")
    if not is_open or not files:
        reasons = []
        if not is_open:
            reasons.append("no open licence found (NIHR's site shows only '© NIHR'; on 21 Oct 2026 nihr.ac.uk "
                           "couldn't be reached at all)")
        if not files:
            reasons.append("no trust-level file found: the research activity league table hasn't been published "
                           "since 2018/19; RDN portfolio data is by region and specialty only, and trust-level "
                           "figures are only in NIHR's interactive Open Data Platform")
        return stop_source(SOURCE, "; ".join(reasons) + ". Ask NIHR (RDN) for trust-level activity under the OGL.",
                           "© NIHR (not open)")
    raise SystemExit("An open licence and a trust-level file were found - finish this script before ingesting: "
                     + "; ".join(u for _, u in files))


if __name__ == "__main__":
    main()
