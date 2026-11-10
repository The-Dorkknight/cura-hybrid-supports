# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Summarise Cura gcode: total time, filament, and filament per feature type.

    python3 gcode_stats.py a.gcode [b.gcode ...]
"""
import re
import sys


def stats(path):
    e_abs, last_e, typ = True, 0.0, "NONE"
    per = {}
    time_s = None
    for line in open(path, errors="replace"):
        if line.startswith(";TIME:"):
            time_s = int(float(line[6:].strip()))
        elif line.startswith(";TYPE:"):
            typ = line[6:].strip()
        elif line.startswith("M83"):
            e_abs = False
        elif line.startswith("M82"):
            e_abs = True
        elif line.startswith("G92"):
            m = re.search(r"E(-?[\d.]+)", line)
            if m:
                last_e = float(m.group(1))
        elif line.startswith(("G1", "G0", "G2", "G3")):
            m = re.search(r"E(-?[\d.]+)", line.split(";")[0])
            if m:
                e = float(m.group(1))
                d = e - last_e if e_abs else e
                if e_abs:
                    last_e = e
                if d > 0 and re.search(r"[XY]", line):
                    per[typ] = per.get(typ, 0.0) + d
    return time_s, per


if __name__ == "__main__":
    for p in sys.argv[1:]:
        t, per = stats(p)
        tot = sum(per.values())
        sup = sum(v for k, v in per.items() if k.startswith("SUPPORT"))
        print(f"{p}: time {t} s ({t / 60:.1f} min), filament {tot:.0f} mm, support filament {sup:.0f} mm")
        for k in sorted(per):
            print(f"    {k:20s} {per[k]:8.1f} mm")
