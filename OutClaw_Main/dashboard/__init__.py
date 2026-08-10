"""
OutClaw TUI Dashboard — Interactive Terminal Interface

Provides real-time monitoring, visualization, and control for OutClaw
citation audit operations.
"""

__version__ = "0.3.0"

# NOTE (2026-08-03): the web dashboard (LAUNCH_ME.py -> dashboard.web_app)
# must run with ONLY flask + pypdf installed. The TUI app pulls in `rich`,
# so it is imported lazily here — a missing `rich` must not break the
# one-click web experience.
__all__ = [
    "SecureInput",
    "DashboardOrchestrator",
]

from .security import SecureInput
from .orchestrator import DashboardOrchestrator

try:  # TUI is optional; web dashboard does not need it.
    from .app import DashboardApp  # type: ignore

    __all__.append("DashboardApp")
except Exception:  # pragma: no cover - TUI deps missing is fine for web
    DashboardApp = None  # type: ignore[assignment]
