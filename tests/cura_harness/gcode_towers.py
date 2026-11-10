# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Check every generated trunk actually prints on every layer (no half-printed "ghost" towers).

    python3 gcode_towers.py results.json hybrid.gcode

For each support the harness recorded, it looks at every layer between the landing and the top
of the trunk and checks there is support extrusion within (trunk radius + 1 mm) of its axis.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gcode_layers import layers  # noqa: E402


def main():
    res = json.load(open(sys.argv[1]))
    lay = layers(sys.argv[2])
    m = res["machine"]
    ox = 0.0 if m["machine_center_is_zero"] else m["machine_width"] / 2
    oy = 0.0 if m["machine_center_is_zero"] else m["machine_depth"] / 2
    zs = sorted(lay)
    worst = 1.0
    for i, u in enumerate(res["units"]):
        if u["rt"] <= 0 or u["top"] - u["land"] < 2:
            print(f"support {i}: standing webs / no trunk, under {u['under']:.1f} mm, {u['branches']} webs")
            continue
        cx, cy = u["trunk_xy"][0] + ox, u["trunk_xy"][1] + oy
        want = [z for z in zs if u["land"] + 1.0 <= z <= u["top"] - 0.5]
        hit = 0
        for z in want:
            for typ, x0, y0, x1, y1 in lay[z]:
                if typ.startswith("SUPPORT") and min(math.hypot(x0 - cx, y0 - cy),
                                                     math.hypot(x1 - cx, y1 - cy)) <= u["rt"] + 1.0:
                    hit += 1
                    break
        frac = hit / len(want) if want else 1.0
        worst = min(worst, frac)
        print(f"support {i}: trunk at ({cx:.1f},{cy:.1f}) r={u['rt']:.1f} z {u['land']:.1f}-{u['top']:.1f}: "
              f"prints on {hit}/{len(want)} layers ({100 * frac:.0f}%), {u['branches']} branches, "
              f"reach {100 * u['coverage']:.0f}%")
    print(f"WORST trunk layer coverage: {100 * worst:.0f}%")


if __name__ == "__main__":
    main()
