# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Render a test model with generated supports to PNG (needs matplotlib).

    python3 tools/preview.py out.png [trapezoid|conform] [gusset_height_mm]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "HybridSupports"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
import hybrid_core as hc  # noqa: E402
from test_core import box  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402


def demo_model():
    # pillar, a wide shelf, and a sloped shelf on the other side above a ledge
    v = np.array([[-10, 0, 22], [-30, 0, 30], [-30, 12, 30], [-10, 12, 22],
                  [-10, 0, 34], [-30, 0, 34], [-30, 12, 34], [-10, 12, 34]], float)
    slope = hc.Mesh(v, box(0, 0, 0, 1, 1, 1).faces[:, ::-1])
    return hc.Mesh.concat([box(-10, 0, 0, 10, 12, 40), box(10, -10, 30, 34, 22, 34),
                           slope, box(-26, 0, 8, -10, 12, 10)])


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "preview.png"
    mode = sys.argv[2] if len(sys.argv) > 2 else "conform"
    g_h = float(sys.argv[3]) if len(sys.argv) > 3 else hc.HybridSettings.gusset_height
    m = demo_model()
    units = hc.generate(m.vertices, m.faces, hc.HybridSettings(head_mode=mode, gusset_height=g_h))
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    ax.add_collection3d(Poly3DCollection(m.vertices[m.faces], alpha=0.25, facecolor="#8899aa", edgecolor="none"))
    for u in units:
        ax.add_collection3d(Poly3DCollection(u.support.vertices[u.support.faces], alpha=0.9,
                                             facecolor="#e07b39", edgecolor="#7a3a10", linewidth=0.1))
        if u.blocker is not None:
            ax.add_collection3d(Poly3DCollection(u.blocker.vertices[u.blocker.faces], alpha=0.15,
                                                 facecolor="#cc2222", edgecolor="none"))
    ax.set_xlim(-35, 35); ax.set_ylim(-20, 30); ax.set_zlim(0, 42)
    ax.set_box_aspect((70, 50, 42)); ax.view_init(elev=14, azim=-62)
    ax.set_title(f"Hybrid tower supports: {mode} head, gusset height {g_h:g} mm, {len(units)} units")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    for u in units:
        print(u.island_id, f"land={u.landing_z:.1f} tower_top={u.tower_top:.1f} under={u.underside_z:.1f}", u.notes)


if __name__ == "__main__":
    main()
