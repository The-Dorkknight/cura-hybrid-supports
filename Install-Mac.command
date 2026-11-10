#!/bin/sh
# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
#
# Hybrid Supports for Cura: double-click to install and check (macOS).
# First time: right-click > Open, because the file is not signed. WORK IN PROGRESS.
# Not yet tested on a Mac.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    osascript -e 'display dialog "Python 3 is needed. Install it from https://www.python.org/downloads/ and run this again." buttons {"OK"} default button 1 with title "Hybrid Supports Installer"' >/dev/null 2>&1
    echo "Python 3 is needed. Install it from https://www.python.org/downloads/ and run this again."
    exit 1
fi

if python3 -c 'import tkinter' 2>/dev/null; then
    python3 install.py "$@"
else
    python3 install.py --cli "$@"
    echo
    printf 'Press Enter to close. '; read x
fi
