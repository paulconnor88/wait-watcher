"""Wait Watcher slide library: six simple pictures in the house style.

Usage from another script:
    from slides import *
    fig, ax = canvas()
    headline(ax, "In London, a bones-and-joints\noperation took anywhere from\nabout 16 to 48 weeks.")
    dot_strip(ax, values=[15.6, 19.0, 48.4], lo=10, hi=55, unit="weeks, typical total wait")
    footer(ax, "18 London NHS trusts, June to August 2026. Source: NHS England RTT statistics.")
    save(fig, "out/3-london.png")

Run `python slides.py --demo` to draw one of each picture into out/.
Only matplotlib is needed. Fonts load from ../assets/fonts relative to this file.
"""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "assets", "fonts")
R = fm.FontProperties(fname=os.path.join(FONT_DIR, "Figtree-Regular-static.ttf"))
B = fm.FontProperties(fname=os.path.join(FONT_DIR, "Figtree-Bold-static.ttf"))

# House tokens
PAPER = "#F7F1E6"; INK = "#1F2A26"; INK2 = "#5F5E5A"; INK3 = "#888780"
LINE = "#D3D1C7"; GREEN = "#2F6B4F"; CLAY = "#D85A30"; GREY = "#B4B2A9"
W, H = 1080, 1350  # LinkedIn portrait
MARGIN = 80


def canvas():
    """A paper-coloured 1080x1350 canvas in pixel coordinates (y down)."""
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    return fig, ax


def text(ax, x, y, s, size, bold=False, color=INK, **kw):
    ax.text(x, y, s, fontproperties=B if bold else R, fontsize=size, color=color, va="top", **kw)


def headline(ax, s, size=50, y=110):
    """The pub sentence. Under 15 words. Returns the y where body text can start."""
    text(ax, MARGIN, y, s, size, bold=True, linespacing=1.15)
    return y + size * 1.6 * (s.count("\n") + 1) + 40


def body(ax, y, s, size=28, color=INK2):
    text(ax, MARGIN, y, s, size, color=color, linespacing=1.3)
    return y + size * 1.7 * (s.count("\n") + 1) + 30


def footer(ax, src, page=None):
    """Source line and wordmark. src: two short lines max."""
    ax.plot([MARGIN, W - MARGIN], [1210, 1210], color=LINE, lw=1)
    text(ax, MARGIN, 1230, src, 15, color=INK3)
    text(ax, MARGIN, 1290, "wait watcher", 26, bold=True)
    ax.text(302, 1290, ".", fontproperties=B, fontsize=26, color=CLAY, va="top")
    if page:
        text(ax, W - MARGIN, 1296, page, 18, color=INK3, ha="right")


def save(fig, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, facecolor=PAPER); plt.close(fig)


# ---------- the six pictures ----------

def big_number(ax, number, y=110, color=CLAY, size=150):
    """1. The number is the sentence. Returns y below it."""
    text(ax, MARGIN, y, number, size, bold=True, color=color)
    return y + size * 1.3


def dot_strip(ax, values, lo, hi, unit, y=700, best="min", labels=True):
    """2. Spread between best and worst. Fastest green, slowest clay, others grey, beeswarm when crowded."""
    x0, x1 = 110, 970
    sc = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    ax.plot([x0, x1], [y + 60, y + 60], color=LINE, lw=2)
    step = 10 if hi - lo <= 60 else 20
    for v in range(int(lo), int(hi) + 1, step):
        ax.plot([sc(v)] * 2, [y + 48, y + 72], color=LINE, lw=2)
        text(ax, sc(v), y + 90, str(v), 18, color=INK3, ha="center")
    text(ax, (x0 + x1) / 2, y + 120, unit, 17, color=INK3, ha="center")
    vmin, vmax = min(values), max(values)
    good, bad = (vmin, vmax) if best == "min" else (vmax, vmin)
    placed = []
    for v in sorted(values):
        x, yy = sc(v), y
        while any(abs(x - px) < 24 and abs(yy - py) < 24 for px, py in placed):
            yy -= 26
        placed.append((x, yy))
        c = GREEN if v == good else CLAY if v == bad else GREY
        ax.scatter([x], [yy], s=380, color=c, zorder=5 if c != GREY else 3, edgecolors=PAPER, linewidths=1.5)
    if labels:
        text(ax, sc(good) + 40, y - 140, f"Fastest\n{good:.0f} weeks", 22, bold=True, color=GREEN, ha="center")
        text(ax, sc(bad), y - 140, f"Slowest\n{bad:.0f} weeks", 22, bold=True, color=CLAY, ha="center")


