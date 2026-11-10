# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Synthetic test models (Z-up, mm) shaped like the parts that showed the 0.1.x problems.

rugged_box()  - a 70 x 40 x 120 box standing on its end, open on one side, with ribs,
                hinge knuckles and latch lugs on the outside (like the "EN4 Rugged Box").
tilted_blob() - a small rounded part tilted on the plate with a side boss: lots of
                small, low, curved overhangs.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "HybridSupports"))
import hybrid_core as hc  # noqa: E402


def box(x0, y0, z0, x1, y1, z1):
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return hc.Mesh(v, f)


def rugged_box() -> hc.Mesh:
    w = 2.5
    parts = [
        box(0, 0, 0, 70, 40, w),                 # bottom end wall (on the plate)
        box(0, 0, 120 - w, 70, 40, 120),         # top end wall: its underside is the big inner ceiling
        box(0, 0, w, w, 40, 120 - w),            # side walls
        box(70 - w, 0, w, 70, 40, 120 - w),
        box(w, 40 - w, w, 70 - w, 40, 120 - w),  # back wall; the box is open towards -y
    ]
    for z in (30, 60, 90):                       # horizontal ribs on both sides
        parts += [box(-3, 5, z, 0, 35, z + 3), box(70, 5, z, 73, 35, z + 3)]
    for x0 in (10, 50):                          # hinge knuckles on the back
        parts.append(box(x0, 40, 105, x0 + 10, 46, 113))
    parts.append(box(25, -4, 110, 45, 0, 116))   # latch lug on the open side
    return hc.Mesh.concat(parts)


def tether_test_box() -> hc.Mesh:
    """A quick test print (about 25 min): 60 x 36 x 24 mm box, open towards -y, with a
    55 x 33.5 mm inner ceiling 19 mm above the inner floor. Small enough to print three times
    to compare lobes, tethers and stepped tethers."""
    w = 2.5
    return hc.Mesh.concat([
        box(0, 0, 0, 60, 36, w),                  # floor
        box(0, 0, 24 - w, 60, 36, 24),            # ceiling
        box(0, 0, w, w, 36, 24 - w),              # side walls
        box(60 - w, 0, w, 60, 36, 24 - w),
        box(w, 36 - w, w, 60 - w, 36, 24 - w),    # back wall
    ])


def u_channel(span=40.0, length=40.0, height=16.0, wall=3.5, roof=3.5, brim=10.0, brim_t=0.4) -> hc.Mesh:
    """The simple test bed: an upside-down U channel (two 3.5 mm legs and a 3.5 mm roof, open
    underneath and at both ends) on a big 0.4 mm brim plate. Inner span 40 mm, inner height 16 mm."""
    x1 = 2 * wall + span
    return hc.Mesh.concat([
        box(-brim, -brim, 0, x1 + brim, length + brim, brim_t),            # brim plate (2 layers)
        box(0, 0, brim_t, wall, length, brim_t + height),                   # left leg
        box(wall + span, 0, brim_t, x1, length, brim_t + height),           # right leg
        box(0, 0, brim_t + height, x1, length, brim_t + height + roof),     # roof
    ])


def l_corner(arm=40.0, height=16.0, wall=3.5, roof=3.5, brim=10.0, brim_t=0.4) -> hc.Mesh:
    """Two walls meeting at a corner (an L) with a square roof over them, open on the other two sides,
    on a big 0.4 mm brim plate. The roof's underside is a 40 x 40 mm overhang with walls on two sides only."""
    return hc.Mesh.concat([
        box(-brim, -brim, 0, arm + brim, arm + brim, brim_t),
        box(0, 0, brim_t, arm, wall, brim_t + height),                      # back wall (along X)
        box(0, 0, brim_t, wall, arm, brim_t + height),                      # left wall (along Y)
        box(0, 0, brim_t + height, arm, arm, brim_t + height + roof),       # roof
    ])


def plate_channel(height=15.1, span=40.0, length=40.0, wall=3.5, roof=3.5) -> hc.Mesh:
    """The channel without a built-in brim plate (Cura's own brim does that job): two legs and a roof, the roof's
    underside `height` above the bed (15.1 lands exactly on a layer top with a 0.3 mm first layer and 0.2 mm layers)."""
    x1 = 2 * wall + span
    return hc.Mesh.concat([
        box(0, 0, 0, wall, length, height),
        box(wall + span, 0, 0, x1, length, height),
        box(0, 0, height, x1, length, height + roof),
    ])


def plate_corner(height=15.1, arm=40.0, wall=3.5, roof=3.5) -> hc.Mesh:
    """The L corner without a built-in brim plate."""
    return hc.Mesh.concat([
        box(0, 0, 0, arm, wall, height),
        box(0, 0, 0, wall, arm, height),
        box(0, 0, height, arm, arm, height + roof),
    ])


def ellipsoid(c, r, tilt_deg=0.0, n=40):
    th = np.linspace(0, np.pi, n + 1)
    ph = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    v = np.array([[r[0] * math.sin(t) * math.cos(p), r[1] * math.sin(t) * math.sin(p), r[2] * math.cos(t)]
                  for t in th for p in ph])
    a = math.radians(tilt_deg)
    rot = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    v = v @ rot.T + np.asarray(c, float)
    m = 2 * n
    f = []
    for i in range(n):
        for j in range(m):
            p, q = i * m + j, i * m + (j + 1) % m
            f += [[p, p + m, q], [q, p + m, q + m]]
    mesh = hc.Mesh(v, np.array(f))
    if mesh.volume() < 0:
        mesh.faces = mesh.faces[:, ::-1]
    return mesh


def cylinder_x(x0, x1, cy, cz, r, n=32):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring0 = np.column_stack([np.full(n, x0), cy + r * np.cos(th), cz + r * np.sin(th)])
    ring1 = ring0.copy()
    ring1[:, 0] = x1
    v = np.vstack([ring0, ring1, [[x0, cy, cz]], [[x1, cy, cz]]])
    c0, c1 = 2 * n, 2 * n + 1
    f = []
    for i in range(n):
        j = (i + 1) % n
        f += [[i, n + i, j], [j, n + i, n + j], [c0, i, j], [c1, n + j, n + i]]
    m = hc.Mesh(v, np.array(f))
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


def tilted_blob() -> hc.Mesh:
    body = ellipsoid((0, 0, 15.2), (18, 12, 15), tilt_deg=30)
    body.vertices[:, 2] = np.maximum(body.vertices[:, 2], 0.0)   # flat patch on the plate
    boss = cylinder_x(10, 24, 0, 9, 3.5)
    return hc.Mesh.concat([body, boss])


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    hc.write_stl(os.path.join(out, "rugged_box.stl"), rugged_box())
    hc.write_stl(os.path.join(out, "tilted_blob.stl"), tilted_blob())
    hc.write_stl(os.path.join(out, "tether_test_box.stl"), tether_test_box())
    hc.write_stl(os.path.join(out, "u_channel.stl"), u_channel())
