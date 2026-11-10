"""Compare support cost on the big parts: total minus the bare part, from Cura's G-code headers."""
import glob, json, os, re, sys

ROOT = "/home/claude/bigruns"
DENS, DIA = 1.24, 1.75            # PLA, g/cm3 and mm
AREA = 3.14159265 * (DIA / 2) ** 2


def extruded(path):
    import subprocess
    out = subprocess.run([sys.executable, "/home/claude/scripts/bymesh.py", path], capture_output=True, text=True).stdout
    return sum(float(l.split()[-2]) for l in out.splitlines() if l.strip())


def head(path):
    t = m = None
    with open(path) as fh:
        for i, line in enumerate(fh):
            if line.startswith(";TIME:"):
                t = float(line[6:])
            elif line.startswith(";Filament used:"):
                m = float(re.findall(r"[\d.]+", line)[0])
            if i > 60 or (t is not None and m is not None):
                break
    return t, extruded(path)      # filament actually extruded (the header is from before the cap stack)


rows = []
for part in ("U200_h50", "U200_h150", "mushroom200_h150"):
    d = os.path.join(ROOT, part)
    base = head(os.path.join(d, "plain", "plain.gcode")) if os.path.exists(os.path.join(d, "plain", "plain.gcode")) else None
    cands = [("Cura normal support", "lobes/cura_support.gcode"), ("Cura tree support", "lobes/cura_tree.gcode"),
             ("Hybrid lobes", "lobes/hybrid.gcode"), ("Hybrid branch", "branch/hybrid.gcode"), ("Hybrid cone", "cone/hybrid.gcode")]
    for name, rel in cands:
        p = os.path.join(d, rel)
        if not os.path.exists(p) or base is None:
            continue
        t, m = head(p)
        units = ""
        rj = os.path.join(os.path.dirname(p), "results.json")
        if name.startswith("Hybrid") and os.path.exists(rj):
            r = json.load(open(rj))
            us = r.get("units", [])
            units = f"{len(us)} tower(s), reach {min((u['coverage'] for u in us), default=0) * 100:.0f}%"
        st, sm = t - base[0], m - base[1]
        rows.append({"part": part, "support": name, "total_min": t / 60, "total_m": m, "sup_min": st / 60, "sup_m": sm,
                     "sup_g": sm * 1000 * AREA / 1000 * DENS, "towers": units, "bare_min": base[0] / 60, "bare_m": base[1]})

json.dump(rows, open(os.path.join(ROOT, "summary.json"), "w"), indent=1)
for r in rows:
    print(f"{r['part']:18s} {r['support']:20s} total {r['total_min']:6.0f} min {r['total_m']:6.1f} m | support {r['sup_min']:6.0f} min "
          f"{r['sup_m']:6.1f} m {r['sup_g']:5.0f} g  {r['towers']}")
