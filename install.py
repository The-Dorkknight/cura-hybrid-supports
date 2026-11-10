#!/usr/bin/env python3
# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Hybrid Supports installer: builds the plugin, installs it into Cura and checks it.

Double-click the launcher for your system (Install-Linux.sh, Install-Windows.bat,
Install-Mac.command) or run:

    python3 install.py              opens the installer window (text mode if no window is possible)
    python3 install.py --cli        install into every Cura 5.x found, then check, in the terminal
    python3 install.py --check      only report what is installed and whether Cura loaded it
    python3 install.py --uninstall  remove the plugin from Cura
    python3 install.py --package    only write dist/*.curapackage and a plugin zip
    python3 install.py --cura-dir DIR   use one Cura folder, e.g. ~/.local/share/cura/5.13
    python3 install.py --version

WORK IN PROGRESS: many features may be broken. Needs only Python 3.8+.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(ROOT, "HybridSupports")
PLUGIN_ID = "HybridSupports"
APP_NAME = "Hybrid Supports Installer"
REPO = "https://github.com/The-Dorkknight/cura-hybrid-supports"
WIP = "WORK IN PROGRESS: many features may be broken"
WHERE = ("In Cura: load a model and click it. The Hybrid Supports button (a small tower) is at the bottom "
         "of the left tool bar (shortcut H). It is also listed under Extensions > Hybrid Supports and "
         "in Marketplace > Manage (the cog, top right).")


class InstallError(Exception):
    pass


# ------------------------------------------------------------------ the plugin

def version() -> str:
    src = open(os.path.join(PLUGIN, "hybrid_core.py"), encoding="utf-8").read()
    return re.search(r'__version__ = "([^"]+)"', src).group(1)


def plugin_files():
    for dirpath, dirnames, filenames in os.walk(PLUGIN):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for f in sorted(filenames):
            if f.endswith((".pyc", ".pyo")) or f == "build_info.json":
                continue
            full = os.path.join(dirpath, f)
            yield full, os.path.relpath(full, PLUGIN)


def build_date() -> str:
    newest = max(os.path.getmtime(full) for full, _ in plugin_files())
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(newest))


__version__ = version()
__build_date__ = build_date()


def build_info() -> str:
    return json.dumps({"version": __version__, "build_date": __build_date__})


def icon_is_safe(path: str) -> bool:
    """Cura inserts fill="..." after "<svg " to recolour toolbar icons. A fill already
    on that tag makes invalid XML and Cura crashes while starting (0.1.0-wip did)."""
    try:
        raw = open(path, "rb").read()
        ET.fromstring(raw.replace(b"<svg ", b'<svg fill="#000000" '))
        return True
    except (OSError, ET.ParseError):
        return False


def self_check() -> None:
    """Refuse to build something that would stop Cura from starting."""
    meta = json.load(open(os.path.join(PLUGIN, "plugin.json"), encoding="utf-8"))
    if __version__.split("-")[0] != meta["version"]:
        raise InstallError(f"Version mismatch: hybrid_core.py says {__version__}, plugin.json says {meta['version']}.")
    if not icon_is_safe(os.path.join(PLUGIN, "tool_icon.svg")):
        raise InstallError("tool_icon.svg would crash Cura at startup. Remove fill from its <svg> tag.")
    for full, _ in plugin_files():
        if full.endswith(".py"):
            compile(open(full, encoding="utf-8").read(), full, "exec")


def package_info() -> dict:
    meta = json.load(open(os.path.join(PLUGIN, "plugin.json"), encoding="utf-8"))
    return {
        "package_id": PLUGIN_ID,
        "package_type": "plugin",
        "display_name": meta["name"],
        "description": meta["description"],
        "package_version": meta["version"],
        "sdk_version": "8.0.0",
        "sdk_version_semver": "8.0.0",
        "website": REPO,
        "author": {"author_id": "The-Dorkknight", "display_name": "Matthew Armstrong",
                   "website": "https://github.com/The-Dorkknight"},
        "tags": ["support", "supports", "tower", "tree", "material saving"],
    }


# ---------------------------------------------------------------- finding Cura

def cura_roots():
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        roots = [os.path.join(os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")), "cura")]
    elif sys.platform == "darwin":
        roots = [os.path.join(home, "Library", "Application Support", "cura")]
    else:
        data = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
        roots = [os.path.join(data, "cura"),
                 os.path.join(home, ".var", "app", "com.ultimaker.cura", "data", "cura")]   # Flatpak
    return [r for r in roots if os.path.isdir(r)]


def _version_key(name: str):
    return tuple(int(p) for p in re.findall(r"\d+", name)[:3])


def cura_version_dirs():
    out = []
    for root in cura_roots():
        for name in os.listdir(root):
            if re.fullmatch(r"\d+\.\d+", name) and int(name.split(".")[0]) >= 5:
                out.append(os.path.join(root, name))
    return sorted(out, key=lambda d: _version_key(os.path.basename(d)), reverse=True)


def cura_running() -> bool:
    """Best effort: is a Cura window open right now?"""
    names = {"ultimaker-cura", "ultimaker_cura", "cura", "cura.exe", "ultimaker-cura.exe"}
    try:
        if sys.platform.startswith("linux"):
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    try:
                        if open(f"/proc/{pid}/comm").read().strip().lower() in names:
                            return True
                    except OSError:
                        pass
            return False
        if sys.platform.startswith("win"):
            out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10).stdout.lower()
            return "ultimaker-cura.exe" in out
        out = subprocess.run(["pgrep", "-fil", "cura"], capture_output=True, text=True, timeout=10).stdout
        return any("cura.app" in line.lower() for line in out.splitlines())
    except Exception:
        return False


def find_cura_apps():
    """Return [(label, command list)] for Cura programs found on this computer, newest first."""
    home = os.path.expanduser("~")
    found = []
    if sys.platform.startswith("win"):
        for base in filter(None, [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]):
            for exe in glob.glob(os.path.join(base, "*Cura*", "*Cura.exe")):
                found.append((os.path.basename(os.path.dirname(exe)), [exe]))
    elif sys.platform == "darwin":
        for base in ("/Applications", os.path.join(home, "Applications")):
            for app in glob.glob(os.path.join(base, "*Cura*.app")):
                found.append((os.path.basename(app)[:-4], ["open", "-a", app]))
    else:
        seen = set()
        for base in (home, "Applications", "Downloads", "Desktop", "AppImages", "bin", ".local/bin", "/opt"):
            base = base if os.path.isabs(base) else os.path.join(home, base)
            for pat in ("*[Cc]ura*.AppImage", "*/*[Cc]ura*.AppImage"):
                for f in glob.glob(os.path.join(base, pat)):
                    real = os.path.realpath(f)
                    if real not in seen and os.path.isfile(real):
                        seen.add(real)
                        found.append((os.path.basename(f), [f]))
        if os.path.isdir(os.path.join(home, ".var", "app", "com.ultimaker.cura")) and shutil.which("flatpak"):
            found.append(("Cura (Flatpak)", ["flatpak", "run", "com.ultimaker.cura"]))
        if not found and shutil.which("cura"):
            found.append(("cura", [shutil.which("cura")]))
    return sorted(found, key=lambda f: _version_key(f[0]), reverse=True)


