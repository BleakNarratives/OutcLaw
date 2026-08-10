#!/usr/bin/env python3
"""
outclaw_bridge_bootstrap.py -- Bootstraps OutClaw + cross-device file bus.

This is the entry point for a single device that wants to:
  1. Run the OutClaw orchestrator / regression CLI locally.
  2. Mirror every audit digest to its peers via the rclone 'cloud' carrier.
  3. Receive peer digests and route them through the local Syntax bus.

The bootstrap is intentionally a context manager so test code (and
crontab entries) can use it as ``with bridge_session() as (bus, bridge,
orch): ...`` and have it tear down cleanly on exit. The bootstrap NEVER
calls generate_document() -- the manfiesto DRAFT block is preserved.

Round-9 polish: the ``OutclawOrchestrator`` class has been RELOCATED to
``OutClaw/outclaw_unified.py`` so it lives next to the underlying
``audit_text`` function. This module is now a thin consumer, importing
it directly.

Public surface:
  bridge_session(...)        -- context manager entrypoint
  BridgeBundle               -- (bus, bridge, orchestrator) namedtuple-ish
  start_bridge(...)          -- imperative start, returns bundle
  stop_bridge(bundle)        -- imperative stop

Configuration via env (consumed by the underlying modules):
  BUS_DEVICE_ID              default = hostname lowercased
  BUS_SYNC_ROOT              default = ~/bleaknarratives/sync_bus
  BUS_POLL_INTERVAL          default 30
  BUS_HEARTBEAT_INTERVAL     default 300
  BUS_TTL_SECONDS            default 7 days
  LOCAL_AUDIT_TEXT           default '' (only for smoke-mode)
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from OutClaw.outclaw_bus import OutClawBus
from SyntaxIntelligence.sync_bridge import SyncBridge

# ---------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------


# ═══════════════════════════════════════════════════════
#  OUTCLAW_BRIDGE_BOOTSTRAP
# ═══════════════════════════════════════════════════════════════

class BridgeBundle:
    """The triple of objects a cross-device-aware OutClaw session needs."""

    __slots__ = ("_owns_bridge", "_owns_bus", "bridge", "bus", "orchestrator")

    def __init__(
        self,
        bus: OutClawBus,
        bridge: SyncBridge,
        orchestrator: Any,
        *,
        owns_bridge: bool = False,
        owns_bus: bool = False,
    ):
        self.bus = bus
        self.bridge = bridge
        self.orchestrator = orchestrator
        self._owns_bridge = owns_bridge
        self._owns_bus = owns_bus

    @property
    def is_cross_device_wired(self) -> bool:
        """True iff the bus publishes reach the bridge's egress subscribers.

        Tests should assert on this instead of poking at private bus state.
        Detects the ``share_local_bus=False`` or ``bridge.local_bus is None``
        misconfiguration that would otherwise silently lose cross-device
        egress.
        """
        return (
            self.bus.is_live
            and self.bus.local_bus is not None
            and self.bridge.local_bus is not None
            and self.bus.local_bus is self.bridge.local_bus
        )

    def diagnostics(self) -> dict:
        return {
            "bus": self.bus.diagnostics().__dict__,
            "bridge": self.bridge.diagnostics(),
            "orchestrator": (
                getattr(
                    self.orchestrator,
                    "diagnostics",
                    lambda: {"note": "no diagnostics()"},
                )()
            ),
            "is_cross_device_wired": self.is_cross_device_wired,
        }

    def shutdown(self) -> None:
        if self._owns_bridge:
            try:
                self.bridge.stop()
            except Exception:
                pass
        if self._owns_bus and self.bus.is_live:
            # The SyntaxEventBus has no public stop; daemon threads exit
            # when the process does. Nothing to do here.
            pass


# ---------------------------------------------------------------------
# Imperative API
# ---------------------------------------------------------------------


def _default_device_id() -> str:
    env = os.environ.get("BUS_DEVICE_ID", "").strip()
    if env:
        return env
    try:
        host = socket.gethostname().lower().strip()
        if host:
            return host
    except Exception:
        pass
    return "unknown"


def _build_orchestrator():
    """
    Lazy-import ``OutclawOrchestrator`` from ``outclaw_unified``. The
    orchestrator class was relocated there in round-9 polish so the
    bootstrap module is a thin consumer rather than the orchestrator's
    home.
    """
    try:
        from OutClaw.outclaw_unified import OutclawOrchestrator  # type: ignore

        return OutclawOrchestrator()
    except (ImportError, ModuleNotFoundError, AttributeError) as exc:
        sys.stderr.write(
            f"[outclaw_bridge_bootstrap] WARN: orchestrator unavailable: {exc!r}\n"
        )
        return None


def start_bridge(
    *,
    bus: OutClawBus | None = None,
    bridge: SyncBridge | None = None,
    orchestrator: Any = None,
    share_local_bus: bool = True,
) -> BridgeBundle:
    """
    Imperative start. Constructs the bridge + bus if not provided. Returns
    a BridgeBundle; the caller is responsible for ``bundle.shutdown()``.

    When ``share_local_bus=True`` (default) the bus and bridge end up wired
    to the SAME ``SyntaxEventBus`` instance -- so outclaw-bus publishes
    reach bridge egress subscribers in the same process. This is what
    enables cross-device fan-out through the bridge's _egress_cb.

    Hardening: if ``share_local_bus=True`` but the bridge has no bus to
    share (caller constructed ``SyncBridge(local_bus=None)`` explicitly),
    or if the caller passes ``share_local_bus=False``, we degrade loudly:
    OutClawBus is constructed with ``bus=None`` and falls through to its
    lazy-import path. Bundle.is_cross_device_wired will report False so the
    caller can detect the degraded wiring before relying on it.
    """
    owns_bridge = bridge is None
    owns_bus = bus is None
    if bridge is None:
        bridge = SyncBridge()
        bridge.start()
    if bus is None:
        shared_local_bus = (
            bridge.local_bus
            if (share_local_bus and bridge.local_bus is not None)
            else None
        )
        if shared_local_bus is None:
            # Always WARN on degraded wiring so operators see fan-out
            # config choices immediately at construction time, and
            # bundle.is_cross_device_wired == False at runtime.
            reason = (
                "bridge.local_bus is None"
                if share_local_bus
                else "share_local_bus=False (caller opted out)"
            )
            sys.stderr.write(
                f"[outclaw_bridge_bootstrap] WARN: cross-device egress "
                f"is DEGRADED ({reason}). Bus publishes will NOT reach "
                f"bridge egress subscribers in this process. Pass "
                f"share_local_bus=True with a live bridge.local_bus to "
                f"restore fan-out.\n"
            )
            sys.stderr.flush()
        bus = OutClawBus(bus=shared_local_bus)
    bus.attach_bridge(bridge)
    if orchestrator is None:
        orchestrator = _build_orchestrator()
    return BridgeBundle(
        bus,
        bridge,
        orchestrator,
        owns_bridge=owns_bridge,
        owns_bus=owns_bus,
    )


def stop_bridge(bundle: BridgeBundle) -> None:
    bundle.shutdown()


# ---------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------


@contextlib.contextmanager
def bridge_session(
    *,
    bus: OutClawBus | None = None,
    bridge: SyncBridge | None = None,
    orchestrator: Any = None,
) -> Iterator[BridgeBundle]:
    """
    Bootstraps OutClaw + cross-device file bus in a context manager.

    Usage (production):
        with bridge_session() as bundle:
            audit_text = bundle.orchestrator.audit_text(some_draft)
            bundle.bus.publish_findings(audit_text.to_dict())
            # Egress runs automatically via bridge._egress_cb subscription
            # on the local bus + on the _dispatch fallback path.

    Usage (tests):
        with bridge_session(bus=stub_bus, bridge=stub_bridge_test_only) as bundle:
            ... boundary tests ...

    The context manager ALWAYS cleans up the bridge (stopping its threads).
    It does NOT destroy the bus (the bus shares its daemon threads with the
    rest of the process) nor the orchestrator. Whichever caller supplied
    owns the lifetime policy on those two.
    """
    bundle = start_bridge(bus=bus, bridge=bridge, orchestrator=orchestrator)
    try:
        yield bundle
    finally:
        bundle.shutdown()


# ---------------------------------------------------------------------
# Smoke-mode CLI
# ---------------------------------------------------------------------


def _smoke() -> None:
    """Manual end-to-end smoke: brings up the bridge + bus, publishes one digest."""
    import json
    import time

    bundle = start_bridge()
    diag = bundle.bus.diagnostics()
    print(f"[smoke] device_id={bundle.bridge.device_id}")
    print(
        f"[smoke] bus_available={diag.bus_available} import_error={diag.bus_import_error!r}"
    )
    print(f"[smoke] bridge_thread_running={bundle.bridge.is_running}")
    # Publish a synthetic digest (mimic what publish_findings does).
    digest = {
        "audit_id": "smoke-" + str(int(time.time())),
        "severity_counts": {"HIGH": 0, "MEDIUM": 0, "OK": 1},
        "safe_to_draft": True,
        "high_count": 0,
        "high_findings": [],
    }
    bundle.bus.publish("outclaw.findings", digest)  # public facade
    time.sleep(0.5)
    snap = bundle.diagnostics()
    print(json.dumps(snap, indent=2, default=str))
    bundle.shutdown()


if __name__ == "__main__":
    _smoke()
