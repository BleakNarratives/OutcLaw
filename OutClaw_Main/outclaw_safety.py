#!/usr/bin/env python3
"""
outclaw_safety.py -- OutClaw Safety Gate.

The hard constraint, made explicit -- rewrite after code review.

The manifesto at OutClaw/outclaw_manifesto.md mandates a permanent block on
``generate_document()`` because the regex surface-pattern checks aren't reliable
enough to trust unsupervised federal filing generation. This module is the
deliberate, narrow safety surface for that block.

Post-review fixes (this revision):
  * ACK TOKEN FINGERPRINT IS VALIDATED. Earlier draft computed text_fingerprint
    on the AckToken object but never compared it inside safe_generate_document.
    Now we take an AckToken object (or its fingerprint + intent) and the
    caller MUST pass the matching fingerprint for the current draft text, or
    the gate stays closed.
  * TOKEN SUFFIX IS crypto-quality throughout. The earlier draft had a
    /dev/urandom fallback that produced deterministic tokens on platforms
    without /dev/urandom. The rewrite uses `secrets.token_hex` end-to-end.
  * ACK TOKEN VALIDATION PATH is explicit in safe_generate_document. The
    previous draft's _is_well_formed_ack was accepting any 4+4 hex token
    from any prior session. That's now accompanied by a fingerprint match.

Module-level controls:
  1. Acceptance into this module is by INTENT name only. Anything not in the
     enumerated intents raises IntentRejected before even touching audit.
  2. Every accepted intent is audited through outclaw_unified.audit_text().
     Unresolved HIGH or MEDIUM findings raise GenerateDocumentBlocked.
  3. When the audit finds nothing blocking, the operator MUST supply an
     ack_token whose text_fingerprint MATCHES the current draft text. This
     is the human-in-the-loop step. The token is bound to a specific draft
     snapshot, randomly generated, and single-use. It is not an
     authentication credential.
  4. THEN -- and only then -- may generate_document() execute. In practice
     that call still raises NotImplementedError (the upstream block) but the
     EVIDENCE that this module assembled (audit summary + ack_token trace)
     is the documented, defensible signal: "safe to draft".

Dependency direction (held by code review): this module imports unified.
Unified never imports safety. CLI imports both.
"""

from __future__ import annotations

import hashlib
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
try:
    # Prefer the canonical package identity so root and project invocations
    # share the same orchestrator module rather than loading two copies.
    from OutClaw import outclaw_unified as unified  # type: ignore
except ImportError:
    # Preserve direct flat-module execution from OutClaw_Main.
    import outclaw_unified as unified  # type: ignore

# ---------------------------------------------------------------------------
# Enumerated intents -- the manifesto's federal filings only.
# ---------------------------------------------------------------------------

ACCEPTED_INTENTS = frozenset(
    {
        # Federal civil filings
        "draft_1983_complaint",
        "draft_motion_to_dismiss",
        "draft_affidavit",
        "draft_discovery_request",
        "draft_motion_for_summary_judgment",
        # Federal habeas corpus (Buff-expansion 2026-07-26)
        "draft_2254_habeas_petition",
        "draft_2255_motion_to_vacate",
        # State-court filings (Buff-expansion 2026-07-26)
        "draft_state_habeas_petition",
        "draft_state_postconviction_motion",
        # Appellate filings (Buff-expansion 2026-07-26)
        "draft_notice_of_appeal",
        "draft_appellate_brief",
        # Emergency / injunctive relief (Buff-expansion 2026-07-26)
        "draft_motion_for_tro",
        "draft_motion_for_preliminary_injunction",
    }
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════
#  OUTCLAW_SAFETY
# ═══════════════════════════════════════════════════════════════

class IntentRejected(ValueError):
    """Raised before audit -- the intent is not on the allow-list."""


class GenerateDocumentBlocked(RuntimeError):
    """
    Raised AFTER audit, BEFORE generation. Payload is the litany of
    unresolved findings so the operator can fix the draft.
    """

    def __init__(
        self,
        message: str,
        unresolved: list[dict[str, Any]],
        audit_summary: dict[str, Any],
        intent: str,
    ):
        super().__init__(message)
        self.unresolved = unresolved
        self.audit_summary = audit_summary
        self.intent = intent


# ---------------------------------------------------------------------------
# Token plumbing
# ---------------------------------------------------------------------------


def _text_fingerprint(text: str) -> str:
    """
    SHA-256 of the normalized text, truncated to 16 hex chars (64 bits).
    Deterministic enough to bind an ack_token to a specific draft snapshot.
    """
    norm = " ".join(text.split()).encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:16]


def _generate_ack_token_string() -> str:
    """
    Generate a randomly generated acknowledgment token using secrets.token_hex.
    Two halves of 4 hex chars separated by a dash. Total entropy: 16 bits
    per half, 32 bits total. The token is additionally bound to the draft
    fingerprint and is intended as a human-in-the-loop confirmation, not a
    standalone authentication credential.
    """
    return secrets.token_hex(2) + "-" + secrets.token_hex(2)


