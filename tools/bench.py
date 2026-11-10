# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Time generate() on a dense UV sphere floating above the plate (lots of overhang).

    python3 tools/bench.py [lat_steps]
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "HybridSupports"))
import hybrid_core as hc  # noqa: E402


def sphere(n, r=25.0, z=40.0):
    th = np.linspace(0, np.pi, n + 1)
    ph = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    v = [[r * np.sin(t) * np.cos(p), r * np.sin(t) * np.sin(p), z + r * np.cos(t)] for t in th for p in ph]
    m = 2 * n
    f = []
    for i in range(n):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            c, d = a + m, b + m
            f += [[a, c, b], [b, c, d]]
    return np.array(v), np.array(f)


n = int(sys.argv[1]) if len(sys.argv) > 1 else 160
v, f = sphere(n)
t = time.perf_counter()
u = hc.generate(v, f, hc.HybridSettings(head_mode="conform"))
print(f"{len(f)} triangles -> {len(u)} units in {time.perf_counter() - t:.2f} s")