def launch_cura(command) -> None:
    exe = command[0]
    if os.path.isabs(exe) and exe.endswith(".AppImage") and not os.access(exe, os.X_OK):
        raise InstallError(f"{exe} is not marked as a program. Right-click it > Properties > Permissions > "
                           "tick 'Allow executing file as program', then try again.")
    kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    if os.name == "posix":
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


# ------------------------------------------------------------ install / remove

def _plugin_dirs(cura_dir: str):
    """Where a copy may sit: Cura's own package layout (nested) or a hand-copied one (flat)."""
    base = os.path.join(cura_dir, "plugins", PLUGIN_ID)
    return [os.path.join(base, PLUGIN_ID), base]


def _read_packages(cura_dir: str):
    path = os.path.join(cura_dir, "packages.json")
    try:
        data = json.load(open(path, encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"dismissed": [], "installed": {}, "to_install": {}, "to_remove": [], "version": 1}


def _write_packages(cura_dir: str, data: dict) -> None:
    path = os.path.join(cura_dir, "packages.json")
    if os.path.isfile(path):
        shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=4)


def remove_from(cura_dir: str) -> bool:
    target = os.path.join(cura_dir, "plugins", PLUGIN_ID)
    existed = os.path.isdir(target)
    if existed:
        shutil.rmtree(target)
    data = _read_packages(cura_dir)
    changed = False
    for key in ("installed", "to_install"):
        if isinstance(data.get(key), dict) and PLUGIN_ID in data[key]:
            del data[key][PLUGIN_ID]
            changed = True
    if isinstance(data.get("to_remove"), list) and PLUGIN_ID in data["to_remove"]:
        data["to_remove"].remove(PLUGIN_ID)
        changed = True
    if changed:
        _write_packages(cura_dir, data)
    return existed


