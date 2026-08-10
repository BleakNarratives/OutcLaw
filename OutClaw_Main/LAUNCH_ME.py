#!/usr/bin/env python3
"""
LAUNCH_ME.py — One-click start for OutClaw.

DOUBLE-CLICK THIS FILE (or run: python3 LAUNCH_ME.py)

It does everything for you:
  1. Checks that the few required pieces are installed.
  2. Installs anything missing — automatically, no technical steps.
  3. Starts the OutClaw dashboard.
  4. Opens your web browser to it.

If you see a window/terminal asking anything, the answer is almost always
"yes". If something goes wrong, the message on screen will tell you exactly
what to paste back to a helper.

No special knowledge needed. That's the whole point.

Notes for helpers:
  * OutClaw installs its few dependencies into a private environment
    (a "virtual environment" named `.venv`) inside the project folder.
    This is intentional: it keeps the tool self-contained and works even
    on computers that block normal installs (PEP 668).
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── The only things OutClaw needs beyond Python itself ──
REQUIRED = {
    "flask": "flask>=2.0",
    "pypdf": "pypdf>=3.0",
}

PORT = 8765  # fixed port so the browser shortcut never changes

VENV_DIR = HERE / ".venv"


def say(text: str) -> None:
    """Friendly, plain-English console output."""
    print(f"\n  {text}")


def banner() -> None:
    print(r"""
  ╔══════════════════════════════════════════════════════╗
  ║                                                      ║
  ║      OUTCLAW  —  Check Your Court Papers             ║
  ║                                                      ║
  ║   A tool that checks legal documents for problems    ║
  ║   before you file them. Free. Private. On your      ║
  ║   own computer.                                      ║
  ║                                                      ║
  ╚══════════════════════════════════════════════════════╝
""")


def venv_python() -> Path:
    """Path to the Python interpreter inside the project's private env."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> bool:
    """Create the private environment if it does not exist yet."""
    if venv_python().exists():
        return True
    say("Creating a private workspace for OutClaw (only needed once)…")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=True,
            timeout=300,
        )
        return venv_python().exists()
    except Exception as exc:
        say(f"Could not create the private workspace: {exc}")
        return False


def module_ok(name: str, python: Path) -> bool:
    """True only if `import name` succeeds inside the private env."""
    try:
        result = subprocess.run(
            [str(python), "-c", f"import {name}"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def install(module: str, spec: str, python: Path) -> bool:
    """Install one missing module into the private env. Returns True on success."""
    say(f"Installing {module} (only needed once)…")
    try:
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", spec],
            check=True,
            timeout=300,
        )
        return module_ok(module, python)
    except Exception as exc:
        say(f"Could not install {module} automatically: {exc}")
        return False


def ensure_dependencies(python: Path) -> bool:
    """Make sure everything is installed inside the private env."""
    missing = [m for m, spec in REQUIRED.items() if not module_ok(m, python)]
    if not missing:
        return True

    say("OutClaw needs a couple of small pieces installed. Doing that now.")
    for module, spec in REQUIRED.items():
        if not module_ok(module, python):
            if not install(module, spec, python):
                say(
                    "If you see instructions above, paste this whole message to "
                    "whoever helps you."
                )
                return False
    return True


def port_in_use(port: int) -> bool:
    """True if something is already listening on the port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_browser_later(url: str) -> None:
    """Wait until the server answers, then open the browser.

    Polls the port instead of a blind sleep so a slow first cold start
    (venv import + Flask boot on an old computer) still gets its tab.
    """
    for _ in range(30):  # up to ~15s
        if port_in_use(PORT):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main() -> int:
    banner()

    url = f"http://localhost:{PORT}/"

    # Already running? (e.g. the user double-clicked, or another OutClaw
    # instance is up) — just open the browser to it. No second server.
    if port_in_use(PORT):
        say(f"OutClaw is already running — opening it now: {url}")
        webbrowser.open(url)
        return 0

    if not ensure_venv():
        say("Setup did not finish. Paste the message above to whoever helps you.")
        return 1

    python = venv_python()

    if not ensure_dependencies(python):
        say("Setup did not finish. Paste the message above to whoever helps you.")
        return 1

    # Run the server with the private env's interpreter so Flask/pypdf resolve.
    # OUTCLAW_NO_AUTOOPEN tells the module not to also pop a browser tab
    # (this launcher already opens one).
    cmd = [str(python), "-m", "dashboard.web_app"]
    say(f"Starting… your browser will open to {url}")
    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    env = dict(os.environ)
    env["OUTCLAW_NO_AUTOOPEN"] = "1"
    proc = subprocess.run(cmd, cwd=str(HERE), env=env)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
