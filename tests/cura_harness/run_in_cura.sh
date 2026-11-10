#!/usr/bin/env bash
# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
#
# Run Hybrid Supports inside a real Cura and record what happens.
#
#   ./UltiMaker-Cura-5.13.0-linux-X64.AppImage --appimage-extract
#   tests/cura_harness/run_in_cura.sh squashfs-root/AppRun 5.13 out_dir [trapezoid|conform]
#
# Needs xvfb-run. Uses a throwaway HOME, so your own Cura settings are untouched, and turns off
# Cura's crash and usage reporting for the run.
# Optional env: HS_HARNESS_SET='{"GussetHeight":"10"}'  HS_HARNESS_WINDOW=1500x950
#               HS_HARNESS_QUICK=1 (skip the two comparison slices)
#               HS_MODEL_FILE=part.stl  HS_HARNESS_PRINTER=elegoo_neptune_4  HS_HARNESS_SUPPORT=off|normal|tree
#               HS_HOME=dir (keep and reuse the fake HOME)  HS_NO_PLUGIN=1 (don't copy the plugin in)
#               HS_HARNESS_INSTALL=file.curapackage (install it the drag-and-drop way, then quit)
# Writes results.json, screenshots and two gcode files (hybrid / cura_support) to out_dir.
set -u
APPRUN="$(readlink -f "$1")"; CFGVER="$2"; OUT="$(mkdir -p "$3" && readlink -f "$3")"; MODE="${4:-trapezoid}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
FAKEHOME="${HS_HOME:-$(mktemp -d)}"
PLUG="$FAKEHOME/.local/share/cura/$CFGVER/plugins"
mkdir -p "$PLUG"
[ "${HS_NO_PLUGIN:-0}" = 1 ] || python3 "$ROOT/install.py" --cli --cura-dir "$FAKEHOME/.local/share/cura/$CFGVER" > /dev/null
rm -rf "$PLUG/HSHarness"
[ "${HS_NO_HARNESS:-0}" = 1 ] || cp -r "$HERE/HSHarness" "$PLUG/HSHarness"
find "$PLUG" -name __pycache__ -prune -exec rm -rf {} +
if [ -n "${HS_MODEL_FILE:-}" ]; then cp "$HS_MODEL_FILE" "$OUT/model.stl"; else python3 "$HERE/make_model.py" "$OUT/model.stl"; fi
cd "$(dirname "$APPRUN")"
HOME="$FAKEHOME" USE_SENTRY=0 LANG=C.UTF-8 LC_ALL=C.UTF-8 LIBGL_ALWAYS_SOFTWARE=1 HS_HARNESS_OUT="$OUT" HS_HARNESS_MODEL="$OUT/model.stl" \
  HS_HARNESS_MODE="$MODE" HS_HARNESS_PLAIN="${HS_HARNESS_PLAIN:-0}" HS_HARNESS_SUPPORT="${HS_HARNESS_SUPPORT:-off}" HS_HARNESS_OVERRIDES="${HS_HARNESS_OVERRIDES:-{\}}" HS_HARNESS_PRINTER="${HS_HARNESS_PRINTER:-creality_ender3}" HS_HARNESS_QUICK="${HS_HARNESS_QUICK:-0}" HS_HARNESS_WINDOW="${HS_HARNESS_WINDOW:-}" HS_HARNESS_INSTALL="${HS_HARNESS_INSTALL:-}" HS_HARNESS_SET="${HS_HARNESS_SET:-{\}}" \
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy timeout "${HS_TIMEOUT:-420}" xvfb-run -a -s "-screen 0 1600x1000x24" "$APPRUN" > "$OUT/cura.stdout" 2>&1
code=$?
cp "$FAKEHOME/.local/share/cura/$CFGVER/cura.log" "$OUT/cura.log" 2>/dev/null
cp "$FAKEHOME/.local/share/cura/stderr.log" "$OUT/stderr.log" 2>/dev/null
[ -n "${HS_HOME:-}" ] || rm -rf "$FAKEHOME"
echo "cura exit code: $code (0 = harness quit cleanly, 124 = timed out, 139 = segfault)"
exit $code
