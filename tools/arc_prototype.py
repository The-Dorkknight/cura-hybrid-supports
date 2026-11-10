# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Research prototype (not part of the Cura plugin): how many arc-overhang lines would it take to
grow a layer outward from a supported edge, and how long would they take to print?

Written from the public description of arc overhangs: concentric arcs about a point on the supported
edge, each arc lying beside the one before; the next centre is the far end of the last arc. Needs
shapely and matplotlib (`pip install shapely matplotlib`). Run: python3 tools/arc_prototype.py out.png
"""
import math
import sys

import numpy as np
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import unary_union

W = 0.42          # line width, mm


def _pieces(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString) and not g.is_empty]


def _arcs_from(c, region, printed, r_min, r_max, w):
    """Concentric arcs about c, clipped to `region`; an arc counts when both its ends rest on printed material."""
    out = []
    r = r_min
    zone = region.buffer(w * 0.25)
    while r <= r_max:
        for piece in _pieces(Point(c).buffer(r, 48).exterior.intersection(zone)):
            a, b = Point(piece.coords[0]), Point(piece.coords[-1])
            if a.distance(printed) <= w and b.distance(printed) <= w and piece.length > 2 * w:
                out.append(piece)
        r += w * 0.9                                    # each arc overlaps the one before a little
    return out


def grow_arcs(target: Polygon, supported, r_max=25.0, r_min=2.0, w=W, max_rounds=16):
    """Arcs (LineStrings) that fill `target` outward from `supported` (polygon or union).

    Each round tries centres along the edge of what is already printed, keeps the one whose arcs
    cover the most new area per millimetre of line, prints it, and goes on from the new edge."""
    printed = supported
    arcs = []
    for _ in range(max_rounds):
        remaining = target.difference(printed.buffer(w * 0.5))
        if remaining.is_empty or remaining.area < 6 * w * w:
            break
        edge = printed.boundary.intersection(remaining.buffer(r_max))
        edge_lines = _pieces(edge) or _pieces(printed.boundary)
        best = None
        for line in edge_lines:
            n = max(2, min(30, int(line.length / 4.0)))
            for i in range(n + 1):
                c = line.interpolate(i / n, normalized=True)
                if remaining.distance(c) > r_max:
                    continue
                cand = _arcs_from(c, remaining, printed, r_min, r_max, w)
                if not cand:
                    continue
                score = sum(a.length for a in cand) * w          # new area is about length x line width
                if best is None or score > best[0]:
                    best = (score, cand)
        if best is None or best[0] < 6 * w * w:
            break
        arcs += best[1]
        printed = unary_union([printed] + [a.buffer(w * 0.5) for a in best[1]])
    covered = unary_union([supported] + [a.buffer(w * 0.5) for a in arcs])
    return arcs, target.difference(covered).area


def report(name, target, supported, speed_mm_s=2.0, ax=None, r_max=25.0):
    arcs, left = grow_arcs(target, supported, r_max=r_max)
    length = sum(a.length for a in arcs)
    print(f"{name:46s} area {target.difference(supported).area:6.0f} mm2  arcs {len(arcs):4d}  "
          f"path {length:7.0f} mm  {length / speed_mm_s / 60:5.1f} min at {speed_mm_s:g} mm/s  "
          f"{length / 10 / 60:5.1f} min at 10 mm/s  unfilled {left:5.1f} mm2")
    if ax is not None:
        for a in arcs:
            x, y = a.xy
            ax.plot(x, y, "-", color="tab:green", lw=0.5)
        sup = supported.geoms if hasattr(supported, "geoms") else [supported]
        for g in sup:
            x, y = g.exterior.xy
            ax.fill(x, y, color="0.6")
        ax.set_aspect("equal")
        ax.set_title(f"{name}\n{len(arcs)} arcs, {length:.0f} mm", fontsize=8)
    return len(arcs), length


def estimate(name, target, supported, speed=2.0):
    """Quick estimate: arcs lie side by side, so line length is about the area to fill / line width.
    (The full search below agrees on the channel roof: 3958 mm found against 3810 mm estimated.)"""
    area = target.difference(supported).area
    length = area / W
    print(f"{name:52s} fill {area:6.0f} mm2  ~{length:6.0f} mm of arc  {length / speed / 60:5.1f} min at {speed:g} mm/s"
          f"  {length / 10 / 60:4.1f} min at 10 mm/s")


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = sys.argv[1] if len(sys.argv) > 1 else "arc_prototype.png"
    roof = box(3.5, 0, 43.5, 40)                       # the channel roof's underside, legs on the long sides
    legs = unary_union([box(0, 0, 3.5, 40), box(43.5, 0, 47, 40)])
    strips = lambda n: unary_union([box(3.5, 20 + (i - (n - 1) / 2) * (40 / n) - 0.63, 43.5,
                                        20 + (i - (n - 1) / 2) * (40 / n) + 0.63) for i in range(n)])
    print("One mid-air layer filled with arcs (everything else printed normally):")
    estimate("channel roof, arcs grown from the two legs", roof, legs)
    for n in (1, 2, 3):
        estimate(f"channel roof, {n} tether(s) across, arcs between", roof, unary_union([legs, strips(n)]))
    estimate("channel roof, 6 tethers (20 %): arcs fill the gaps", roof, unary_union([legs, strips(6)]))
    sq = box(3.5, 3.5, 40, 40)
    walls = unary_union([box(0, 0, 40, 3.5), box(0, 0, 3.5, 40)])
    estimate("L roof, arcs from the two walls only", sq, walls)
    tri = Polygon([(3.5, 40), (3.5, 3.5), (40, 3.5)])
    estimate("L roof far corner left by the radial tethers", sq, unary_union([walls, tri.buffer(10)]))
    # the full search on the channel roof, 3 rounds, for the picture
    arcs, left = grow_arcs(roof, legs, r_max=25.0, max_rounds=3)
    print(f"full search, channel roof from the legs: {len(arcs)} arcs, {sum(a.length for a in arcs):.0f} mm, {left:.0f} mm2 unfilled")
    fig, ax = plt.subplots(figsize=(6.5, 6))
    for a in arcs:
        x, y = a.xy
        ax.plot(x, y, "-", color="tab:green", lw=0.4)
    for g in legs.geoms:
        x, y = g.exterior.xy
        ax.fill(x, y, color="0.6")
    ax.set_aspect("equal")
    ax.set_title("Arc overhang over the channel roof: arcs grown from the two legs", fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=80)
    print("wrote", out)
