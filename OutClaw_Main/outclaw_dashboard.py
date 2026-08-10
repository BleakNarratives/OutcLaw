#!/usr/bin/env python3
"""
OutClaw TUI Dashboard — Main Entry Point

Interactive terminal dashboard for OutClaw citation audit operations.

Usage:
    python3 outclaw_dashboard.py
    
    # Or install and use as command:
    pip install -e .
    outclaw dashboard

Features:
    - Real-time audit monitoring
    - Risk score visualization
    - Citation lookup integration
    - FOIA request generation
    - IRAC legal analysis
    - Security-hardened input validation
    - Lightweight and fast

Requirements:
    - Python 3.8+
    - rich>=13.0.0
    - pyyaml>=6.0

Security:
    - All inputs validated and sanitized
    - Path traversal prevention
    - No shell command injection
    - Rate limiting on API calls
    - Safe YAML config loading
"""

import sys
from pathlib import Path

# Add OutClaw to path if running standalone
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dashboard.app import main

if __name__ == "__main__":
    sys.exit(main())
