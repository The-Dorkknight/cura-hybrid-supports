#!/usr/bin/env python3
"""layers.py - does tether layer 2 (and 3) fuse onto the sagged strand below?
Strand n+1 is nominally layer_h above strand n. It fuses where its centre gets
within 0.9*d of the lower strand centre while still hotter than T_fuse (120 C).
Z-offset schedules (nozzle lowered along the path, +down):
  flat        : no offset
  k * sag     : offset = k * predicted sag of the strand below (k = 0.5, 0.75, 1.0)
  1.0*sag+0.1 : deliberately over-offset (nozzle ploughs into the strand below)
"""
import json, sys, time
import numpy as np
sys.path.insert(0, ".")
from tether_sim import run_strand

t0 = time.time()
def stack(printer, span, v, schedule, layer_h=0.2, n_layers=3, ae=0.0):
    rows = []
    r = run_strand(span, printer, v=v, layer_h=layer_h, anchor_eff=ae)
    below = r["w"]; d = r["d_mm"]
    rows.append(dict(layer=1, sag=r["sag_mm"], fused=None, plough=0.0))
    for L in range(2, n_layers+1):
        if schedule == "flat": off = np.zeros_like(below)
        elif schedule == "over": off = below + 0.1
        else: off = float(schedule)*below
        obstacle = layer_h + below - 0.9*d          # in this strand's +down frame
        rr = run_strand(span, printer, v=v, layer_h=layer_h, obstacle=obstacle, z_offset=off, anchor_eff=ae)
        plough = float(np.max(off - below))         # >0: nozzle lower than a normal layer above strand below
        rows.append(dict(layer=L, sag=rr["sag_mm"], fused=rr["fused_frac"], plough=max(plough, 0.0),
                         max_offset=float(off.max())))
        # composite: strand above now rests on/with the one below; next strand sees the upper one
        below = rr["w"]                              # next strand: same +down frame, nominal 1 layer higher
    print(f"[{time.time()-t0:5.1f}s] {printer} span {span} v{v} {schedule}: " +
          " | ".join(f"L{x['layer']} sag {x['sag']:.2f} fused {x['fused'] if x['fused'] is None else round(x['fused']*100)}%"
                     for x in rows), flush=True)
    return rows

out = {}
# conservative: soft walls (no shrink pull-taut), so layer-1 sag is the 'while printing' value
for printer in ("Ender 3", "Neptune 4"):
    for span in (60, 80, 100):
        for sched in ("flat", 0.5, 0.75, 1.0, "over"):
            out[f"{printer}|{span}|{sched}"] = stack(printer, span, 20, sched)
json.dump(out, open("layers.json", "w"), indent=1)
