import sys, os
sys.path.insert(0, sys.argv[1])  # leo-infographic/scripts
from slides import *

OUT = sys.argv[2]


def share_bars(ax, y, rows, gap=150):
    """Two bars on a 0-100 track: 'out of every 100 people'. rows: [(label, value, colour, value_label)]."""
    width = W - 2 * MARGIN
    for i, (lab, v, c, vl) in enumerate(rows):
        yy = y + i * gap
        text(ax, MARGIN, yy, lab, 26, bold=True)
        ax.add_patch(plt.Rectangle((MARGIN, yy + 44), width, 48, color=LINE))
        ax.add_patch(plt.Rectangle((MARGIN, yy + 44), max(width * v / 100, 6), 48, color=c))
        text(ax, MARGIN + max(width * v / 100, 6) + 14, yy + 50, vl, 26, bold=True, color=c)
    return y + len(rows) * gap


# 1. Sheffield vs Rotherham, ultrasound -------------------------------------
fig, ax = canvas()
y = headline(ax, "In Sheffield, 2 in 3 people\nwaiting for an ultrasound\nhave waited over 6 weeks.")
y = hundred_people(ax, y, 66, "Sheffield", "about 66 in every 100")
y = hundred_people(ax, y + 10, 0, "Rotherham, next door", "nobody")
body(ax, y - 10, "A year ago, Sheffield was about 1 in 4.", 28, INK)
footer(ax, "Waiting 6+ weeks for an ultrasound (not pregnancy), Aug 2026: Sheffield Teaching Hospitals\n"
           "8,948 of 13,625; Rotherham 0 of 1,342. NHS aim: under 1 in 100. Source: NHS England DM01 (OGL).")
save(fig, f"{OUT}/1-sheffield-ultrasound.png")

# 2. London MRI ---------------------------------------------------------------
fig, ax = canvas()
y = headline(ax, "In south-west London, just\n1 in 100 wait more than\n6 weeks for an MRI scan.")
y = body(ax, y, "In north-east London, it's about 1 in 3.", 32, INK)
text(ax, MARGIN, y + 10, "Out of every 100 people waiting for an MRI, how many\nhave waited more than 6 weeks", 22, color=INK3, linespacing=1.3)
y = share_bars(ax, y + 120, [("South-west London", 1, GREEN, "1"), ("North-east London", 35, CLAY, "35")])
body(ax, y + 20, "South-west London has just met the NHS aim\nof fewer than 1 in 100. A year ago it was about 8.", 28, INK2)
footer(ax, "Waiting 6+ weeks for an MRI, Aug 2026: south-west London 67 of 6,861; north-east 5,174 of 14,813.\n"
           "Homerton (north-east) has none. Hospital location, not home. Source: NHS England DM01 (OGL).")
save(fig, f"{OUT}/2-london-mri.png")

# 3. Midlands MRI -------------------------------------------------------------
fig, ax = canvas()
y = headline(ax, "In three Midlands counties,\nnearly half now wait over\n6 weeks for an MRI scan.")
y = body(ax, y, "A year ago, it was about 1 in 10.", 32, INK)
width = W - 2 * MARGIN
rows = [("Lincolnshire", 16, 50), ("Derbyshire", 13, 48), ("Staffordshire", 7, 41)]
y += 20
for i, (place, then, now) in enumerate(rows):
    yy = y + i * 190
    text(ax, MARGIN, yy, place, 28, bold=True)
    for j, (lab, v, c) in enumerate([("2025", then, GREY), ("2026", now, INK)]):
        by = yy + 50 + j * 56
        text(ax, MARGIN, by + 6, lab, 20, color=INK3)
        ax.add_patch(plt.Rectangle((MARGIN + 80, by), width - 80, 40, color=LINE))
        ax.add_patch(plt.Rectangle((MARGIN + 80, by), (width - 80) * v / 100, 40, color=c))
        text(ax, MARGIN + 80 + (width - 80) * v / 100 + 12, by + 4, f"{v} in 100", 22, bold=True, color=INK if c == INK else INK2)
body(ax, y + 3 * 190 + 10, "They're doing about as many scans as a year ago.\nBut far more people are waiting for one.", 26, INK2)
footer(ax, "Waiting 6+ weeks for an MRI at NHS hospitals in each county, Aug 2025 vs Aug 2026.\n"
           "England: about 59,000 to 79,000. NHS aim: under 1 in 100. Source: NHS England DM01 (OGL).")
save(fig, f"{OUT}/3-midlands-mri.png")
print("done")
