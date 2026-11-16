"""RUDY routing-demand map from a placed DEF (no OpenROAD needed), and which logic sits in the hotspots.

For each net, its pin bounding box (from the placed instances' locations) spreads a demand of
(w + h) / (w * h) per unit area over the box (RUDY). The map is binned on a grid; the top bins are
reported with the share of their cells by RTL group, using the output-net name of each cell when it
carries an RTL name (Yosys keeps register/wire names on nets), else the nearest named net is not
resolved and the cell counts as "anonymous".
It is an estimate from the placement, not a routing result: the global router's overflow is the
measurement. The hot-area lines compare designs of different size at the same absolute bin size.
Usage: python3 rudy.py DEF [BIN_UM]   (default 20 um bins)
"""
import re
import sys
from collections import Counter, defaultdict

path = sys.argv[1]
bin_um = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
text = open(path).read()
units = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", text).group(1))
die = [int(v) / units for v in re.search(r"DIEAREA \( (\d+) (\d+) \) \( (\d+) (\d+) \)", text).groups()]
comp_sec = text[text.index("\nCOMPONENTS"):text.index("END COMPONENTS")]
loc = {}
master = {}
for m in re.finditer(r"- (\S+) (\S+)[^;]*?\+ (?:PLACED|FIXED) \( (-?\d+) (-?\d+) \)", comp_sec):
    loc[m.group(1)] = (int(m.group(3)) / units, int(m.group(4)) / units)
    master[m.group(1)] = m.group(2)
net_sec = text[text.index("\nNETS"):text.index("END NETS")]
W, H = die[2] - die[0], die[3] - die[1]
grid = max(1, round(W / bin_um))
bx, by = W / grid, H / grid
demand = [[0.0] * grid for _ in range(grid)]
cell_group = {}


def group_of(name):
    n = name.replace("\\", "")
    for key, label in (("wr_re", "work buffer"), ("wr_im", "work buffer"), ("frame_", "frame"),
                       ("piped.p_", "X3 operand (product reg)"), ("piped.mul_", "X2 multiply"),
                       ("piped.om_", "X2 operand reg"), ("piped.ot_", "X2 operand reg"), ("piped.ox_", "X2 operand reg"),
                       ("piped.sel_", "X1 select"), ("a_re_q", "fetch regs"), ("a_im_q", "fetch regs"),
                       ("b_re_q", "fetch regs"), ("b_im_q", "fetch regs"), ("sparse_read", "read ports"),
                       ("rd_a_", "read ports"), ("rd_b_", "read ports"), ("wa_", "write-back"), ("wb_", "write-back"),
                       ("sample_o", "output"), ("emit", "output")):
        if key in n:
            return label
    m = re.search(r"lane\[(\d)\]", n)
    return f"lane{m.group(1)} other" if m else None


for block in re.split(r"\n\s+- ", net_sec)[1:]:
    head = block.split(None, 1)[0]
    pins = re.findall(r"\( (\S+) (\S+) \)", block.split(";")[0])
    pts = [loc[c] for c, _ in pins if c in loc]
    g = group_of(head)
    if g:
        for c, pin in pins:
            if c in loc and pin in ("X", "Q", "Y", "Q_N"):
                cell_group[c] = g
    if len(pts) < 2:
        continue
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 2.72
    w, h = x1 - x0, y1 - y0
    d = (w + h) / (w * h)
    i0, i1 = int(x0 / bx), min(grid - 1, int(x1 / bx))
    j0, j1 = int(y0 / by), min(grid - 1, int(y1 / by))
    for i in range(i0, i1 + 1):
        ox = max(0.0, min(x1, (i + 1) * bx) - max(x0, i * bx))
        for j in range(j0, j1 + 1):
            oy = max(0.0, min(y1, (j + 1) * by) - max(y0, j * by))
            demand[i][j] += d * ox * oy
area = bx * by
flat = sorted(((demand[i][j] / area, i, j) for i in range(grid) for j in range(grid)), reverse=True)
mean = sum(v for v, _, _ in flat) / len(flat)
print(f"die {W:.0f} x {H:.0f} um, grid {grid}x{grid} ({bx:.0f} um bins), mean RUDY {mean:.3f} um/um2")
values = [v for v, _, _ in flat]
count = len(values)
print(f"bins {count}: p50 {values[count // 2]:.2f}, p90 {values[count // 10]:.2f}, "
      f"p99 {values[count // 100]:.2f}, max {values[0]:.2f} um/um2")
for threshold in (3.0, 4.0, 5.0):
    hot = sum(1 for v in values if v > threshold)
    print(f"  area with RUDY > {threshold:.0f} um/um2: {hot * area / 1e6:.4f} mm2 ({100 * hot / count:.1f} % of the die)")
cells_in = defaultdict(list)
for c, (x, y) in loc.items():
    cells_in[(min(grid - 1, int(x / bx)), min(grid - 1, int(y / by)))].append(c)
print("top bins: RUDY/mean, bin (i,j), cells, groups of named cells")
for v, i, j in flat[:12]:
    cs = cells_in[(i, j)]
    groups = Counter(cell_group.get(c, "anonymous") for c in cs)
    named = {k: n for k, n in groups.most_common(5)}
    print(f"  {v / mean:5.2f}x  ({i:2d},{j:2d})  {len(cs):5d} cells  {named}")
# Where each named group sits (centroid and spread), to compare with the hotspots.
pos = defaultdict(list)
for c, g in cell_group.items():
    pos[g].append(loc[c])
print("group centroids (bin units):")
for g, pts in sorted(pos.items()):
    cx = sum(p[0] for p in pts) / len(pts) / bx
    cy = sum(p[1] for p in pts) / len(pts) / by
    print(f"  {g:28s} {len(pts):6d} cells  centroid ({cx:5.1f},{cy:5.1f})")
