"""
kitchen/site_data.py - the website's patient and staff figures.

What this script does, in plain English:
  Builds site/data/experience.json - what each hospital card says about
  patients and staff - from the processed FFT and Staff Survey files. The
  format is exactly what the website already reads:
    {fft: {months, label}, staff: {year, question},
     providers: {code: {inpatient: {responses, positive},
                        outpatient: {responses, positive},
                        staff: {agree, responses}}}}
  - FFT: the latest three months combined, each provider's share positive
    weighted by its responses; left out under MIN_RESPONSES responses.
  - Staff: the latest survey year's "happy with the standard of care for a
    friend or relative" (Q25d), NHS trusts only.

Run it with:   python kitchen/site_data.py   (after fft.py and staff_survey.py)
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MONTH_NAMES, PROCESSED_DIR, SITE_DATA_DIR, our_provider_codes  # noqa: E402

MIN_RESPONSES = 30
MONTHS = 3


def month_label(months):
    """["2026-06", "2026-07", "2026-08"] -> "June to August 2026"."""
    first, last = min(months), max(months)
    name = lambda m: MONTH_NAMES[int(m[5:]) - 1].capitalize()
    if first == last:
        return f"{name(last)} {last[:4]}"
    return f"{name(first)}{'' if first[:4] == last[:4] else ' ' + first[:4]} to {name(last)} {last[:4]}"


def main():
    ours = our_provider_codes()
    fft = pd.read_csv(PROCESSED_DIR / "fft" / "fft.csv")
    staff = pd.read_csv(PROCESSED_DIR / "staff_survey" / "staff_survey.csv")

    months = sorted(fft["month"].unique())[-MONTHS:]
    recent = fft[fft["month"].isin(months) & fft["service"].isin(["inpatient", "outpatient"])
                 & fft["provider_code"].isin(ours)].copy()
    recent["positive_responses"] = recent["pct_positive"] / 100 * recent["responses"]
    combined = recent.groupby(["provider_code", "service"])[["responses", "positive_responses"]].sum().reset_index()
    combined = combined[combined["responses"] >= MIN_RESPONSES]

    providers = {}
    for row in combined.itertuples(index=False):
        providers.setdefault(row.provider_code, {})[row.service] = {
            "responses": int(row.responses), "positive": round(row.positive_responses / row.responses, 3)}

    year = int(staff["year"].max())
    latest = staff[(staff["year"] == year) & staff["provider_code"].isin(ours)
                   & staff["recommend_place_for_treatment_pct"].notna()]
    for row in latest.itertuples(index=False):
        if row.recommend_place_for_treatment_responses >= MIN_RESPONSES:
            providers.setdefault(row.provider_code, {})["staff"] = {
                "agree": round(row.recommend_place_for_treatment_pct / 100, 3),
                "responses": int(row.recommend_place_for_treatment_responses)}

    out = {"fft": {"months": months, "label": month_label(months)},
           "staff": {"year": year, "question": "Q25d"},
           "providers": dict(sorted(providers.items()))}
    (SITE_DATA_DIR / "experience.json").write_text(json.dumps(out, separators=(",", ":")))
    count = lambda key: sum(1 for p in providers.values() if key in p)
    print(f"Saved site/data/experience.json: FFT {out['fft']['label']}, staff survey {year}. "
          f"Inpatient {count('inpatient')}, outpatient {count('outpatient')}, staff {count('staff')} providers.")


if __name__ == "__main__":
    main()
