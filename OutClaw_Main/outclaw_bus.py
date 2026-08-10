#!/usr/bin/env python3
"""
outclaw_bus.py -- OutClaw <-> Syntax event bus adapter.

Post-review fixes (cumulative):
  * PII redaction is multi-layer (name-strip + numeric-strip + length cap)
    with a legal-term allowlist so tokens like "Federal Rules" survive.
    Adds docket-notation regex so "21-CV-12345" gets stripped in excerpt.
  * Lazy import distinguishes ImportError/ModuleNotFoundError (legitimate
    "Syntax isn't installed") from AttributeError/SyntaxError (real drift --
    the bus moved). The first time drift is detected, a WARN-level entry is
    appended to the stderr so the operator sees it without needing to call
    diagnostics().
  * `OutClawBus.publish_findings` publishes a digest calibrated for downstream
    redacted composition.
  * `OutClawBus.publish` is a public facade for callers that want to bypass
    the typed helpers. It does NOT redact; callers are responsible for PII
    when using the generic channel.
  * `OutClawBus.__init__(sync_bridge=None)` enables optional cross-device
    fan-out via a `SyncBridge`. `_dispatch` writes through the bridge on the
    fallback path (local bus dead), tags the fallback_log entry with
    `bridged: bool`, and skips forwarding when `_bridge_origin == "ingress"`
    (loop-guard).
  * `force_no_bus=True` constructor flag for tests that need to simulate a
    dead local bus without touching underscore-prefixed internals.
"""

from __future__ import annotations

import hashlib
import re
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent

_EVT_BUS = None
_EVT_BUS_IMPORT_ERROR: str | None = None
_EVT_BUS_FIRST_FAILURE_LOGGED = False
_FORCE_NO_BUS_CONFLICT_WARNED = False


# ═══════════════════════════════════════════════════════
#  OUTCLAW_BUS
# ═══════════════════════════════════════════════════════════════

def _warn_force_no_bus_conflict_once() -> None:
    """One-shot stderr WARN when force_no_bus=True AND bus= are both passed."""
    global _FORCE_NO_BUS_CONFLICT_WARNED
    if _FORCE_NO_BUS_CONFLICT_WARNED:
        return
    _FORCE_NO_BUS_CONFLICT_WARNED = True
    sys.stderr.write(
        "[outclaw_bus] WARN: force_no_bus=True overrides "
        "explicit bus= kwarg. Drop one or the other.\n"
    )
    sys.stderr.flush()


def _ensure_bus():
    """
    Lazily import the Syntax event bus. Distinguishes:
      * ImportError / ModuleNotFoundError: Syntax isn't installed; expected.
      * AttributeError / SyntaxError: real drift in Syntax API; unusual.
    Logs a WARN-level entry to stderr on first failure of either kind so
    an operator sees it without needing diagnostics().
    """
    global _EVT_BUS, _EVT_BUS_IMPORT_ERROR, _EVT_BUS_FIRST_FAILURE_LOGGED
    if _EVT_BUS is not None:
        return _EVT_BUS
    parent = _HERE.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))

    klass: type | None = None
    err_msg: str | None = None
    try:
        from SyntaxIntelligence.event_bus import SyntaxEventBus  # type: ignore

        klass = SyntaxEventBus
    except (ImportError, ModuleNotFoundError) as e:
        err_msg = f"Syntax event bus not available on this system: {e!r}"
    except (AttributeError, SyntaxError) as e:
        err_msg = f"Syntax event bus API drift detected: {e!r}"
    except Exception as e:
        err_msg = f"Unexpected import error: {e!r}"

    if err_msg is not None:
        _EVT_BUS_IMPORT_ERROR = err_msg
        if not _EVT_BUS_FIRST_FAILURE_LOGGED:
            _EVT_BUS_FIRST_FAILURE_LOGGED = True
            sys.stderr.write(f"[outclaw_bus] WARN: {err_msg}\n")
            sys.stderr.flush()

    _EVT_BUS = klass
    return klass


_HOST = "outclaw-orchestrator"


CHANNEL_FINDINGS = "outclaw.findings"
CHANNEL_DRAFT_BLOCKED = "outclaw.draft_blocked"
CHANNEL_PULSE = "swarm.heartbeat"


# ---------------------------------------------------------------------------
# PII redaction -- multi-layer (post-review: legal-term allowlist + docket pattern)
# ---------------------------------------------------------------------------

_NAME_PAT = re.compile(
    r"\b(?:[A-Z][a-z]{1,20}\s+)+[A-Z][a-z]{1,20}\b"
)
_REDACTION_SENTINEL = "__OUTCLAW_LEGAL_TERM_{:03d}__"
_DIGIT_RUN_PAT = re.compile(r"\b\d[\d\-\.]{6,}\b")
_DOCKET_PAT = re.compile(r"\b\d{1,3}[:\-][A-Z]{2,4}[\-\.\:]?\d{2,8}[A-Z]?\b")
_LEGAL_TERM_ALLOWLIST = (
    "federal rules",
    "supreme court",
    "united states",
    "district court",
    "chief justice",
    "associate justice",
    "bankruptcy code",
    "civil procedure",
    "criminal procedure",
    "evidence code",
    "constitution",
    "rules of",
    "court of",
    "court of appeals",
    "circuit court",
    "magistrate judge",
    "law review",
    "legal aid",
    "u.s. constitution",
    "u.s. code",
    "code of federal",
    "federal regulations",
    "state statute",
    "common law",
)


