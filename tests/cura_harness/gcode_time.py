# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Rough print time of a G-code file: path length / feed rate for every move (no acceleration).

Cura's own ;TIME: estimate is made before the plugin slows the bridge layers, so it misses the extra
minute or so. Compare two files with this estimator and add the difference to Cura's number.

    python3 gcode_time.py a.gcode [b.gcode ...]
"""
import math
import re
import sys

_NUM = re.compile(r"([XYZEF])(-?\d+\.?\d*)")


def seconds(path):
    x = y = z = 0.0
    f = 1500.0
    total = 0.0
    for line in open(path, errors="replace"):
        if not line.startswith(("G0", "G1")):
            continue
        v = {k: float(n) for k, n in _NUM.findall(line.split(";")[0])}
        f = v.get("F", f)
        nx, ny, nz = v.get("X", x), v.get("Y", y), v.get("Z", z)
        d = math.sqrt((nx - x) ** 2 + (ny - y) ** 2 + (nz - z) ** 2)
        if d == 0 and "E" in v:
            continue                                   # retraction / prime: ignored
        total += d / max(f / 60.0, 1e-6)
        x, y, z = nx, ny, nz
    return total


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(f"{p}: {seconds(p) / 60:.1f} min (rough, no acceleration)")