def install_into(cura_dir: str) -> str:
    """Install the same way Cura's own package installer does, so Cura lists it in Marketplace > Manage."""
    self_check()
    replaced = remove_from(cura_dir)
    target = _plugin_dirs(cura_dir)[0]
    for full, rel in plugin_files():
        dst = os.path.join(target, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(full, dst)
    shutil.copy2(os.path.join(ROOT, "LICENSE.md"), os.path.join(target, "LICENSE.md"))
    with open(os.path.join(target, "build_info.json"), "w", encoding="utf-8") as fh:
        fh.write(build_info())
    data = _read_packages(cura_dir)
    info = package_info()
    info.update(is_active=True, is_bundled=False, is_installed=True)
    data.setdefault("installed", {})[PLUGIN_ID] = {"filename": "", "package_info": info}
    _write_packages(cura_dir, data)
    # read back: never report success on a guess
    st = status(cura_dir)
    if st["installed"] != __version__ or not st["listed"] or st["broken"]:
        raise InstallError(f"Copied the files to {target} but the read-back check failed: {st['summary']}")
    return "replaced an older copy" if replaced else "new install"


# -------------------------------------------------------------------- checking

_LOG_TIME = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
_LOG_EVENTS = [
    (re.compile(r"Loaded plugin %s (\S+)" % PLUGIN_ID), "loaded"),
    (re.compile(r"Plugin \[%s\] has been disabled" % PLUGIN_ID), "disabled"),
    (re.compile(r"Plugin \[%s\] with supported sdk versions" % PLUGIN_ID), "incompatible"),
    (re.compile(r"Error loading plugin %s" % PLUGIN_ID), "error"),
    (re.compile(r"Plugin \[%s\] failed to register" % PLUGIN_ID), "error"),
    (re.compile(r"Plugin %s did not return any objects" % PLUGIN_ID), "error"),
]


def _read_log(cura_dir: str):
    """Last thing Cura's log says about the plugin: (event, detail, when, last_log_time)."""
    path = os.path.join(cura_dir, "cura.log")
    if not os.path.isfile(path):
        return None, "", None, None
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 6_000_000))
        lines = fh.read().decode("utf-8", "replace").splitlines()
    event = detail = when = last = None
    for i, line in enumerate(lines):
        m = _LOG_TIME.match(line)
        if m:
            last = m.group(1)
        if PLUGIN_ID not in line:
            continue
        for rx, name in _LOG_EVENTS:
            hit = rx.search(line)
            if hit:
                event, when = name, last
                detail = hit.group(1) if name == "loaded" else "\n".join(l[:300] for l in lines[i:i + 12])
    parse = lambda s: datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None  # noqa: E731
    return event, detail or "", parse(when), parse(last)


