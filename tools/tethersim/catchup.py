#!/usr/bin/env python3
"""catchup.py - how many layers until the tether stack is back at nominal Z?
Layer 1 sags; each later layer is laid flat (or with 0.5*sag offset) and may use a
flow boost. Deficit after layer n = sag of that layer in its own frame."""
import sys, time, json
import numpy as np
sys.path.insert(0, ".")
from tether_sim import run_strand
t0 = time.time(); out = {}
def stack(printer, span, v=20, flow1=0.9, flow_up=0.9, k_off=0.5, n=6, layer_h=0.2):
    r = run_strand(span, printer, v=v, flow=flow1, anchor_eff=0.0)
    below, d_below = r["w"], r["d_mm"]; sags = [r["sag_mm"]]
    for L in range(2, n+1):
        rr0 = run_strand(1, printer, flow=flow_up)        # just to get this layer's strand d
        d_up = rr0["d_mm"]
        contact = 0.45*(d_below + d_up)                   # centre spacing at fusion (10% overlap)
        obstacle = layer_h + below - contact
        rr = run_strand(span, printer, v=v, flow=flow_up, obstacle=obstacle,
                        z_offset=k_off*np.clip(below, 0, None), anchor_eff=0.0)
        below, d_below = rr["w"], d_up; sags.append(rr["sag_mm"])
    print(f"[{time.time()-t0:5.1f}s] {printer} {span}mm v{v} flow_up {flow_up}: deficit per layer "
          + " ".join(f"{s:.2f}" for s in sags), flush=True)
    return sags
for p in ("Ender 3", "Neptune 4"):
    for span in (60, 80, 100):
        for fu in (0.9, 1.2, 1.5):
            out[f"{p}|{span}|{fu}"] = stack(p, span, flow_up=fu)
json.dump(out, open("catchup.json", "w"), indent=1)
