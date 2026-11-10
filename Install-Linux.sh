#!/bin/sh
# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
#
# Hybrid Supports for Cura: double-click to install and check (Linux).
# In the file manager choose "Run" if it asks. WORK IN PROGRESS.
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
        PY="$c"; break
    fi
done

say() {  # show a message whether or not there is a terminal
    if [ -t 1 ]; then echo "$1"
    elif command -v zenity >/dev/null 2>&1; then zenity --info --no-wrap --title="Hybrid Supports Installer" --text="$1"
    elif command -v kdialog >/dev/null 2>&1; then kdialog --title "Hybrid Supports Installer" --msgbox "$1"
    elif command -v xmessage >/dev/null 2>&1; then xmessage "$1"
    else echo "$1"; fi
}

if [ -z "$PY" ]; then
    say "Python 3.8 or newer is needed. On Linux Mint, Ubuntu or Debian install it with:  sudo apt install python3 python3-tk"
    exit 1
fi

# Window version when tkinter and a display are there.
if "$PY" -c 'import tkinter' 2>/dev/null && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    exec "$PY" install.py "$@"
fi

# No tkinter: text version. Open a terminal if this was double-clicked.
TIP="Tip: 'sudo apt install python3-tk' gives you the installer window instead of this text version."
if [ -t 1 ]; then
    "$PY" install.py --cli "$@"; code=$?
    echo; echo "$TIP"
    exit $code
fi
for t in x-terminal-emulator gnome-terminal konsole xfce4-terminal mate-terminal xterm; do
    if command -v "$t" >/dev/null 2>&1; then
        exec "$t" -e sh -c "'$PY' install.py --cli; echo; echo \"$TIP\"; printf 'Press Enter to close. '; read x"
    fi
done
OUT="$("$PY" install.py --cli "$@" 2>&1)"
say "$OUT"
