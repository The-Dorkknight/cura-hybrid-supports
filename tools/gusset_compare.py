# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Side-by-side render of one tower at different gusset heights, with volumes.

    python3 tools/gusset_compare.py out.png 3 8 15
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "HybridSupports"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
import hybrid_core as hc  # noqa: E402
from test_core import box  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "gussets.png"
    heights = [float(x) for x in sys.argv[2:]] or [3.0, 8.0, 15.0]
    model = hc.Mesh.concat([box(0, 0, 0, 10, 16, 60), box(10, 0, 50, 30, 16, 54)])
    fig = plt.figure(figsize=(3.6 * len(heights), 5.2))
    for i, h in enumerate(heights):
        s = hc.HybridSettings(gusset_height=h, gusset_length=6, blocker=False)
        u = hc.generate(model.vertices, model.faces, s)[0]
        ax = fig.add_subplot(1, len(heights), i + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(model.vertices[model.faces], alpha=0.2, facecolor="#8899aa", edgecolor="none"))
        ax.add_collection3d(Poly3DCollection(u.support.vertices[u.support.faces], alpha=0.95,
                                             facecolor="#e07b39", edgecolor="#7a3a10", linewidth=0.1))
        ax.set_xlim(5, 35); ax.set_ylim(-7, 23); ax.set_zlim(0, 56)
        ax.set_box_aspect((30, 30, 56)); ax.view_init(elev=10, azim=-60)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"gusset {h:g} mm\nsupport volume {u.support.volume() / 1000:.2f} cm³", fontsize=10)
    fig.suptitle("Same tower, different gusset heights (before Cura's support infill)", fontsize=11)
    fig.savefig(out, dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main()
