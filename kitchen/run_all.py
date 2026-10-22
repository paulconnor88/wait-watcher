"""
kitchen/run_all.py - run the whole kitchen, in order, and stop at the first error.

Order:
  Phase 2 sources (everything else matches to RTT's provider codes):
   1. sources/rtt.py               waiting lists
   2. sources/ods.py               locations and provider types (needs rtt)
   3. sources/cqc.py               inspection ratings (needs ods)
   4. sources/fft.py               Friends and Family Test
   5. sources/staff_survey.py      NHS Staff Survey
   6. sources/dm01.py              diagnostic waiting times
   7. sources/njr.py               National Joint Registry (licence check only)
  Phase 3 sources, in the brief's order:
   8. sources/ers.py               e-Referral Service appointment slot issues
   9. sources/wlmds.py             weekly waiting list (WLMDS)
  10. sources/cancer.py            cancer waiting times (sensitive)
  11. sources/gp_practices.py      GP practice list and locations (before gpad)
  12. sources/gpad.py              GP appointments by practice (large: ~200 MB of zips)
  13. sources/gpps.py              GP Patient Survey (stops: licence not stated)
  14. sources/talking_therapies.py NHS Talking Therapies
  15. sources/mhsds.py             mental health waits
  16. sources/community.py         community health services waiting lists
  17. sources/ae.py                A&E four-hour waits
  18. sources/ambulance.py         ambulance response times
  19. sources/uec_sitreps.py       winter sitreps (beds, handovers)
  20. sources/workforce.py         vacancies (region) and sickness absence (trust)
  21. sources/fingertips.py        deprivation, over-65s, healthy life expectancy
  22. sources/population.py        ONS population
  23. sources/dental.py            NHS dental activity
  24. sources/phin.py              PHIN (licence check only - stops)
  25. sources/uk_nations.py        Scotland, Wales, NI headline waits (not comparable)
  Phase 4 sources, UK clinical research:
  26. sources/clinicaltrials.py    ClinicalTrials.gov, UK sites (full fetch every 28 days, else updates)
  27. sources/isrctn.py            ISRCTN registry, UK studies (same)
  28. sources/trials.py            the two de-duplicated, sites matched to providers, conditions mapped
  29. sources/nihr_activity.py     NIHR research activity by trust (stops: not published openly)
  30. sources/hra_summaries.py     HRA research summaries (stops: not openly licensed)
  31. sources/bepartofresearch.py  Be Part of Research link patterns (links only)
  The gate:
  32. reconcile.py                 England figures against the published ones - stops the run if any
                                   differs by more than a documented, computed gap (kitchen/DEFINITIONS.md)
  Then (only if the gate passes):
  33. site_data.py                 the website's patient and staff figures
  34. make_findings.py             the month's findings, report facts and questions.md
  35. lab_data.py                  Wait Watcher Lab's data files (lab/data/)

Each step runs as its own Python process, exactly as if you ran it by hand. Every
source's coverage summary is also saved to data/processed/coverage.txt.
If any step fails, this script stops straight away with a non-zero exit
code and says which step failed - so an automated run fails loudly.

Run it with:   python kitchen/run_all.py
"""

import subprocess
import sys
import time
from pathlib import Path

KITCHEN = Path(__file__).resolve().parent
STEPS = [
    "sources/rtt.py",
    "sources/ods.py",
    "sources/cqc.py",
    "sources/fft.py",
    "sources/staff_survey.py",
    "sources/dm01.py",
    "sources/njr.py",
    "sources/ers.py",
    "sources/wlmds.py",
    "sources/cancer.py",
    "sources/gp_practices.py",
    "sources/gpad.py",
    "sources/gpps.py",
    "sources/talking_therapies.py",
    "sources/mhsds.py",
    "sources/community.py",
    "sources/ae.py",
    "sources/ambulance.py",
    "sources/uec_sitreps.py",
    "sources/workforce.py",
    "sources/fingertips.py",
    "sources/population.py",
    "sources/dental.py",
    "sources/phin.py",
    "sources/uk_nations.py",
    "sources/clinicaltrials.py",
    "sources/isrctn.py",
    "sources/trials.py",
    "sources/nihr_activity.py",
    "sources/hra_summaries.py",
    "sources/bepartofresearch.py",
    "reconcile.py",
    "site_data.py",
    "make_findings.py",
    "lab_data.py",
]


def run_step(step):
    """Run one step, printing its output as it comes and keeping its coverage summary."""
    process = subprocess.Popen([sys.executable, "-u", str(KITCHEN / step)], cwd=KITCHEN.parent,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    coverage, inside = [], False
    for line in process.stdout:
        print(line, end="", flush=True)
        if line.startswith("COVERAGE: "):
            inside = True
            coverage.append("----\n" + line)
        elif inside and line.startswith("  "):
            coverage.append(line)
        elif inside and not line.startswith("====="):
            inside = False
    return process.wait(), coverage


def main():
    started = time.time()
    coverage = []
    for number, step in enumerate(STEPS, 1):
        print(f"\n{'#' * 70}\n# {number}/{len(STEPS)}  {step}\n{'#' * 70}", flush=True)
        step_started = time.time()
        returncode, step_coverage = run_step(step)
        coverage += step_coverage
        if returncode != 0:
            print(f"\n!! FAILED: {step} (exit code {returncode}). Stopping.", file=sys.stderr)
            sys.exit(returncode)
        print(f"\n-- {step} done in {time.time() - step_started:.0f}s", flush=True)
    # Every source's coverage summary in one committed file.
    (KITCHEN.parent / "data" / "processed" / "coverage.txt").write_text("".join(coverage))
    print(f"\nAll {len(STEPS)} steps finished in {(time.time() - started) / 60:.1f} minutes. "
          "Coverage summaries saved to data/processed/coverage.txt.")


if __name__ == "__main__":
    main()