def _person(ax, x, y, c, s):
    ax.add_patch(plt.Circle((x, y), s * 0.42, color=c))
    ax.add_patch(plt.Rectangle((x - s * 0.5, y + s * 0.55), s, s * 1.3, color=c))


def hundred_people(ax, y, filled, label, sublabel, color=CLAY):
    """3. A share as 100 figures, `filled` of them in colour. Returns y below the grid."""
    text(ax, MARGIN, y, label, 26, bold=True)
    text(ax, MARGIN + 18 * len(label) + 20, y + 2, sublabel, 24, color=INK2)
    for i in range(100):
        r, c = divmod(i, 20)
        _person(ax, 100 + c * 46, y + 70 + r * 52, color if i < filled else GREY, 13)
    return y + 70 + 5 * 52 + 40


def two_bars(ax, y, rows, vmax, target=None, target_label="NHS aim", width=920):
    """4. Then and now (or here and there). rows: [(label, value, colour)]. Returns y below."""
    for i, (lab, v, c) in enumerate(rows):
        yy = y + i * 110
        text(ax, MARGIN, yy, lab, 24, bold=True)
        ax.add_patch(plt.Rectangle((MARGIN, yy + 40), width, 40, color=LINE))
        ax.add_patch(plt.Rectangle((MARGIN, yy + 40), width * v / vmax, 40, color=c))
        if v / vmax > 0.85:  # label inside the bar so it never runs off the page
            text(ax, MARGIN + width * v / vmax - 12, yy + 44, f"{v:,.0f}", 24, bold=True, color=PAPER, ha="right")
        else:
            text(ax, MARGIN + width * v / vmax + 12, yy + 44, f"{v:,.0f}", 24, bold=True, color=c)
    if target is not None:
        tx = MARGIN + width * target / vmax
        ax.plot([tx] * 2, [y - 10, y + len(rows) * 110 - 20], color=CLAY, lw=2, ls=(0, (4, 3)))
        text(ax, tx, y + len(rows) * 110 - 10, f"{target_label}: {target:.0f}", 18, bold=True, color=CLAY, ha="center")
    return y + len(rows) * 110 + 40


def ranked_bars(ax, y, rows, vmax, highlight=0, label_w=340):
    """5. A short league, five rows max. rows: [(name, value)], the highlighted row in clay."""
    for i, (n, v) in enumerate(rows[:5]):
        yy = y + i * 62
        text(ax, MARGIN, yy + 6, n, 20, color=INK2)
        ax.add_patch(plt.Rectangle((MARGIN + label_w, yy), 540, 34, color=LINE))
        ax.add_patch(plt.Rectangle((MARGIN + label_w, yy), 540 * v / vmax, 34, color=CLAY if i == highlight else GREY))
        text(ax, MARGIN + label_w + 540 * v / vmax + 12, yy + 5, f"{v:,.0f}", 20, bold=True, color=INK2)
    return y + len(rows[:5]) * 62 + 40


