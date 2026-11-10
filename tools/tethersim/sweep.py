#!/usr/bin/env python3
"""sweep.py - runs the tether_sim studies and writes results.json (heartbeat per run)."""
import json, time, sys
import numpy as np
sys.path.insert(0, ".")
from tether_sim import run_strand, PRINTERS

SPANS = [20, 30, 40, 50, 60, 80, 100, 120, 150]
t0 = time.time(); n = [0]
def hb(msg):
    n[0] += 1
    print(f"[{time.time()-t0:6.1f}s #{n[0]:3d}] {msg}", flush=True)

def curve(printer, **kw):
    res = []
    for L in SPANS:
        r = run_strand(L, printer, **kw)
        res.append(dict(span=L, laying=r["sag_laying_mm"], noshrink=r["sag_noshrink_mm"],
                        final=r["sag_mm"], hot=r["hot_len_mm"]))
    hb(f"{printer} {kw}")
    return res

def max_span(c, budget, key="noshrink"):
    """linear interpolation of span where sag crosses budget"""
    s = [p["span"] for p in c]; y = [p[key] for p in c]
    for i in range(1, len(s)):
        if y[i] > budget:
            return s[i-1] + (budget - y[i-1])*(s[i]-s[i-1])/(y[i]-y[i-1]) if y[i] != y[i-1] else s[i-1]
    return float(">" and s[-1])

R = {"speed": {}, "fan": {}, "flow": {}, "air": {}}
for p in PRINTERS:
    R["speed"][p] = {v: curve(p, v=v) for v in (10, 15, 20, 30, 40)}
    R["fan"][p]   = {f: curve(p, v=20, fan=f) for f in (0.5, 0.75)}
    R["flow"][p]  = {fl: curve(p, v=20, flow=fl) for fl in (0.8, 1.0)}
    base = PRINTERS[p]
    R["air"][p]   = {m: curve(p, v=20, air=dict(U0=base["U0"]*m, U_aux=base["U_aux"]*m)) for m in (0.5, 1.5)}

summary = {}
for p in PRINTERS:
    summary[p] = {}
    for v, c in R["speed"][p].items():
        summary[p][f"v{v}"] = {b: round(max_span(c, b), 1) for b in (0.3, 0.6, 1.0)}
json.dump(dict(results=R, max_span_noshrink=summary), open("results.json", "w"), indent=1, default=str)
print(json.dumps(summary, indent=1))
print(f"done in {time.time()-t0:.0f}s")
