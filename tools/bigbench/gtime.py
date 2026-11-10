"""Rough print time of a G-code (distance / feed rate per move, no acceleration), in minutes,
split into part / support (towers, caps, Cura support) / travel, so every file is measured the same way."""
import math, re, sys
from collections import defaultdict


def gtime(path):
    x = y = z = 0.0
    f = 3000.0
    mesh, typ = "", ""
    out = defaultdict(float)
    for line in open(path):
        if line.startswith(";MESH:"):
            mesh = line[6:].strip()
            continue
        if line.startswith(";TYPE:"):
            typ = line[6:].strip()
            continue
        if not line.startswith(("G0", "G1")):
            continue
        d = {k: float(v) for k, v in re.findall(r"([XYZEF])(-?[\d.]+)", line.split(";")[0])}
        f = d.get("F", f)
        nx, ny, nz = d.get("X", x), d.get("Y", y), d.get("Z", z)
        dist = math.dist((x, y, z), (nx, ny, nz))
        if dist > 0 and f > 0:
            t = dist / f
            if line.startswith("G0") or "E" not in d:
                k = "travel"
            elif mesh.startswith(("HybridTower", "HybridCap")) or typ.startswith("SUPPORT"):
                k = "support"
            else:
                k = "part"
            out[k] += t
        x, y, z = nx, ny, nz
    return dict(out)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        o = gtime(p)
        print(p, {k: round(v, 1) for k, v in o.items()}, "total", round(sum(o.values()), 1))
