@echo off
rem Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
rem Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
rem
rem Hybrid Supports for Cura: double-click to install and check (Windows).
rem WORK IN PROGRESS. Not yet tested on Windows.
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 install.py %*
    goto done
)
where python >nul 2>nul
if not errorlevel 1 (
    python install.py %*
    goto done
)
echo Python 3 is needed.
echo Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run this again.
pause
exit /b 1

:done
if errorlevel 1 pause