def _redact_names(text: str) -> str:
    """Redact title-cased name chains while restoring legal phrases verbatim."""
    preserved: list[str] = []

    def preserve(match: re.Match[str]) -> str:
        preserved.append(match.group(0))
        return _REDACTION_SENTINEL.format(len(preserved) - 1)

    masked = text
    # Longest phrases first prevents ``court of`` from consuming part of
    # ``court of appeals`` before the more specific phrase is protected.
    for term in sorted(_LEGAL_TERM_ALLOWLIST, key=len, reverse=True):
        masked = re.sub(re.escape(term), preserve, masked, flags=re.IGNORECASE)
    masked = _NAME_PAT.sub("REDACTED-NAME", masked)
    for index, original in enumerate(preserved):
        masked = masked.replace(_REDACTION_SENTINEL.format(index), original)
    return masked


def _redact_numbers(text: str) -> str:
    """
    Strip both plain numeric sequences (SSN, monetary amounts) AND docket
    notation (year-letters-seq).
    """
    text = _DOCKET_PAT.sub("REDACTED-NUMBER", text)
    text = _DIGIT_RUN_PAT.sub("REDACTED-NUMBER", text)
    return text


def redact_excerpt(text: str, max_chars: int = 160) -> str:
    """
    Apply name-strip (with legal-term allowlist) + docket/numeric-strip +
    whitespace-collapse + length cap.

    Order matters: stripping first prevents later passes from accidentally
    exposing a name or number that crossed the cap boundary.
    """
    text = " ".join(text.split())
    text = _redact_names(text)
    text = _redact_numbers(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def citation_fingerprint(citation: str) -> str:
    """Stable short hash of a citation, used in bus payloads."""
    norm = " ".join(citation.split()).lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:12]


# ---------------------------------------------------------------------------
# OutClawBus -- thin wrapper, doesn't take over bus ownership.
# ---------------------------------------------------------------------------


@dataclass
class BusDiagnostics:
    bus_available: bool
    bus_import_error: str | None
    published_count: int = 0
    subscribed_channels: list[str] = field(default_factory=list)


