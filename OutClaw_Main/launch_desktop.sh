#!/bin/bash
# launch_desktop.sh — tiny helper that starts OutClaw from wherever this
# folder lives. The desktop icon (OutClaw.desktop) calls this file.
#
# Why a wrapper? The .desktop file needs an absolute path, but this project
# can live anywhere. This script figures out its own folder, then hands over
# to LAUNCH_ME.py, which does the rest (checks setup, installs anything
# missing, starts the dashboard, opens the browser).

cd "$(dirname "$0")" || exit 1
exec python3 LAUNCH_ME.py