@dataclass
class AckToken:
    """
    On-the-fly human acknowledgment token. Generated by request_ack_token,
    consumed by safe_generate_document. text_fingerprint binds the token to
    the specific draft snapshot it was emitted for.
    """

    token: str
    intent: str
    text_fingerprint: str
    emitted_at: float
    consumed: bool = False

    def display(self) -> str:
        ts = int(self.emitted_at)
        return (
            f"\n  === OutClaw ack_token -- copy this back exactly ===\n"
            f"  Intent                  : {self.intent}\n"
            f"  Token                   : {self.token}\n"
            f"  Token fingerprint (sha256, 16 hex): {self.text_fingerprint}\n"
            f"  Required fingerprint    : same as audit will compute\n"
            f"  Issued at               : {ts}\n"
            f"  ============================================\n"
        )


def request_ack_token(
    intent: str,
    text: str,
    sink: Callable[[str], None] | None = None,
) -> AckToken:
    """
    Generate and emit a fresh acknowledgment token for an intent + text snapshot.

    This is a low-level token constructor. The interactive CLI path performs
    a pre-audit before calling it; callers using this helper directly remain
    responsible for auditing first. The token is not an authentication
    credential. It is bound to (intent, text_fingerprint) and cannot be reused
    across drafts because safe_generate_document will re-compute the
    fingerprint and refuse a mismatch.
    """
    if intent not in ACCEPTED_INTENTS:
        raise IntentRejected(
            f"Intent '{intent}' not on OutClaw allow-list. Accepted: "
            f"{sorted(ACCEPTED_INTENTS)}"
        )

    ack = AckToken(
        token=_generate_ack_token_string(),
        intent=intent,
        text_fingerprint=_text_fingerprint(text),
        emitted_at=time.time(),
    )

    msg = ack.display()
    if sink is not None:
        sink(msg)
    else:
        # Default stream is stderr: keeps the operator-visible token out of
        # any piping path that might capture the audit or the document.
        sys.stderr.write(msg)
        sys.stderr.flush()
    return ack


def _is_well_formed_ack(token: str) -> bool:
    parts = token.split("-")
    if len(parts) != 2:
        return False
    # Both halves must be exactly 4 lowercase hex chars.
    if not all(len(p) == 4 and all(c in "0123456789abcdef" for c in p) for p in parts):
        return False
    return True


def _fingerprint_matches(token: AckToken, text: str) -> bool:
    return token.text_fingerprint == _text_fingerprint(text)


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


@dataclass
class SafetyTrace:
    """
    Audit + ack evidence captured every time the gate is exercised.
    Operators should pipe these into their case file as proof-of-review.
    """

    intent: str
    audit_summary: dict[str, Any]
    unresolved: list[dict[str, Any]]
    ack_token: str | None = None
    ack_token_fingerprint: str | None = None
    ack_consumed_at: float | None = None
    outcome: str = "blocked"

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "audit_summary": self.audit_summary,
            "unresolved": self.unresolved,
            "ack_token": self.ack_token,
            "ack_token_fingerprint": self.ack_token_fingerprint,
            "ack_consumed_at": self.ack_consumed_at,
            "outcome": self.outcome,
        }


def _complete_clean_ack(
    intent: str,
    text: str,
    report: Any,
    ack: AckToken | None,
) -> SafetyTrace:
    """Validate a single-use token against an already-clean audit."""
    if ack is None:
        raise GenerateDocumentBlocked(
            message=(
                f"OutClaw audit clean for '{intent}', but no ack_token was "
                "supplied. Call request_ack_token(intent, text) and supply "
                "the returned AckToken (not just the string) to "
                "safe_generate_document before any document generation can occur."
            ),
            unresolved=[],
            audit_summary=report.summary,
            intent=intent,
        )

    if ack.consumed:
        raise GenerateDocumentBlocked(
            message=(
                f"Ack token '{ack.token}' has already been consumed. "
                "Request a fresh token before retrying; acknowledgment tokens "
                "cannot be replayed."
            ),
            unresolved=[],
            audit_summary=report.summary,
            intent=intent,
        )

    if not _is_well_formed_ack(ack.token):
        raise ValueError(f"Ack token '{ack.token}' is not well-formed.")

    if ack.intent != intent:
        raise ValueError(
            f"Ack token was emitted for intent '{ack.intent}' but "
            f"safe_generate_document called with intent '{intent}'."
        )

    current_fingerprint = _text_fingerprint(text)
    if not _fingerprint_matches(ack, text):
        raise ValueError(
            f"Ack token's fingerprint ({ack.text_fingerprint}) does not "
            f"match the current draft's fingerprint ({current_fingerprint}). "
            "Tokens are bound to a specific draft snapshot; call "
            "request_ack_token(intent, text) again for the new draft."
        )

    ack.consumed = True
    return SafetyTrace(
        intent=intent,
        audit_summary=report.summary,
        unresolved=[],
        ack_token=ack.token,
        ack_token_fingerprint=ack.text_fingerprint,
        ack_consumed_at=time.time(),
        outcome="audit-clean-ack-verified",
    )


