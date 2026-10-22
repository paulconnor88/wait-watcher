"""
out/research/slides_research.py - the top three research findings as 1080x1350 LinkedIn slides.

Uses the leo-infographic skill's slides.py (canvas, headline, body, house colours and Figtree fonts).
Every number comes from out/research/numbers.json (run analysis.py first).

Run:   .venv-slides/bin/python out/research/slides_research.py
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = Path("/Users/paulconnor/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/"
             "b3f90b31-11df-4ee5-9ae7-d03fa2ff9535/a95fdae6-9c48-4ccf-b77c-ac29b904d047/skills/leo-infographic/scripts")
sys.path.insert(0, str(SKILL))
from slides import (CLAY, GREEN, GREY, INK, INK2, INK3, LINE, MARGIN, W, B, body, canvas, headline,  # noqa: E402
                    plt, save, text)

N = json.loads((HERE / "numbers.json").read_text())
DATE = "21 Oct 2026"
SOURCE = (f"Source: ClinicalTrials.gov (processed {DATE}); contains information from the ISRCTN\n"
          "registry, licensed CC BY. Changed by Wait Watcher: UK sites only, contact details removed, registries merged.")


def footer(ax, lines):
    """The skill's footer, with room for the attribution: up to four short lines above the wordmark."""
    top = 1268 - 22 * (lines.count("\n") + 1)
    ax.plot([MARGIN, W - MARGIN], [top - 14, top - 14], color=LINE, lw=1)
    text(ax, MARGIN, top, lines, 13.5, color=INK3, linespacing=1.35)
    text(ax, MARGIN, 1290, "wait watcher", 26, bold=True)
    ax.text(302, 1290, ".", fontproperties=B, fontsize=26, color=CLAY, va="top")


def bars(ax, y, rows, vmax, label, width=920, target=None, target_label=None, fmt="{:,.0f}"):
    """The skill's two_bars, with a caption above and labels in a chosen format (e.g. one decimal)."""
    text(ax, MARGIN, y, label, 22, color=INK2)
    y += 50
    for i, (name, v, colour) in enumerate(rows):
        yy = y + i * 120
        text(ax, MARGIN, yy, name, 26, bold=True)
        ax.add_patch(plt.Rectangle((MARGIN, yy + 44), width, 44, color=LINE))
        ax.add_patch(plt.Rectangle((MARGIN, yy + 44), width * v / vmax, 44, color=colour))
        inside = v / vmax > 0.8
        outside = INK2 if colour == GREY else colour          # grey on grey can't be read
        text(ax, MARGIN + width * v / vmax + (-14 if inside else 14), yy + 49, fmt.format(v), 26, bold=True,
             color="#F7F1E6" if inside else outside, ha="right" if inside else "left")
    if target is not None:
        tx = MARGIN + width * target / vmax
        ax.plot([tx] * 2, [y + 30, y + len(rows) * 120 - 10], color=CLAY, lw=2, ls=(0, (4, 3)))
        text(ax, tx - 8, y + len(rows) * 120 + 2, target_label, 18, bold=True, color=CLAY, ha="right")
    return y + len(rows) * 120 + 40


# 1. Essex and east London ---------------------------------------------------------------
f = N["finding_1"]
essex, nel = f["essex"], f["north_east_london"]
fig, ax = canvas()
y = headline(ax, "In Essex, there's one clinical\ntrial recruiting for every\n2,500 people waiting.", 52)
y = body(ax, y, "Next door in east London,\nit's one for every 550.", 34, INK)
bars(ax, y + 110, [("Essex", essex["waiting_per_study"], CLAY), ("North East London", nel["waiting_per_study"], GREEN)],
     2700, "People waiting for hospital treatment, for each trial recruiting there")
footer(ax, f"People waiting for hospital treatment, NHS England, Aug 2026: Essex {essex['waiting']:,}, North East London {nel['waiting']:,}.\n"
           f"Studies recruiting on {DATE} with a site in the area: {essex['recruiting_studies']} and {nel['recruiting_studies']}. A study counts in\n"
           "every area where it has a site, and people can join studies further away.\n" + SOURCE)
save(fig, str(HERE / "1-essex.png"))

# 2. Lungs and bones ---------------------------------------------------------------------
f = N["finding_2"]
lungs, bones = f["lungs"], f["bones_and_joints"]
fig, ax = canvas()
y = headline(ax, f"Per person waiting, lung\ncare has about {f['ratio_lungs_to_bones']} times the\ntrials of bones and joints.", 52)
y = bars(ax, y + 90, [("Lungs", lungs["per_10k_waiting"], GREEN), ("Bones and joints", bones["per_10k_waiting"], CLAY)],
         26, "Clinical trials recruiting, for every 10,000 people waiting", fmt="{:.1f}")
body(ax, y + 30, "Bones and joints has the biggest NHS waiting\nlist: about 850,000 people. Mouth and jaw, and\n"
                 "ear, nose and throat, are lower still.", 28, INK2)
footer(ax, f"Studies recruiting on {DATE} whose conditions map to each department: lungs {lungs['recruiting_studies']}, bones and joints\n"
           f"{bones['recruiting_studies']} (a rule-based guess, about 3 in 4 right on a sample; lung trials include cancer and infection).\n"
           f"People waiting, NHS England, Aug 2026: {lungs['waiting']:,} and {bones['waiting']:,}.\n" + SOURCE)
save(fig, str(HERE / "2-lungs-and-bones.png"))

# 3. Research and waits ------------------------------------------------------------------
f = N["finding_3"]
most, fewest = f["rtt"]["quarters"][-1], f["rtt"]["quarters"][0]
fig, ax = canvas()
y = headline(ax, "Hospitals running the most\ntrials have waits just like\neveryone else's.", 52)
y = bars(ax, y + 90, [(f"The {most['trusts']} hospitals running the most trials", most["median"], GREY),
                      (f"The {fewest['trusts']} running the fewest", fewest["median"], GREY)],
         100, "Out of every 100 people waiting, how many within 18 weeks", target=92, target_label="NHS aim: 92")
c = f["cancer"]["62D"]["quarters"]
body(ax, y + 30, f"Same for cancer: about {c[-1]['median']:.0f} and {c[0]['median']:.0f} in 100 treated\nwithin 62 days. "
                 "No link either way.", 28, INK2)
footer(ax, f"{f['rtt']['trusts']} acute trusts with 10,000+ waiting, in quarters by studies recruiting on {DATE} at sites matched\n"
           f"to them (about 63% of sites match). Typical trust in each quarter, Aug 2026; cancer Jun-Aug 2026.\n"
           f"Correlation {f['rtt']['correlation']}: a picture, not a cause.\n" + SOURCE)
save(fig, str(HERE / "3-research-and-waits.png"))
print("wrote 1-essex.png, 2-lungs-and-bones.png, 3-research-and-waits.png to out/research/")
