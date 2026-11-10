# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Render the test models (tests/models.py) with generated supports.

    python3 tools/preview_models.py out_dir [branch|trapezoid|conform]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "HybridSupports"), os.path.join(HERE, "..", "tests")]
import hybrid_core as hc  # noqa: E402
import models  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402


def render(model, units, path, title, views):
    fig = plt.figure(figsize=(6.2 * len(views), 6.4))
    allv = [model.vertices] + [u.support.vertices for u in units]
    lo = min(v.min(axis=0) for v in allv) if False else __import__("numpy").vstack(allv).min(axis=0)
    hi = __import__("numpy").vstack(allv).max(axis=0)
    for i, (elev, azim) in enumerate(views):
        ax = fig.add_subplot(1, len(views), i + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(model.vertices[model.faces], alpha=0.18, facecolor="#8899aa",
                                             edgecolor="none"))
        for u in units:
            ax.add_collection3d(Poly3DCollection(u.support.vertices[u.support.faces], alpha=0.95,
                                                 facecolor="#e07b39", edgecolor="#7a3a10", linewidth=0.05))
        size = (hi - lo).max()
        mid = (hi + lo) / 2
        ax.set_xlim(mid[0] - size / 2, mid[0] + size / 2)
        ax.set_ylim(mid[1] - size / 2, mid[1] + size / 2)
        ax.set_zlim(0, size)
        ax.view_init(elev=elev, azim=azim)
        ax.set_box_aspect((1, 1, 1))
    fig.suptitle(title)
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    mode = sys.argv[2] if len(sys.argv) > 2 else "branch"
    os.makedirs(out, exist_ok=True)
    s = hc.HybridSettings(head_mode=mode, support_angle=45)
    for name, model, views in (("rugged_box", models.rugged_box(), [(18, -70), (60, -100)]),
                               ("tilted_blob", models.tilted_blob(), [(10, -60), (-25, -60)])):
        units = hc.generate(model.vertices, model.faces, s)
        render(model, units, os.path.join(out, f"{name}_{mode}.png"),
               f"{name}: {len(units)} supports ({mode} head)", views)
        print(name, len(units))


if __name__ == "__main__":
    main()
