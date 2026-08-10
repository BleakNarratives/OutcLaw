#!/bin/bash
# OutClaw Dashboard Launcher (with venv activation)
cd "$(dirname "$0")"
source .venv/bin/activate
python3 outclaw_dashboard.py "$@"