def status(cura_dir: str) -> dict:
    """Everything the installer knows about the plugin in one Cura folder."""
    st = {"cura": os.path.basename(cura_dir), "dir": cura_dir, "installed": None, "built": "", "plugin_dir": "",
          "broken": False, "listed": False, "installed_at": None, "state": "missing", "detail": ""}
    for d in _plugin_dirs(cura_dir):
        if os.path.isfile(os.path.join(d, "plugin.json")):
            st["plugin_dir"] = d
            try:
                st["installed"] = json.load(open(os.path.join(d, "plugin.json"), encoding="utf-8")).get("version", "?")
            except Exception:
                st["installed"] = "?"
            try:
                info = json.load(open(os.path.join(d, "build_info.json"), encoding="utf-8"))
                st["installed"], st["built"] = info.get("version", st["installed"]), info.get("build_date", "")
                st["installed_at"] = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(d, "build_info.json")))
            except Exception:
                st["installed_at"] = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(d, "plugin.json")))
            st["broken"] = not icon_is_safe(os.path.join(d, "tool_icon.svg"))
            break
    st["listed"] = PLUGIN_ID in (_read_packages(cura_dir).get("installed") or {})
    event, detail, when, last = _read_log(cura_dir)
    st["log_event"], st["log_when"], st["cura_last_ran"] = event, when, last

    if st["installed"] is None:
        st["state"], st["summary"] = "missing", "Not installed"
        st["detail"] = "Press Install."
    elif st["broken"]:
        st["state"], st["summary"] = "bad", f"Broken copy ({st['installed']}): stops Cura starting"
        st["detail"] = "This copy has the icon fault that crashes Cura at startup. Press Install to replace it."
    elif when is None or (st["installed_at"] and when < st["installed_at"].replace(microsecond=0)):
        st["state"], st["summary"] = "wait", f"{st['installed']} installed. Cura not started since"
        st["detail"] = ("The files are in place and Cura has it on its plugin list, but Cura has not been started "
                        "since. Press Start Cura (or start it yourself) and the check finishes by itself.")
    elif event == "loaded":
        if detail.split("-")[0] == st["installed"].split("-")[0]:
            st["state"], st["summary"] = "ok", f"{st['installed']} installed and loaded by Cura"
            st["detail"] = f"Cura {st['cura']} loaded Hybrid Supports {detail} at {when:%H:%M on %d %b}.\n\n" + WHERE
        else:
            st["state"], st["summary"] = "wait", f"{st['installed']} installed. Cura last loaded {detail}"
            st["detail"] = "Cura has not been restarted since this version was installed. Restart Cura."
    elif event == "disabled":
        st["state"], st["summary"] = "bad", "Installed, but switched off inside Cura"
        st["detail"] = "In Cura open Marketplace > Manage (the cog), find Hybrid Supports, switch it on and restart Cura."
    elif event == "incompatible":
        st["state"], st["summary"] = "bad", "Installed, but this Cura is too old or too new for it"
        st["detail"] = "Cura refused the plugin as incompatible. It needs Cura 5.x.\n\n" + detail
    else:
        st["state"], st["summary"] = "bad", "Installed, but Cura reported an error loading it"
        st["detail"] = "Cura's log says:\n\n" + detail + "\n\nPlease report this with the text above."
    if st["installed"] and not st["listed"] and st["state"] in ("ok", "wait"):
        st["detail"] += ("\n\nNote: this copy is not on Cura's own plugin list (Marketplace > Manage). "
                         "Press Install to register it.")
    return st


# -------------------------------------------------------------------- packaging

