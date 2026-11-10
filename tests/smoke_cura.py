# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Smoke test of the Cura adapter against real Cura + Uranium source checkouts.

Not a GUI test: it builds a Cura scene node, converts it, generates a tower and
checks coordinates, winding and the panel property plumbing. Native Cura
modules (pyArcus, pySavitar, ...) are stubbed.

    git clone --depth 1 https://github.com/Ultimaker/Cura.git ../Cura
    git clone --depth 1 https://github.com/Ultimaker/Uranium.git ../Uranium
    pip install PyQt6 numpy scipy shapely pyclipper trimesh
    CURA_SRC=../Cura URANIUM_SRC=../Uranium QT_QPA_PLATFORM=offscreen python3 tests/smoke_cura.py

Cura source needs a cura/CuraVersion.py; the script writes a stub if missing.
"""
import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CURA = os.path.abspath(os.environ.get("CURA_SRC", os.path.join(ROOT, "..", "Cura")))
URANIUM = os.path.abspath(os.environ.get("URANIUM_SRC", os.path.join(ROOT, "..", "Uranium")))
if not (os.path.isdir(CURA) and os.path.isdir(URANIUM)):
    print("skip: set CURA_SRC and URANIUM_SRC to Cura/Uranium source checkouts")
    sys.exit(0)
_ver = os.path.join(CURA, "cura", "CuraVersion.py")
if not os.path.exists(_ver):
    with open(_ver, "w") as fh:
        fh.write('CuraAppName = "cura"; CuraAppDisplayName = "UltiMaker Cura"; CuraVersion = "5.14.0"; CuraBuildType = ""\n'
                 'CuraDebugMode = False; CuraCloudAPIRoot = ""; CuraCloudAPIVersion = ""; CuraCloudAccountAPIRoot = ""\n'
                 'CuraDigitalFactoryURL = ""; CuraLatestURL = ""; ConanInstalls = {}; PythonInstalls = {}; DependenciesDescriptions = {}\n')
sys.path[:0] = [URANIUM, CURA, ROOT]
import unittest.mock as _um
class _Stub(types.ModuleType):
    class Socket: pass
    class SocketState: pass
    def __getattr__(self, k): return _um.MagicMock()
for mod in ("pyUvula", "pySavitar", "pyArcus", "pynest2d", "pyDulcificum"):
    sys.modules.setdefault(mod, _Stub(mod))
import importlib
import numpy as np
T = importlib.import_module("HybridSupports.HybridSupportsTool")
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Math.Vector import Vector
from cura.Scene.CuraSceneNode import CuraSceneNode
sys.path.insert(0, HERE)
from test_core import box
hc = T.hc

# cantilever in core coords (Z-up), convert to Cura (Y-up) for the node's mesh
m = hc.Mesh.concat([box(0, 0, 0, 10, 10, 40), box(10, 0, 30, 30, 10, 34)])
v = m.vertices
cura_v = np.column_stack([v[:, 0], v[:, 2], -v[:, 1]])
mb = MeshBuilder(); mb.setVertices(cura_v.astype(np.float32)); mb.setIndices(m.faces.astype(np.int32))
node = CuraSceneNode(no_setting_override=True); node.setMeshData(mb.build())
node.setPosition(Vector(50, 0, 20))           # move the model on the plate

import UM.Application
UM.Application.Application.getInstance = staticmethod(lambda: _um.MagicMock())
tool = T.HybridSupportsTool()
wv, wf = tool._worldTriangles(node)
assert np.isclose(wv[:, 2].min(), 0) and np.isclose(wv[:, 2].max(), 40), "Z-up conversion wrong"
assert np.isclose(wv[:, 0].min(), 50), "world X offset lost"
units = hc.generate(wv, wf, tool._s)
assert len(units) == 1
md, centre = tool._toCuraMesh(units[0].support)
world = md.getVertices() + np.array([centre.x, centre.y, centre.z])
print("tower Y range (Cura up):", world[:, 1].min().round(3), world[:, 1].max().round(3))
assert np.isclose(world[:, 1].min(), 0, atol=1e-4) and np.isclose(world[:, 1].max(), 29.8, atol=1e-4)
assert world[:, 0].min() > 50, "tower not under the shelf"
# winding survives the axis swap: outward normals => positive volume in Cura frame too
f = md.getIndices(); tri = world[f]
vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
assert vol > 0, vol

# property plumbing as ActiveToolProxy uses it (getX / setX by name)
for name, val, want in [("HeadPercent", "35", 35), ("GussetHeight", "4,5", 4.5), ("GussetCount", "0", 0),
                        ("HeadMode", "conform", "conform"), ("GussetLength", "abc", 5.0), ("WallLines", "99", 10)]:
    getattr(tool, "set" + name)(val)
    got = getattr(tool, "get" + name)()
    assert got == want, (name, got, want)
assert all(hasattr(tool, "get" + p) for p in tool.getExposedProperties())
print("smoke OK:", tool.getVersionText())
