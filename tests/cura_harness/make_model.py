# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Write the harness test model: a 60 mm pillar with a 30 x 20 mm shelf 50 mm up."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "HybridSupports"))
sys.path.insert(0, os.path.join(HERE, ".."))
import hybrid_core as hc  # noqa: E402
from test_core import box  # noqa: E402

model = hc.Mesh.concat([box(0, 0, 0, 20, 20, 60), box(20, 0, 50, 50, 20, 54)])
hc.write_stl(sys.argv[1], model)