def write_packages() -> list:
    self_check()
    info = build_info()
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    cura_pkg = os.path.join(ROOT, "dist", f"HybridSupports-{__version__}.curapackage")
    with zipfile.ZipFile(cura_pkg, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("package.json", json.dumps(package_info(), indent=2))
        z.write(os.path.join(ROOT, "LICENSE.md"), "LICENSE.md")
        for full, rel in plugin_files():
            z.write(full, f"files/plugins/{PLUGIN_ID}/{rel}")
        z.writestr(f"files/plugins/{PLUGIN_ID}/build_info.json", info)
        z.write(os.path.join(ROOT, "LICENSE.md"), f"files/plugins/{PLUGIN_ID}/LICENSE.md")
    plain = os.path.join(ROOT, "dist", f"HybridSupports-{__version__}-plugin.zip")
    with zipfile.ZipFile(plain, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in plugin_files():
            z.write(full, f"{PLUGIN_ID}/{rel}")
        z.writestr(f"{PLUGIN_ID}/build_info.json", info)
        z.write(os.path.join(ROOT, "LICENSE.md"), f"{PLUGIN_ID}/LICENSE.md")
    return [cura_pkg, plain]


# -------------------------------------------------------------------- text mode

def run_cli(args, dirs) -> int:
    print(f"{APP_NAME} {__version__} (Built {__build_date__})  -  {WIP}")
    if not dirs:
        print("\nNo Cura 5.x settings folder was found on this computer.")
        print("Start Cura once and close it, then run this again. Or point at the folder yourself")
        print("(in Cura: Help > Show Configuration Folder):  python3 install.py --cura-dir <that folder>")
        return 1
    if not args.check and cura_running():
        print("\nCura is open. Close Cura first, then run this again.")
        return 1
    code = 0
    for d in dirs:
        if args.cura_dir:
            os.makedirs(d, exist_ok=True)
        try:
            if args.uninstall:
                print(f"\nCura {os.path.basename(d)}: " + ("removed" if remove_from(d) else "was not installed"))
                continue
            if not args.check:
                print(f"\nCura {os.path.basename(d)}: installed ({install_into(d)})")
            st = status(d)
            mark = {"ok": "[OK]", "wait": "[..]", "bad": "[!!]", "missing": "[--]"}[st["state"]]
            print(f"{mark} Cura {st['cura']}: {st['summary']}")
            if st["plugin_dir"]:
                print(f"     folder: {st['plugin_dir']}")
            print("     " + st["detail"].replace("\n", "\n     "))
            code = code or (1 if st["state"] == "bad" else 0)
        except (InstallError, OSError) as e:
            print(f"[!!] Cura {os.path.basename(d)}: {e}")
            code = 1
    if not args.uninstall and not args.check:
        print("\nNow start Cura, then run  python3 install.py --check  to confirm Cura loaded it.")
    return code


# ----------------------------------------------------------------------- window

class NoWindow(Exception):
    pass


def run_gui(dirs, script=None) -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        root = tk.Tk()
    except Exception as e:   # tkinter missing, or no display
        raise NoWindow(str(e))
    root.title(f"{APP_NAME} {__version__} (Built {__build_date__})")
    root.geometry("780x540")
    root.minsize(720, 470)
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    state = {"dirs": list(dirs), "rows": {}, "watch_until": 0.0, "apps": find_cura_apps()}
    colours = {"ok": "#1b7f3b", "wait": "#9a6700", "bad": "#b42318", "missing": "#555555"}
    marks = {"ok": "\u2714", "wait": "\u2026", "bad": "\u2716", "missing": "\u2013"}

    head = ttk.Frame(root, padding=(12, 10, 12, 4))
    head.pack(fill="x")
    ttk.Label(head, text="Hybrid Supports for Cura", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
    ttk.Label(head, text=WIP + ". Installs the plugin into Cura and checks that Cura loaded it.",
              foreground="#9a6700").pack(anchor="w")

    tree = ttk.Treeview(root, columns=("cura", "status"), show="headings", height=5, selectmode="browse")
    tree.heading("cura", text="Cura found", anchor="w")
    tree.heading("status", text="Hybrid Supports plugin", anchor="w")
    tree.column("cura", width=110, stretch=False)
    tree.column("status", width=560)
    for key, col in colours.items():
        tree.tag_configure(key, foreground=col)
    tree.pack(fill="x", padx=12, pady=(6, 4))

    buttons = ttk.Frame(root, padding=(12, 2))
    buttons.pack(fill="x")
    detail = tk.Text(root, height=9, wrap="word", relief="solid", borderwidth=1, padx=8, pady=6,
                     font="TkDefaultFont")
    detail.pack(fill="both", expand=True, padx=12, pady=(6, 6))
    bar = ttk.Label(root, anchor="w", relief="sunken", padding=(8, 2))
    bar.pack(fill="x", side="bottom")

    def say(text):
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", text)
        detail.configure(state="disabled")

    def refresh(keep_text=False):
        selected = tree.selection()
        chosen = state["rows"].get(selected[0], {}).get("dir") if selected else None
        tree.delete(*tree.get_children())
        state["rows"].clear()
        for d in state["dirs"]:
            st = status(d)
            iid = tree.insert("", "end", values=(f"Cura {st['cura']}", f"{marks[st['state']]}  {st['summary']}"),
                              tags=(st["state"],))
            state["rows"][iid] = st
            if d == chosen:
                tree.selection_set(iid)
        if state["rows"] and not tree.selection():
            tree.selection_set(next(iter(state["rows"])))
        if keep_text:   # rebuilding the list fires selection events; they must not wipe a result message
            state["hold_until"] = time.time() + 0.6
        n = len(state["dirs"])
        running = "Cura is open" if cura_running() else "Cura is closed"
        bar.configure(text=f"v{__version__} \u2022 {__build_date__} \u2022 {n} Cura folder{'s' if n != 1 else ''} "
                           f"\u2022 {running} \u2022 WORK IN PROGRESS")
        if not state["dirs"]:
            say("No Cura 5.x settings folder was found on this computer.\n\nStart Cura once and close it, then "
                "press Check. Or press 'Add Cura folder' and choose the folder Cura opens from "
                "Help > Show Configuration Folder.")
        elif not keep_text:
            show_selected()

    def show_selected(event=None):
        if event is not None and time.time() < state.get("hold_until", 0):
            return
        sel = tree.selection()
        if sel and sel[0] in state["rows"]:
            st = state["rows"][sel[0]]
            where = f"\n\nFolder: {st['plugin_dir']}" if st["plugin_dir"] else f"\n\nCura folder: {st['dir']}"
            say(f"Cura {st['cura']}: {st['summary']}\n\n{st['detail']}{where}")

    def do_install():
        if not state["dirs"]:
            return refresh()
        if cura_running() and not messagebox.askokcancel(
                APP_NAME, "Cura is open.\n\nClose Cura first, then press OK to install.\n"
                          "(Cura only looks for plugins when it starts.)"):
            return
        lines = []
        for d in state["dirs"]:
            try:
                lines.append(f"Cura {os.path.basename(d)}: installed ({install_into(d)}) and read back OK.")
            except (InstallError, OSError) as e:
                lines.append(f"Cura {os.path.basename(d)}: FAILED. {e}")
        refresh(keep_text=True)
        say("\n".join(lines) + "\n\nNext: press Start Cura. This window then confirms that Cura loaded the plugin.")

    def do_uninstall():
        if not state["dirs"] or not messagebox.askokcancel(APP_NAME, "Remove Hybrid Supports from Cura?"):
            return
        lines = [f"Cura {os.path.basename(d)}: " + ("removed." if remove_from(d) else "was not installed.")
                 for d in state["dirs"]]
        refresh(keep_text=True)
        say("\n".join(lines) + "\n\nRestart Cura if it is open.")

    def do_start():
        apps = state["apps"] = find_cura_apps()
        if cura_running():
            say("Cura is already open. Close it and start it again so it picks up the plugin; this window "
                "keeps checking for two minutes.")
        else:
            if not apps:
                path = filedialog.askopenfilename(title="Choose the Cura program (AppImage, .exe or .app)")
                if not path:
                    return
                apps = [(os.path.basename(path), ["open", "-a", path] if path.endswith(".app") else [path])]
            try:
                launch_cura(apps[0][1])
            except (InstallError, OSError) as e:
                return say(f"Could not start Cura: {e}")
            say(f"Starting {apps[0][0]}. Waiting for Cura to load the plugin (this can take a minute)...")
        state["watch_until"] = time.time() + 150
        root.after(2000, watch)

    def watch():
        if time.time() > state["watch_until"]:
            return
        refresh(keep_text=True)
        states = [st["state"] for st in state["rows"].values()]
        if "ok" in states or "bad" in states:
            state["watch_until"] = 0
            for iid, st in state["rows"].items():
                if st["state"] in ("ok", "bad"):
                    tree.selection_set(iid)
                    break
            return show_selected()
        root.after(2000, watch)

    def do_add():
        path = filedialog.askdirectory(title="Choose Cura's configuration folder (the one with cura.log in it)")
        if path and path not in state["dirs"]:
            state["dirs"].insert(0, path)
            refresh()

    def do_open():
        sel = tree.selection()
        if not sel:
            return
        st = state["rows"][sel[0]]
        path = st["plugin_dir"] or st["dir"]
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)   # noqa: S606
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            say(f"Could not open {path}: {e}")

    actions = {"install": do_install, "check": refresh, "start": do_start, "uninstall": do_uninstall}
    for text, cmd in (("Install / Update", do_install), ("Check", refresh), ("Start Cura", do_start),
                      ("Open plugin folder", do_open), ("Add Cura folder", do_add), ("Uninstall", do_uninstall)):
        ttk.Button(buttons, text=text, command=cmd).pack(side="left", padx=(0, 6))
    tree.bind("<<TreeviewSelect>>", show_selected)
    refresh()

    if script:   # hidden test hook: "install,sleep:1500,quit"
        steps = [s for s in script.split(",") if s]
        messagebox.askokcancel = lambda *a, **k: True

        def step():
            if not steps:
                return
            s = steps.pop(0)
            wait = 300
            if s.startswith("sleep:"):
                wait = int(s[6:])
            elif s == "quit":
                return root.destroy()
            else:
                actions[s]()
            root.after(wait, step)
        root.after(400, step)
    root.mainloop()
    return 0


# ------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Build Hybrid Supports, install it into Cura and check it.")
    ap.add_argument("--cli", action="store_true", help="text mode: install and check in the terminal")
    ap.add_argument("--check", action="store_true", help="only report what is installed and whether Cura loaded it")
    ap.add_argument("--uninstall", action="store_true", help="remove the plugin from Cura")
    ap.add_argument("--package", action="store_true", help="only write dist/*.curapackage and a plugin zip")
    ap.add_argument("--cura-dir", action="append", metavar="DIR",
                    help="a Cura version folder (the one holding cura.log); may be given more than once")
    ap.add_argument("--version", action="store_true", help="print the version and exit")
    ap.add_argument("--gui-script", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.version:
        print(f"{APP_NAME} {__version__} (Built {__build_date__}) - {WIP}")
        return 0
    try:
        self_check()
        if args.package:
            print(f"{APP_NAME} {__version__} (Built {__build_date__})  -  {WIP}")
            for p in write_packages():
                print(f"  wrote {os.path.relpath(p, ROOT)}  ({os.path.getsize(p)} bytes)")
            return 0
    except InstallError as e:
        print(f"Cannot build: {e}")
        return 1

    dirs = [os.path.abspath(os.path.expanduser(d)) for d in args.cura_dir] if args.cura_dir else cura_version_dirs()
    if args.cli or args.check or args.uninstall:
        return run_cli(args, dirs)
    try:
        return run_gui(dirs, args.gui_script)
    except NoWindow as e:
        print(f"(No window available: {e}. Using text mode.)\n")
        return run_cli(args, dirs)


if __name__ == "__main__":
    sys.exit(main())
