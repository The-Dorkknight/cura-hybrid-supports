# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
#
# Scene-node creation follows the pattern of Cura's own SupportEraser tool
# (Ultimaker B.V., LGPLv3); no code was copied from it.
"""Cura tool: generate hybrid tower supports for the selected model(s)."""

import json
import os
import time
from datetime import datetime
from typing import List, Optional

import numpy

from PyQt6.QtCore import Qt

from UM.Logger import Logger
from UM.Math.Vector import Vector
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Message import Message
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from UM.Operations.TranslateOperation import TranslateOperation
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Selection import Selection
from UM.Settings.SettingInstance import SettingInstance
from UM.Tool import Tool

from cura.CuraApplication import CuraApplication
from cura.Operations.SetParentOperation import SetParentOperation
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator
from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator

from . import hybrid_core as hc
from . import tether_gcode

__version__ = hc.__version__


def _buildDate() -> str:
    """Build stamp written by install.py; file time when run from source."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "build_info.json"), encoding="utf-8") as fh:
            return str(json.load(fh)["build_date"])
    except Exception:
        return datetime.fromtimestamp(os.path.getmtime(__file__)).strftime("%Y-%m-%d %H:%M") + " dev"


__build_date__ = _buildDate()

TOWER_PREFIX = "HybridTower"
BLOCKER_PREFIX = "HybridBlocker"
CAP_PREFIX = "HybridCap"        # tether_gcode.cap_stack finds the cap's lines by this mesh name


class HybridSupportsTool(Tool):
    def __init__(self) -> None:
        super().__init__()
        self._shortcut_key = Qt.Key.Key_H
        self._s = hc.HybridSettings()
        self._status = "Select a model, then press Generate."
        self._last_units = []
        self._support_hint = False
        self._wall_settings = {}
        self._cap_settings = {}
        self._global_saved = {}
        self._gcode_plans = []                # tethers: per-layer stagger applied to the G-code
        self._plans_by_model = {}             # model id -> its G-code plans (so models with different heads can share a plate)
        self._need_by_model = {}              # model id -> Cura settings its supports need
        try:
            CuraApplication.getInstance().getOutputDeviceManager().writeStarted.connect(self._onWriteStarted)
        except Exception:
            Logger.logException("w", "Hybrid Supports: could not hook G-code output; tethers won't be staggered or slowed")
        self.setExposedProperties(
            "HeadMode", "ConeFill", "BridgeGap", "GussetCount", "GussetHeight", "GussetLength",
            "WallLines", "MaxSpan", "TetherHeight", "TetherCoverage", "BridgeSpeed", "CapFlow", "CapStack", "ContactGap", "MaxTowerRadius", "UseBlocker",
            "UseCuraAngle", "SupportAngle", "Status", "VersionText",
        )

    # ---------------------------------------------------------------- props
    def _num(self, value, cast=float):
        try:
            return cast(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    def getHeadMode(self) -> str:
        return self._s.head_mode

    def setHeadMode(self, v: str) -> None:
        if v in ("cone", "lobes", "tethers", "branch", "trapezoid", "conform") and v != self._s.head_mode:
            self._s.head_mode = v
            self.propertyChanged.emit()

    def getConeFill(self) -> str:
        return self._s.cone_fill

    def setConeFill(self, v: str) -> None:
        if v in ("cross", "rings", "none") and v != self._s.cone_fill:
            self._s.cone_fill = v
            self.propertyChanged.emit()

    def _setter(name, field, cast=float, lo=None, hi=None, scale=1.0):  # noqa: N805
        def setter(self, v):
            x = self._num(v, cast)
            if x is None:
                return
            x = x * scale
            if lo is not None:
                x = max(lo, x)
            if hi is not None:
                x = min(hi, x)
            if getattr(self._s, field) != x:
                setattr(self._s, field, cast(x) if cast is int else x)
                self.propertyChanged.emit()
        setter.__name__ = "set" + name
        return setter

    getBridgeGap = lambda self: self._s.bridge_gap  # noqa: E731
    setBridgeGap = _setter("BridgeGap", "bridge_gap", float, 0.0, 60.0)
    getGussetCount = lambda self: self._s.gusset_count  # noqa: E731
    setGussetCount = _setter("GussetCount", "gusset_count", int, 0, 8)
    getGussetHeight = lambda self: self._s.gusset_height  # noqa: E731
    setGussetHeight = _setter("GussetHeight", "gusset_height", float, 0.0, 100.0)
    getGussetLength = lambda self: self._s.gusset_length  # noqa: E731
    setGussetLength = _setter("GussetLength", "gusset_length", float, 0.0, 50.0)
    getWallLines = lambda self: self._s.wall_lines  # noqa: E731
    setWallLines = _setter("WallLines", "wall_lines", int, 1, 10)
    getMaxSpan = lambda self: self._s.max_span  # noqa: E731
    setMaxSpan = _setter("MaxSpan", "max_span", float, 5.0, 500.0)
    getTetherHeight = lambda self: self._s.tether_height  # noqa: E731
    setTetherHeight = _setter("TetherHeight", "tether_height", float, 3.0, 40.0)
    def getTetherCoverage(self):
        return round(100.0 * self._s.tether_coverage, 1)
    setTetherCoverage = _setter("TetherCoverage", "tether_coverage", float, 0.05, 0.6, 0.01)   # panel shows %; bounds are fractions
    getBridgeSpeed = lambda self: self._s.tether_bridge_speed  # noqa: E731
    setBridgeSpeed = _setter("BridgeSpeed", "tether_bridge_speed", float, 0.0, 120.0)
    def getCapFlow(self):
        return round(100.0 * self._s.tether_cap_flow, 1)
    setCapFlow = _setter("CapFlow", "tether_cap_flow", float, 0.3, 1.0, 0.01)   # panel shows %; 100 = off
    getContactGap = lambda self: self._s.contact_gap  # noqa: E731
    setContactGap = _setter("ContactGap", "contact_gap", float, 0.0, 2.0)
    getMaxTowerRadius = lambda self: self._s.max_tower_radius  # noqa: E731
    setMaxTowerRadius = _setter("MaxTowerRadius", "max_tower_radius", float, 1.0, 30.0)
    getSupportAngle = lambda self: self._s.support_angle  # noqa: E731
    setSupportAngle = _setter("SupportAngle", "support_angle", float, 0.0, 89.0)
    del _setter

    _use_cura_angle = True

    def getUseCuraAngle(self) -> bool:
        return self._use_cura_angle

    def setUseCuraAngle(self, v) -> None:
        v = bool(v)
        if v != self._use_cura_angle:
            self._use_cura_angle = v
            self.propertyChanged.emit()

    def getCapStack(self) -> bool:
        return self._s.tether_cap_stack

    def setCapStack(self, v) -> None:
        v = bool(v)
        if v != self._s.tether_cap_stack:
            self._s.tether_cap_stack = v
            self.propertyChanged.emit()

    def getUseBlocker(self) -> bool:
        return self._s.blocker

    def setUseBlocker(self, v) -> None:
        v = bool(v)
        if v != self._s.blocker:
            self._s.blocker = v
            self.propertyChanged.emit()

    def getStatus(self) -> str:
        return self._status

    def getVersionText(self) -> str:
        return f"Hybrid Supports v{__version__} (Built {__build_date__}) \u2022 WORK IN PROGRESS"

    def _setStatus(self, text: str) -> None:
        self._status = text
        self.propertyChanged.emit()

    # -------------------------------------------------------------- helpers
    def _readCuraSettings(self) -> None:
        stack = CuraApplication.getInstance().getGlobalContainerStack()
        if not stack:
            return
        try:
            nr = int(stack.getExtruderPositionValueWithDefault("support_extruder_nr"))
            ext = stack.extruderList[nr]
        except Exception:  # single-extruder or odd machine definitions
            ext = stack
        def val(key, default=None):
            try:
                v = ext.getProperty(key, "value")
                return default if v is None else v
            except Exception:
                return default
        lw = val("support_line_width")
        if lw:
            self._s.line_width = float(lw)
        self._s.layer_height = float(val("layer_height", 0.2))
        self._s.layer_height_0 = float(val("layer_height_0", self._s.layer_height))
        # keep the towers out of the zone Cura strips around the model, so it can't cut them up
        self._s.xy_clearance = float(val("support_xy_distance", 0.7)) + 0.1
        # with no support walls, Cura prints thin support areas only where its infill lines
        # cross them; make branches at least one infill spacing thick so none go missing
        walls = int(val("support_wall_count", 0) or 0)
        spacing = float(val("support_line_distance", 0) or 0)
        self._s.min_branch_thickness = 0.0 if walls > 0 or spacing <= 0 else min(spacing + self._s.line_width, 4.0)
        self._support_hint = walls == 0 and not self._s.print_walls
        # towers printed as walls: a normal mesh with one wall round every outline (a 2-line-thick wall
        # prints as one closed loop), no infill and no top or bottom skin, at the support speed and flow
        sp = val("speed_support")
        flow = val("support_material_flow")
        self._wall_settings = {
            # solid rounded lobes get this many walls (thin parts get as many as fit), no infill
            "wall_line_count": max(1, int(self._s.wall_lines)), "infill_sparse_density": 0,
            "top_layers": 0, "bottom_layers": 0, "initial_bottom_layers": 0,
            "roofing_layer_count": 0, "flooring_layer_count": 0,
            "xy_offset": 0, "xy_offset_layer_0": 0,              # no elephant-foot shrink eating thin walls
            "wall_line_width_0": self._s.line_width, "wall_line_width_x": self._s.line_width,
            "wall_0_wipe_dist": 0, "support_enable": False, "meshfix_union_all": True,
        }
        # the interface cap on the towers: solid skin on every layer, which the cap stack replaces on save
        self._cap_settings = {
            "wall_line_count": 0, "infill_sparse_density": 0,
            "top_layers": 99, "bottom_layers": 99, "initial_bottom_layers": 99,
            "roofing_layer_count": 0, "flooring_layer_count": 0,
            "xy_offset": 0, "xy_offset_layer_0": 0, "support_enable": False,
            "skin_line_width": self._s.line_width, "meshfix_union_all": True,
        }
        if sp:
            self._wall_settings.update({"speed_wall_0": float(sp), "speed_wall_x": float(sp)})
            self._cap_settings.update({"speed_topbottom": float(sp)})
        if flow:
            self._wall_settings.update({"wall_0_material_flow": float(flow), "wall_x_material_flow": float(flow)})
        if self._use_cura_angle:
            ang = ext.getProperty("support_angle", "value")
            if ang is not None:
                self._s.support_angle = float(ang)

    @staticmethod
    def _models() -> List[CuraSceneNode]:
        out = []
        for node in Selection.getAllSelectedObjects():
            if node.callDecoration("isGroup"):
                cands = [n for n in DepthFirstIterator(node) if n.getMeshData() and not n.callDecoration("isGroup")]
            else:
                cands = [node]
            for n in cands:
                if n.getMeshData() is None or n.callDecoration("isNonPrintingMesh"):
                    continue
                if n.getName().startswith((TOWER_PREFIX, BLOCKER_PREFIX, CAP_PREFIX)):
                    continue
                out.append(n)
        return out

    @staticmethod
    def _worldTriangles(node: CuraSceneNode):
        md = node.getMeshData().getTransformed(node.getWorldTransformation(copy=False))
        v = md.getVertices().astype(numpy.float64)
        f = md.getIndices() if md.hasIndices() else numpy.arange(len(v)).reshape(-1, 3)
        # Cura is Y-up with Z towards the front; the core is Z-up.
        vz = numpy.column_stack([v[:, 0], -v[:, 2], v[:, 1]])
        return vz, f

    @staticmethod
    def _toCuraMesh(mesh: "hc.Mesh"):
        v = mesh.vertices
        vc = numpy.column_stack([v[:, 0], v[:, 2], -v[:, 1]])  # back to Y-up
        centre = (vc.min(axis=0) + vc.max(axis=0)) / 2.0
        mb = MeshBuilder()
        mb.setVertices((vc - centre).astype(numpy.float32))
        mb.setIndices(mesh.faces.astype(numpy.int32))
        mb.calculateNormals()
        return mb.build(), Vector(float(centre[0]), float(centre[1]), float(centre[2]))

    def _makeNode(self, parent: CuraSceneNode, mesh: "hc.Mesh", name: str, setting: Optional[str], op: GroupedOperation,
                  extra: Optional[dict] = None) -> None:
        """setting: "support_mesh" / "anti_overhang_mesh", or None for a normal printed mesh (extra = its settings)."""
        md, centre = self._toCuraMesh(mesh)
        node = CuraSceneNode()
        node.setName(name)
        node.setSelectable(True)
        node.setCalculateBoundingBox(True)
        node.setMeshData(md)
        node.calculateBoundingBoxMesh()
        plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        node.addDecorator(BuildPlateDecorator(plate))
        node.addDecorator(SliceableObjectDecorator())

        stack = node.callDecoration("getStack")
        top = stack.getTop()
        values = {setting: True} if setting else dict(extra or {})
        if setting == "support_mesh":
            values["support_mesh_drop_down"] = False   # we already built down to the landing
            # some printer profiles (e.g. Elegoo) throw away support pieces under 3 mm^2 per layer,
            # which would leave bits of branches and gussets floating; keep every piece
            values["minimum_support_area"] = 0
            values.update(extra or {})
        for key, val in values.items():
            definition = stack.getSettingDefinition(key)
            if definition is None:          # a setting this Cura version doesn't have (e.g. flooring_layer_count)
                continue
            inst = SettingInstance(definition, top)
            inst.setProperty("value", val)
            inst.resetState()
            top.addInstance(inst)

        root = self.getController().getScene().getRoot()
        op.addOperation(AddSceneNodeOperation(node, root))
        op.addOperation(SetParentOperation(node, parent))
        op.addOperation(TranslateOperation(node, centre, set_position=True))

    def _setGlobalOverrides(self, values: dict) -> None:
        """Cura settings the tethers head needs (user changes on the global stack). Remove puts them back."""
        stack = CuraApplication.getInstance().getGlobalContainerStack()
        if stack is None or not values:
            return
        user = stack.userChanges
        for key, val in values.items():
            if key not in self._global_saved:
                self._global_saved[key] = user.getProperty(key, "value") if user.getInstance(key) is not None else None
            stack.setProperty(key, "value", val)

    def _restoreGlobal(self) -> None:
        stack = CuraApplication.getInstance().getGlobalContainerStack()
        saved, self._global_saved = self._global_saved, {}
        if not saved or stack is None:
            return
        user = stack.userChanges
        for key, prev in saved.items():
            if prev is None:
                if user.getInstance(key) is not None:
                    user.removeInstance(key)
            else:
                stack.setProperty(key, "value", prev)

    def postProcessGcode(self, gcode_list):
        """Shift every other layer's tether lines and slow the first, mid-air layers (tether_gcode.py). Safe to call twice."""
        if not self._gcode_plans:
            return gcode_list
        stack = CuraApplication.getInstance().getGlobalContainerStack()
        off = (0.0, 0.0)
        if stack is not None and not stack.getProperty("machine_center_is_zero", "value"):
            off = (stack.getProperty("machine_width", "value") / 2.0, stack.getProperty("machine_depth", "value") / 2.0)
        out = tether_gcode.stagger(gcode_list, self._gcode_plans, off)
        try:
            out = tether_gcode.cap_stack(out, self._gcode_plans, off)
        except Exception:
            Logger.logException("e", "Hybrid Supports: cap stack failed; Cura's plain roof stays")
        return tether_gcode.slow_bridges(out, self._gcode_plans, off)

    def _onWriteStarted(self, output_device) -> None:
        if not self._gcode_plans:
            return
        try:
            scene = self.getController().getScene()
            gd = getattr(scene, "gcode_dict", None)
            plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
            if gd and gd.get(plate):
                gd[plate] = self.postProcessGcode(gd[plate])
                setattr(scene, "gcode_dict", gd)
        except Exception:
            Logger.logException("e", "Hybrid Supports: tether stagger failed; G-code saved without it")

    def _allNeeds(self) -> dict:
        need = {}
        for v in self._need_by_model.values():
            need.update(v)
        return need

    def _ours(self, model: CuraSceneNode):
        return [c for c in model.getChildren() if c.getName().startswith((TOWER_PREFIX, BLOCKER_PREFIX, CAP_PREFIX))]

    # -------------------------------------------------------------- actions
    def generateSupports(self) -> None:
        models = self._models()
        if not models:
            self._setStatus("Select a model first.")
            return
        self._restoreGlobal()                 # read the user's own values, not ones we set last time
        self._readCuraSettings()
        t0 = time.perf_counter()
        op = GroupedOperation()
        n_units, notes = 0, []
        self._last_units = []
        for model in models:
            key = id(model)
            self._plans_by_model[key], self._need_by_model[key] = [], {}
            for old in self._ours(model):
                op.addOperation(RemoveSceneNodeOperation(old))
            try:
                v, f = self._worldTriangles(model)
                units = hc.generate(v, f, self._s)
            except Exception as e:  # keep Cura alive whatever the mesh looks like
                Logger.logException("e", "Hybrid Supports failed on %s", model.getName())
                notes.append(f"{model.getName()}: failed ({e})")
                continue
            self._last_units += units
            for u in units:
                n_units += 1
                if getattr(u, "print_as", "support") == "walls":
                    self._makeNode(model, u.support, f"{TOWER_PREFIX}_{n_units:02d}", None, op,
                                   dict(self._wall_settings, **u.mesh_settings))
                else:
                    self._makeNode(model, u.support, f"{TOWER_PREFIX}_{n_units:02d}", "support_mesh", op, u.mesh_settings)
                for ci, cap in enumerate(getattr(u, "caps", []) or []):
                    self._makeNode(model, cap, f"{CAP_PREFIX}_{n_units:02d}{chr(97 + ci % 26)}", None, op,
                                   dict(self._cap_settings))
                if u.blocker is not None:
                    self._makeNode(model, u.blocker, f"{BLOCKER_PREFIX}_{n_units:02d}", "anti_overhang_mesh", op)
                notes.extend(u.notes)
                self._need_by_model[key].update(u.global_settings)
                if getattr(u, "gcode_plan", None):
                    self._plans_by_model[key].extend(u.gcode_plan if isinstance(u.gcode_plan, list) else [u.gcode_plan])
        if op.getNumChildrenOperations():
            op.push()
        need = self._allNeeds()
        if need:
            self._setGlobalOverrides(need)
        self._gcode_plans = [p for v in self._plans_by_model.values() for p in v]
        dt = time.perf_counter() - t0
        msg = f"{n_units} support(s) in {dt:.1f} s"
        short = [u for u in self._last_units if u.coverage < 0.95]
        if short:
            msg += f" \u2022 {len(short)} only partly reached (blocked by the model)"
        if self._support_hint and n_units and self._s.head_mode in ("cone", "branch"):
            msg += " \u2022 tip: Support Wall Line Count 1 prints thin support walls cleaner"
        if need:
            extra = (f"Support Infill Line Directions {need['support_infill_angles']}" if "support_infill_angles" in need
                     else f"Support Pattern {need.get('support_pattern', '')}")
            msg += (" \u2022 tethers: set Support X/Y Distance 0, Support Roof on and " + extra +
                    " in Cura's settings (Remove puts them back)")
        spaghetti = [n for n in notes if "Flying Spaghetti Monster" in n]
        too_far = [n for n in notes if n.startswith("tethers:") and "limit" in n]
        if spaghetti:
            msg += f" \u2022 {len(spaghetti)} tether(s) past the {self._s.tether_warn_span:.0f} mm warning span"
        if too_far:
            msg += f" \u2022 {len(too_far)} too wide for tethers (lobes used instead)"
        capped = [n for n in notes if "capped" in n]
        if capped:
            msg += f" \u2022 gusset height capped on {len(capped)}"
        self._setStatus(msg)
        if spaghetti or too_far:
            lines = sorted(set(spaghetti + too_far))
            Message("\n".join(lines[:6]), title="Hybrid Supports: tether span",
                    message_type=Message.MessageType.WARNING).show()
        if n_units == 0:
            Message("No overhangs needing support were found at the current support angle.",
                    title="Hybrid Supports", message_type=Message.MessageType.NEUTRAL).show()

    def removeSupports(self) -> None:
        op = GroupedOperation()
        count = 0
        targets = self._models() or [n for n in DepthFirstIterator(self.getController().getScene().getRoot())
                                     if isinstance(n, CuraSceneNode)]
        for model in targets:
            for old in self._ours(model):
                op.addOperation(RemoveSceneNodeOperation(old))
                count += 1
        for model in targets:
            self._plans_by_model.pop(id(model), None)
            self._need_by_model.pop(id(model), None)
        self._restoreGlobal()
        need = self._allNeeds()               # models that keep their supports keep the settings those need
        if need:
            self._setGlobalOverrides(need)
        self._gcode_plans = [p for v in self._plans_by_model.values() for p in v]
        if count:
            op.push()
        self._setStatus(f"Removed {count} generated mesh(es).")