class OutClawBus:
    def __init__(
        self,
        bus: Any = None,
        sender_id: str = _HOST,
        sync_bridge: Any = None,
        force_no_bus: bool = False,
    ):
        self._sender = sender_id
        if force_no_bus and bus is not None:
            # Conflict detection: caller asked for BOTH an explicit bus
            # and force_no_bus=True. We honor force_no_bus (the explicit
            # bus arg is ignored) and surface a one-shot WARN so the
            # configuration error doesn't disappear silently.
            _warn_force_no_bus_conflict_once()
        if force_no_bus:
            # Test/operator override: simulate a dead local bus without
            # touching the lazy-import cache. Use this rather than reassigning
            # ``self._bus`` directly in tests.
            self._bus = None
            self._owns = False
        elif bus is not None:
            self._bus = bus
            self._owns = False
        else:
            klass = _ensure_bus()
            self._bus = klass() if klass is not None else None
            self._owns = self._bus is not None
        # Optional cross-device bridge attachment. When set, OutClawBus will
        # fan out a cross-device copy of every published digest even when
        # the local Syntax bus is unavailable. Set via attach_bridge().
        self._bridge = sync_bridge
        self._fallback_log: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def is_live(self) -> bool:
        return self._bus is not None

    @property
    def has_bridge(self) -> bool:
        return self._bridge is not None

    @property
    def local_bus(self) -> Any:
        """Public accessor for the wrapped in-process bus (None if force_no_bus)."""
        return self._bus

    def attach_bridge(self, bridge: Any) -> None:
        """Opt-in: attach a SyncBridge for cross-device fan-out. Removes any prior bridge."""
        self._bridge = bridge

    def detach_bridge(self) -> None:
        self._bridge = None

    def diagnostics(self) -> BusDiagnostics:
        return BusDiagnostics(
            bus_available=self.is_live,
            bus_import_error=_EVT_BUS_IMPORT_ERROR,
            published_count=len(self._fallback_log),
            subscribed_channels=list(self._bus._subscriptions.keys())
            if self.is_live
            else [],
        )

    def publish_findings(self, audit_report_dict: dict[str, Any]) -> dict[str, Any]:
        summary = audit_report_dict.get("summary", {})
        findings = audit_report_dict.get("findings", []) or []
        high_payload: list[dict[str, Any]] = []
        for f in findings:
            if f.get("severity") == "HIGH":
                excerpt = redact_excerpt(f.get("sentence", ""), max_chars=160)
                high_payload.append(
                    {
                        "citation_fp": citation_fingerprint(f.get("citation", "")),
                        "rule": f.get("rule", ""),
                        "excerpt": excerpt,
                    }
                )
        digest = {
            "audit_id": citation_fingerprint(audit_report_dict.get("text", ""))[:10],
            "severity_counts": summary.get("severity_counts", {}),
            "recovered_by_window_count": summary.get("recovered_by_window_count", 0),
            "safe_to_draft": summary.get("safe_to_draft", False),
            "high_count": len(high_payload),
            "high_findings": high_payload[:5],
        }
        self._dispatch(CHANNEL_FINDINGS, digest)
        return digest

    def publish_blocked(self, intent: str, unresolved: list[dict[str, Any]]) -> None:
        digest = {
            "intent": intent,
            "unresolved_count": len(unresolved),
            "unresolved_rules": list({u.get("rule", "") for u in unresolved}),
        }
        self._dispatch(CHANNEL_DRAFT_BLOCKED, digest)

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """
        Public facade for callers that want to bypass the typed helpers.
        Routes through _dispatch so bus + bridge fan-out apply uniformly.

        IMPORTANT -- does NOT redact PII. For normal audit output use
        ``publish_findings()`` which has the redact_excerpt pipeline.
        Calling ``publish()`` with raw text makes you responsible for
        PII handling at the call site.

        LIVE-BUS CONTRACT: when ``self._bus`` is alive we forward the
        SAME dict reference into ``local_bus.publish``. Callers MUST NOT
        mutate ``payload`` after calling ``publish()`` -- a downstream
        subscriber could see the mutation mid-flight on the SYNTAX event
        bus (which calls subscribers during the publish call). If you
        need to mutate after dispatch, build the dict fresh on the next
        call.

        The FALLBACK path (no local bus) does ``dict(data)`` defensively
        before handing it to the bridge so cross-device writes get a
        fresh copy and don't share state with the caller.
        """
        self._dispatch(channel, payload)

    def subscribe_findings(
        self, agent_id: str, callback: Callable[[str, str, dict[str, Any]], None]
    ) -> None:
        if not self.is_live:
            return
        self._bus.subscribe(agent_id, CHANNEL_FINDINGS, callback)

    def subscribe_pulse(
        self, agent_id: str, callback: Callable[[str, str, dict[str, Any]], None]
    ) -> None:
        if not self.is_live:
            return
        self._bus.subscribe(agent_id, CHANNEL_PULSE, callback)

    def fallback_log(self, n: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._fallback_log[-n:])

    def _dispatch(self, channel: str, data: dict[str, Any]) -> None:
        # Loop-prevention invariant: never re-fan-out an event the bridge
        # already delivered from a peer. Such payloads carry the marker
        # ``_bridge_origin == "ingress"`` and we drop them on the floor.
        if isinstance(data, dict) and data.get("_bridge_origin") == "ingress":
            return

        local_bus = self._bus  # capture once for TOCTOU avoidance
        bridged = False
        if local_bus is not None:
            try:
                local_bus.publish(self._sender, channel, data)
                with self._lock:
                    self._fallback_log.append(
                        {
                            "channel": channel,
                            "data": data,
                            "live": True,
                            "bridged": False,
                        }
                    )
                # Live path: the bridge (if attached) will pick this up via
                # its own _egress_cb subscription to ``channel``. We do NOT
                # also call bridge.publish_local here -- doing so would
                # write the same event twice with two different message_ids.
                # Fallback-only cross-device mirror is below.
                return
            except Exception as exc:
                # Degrade to fallback path. Surface a one-shot WARN so the
                # operator sees the live-bus failure (not just diagnostics()).
                if not getattr(self, "_live_failure_warned", False):
                    self._live_failure_warned = True
                    sys.stderr.write(
                        f"[outclaw_bus] WARN: live publish failed, "
                        f"degrading to fallback log: {exc!r}\n"
                    )
                    sys.stderr.flush()
        # Fallback path: the in-process bus is missing or dead. Best-effort
        # cross-device mirror via the attached bridge (so the audit digest
        # still reaches peers even with no local subscriber routing).
        if self._bridge is not None:
            try:
                sent = self._bridge.publish_local(
                    channel, dict(data), sender_id=self._sender
                )
                bridged = sent is not None
            except Exception as exc:
                # Same drift-detection pattern as live-failure: one-shot WARN
                # so operators see bridge drift without needing diagnostics().
                if not getattr(self, "_bridge_failure_warned", False):
                    self._bridge_failure_warned = True
                    sys.stderr.write(
                        f"[outclaw_bus] WARN: bridge publish_local failed "
                        f"(may indicate bridge API drift): {exc!r}\n"
                    )
                    sys.stderr.flush()
        with self._lock:
            self._fallback_log.append(
                {
                    "channel": channel,
                    "data": data,
                    "live": False,
                    "bridged": bridged,
                }
            )


# ---------------------------------------------------------------------------
# Default singleton (useful for the CLI; tests construct their own).
# ---------------------------------------------------------------------------

_default_bus: OutClawBus | None = None
_default_lock = threading.Lock()


def default_bus() -> OutClawBus:
    global _default_bus
    with _default_lock:
        if _default_bus is None:
            _default_bus = OutClawBus()
        return _default_bus