def ladder(ax, y, rungs, vmax=100, width=920):
    """6. A target over time. rungs: [(label, note, value, colour, future_bool)]."""
    for i, (lab, note, v, c, future) in enumerate(rungs):
        yy = y + i * 150
        text(ax, MARGIN, yy, lab, 26, bold=True, color=c)
        text(ax, MARGIN, yy + 36, note, 18, color=INK3)
        ax.add_patch(plt.Rectangle((MARGIN, yy + 70), width, 40, color=LINE))
        if future:
            ax.add_patch(plt.Rectangle((MARGIN, yy + 70), width * v / vmax, 40, fc=PAPER, ec=c, lw=2, ls="--"))
        else:
            ax.add_patch(plt.Rectangle((MARGIN, yy + 70), width * v / vmax, 40, color=c))
        text(ax, MARGIN + width * v / vmax + 12, yy + 74, str(v), 24, bold=True, color=c)
    return y + len(rungs) * 150


# ---------- demo ----------

def _demo():
    out = os.path.join(os.getcwd(), "out")
    fig, ax = canvas(); y = big_number(ax, "113,000")
    y = headline(ax, "people in England have waited\nmore than a year for treatment.", 44, y)
    body(ax, y, "That's about everyone in Cheltenham.")
    footer(ax, "People waiting over 52 weeks, England, August 2026. Source: NHS England RTT statistics."); save(fig, f"{out}/demo-1-big-number.png")

    fig, ax = canvas(); y = headline(ax, "In London, a bones-and-joints\noperation took anywhere from\nabout 16 to 48 weeks.")
    dot_strip(ax, [15.6, 15.8, 19, 19.1, 25.2, 25.5, 25.6, 26.8, 27.7, 30.3, 30.3, 31.7, 33.5, 37.4, 40.1, 40.4, 40.6, 48.4], 10, 55, "weeks, typical total wait. Each dot is one London NHS trust.")
    body(ax, 900, "That's a difference of about 8 months,\nfor the same type of care, in the same city.", 30, INK)
    footer(ax, "18 London NHS trusts, June to August 2026. Source: NHS England RTT statistics."); save(fig, f"{out}/demo-2-dot-strip.png")

    fig, ax = canvas(); y = headline(ax, "In Essex, 1 in 20 people on the\nwaiting list have waited more\nthan a year.")
    y = hundred_people(ax, y, 5, "Essex", "5 in every 100 people waiting")
    hundred_people(ax, y, 1, "North East London", "about 1 in every 100")
    footer(ax, "People waiting over 52 weeks by where patients live, August 2026. Source: NHS England RTT."); save(fig, f"{out}/demo-3-hundred.png")

    fig, ax = canvas(); y = headline(ax, "Year-long waits are down\nby 41% in a year.")
    two_bars(ax, y + 20, [("August 2025", 192024, GREY), ("August 2026", 112958, GREEN)], 200000)
    footer(ax, "People waiting over 52 weeks, England. Source: NHS England RTT statistics."); save(fig, f"{out}/demo-4-two-bars.png")

    fig, ax = canvas(); y = headline(ax, "One trust holds 1 in 9 of\nEngland's year-long waits.")
    ranked_bars(ax, y + 20, [("Mid and South Essex", 13427), ("Univ. Hospitals Sussex", 5634), ("Northern Care Alliance", 3932), ("Hull", 3500), ("East Kent", 2623)], 14000)
    footer(ax, "People waiting over 52 weeks by NHS trust, August 2026. Source: NHS England RTT statistics."); save(fig, f"{out}/demo-5-ranked.png")

    fig, ax = canvas(); y = headline(ax, "18 weeks. 92 in 100.\nWhat the NHS promises.")
    ladder(ax, y + 20, [("Early 2016", "last time the aim was met", 92, INK2, False), ("August 2026", "now", 65, GREEN, False), ("March 2029", "the government's target", 92, CLAY, True)])
    footer(ax, "92% standard, measured on people still waiting. Source: NHS England RTT statistics."); save(fig, f"{out}/demo-6-ladder.png")
    print("wrote 6 demo slides to", out)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        print(__doc__)
