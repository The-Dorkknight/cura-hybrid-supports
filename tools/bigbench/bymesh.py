"""Filament (m) by mesh-name prefix in a Cura G-code (absolute or relative E)."""
import re, sys
from collections import defaultdict

tot = defaultdict(float)
mesh, e, rel = "", 0.0, False
for line in open(sys.argv[1]):
    if line.startswith(";MESH:"):
        mesh = line[6:].strip()
        continue
    if line.startswith("M83"):
        rel = True
    if line.startswith("G92"):
        m = re.search(r"E(-?[\d.]+)", line)
        if m:
            e = float(m.group(1))
        continue
    if line.startswith(("G1", "G0")) and "E" in line:
        m = re.search(r"E(-?[\d.]+)", line.split(";")[0])
        if not m:
            continue
        v = float(m.group(1))
        de = v if rel else v - e
        if not rel:
            e = v
        if de > 0 and ("X" in line or "Y" in line):
            key = "HybridTower" if mesh.startswith("HybridTower") else "HybridCap" if mesh.startswith("HybridCap") else \
                ("part" if mesh and mesh != "NONMESH" else "other (brim/skirt/support)")
            tot[key] += de
for k, v in sorted(tot.items()):
    print(f"{k:28s} {v / 1000:7.2f} m")
