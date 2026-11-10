# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Plot the extrusion paths of chosen layers of a Cura gcode file, coloured by type.

    python3 gcode_layers.py file.gcode out.png 2.0 20.0 46.0
"""
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COL = {"SUPPORT": "#1f9e9e", "SUPPORT-INTERFACE": "#0b5c8a", "WALL-OUTER": "#c0392b", "WALL-INNER": "#e08e79",
       "FILL": "#e6b422", "SKIN": "#c9c13a", "SKIRT": "#888888"}


def layers(path):
    out, z, typ, x, y, e, e_abs = {}, 0.0, "NONE", 0.0, 0.0, 0.0, True
    for line in open(path, errors="replace"):
        if line.startswith(";TYPE:"):
            typ = line[6:].strip(); continue
        if line.startswith("M83"): e_abs = False
        if line.startswith("M82"): e_abs = True
        if line.startswith("G92"):
            m = re.search(r"E(-?[\d.]+)", line)
            if m: e = float(m.group(1))
            continue
        if not line.startswith(("G0", "G1")):
            continue
        code = line.split(";")[0]
        g = {k: float(v) for k, v in re.findall(r"([XYZE])(-?[\d.]+)", code)}
        nx, ny = g.get("X", x), g.get("Y", y)
        if "Z" in g: z = g["Z"]
        ext = False
        if "E" in g:
            d = g["E"] - e if e_abs else g["E"]
            if e_abs: e = g["E"]
            ext = d > 0
        if ext and (nx != x or ny != y):
            out.setdefault(round(z, 2), []).append((typ, x, y, nx, ny))
        x, y = nx, ny
    return out


def main():
    path, out = sys.argv[1], sys.argv[2]
    want = [float(v) for v in sys.argv[3:]]
    lay = layers(path)
    zs = sorted(lay)
    fig, axes = plt.subplots(1, len(want), figsize=(4.6 * len(want), 4.2))
    axes = [axes] if len(want) == 1 else axes
    for ax, w in zip(axes, want):
        z = min(zs, key=lambda v: abs(v - w))
        counts = {}
        for typ, x0, y0, x1, y1 in lay[z]:
            ax.plot([x0, x1], [y0, y1], color=COL.get(typ, "#444"), lw=1.1)
            counts[typ] = counts.get(typ, 0) + 1
        ax.set_aspect("equal"); ax.set_title(f"z = {z:g} mm", fontsize=10)
        ax.tick_params(labelsize=7)
        print(f"z={z}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    handles = [plt.Line2D([0], [0], color=c, lw=2, label=k.title()) for k, c in COL.items()]
    fig.legend(handles=handles, loc="lower center", ncol=7, fontsize=8, frameon=False)
    fig.subplots_adjust(bottom=0.16)
    fig.savefig(out, dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main()