def safe_generate_document(
    intent: str,
    text: str,
    ack: AckToken | None = None,
) -> SafetyTrace:
    """
    Run the full DRAFT-block chain for an accepted intent.

    Parameters
    ----------
    intent : str
        Must be in ACCEPTED_INTENTS.
    text : str
        Draft text to be vetted; audit runs on this snapshot.
    ack : AckToken | None
        The AckToken object previously emitted by request_ack_token() for
        THIS (intent, text) snapshot. Passing None denies permission even
        when the audit is clean -- this forces the human-in-the-loop step.
        Passing a token whose text_fingerprint doesn't match the current
        text also denies permission (the fingerprint is non-erasable proof
        that the operator reviewed THIS specific draft).
    Note
    ----
    The previous ``auto_pass_medium`` parameter was removed in round 25:
    outclaw_unified.Report.safe_to_draft() is now the canonical gate
    (HIGH or MEDIUM blocks). Any caller still passing ``auto_pass_medium``
    would now raise TypeError -- surface that explicitly in WHO_DID_WHAT
    if you find one.

    Returns
    -------
    SafetyTrace on a successful audit-and-ack gate pass. Blocked paths raise
    GenerateDocumentBlocked with the audit summary and unresolved findings;
    operators should save successful traces with their case file.
    """
    if intent not in ACCEPTED_INTENTS:
        raise IntentRejected(
            f"Intent '{intent}' is not on the OutClaw allow-list. "
            f"Accepted intents: {sorted(ACCEPTED_INTENTS)}"
        )

    # 1. Run the audit. Non-negotiable even if a well-formed ack is presented.
    report = unified.audit_text(text)
    # Round 25 (PATH IV): route the gate through ``Report.safe_to_draft()``
    # so outclaw_unified.py is the SINGLE SOURCE OF TRUTH on the severity
    # threshold. The ``unresolved`` list remains the explanation payload
    # (what's blocking, not just that something is blocking); the
    # ``if not safe_to_draft()`` test guarantees the threshold semantics
    # cannot drift between cmd_audit, cmd_safe_draft, and the demo summary.
    unresolved: list[dict[str, Any]] = [
        f.__dict__
        for f in report.findings
        if f.severity in (unified.HIGH, unified.MEDIUM)
    ]

    if not report.safe_to_draft():
        raise GenerateDocumentBlocked(
            message=(
                f"OutClaw refused to draft '{intent}' -- "
                f"{len(unresolved)} unresolved audit finding(s) [see .unresolved]"
            ),
            unresolved=[
                {k: v for k, v in f.items() if k != "recovered_by_window"}
                for f in unresolved
            ],
            audit_summary=report.summary,
            intent=intent,
        )

    # 2. Audit is clean; validate the single-use token against this snapshot.
    return _complete_clean_ack(intent, text, report, ack)


# ---------------------------------------------------------------------------
# Convenience: the operator-friendly end-to-end.
# ---------------------------------------------------------------------------


def interactive_request_and_verify(
    intent: str, text: str, sink: Callable[[str], None] | None = None
) -> SafetyTrace:
    """
    Audit first, then print the ack token to the supplied sink (defaults to
    stderr), prompt the operator, and ONLY proceed if the operator types back
    the matching token.

    Auditing before token issuance prevents a confusing dead-end where an
    operator copies a token only to learn that the draft was already blocked.
    Use this from a CLI; safe_generate_document is the programmatic primitive.
    Note: in interactive mode we re-emit a fresh token each invocation (the
    string from request_ack_token), but the AckToken object carries the
    fingerprint binding.
    """
    if intent not in ACCEPTED_INTENTS:
        raise IntentRejected(
            f"Intent '{intent}' is not on the OutClaw allow-list. "
            f"Accepted intents: {sorted(ACCEPTED_INTENTS)}"
        )

    report = unified.audit_text(text)
    unresolved = [
        f.__dict__
        for f in report.findings
        if f.severity in (unified.HIGH, unified.MEDIUM)
    ]
    if not report.safe_to_draft():
        raise GenerateDocumentBlocked(
            message=(
                f"OutClaw pre-audit blocked '{intent}' -- "
                f"{len(unresolved)} unresolved audit finding(s). "
                "No ack_token was issued; fix the draft and retry."
            ),
            unresolved=[
                {k: v for k, v in finding.items() if k != "recovered_by_window"}
                for finding in unresolved
            ],
            audit_summary=report.summary,
            intent=intent,
        )

    ack = request_ack_token(intent, text, sink=sink)
    try:
        typed = input(
            f"\n  Type the ack_token to confirm '{intent}', or press Enter to abort: "
        ).strip()
    except EOFError:
        raise GenerateDocumentBlocked(
            message="Operator cancelled ack -- non-interactive stream, refusing to proceed.",
            unresolved=[],
            audit_summary=report.summary,
            intent=intent,
        )
    if typed != ack.token:
        raise GenerateDocumentBlocked(
            message=f"Typed token '{typed}' did not match emitted token. Refusing to proceed.",
            unresolved=[],
            audit_summary=report.summary,
            intent=intent,
        )

    # Bound the typed string to the AckToken object. Reuse the pre-audit
    # report so this interactive path performs exactly one audit.
    return _complete_clean_ack(intent, text, report, ack)
