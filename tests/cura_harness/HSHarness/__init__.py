# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Development-only Cura extension that exercises Hybrid Supports inside a real Cura.

Inert unless the environment variable HS_HARNESS_OUT is set. See run_in_cura.sh.
"""
import json
import os
import traceback

from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication, QMouseEvent

from UM.Extension import Extension
from UM.Logger import Logger
from UM.Math.Quaternion import Quaternion
from UM.Math.Vector import Vector
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Selection import Selection

from cura.CuraApplication import CuraApplication


class HSHarness(Extension):
    def __init__(self) -> None:
        super().__init__()
        self._out = os.environ.get("HS_HARNESS_OUT", "")
        if not self._out:
            return
        os.makedirs(self._out, exist_ok=True)
        self._app = CuraApplication.getInstance()
        self._model = os.environ.get("HS_HARNESS_MODEL", "")
        self._printer = os.environ.get("HS_HARNESS_PRINTER", "creality_ender3")
        self._mode = os.environ.get("HS_HARNESS_MODE", "trapezoid")
        self._res = {"steps": [], "ok": False, "mode": self._mode}
        self._queue = []
        self._slice_state = None
        self._app.engineCreatedSignal.connect(self._onEngine)
        self._app.initializationFinished.connect(self._onReady)

    # ------------------------------------------------------------ plumbing
    def _log(self, msg):
        Logger.log("i", "[HSHarness] %s", msg)
        self._res["steps"].append(msg)
        self._save()

    def _save(self):
        with open(os.path.join(self._out, "results.json"), "w") as fh:
            json.dump(self._res, fh, indent=1, default=str)

    WATCHED = ("wall_thickness", "wall_line_count", "top_bottom_thickness", "top_layers", "infill_sparse_density",
               "support_enable", "layer_height")

    def _snap(self, label):
        """Record a few print settings, to prove the plugin never changes the user's profile."""
        stack = self._app.getGlobalContainerStack()
        ext = stack.extruderList[0] if stack and stack.extruderList else stack
        vals = {k: str(ext.getProperty(k, "value")) for k in self.WATCHED} if ext else {}
        self._res.setdefault("settings", []).append([label, vals])
        if vals and vals.get("wall_line_count") == "0":
            # Seen once in about twenty runs: the harness adds the first printer while Cura's window is still being
            # built, and Cura's own "Recommended" panel then writes 0 into wall and top/bottom thickness.
            # It happens before any plugin code runs. A run like that must not be used for numbers.
            raise RuntimeError("Cura started with wall thickness 0 (first-run race in this harness, not the "
                               "plugin). Run the harness again.")
        first = self._res["settings"][0][1]
        if first and vals != first:
            changed = {k: (first[k], vals[k]) for k in vals if vals[k] != first.get(k)}
            raise RuntimeError(f"print settings changed during '{label}': {changed}")
        self._save()

    def _shot(self, name):
        try:
            img = self._app.getMainWindow().grabWindow()
            img.save(os.path.join(self._out, name + ".png"))
        except Exception as e:
            self._log(f"screenshot {name} failed: {e}")

    def _items(self, item=None, window=None):
        item = item or (window or self._app.getMainWindow()).contentItem()
        yield item
        for child in item.childItems():
            yield from self._items(child)

    def _find(self, test, window=None):
        for it in self._items(window=window):
            try:
                if it.isVisible() and test(it):
                    return it
            except Exception:
                pass
        return None

    def _click(self, item, window=None):
        """Send a real left click to the centre of a QML item."""
        win = window or self._app.getMainWindow()
        p = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        g = QPointF(win.mapToGlobal(p.toPoint()))
        for typ, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                             (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            QCoreApplication.sendEvent(win, QMouseEvent(typ, p, g, Qt.MouseButton.LeftButton, buttons,
                                                        Qt.KeyboardModifier.NoModifier))
        return [round(p.x()), round(p.y())]

    def _hideMessages(self):
        for m in list(self._app.getVisibleMessages()):
            m.hide()

    def _run(self, steps):
        self._queue = list(steps)
        self._next()

    def _next(self, delay=1500):
        if not self._queue:
            return
        fn = self._queue.pop(0)

        def call():
            try:
                wait = fn()
            except Exception:
                self._res["error"] = traceback.format_exc()
                self._log("FAILED in " + fn.__name__)
                self._finish()
                return
            if wait != "async":
                self._next(wait or 1500)
        QTimer.singleShot(delay, call)

    def _finish(self):
        self._save()
        QTimer.singleShot(500, QCoreApplication.quit)

    # --------------------------------------------------------------- steps
    def _onEngine(self):
        prefs = self._app.getPreferences()
        prefs.setValue("general/accepted_user_agreement", True)
        # A test run must not send crash or usage reports to UltiMaker.
        prefs.setValue("info/send_engine_crash", False)
        prefs.setValue("info/send_slice_info", False)
        os.environ["USE_SENTRY"] = "0"
        mm = self._app.getMachineManager()
        if mm.activeMachine is None:
            mm.addMachine(self._printer)
        self._log(f"machine: {mm.activeMachine.getName() if mm.activeMachine else None}")

    def _onReady(self):
        size = os.environ.get("HS_HARNESS_WINDOW", "")
        if "x" in size:
            w, h = (int(v) for v in size.split("x"))
            self._app.getMainWindow().setWidth(w)
            self._app.getMainWindow().setHeight(h)
        pkg = os.environ.get("HS_HARNESS_INSTALL", "")
        if pkg:                                            # install a .curapackage the way drag-and-drop does
            got = self._app.installPackageViaDragAndDrop(QUrl.fromLocalFile(pkg).toString())
            self._log(f"installPackage returned: {got}")
            self._res["ok"] = bool(got)
            QTimer.singleShot(4000, self._finish)
            return
        if os.environ.get("HS_HARNESS_PLATE"):             # several models on one plate, each with its own head
            self._plate = json.load(open(os.environ["HS_HARNESS_PLATE"]))
            self._run([self._plateLoad, self._plateWait, self._plateSettings, self._plateActivate, self._plateGenerateAll,
                       self._slice, self._plateDone])
            return
        if os.environ.get("HS_HARNESS_PLAIN") == "1":      # control: slice the bare model only
            self._snap("cura started")
            self._run([self._load, self._waitModel, self._plainSlice, self._done])
            return
        steps = [self._visibility, self._marketOpen, self._marketManage, self._marketShot,
                 self._load, self._waitModel, self._activate, self._panelCheck, self._generate,
                 self._inspect, self._slice, self._preview]
        if os.environ.get("HS_HARNESS_QUICK") != "1":      # comparison slices take a few minutes
            steps += [self._baseline, self._treeBaseline, self._undoRedo]
        self._run(steps + [self._done])

    # ---- one plate, many models: HS_HARNESS_PLATE=file.json with
    # {"settings": {cura setting: value}, "parts": [{"file", "mode", "x", "y", "set": {tool property: value}}]}
    def _plateLoad(self):
        for part in self._plate["parts"]:
            self._app.readLocalFile(QUrl.fromLocalFile(part["file"]))
        self._app.getPreferences().setValue("physics/automatic_push_free", False)
        self._tries = 0
        return 3000

    def _plateWait(self):
        models = self._models()
        if len(models) < len(self._plate["parts"]):
            self._tries += 1
            if self._tries > 90:
                raise RuntimeError(f"only {len(models)} of {len(self._plate['parts'])} models appeared")
            self._queue.insert(0, self._plateWait)
            return 1000
        stack = self._app.getGlobalContainerStack()
        w = float(stack.getProperty("machine_width", "value"))
        d = float(stack.getProperty("machine_depth", "value"))
        zero = bool(stack.getProperty("machine_center_is_zero", "value"))
        by_name = {n.getName(): n for n in models}
        self._parts = []
        for part in self._plate["parts"]:
            stem = os.path.basename(part["file"])
            node = by_name.get(stem) or by_name.get(os.path.splitext(stem)[0])
            if node is None:
                raise RuntimeError(f"no model named {stem}; have {sorted(by_name)}")
            ox, oy = (0.0, 0.0) if zero else (w / 2.0, d / 2.0)
            node.setOrientation(Quaternion())                  # Cura may have auto-arranged (and turned) it on load
            pos = node.getPosition()
            node.setPosition(Vector(part["x"] - ox, pos.y, -(part["y"] - oy)))     # scene z points to the front
            bb = node.getBoundingBox()
            self._log(f"{stem}: {part['mode']} at x={part['x']} y={part['y']} bbox {bb.minimum} .. {bb.maximum}")
            self._parts.append((node, part))
        self._node = self._parts[0][0]
        self._snap("plate loaded")

    def _plateSettings(self):
        stack = self._app.getGlobalContainerStack()
        ext = stack.extruderList[0] if getattr(stack, "extruderList", None) else stack
        for k, v in self._plate.get("settings", {}).items():
            per_ext = False
            try:
                per_ext = bool(stack.getSettingDefinition(k).settable_per_extruder)
            except Exception:
                pass
            (ext if per_ext else stack).setProperty(k, "value", v)
        keys = list(self._plate.get("settings", {}))
        self._res["plate_settings"] = {k: str(ext.getProperty(k, "value")) for k in keys}
        self._log("plate settings now: " + str(self._res["plate_settings"]))
        self._res["settings"] = []                  # these changes are deliberate: start the "profile unchanged" check afresh
        self._snap("plate settings applied")

    def _plateActivate(self):
        return self._activate()

    def _plateGenerateAll(self):
        self._queue.insert(0, self._panelCheck)       # opens the proxy; then one step per part
        steps = []
        for node, part in self._parts:
            def go(node=node, part=part):
                Selection.clear()
                Selection.add(node)
                self._proxy.setProperty("HeadMode", part["mode"])
                for k, v in part.get("set", {}).items():
                    self._proxy.setProperty(k, v)
                self._tool.generateSupports()
                self._log(f"{node.getName()} [{part['mode']}]: {self._tool.getStatus()}")
                return 2500
            steps.append(go)
        self._queue[1:1] = steps
        return 1500

    def _plateDone(self):
        scene_kids = [n.getName() for n in self._models() if n.getName().startswith(("Hybrid",))]
        self._res["ok"] = True
        self._log("plate finished")
        self._finish()

    def _visibility(self):
        """Can a user tell the plugin is installed, in an empty Cura?"""
        vis = self._res["visibility"] = {}
        pm = self._app.getPackageManager()
        listed = [p["package_id"] for p in pm.getAllInstalledPackagesInfo().get("plugin", [])]
        vis["in_marketplace_list"] = "HybridSupports" in listed
        vis["user_installed"] = bool(pm.isUserInstalledPackage("HybridSupports"))
        menus = [e.getMenuName() for e in self._app.getExtensions()]
        vis["extensions_menu"] = "Hybrid Supports" in menus
        vis["intro_message"] = any("Hybrid Supports" in (m.getText() or "") for m in self._app.getVisibleMessages())
        self._log(f"visibility: {vis}")
        self._supportMode()
        self._snap("cura started")
        for m in list(self._app.getVisibleMessages()):       # keep only ours for the screenshot
            if "Hybrid Supports" not in (m.getText() or ""):
                m.hide()
        self._queue.insert(0, lambda: self._shot("00_empty_cura"))
        return 800

    def _marketOpen(self):
        self._market = self._app.getPluginRegistry().getPluginObject("Marketplace")
        self._market.show()
        return 2500

    def _marketWindow(self):
        main = self._app.getMainWindow()
        for w in QGuiApplication.topLevelWindows():
            if w is not main and w.isVisible() and hasattr(w, "contentItem") and "arket" in (w.title() or ""):
                return w
        return None

    def _marketManage(self):
        win = self._marketWindow()
        if win is None:
            self._log("marketplace: window not found")
            return
        btn = self._find(lambda it: it.property("sourcePage") == "ManagedPackages.qml", window=win)
        if btn is None:
            self._log("marketplace: Manage button not found")
            return
        self._log(f"marketplace: clicked Manage at {self._click(btn, window=win)}")
        return 4000

    def _marketShot(self):
        win = self._marketWindow()
        if win is None:
            return
        try:
            win.grabWindow().save(os.path.join(self._out, "00_marketplace.png"))
            names = [str(it.property("text")) for it in self._items(window=win)
                     if it.isVisible() and it.property("text") == "Hybrid Supports"]
            self._res["visibility"]["shown_in_manage_page"] = bool(names)
            self._log(f"marketplace manage page shows Hybrid Supports: {bool(names)}")
        finally:
            win.close()

    def _load(self):
        self._app.readLocalFile(QUrl.fromLocalFile(self._model))
        self._tries = 0
        return 3000

    def _models(self):
        root = self._app.getController().getScene().getRoot()
        return [n for n in DepthFirstIterator(root)
                if n.callDecoration("isSliceable") and n.getParent() is root]

    def _waitModel(self):
        if not self._models():
            self._tries += 1
            if self._tries > 30:
                raise RuntimeError("model never appeared")
            self._queue.insert(0, self._waitModel)
            return 1000
        self._node = self._models()[0]
        bb = self._node.getBoundingBox()
        self._log(f"model loaded: {self._node.getName()} bbox min={bb.minimum} max={bb.maximum}")
        self._snap("model loaded")

    def _activate(self):
        """Select the model and click the Hybrid Supports toolbar button for real."""
        self._hideMessages()
        Selection.clear()
        Selection.add(self._node)
        icon = self._find(lambda it: str(it.property("source").toString()).endswith("tool_icon.svg"))
        if icon is None:
            raise RuntimeError("toolbar button for Hybrid Supports not found")
        self._log(f"clicked toolbar button at {self._click(icon)}")
        return 2500

    def _panelCheck(self):
        tool = self._app.getController().getActiveTool()
        self._log(f"active tool: {tool.getPluginId() if tool else None}")
        if tool is None or tool.getPluginId() != "HybridSupports":
            raise RuntimeError("clicking the toolbar button did not activate the tool")
        self._tool = tool
        if self._find(lambda it: it.objectName() == "hybridGenerate") is None:
            raise RuntimeError("tool panel did not load (Generate button missing)")
        # Change settings through the same proxy the QML panel uses.
        from UM.Qt.Bindings.ActiveToolProxy import ActiveToolProxy
        self._proxy = ActiveToolProxy()
        self._proxy.setProperty("HeadMode", self._mode)
        for k, v in json.loads(os.environ.get("HS_HARNESS_SET", "{}")).items():
            self._proxy.setProperty(k, v)
        self._log("version text: " + tool.getVersionText())
        self._snap("tool panel open")
        self._queue.insert(0, self._panelShot)
        return 1200

    def _panelShot(self):
        self._hideMessages()
        self._shot("01_panel")

    def _supportMode(self):
        mode = os.environ.get("HS_HARNESS_SUPPORT", "off")
        stack = self._app.getGlobalContainerStack()
        if mode in ("normal", "tree"):
            stack.setProperty("support_enable", "value", True)
            stack.setProperty("support_structure", "value", mode)
        self._res["support_mode"] = mode
        for k, v in json.loads(os.environ.get("HS_HARNESS_OVERRIDES", "{}")).items():
            stack.setProperty(k, "value", v)       # e.g. a printer profile's support settings
        self._res["overrides"] = os.environ.get("HS_HARNESS_OVERRIDES", "{}")

    def _generate(self):
        btn = self._find(lambda it: it.objectName() == "hybridGenerate")
        self._log(f"clicked Generate at {self._click(btn)}")
        self._queue.insert(0, self._afterGenerate)
        return 2500

    def _afterGenerate(self):
        self._log("status: " + self._tool.getStatus())
        self._snap("after Generate")

    def _kids(self):
        out = []
        for c in self._node.getChildren():
            bb = c.getBoundingBox()
            out.append({
                "name": c.getName(),
                "support_mesh": bool(c.callDecoration("isSupportMesh")),
                "anti_overhang": bool(c.callDecoration("isAntiOverhangMesh")),
                "min": [round(bb.minimum.x, 2), round(bb.minimum.y, 2), round(bb.minimum.z, 2)],
                "max": [round(bb.maximum.x, 2), round(bb.maximum.y, 2), round(bb.maximum.z, 2)],
            })
        return out

    def _inspect(self):
        stack = self._app.getGlobalContainerStack()
        self._res["machine"] = {k: stack.getProperty(k, "value") for k in
                                ("machine_width", "machine_depth", "machine_center_is_zero")}
        self._res["units"] = [{"trunk_xy": u.trunk_xy, "rt": u.trunk_radius, "land": u.landing_z,
                               "top": u.tower_top, "under": u.underside_z, "branches": u.branches,
                               "coverage": u.coverage, "notes": u.notes}
                              for u in getattr(self._tool, "_last_units", [])]
        self._res["children"] = self._kids()
        self._log(f"children: {len(self._res['children'])}")
        try:
            st = self._node.callDecoration("getStack")
            self._res["model_overrides"] = {k: st.getTop().getProperty(k, "value") for k in st.getTop().getAllKeys()}
            self._res["model_effective"] = {k: st.getProperty(k, "value") for k in
                                            ("support_xy_distance", "support_xy_distance_overhang", "support_roof_enable")}
            self._log(f"model overrides: {self._res['model_overrides']} effective: {self._res['model_effective']}")
        except Exception as e:
            self._log(f"model overrides: unreadable ({e})")
        self._hideMessages()
        self._shot("02_generated")
        if not any(k["name"].startswith("HybridTower") for k in self._res["children"]):
            raise RuntimeError("no support meshes were created")

    def _sliceThen(self, tag):
        backend = self._app.getBackend()
        self._slice_tag = tag
        self._slice_wait = 0

        def poll():
            self._slice_wait += 1
            scene = self._app.getController().getScene()
            plate = self._app.getMultiBuildPlateModel().activeBuildPlate
            gl = getattr(scene, "gcode_dict", {}).get(plate) or []
            state = int(getattr(backend, "_backend_state", 0))
            if state == 3 and gl:
                if tag == "hybrid" and hasattr(self._tool, "postProcessGcode"):
                    gl = self._tool.postProcessGcode(gl)      # what Cura's Save does through writeStarted
                with open(os.path.join(self._out, tag + ".gcode"), "w") as fh:
                    fh.write("".join(gl))
                self._log(f"slice {tag}: done, {sum(len(g) for g in gl)} bytes of gcode")
                self._next(1000)
            elif state == 4 or self._slice_wait > int(os.environ.get("HS_SLICE_WAIT", "180")):
                self._res["error"] = f"slice {tag} failed/timeout (state {state})"
                self._log(self._res["error"])
                self._finish()
            else:
                QTimer.singleShot(1000, poll)
        # The engine Cura started at boot may have its crash reporter on, which runs out of memory
        # in this test sandbox. Turn it off and restart the engine before the first slice.
        self._app.getPreferences().setValue("info/send_engine_crash", False)
        os.environ["USE_SENTRY"] = "0"
        if not getattr(self, "_engine_restarted", False):
            self._engine_restarted = True
            try:
                backend._terminate()
            except Exception as e:
                self._log(f"engine restart skipped: {e}")
            QTimer.singleShot(4000, backend.forceSlice)
            QTimer.singleShot(8000, poll)
        else:
            backend.forceSlice()
            QTimer.singleShot(3000, poll)
        return "async"

    def _plainSlice(self):
        self._snap("before slice")
        return self._sliceThen("plain")

    def _slice(self):
        Selection.clear()
        self._snap("before slice")
        return self._sliceThen("hybrid")

    def _preview(self):
        self._app.getController().setActiveStage("PreviewStage")
        self._queue.insert(0, self._previewShot)
        return 6000

    def _previewShot(self):
        self._hideMessages()
        self._shot("03_preview")
        self._app.getController().setActiveStage("PrepareStage")
        return 1500

    def _baseline(self):
        """Remove our meshes and slice with Cura's own support for comparison."""
        Selection.add(self._node)
        self._tool.removeSupports()
        self._res["children_after_remove"] = len(self._kids())
        self._log(f"after remove: {self._res['children_after_remove']} children; {self._tool.getStatus()}")
        g = self._app.getGlobalContainerStack()
        self._log("after remove, Cura settings: " + str({k: g.getProperty(k, "value") for k in
                  ("support_xy_distance", "support_xy_distance_overhang", "support_roof_enable",
                                          "support_infill_angles", "support_pattern")}))
        stack = self._app.getGlobalContainerStack()
        stack.setProperty("support_enable", "value", True)
        Selection.clear()
        self._queue.insert(0, self._baselineSlice)
        return 1500

    def _baselineSlice(self):
        return self._sliceThen("cura_support")

    def _treeBaseline(self):
        self._app.getGlobalContainerStack().setProperty("support_structure", "value", "tree")
        self._queue.insert(0, lambda: self._sliceThen("cura_tree"))
        return 1500

    def _undoRedo(self):
        stack = self._app.getOperationStack()
        stack.undo()            # brings the removed meshes back
        self._res["children_after_undo"] = len(self._kids())
        self._log(f"after undo: {self._res['children_after_undo']} children")

    def _done(self):
        self._res["ok"] = True
        self._log("finished")
        self._finish()


def getMetaData():
    return {}


def register(app):
    return {"extension": HSHarness()}
