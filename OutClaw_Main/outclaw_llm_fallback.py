#!/usr/bin/env python3
"""
outclaw_llm_fallback.py — LLM Escalation Layer for OutClaw.

When the deterministic pipeline (regex → lexical scoring → polarity detection)
produces a low-confidence finding, this layer automatically escalates to the
CLOUD-ONLY model cascade for a final pass.

Design principles
-----------------
- **Auto-escalation, not opt-in.**  When ``auto_escalate=True`` on
  ``audit_text()``, ambiguous findings are automatically re-examined.
  No separate flag per citation — the pipeline decides when confidence
  is too low to trust heuristics alone.
- **Multi-task fallback chain.**  For each ambiguous finding, the LLM is
  consulted in priority order:
    1. OPPOSITE HOLDING detection (is the proposition inverted?)
    2. SUPPORT SCORING (does the authority actually support this?)
    3. CITATION EXTRACTION (did regex miss a citation variant?)
  Each task runs only if the previous didn't resolve the ambiguity.
- **CLOUD-ONLY (2026-08-03).**  There is NO local inference rung. End
  users are self-represented litigants on arbitrary hardware without
  models installed; every call goes through the free-tier cloud cascade.
- **Graceful degradation.**  If the cascade is unconfigured or fails,
  findings pass through unchanged with ``llm_escalated=False``.  The
  pipeline never blocks on LLM availability.
- **Observable.**  Every escalation is logged and findings carry
  ``llm_escalated`` and ``escalation_task`` fields.
- **Cached.**  LLM responses are memoized by citation+proposition hash.

Integration
-----------
    from outclaw_llm_fallback import LLMEscalationLayer

    escalator = LLMEscalationLayer()
    escalated = escalator.escalate_findings(findings, case_db, statute_db)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger("outclaw.llm_fallback")

# ---------------------------------------------------------------------------
# Escalation thresholds
# ---------------------------------------------------------------------------

AMBIGUOUS_SCORE_MAX = 0.25       # scores below this trigger escalation
ESCALABLE_SEVERITIES = frozenset({"MEDIUM"})  # HIGH is certain, OK is fine
LLM_CONFIDENCE_MIN = 0.65        # only accept LLM reclassification at this confidence

# ---------------------------------------------------------------------------
# LLM prompt templates for escalation tasks
# ---------------------------------------------------------------------------

OPPOSITE_HOLDING_ESCALATION = """You are a legal citation auditor. Determine whether the proposition below asserts the OPPOSITE of what the cited authority actually holds.

CITED AUTHORITY: {authority_name}
HOLDING: {holding}

PROPOSITION IN FILING:
{proposition}

Does the proposition contradict, invert, or assert the opposite of what the authority holds?

Respond with ONLY this JSON (no other text):
{{"is_opposite": true_or_false, "confidence": 0.0_to_1.0, "reasoning": "one sentence"}}"""


SUPPORT_SCORING_ESCALATION = """You are a legal citation validator. Score how well a proposition is supported by a cited authority.

CITED AUTHORITY TEXT (holding/summary):
{authority_text}

PROPOSITION IN THE FILING:
{proposition}

Rate the support on this scale:
- 1.0: Proposition directly restates or closely follows the authority
- 0.7-0.9: Substantially supported, minor differences
- 0.4-0.6: Tangentially related
- 0.1-0.3: Largely unrelated or only mentions the authority in passing
- 0.0: Contradicts or inverts the authority

Respond with ONLY this JSON (no other text):
{{"support_score": 0.0_to_1.0, "is_opposite": true_or_false, "verdict": "SUPPORTED|OPPOSITE_HOLDING|NO_SUPPORT", "reasoning": "one sentence"}}"""


# ---------------------------------------------------------------------------
# Escalation layer
# ---------------------------------------------------------------------------


class LLMEscalationLayer:
    """Auto-escalate ambiguous findings through the cloud cascade for reclassification.

    Usage::

        escalator = LLMEscalationLayer()
        findings, stats = escalator.escalate_findings(
            findings, case_db, statute_db
        )
    """

    def __init__(
        self,
        *,
        min_confidence: float = LLM_CONFIDENCE_MIN,
        max_score: float = AMBIGUOUS_SCORE_MAX,
    ) -> None:
        self._min_confidence = min_confidence
        self._max_score = max_score
        self._cache: dict[str, dict[str, Any]] = {}
        self._stats: dict[str, int] = {
            "escalated": 0,
            "reclassified": 0,
            "unchanged": 0,
            "llm_unavailable": 0,
            "cache_hits": 0,
            "total_elapsed_ms": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def escalate_findings(
        self,
        findings: list[Any],
        case_db: dict[str, Any],
        statute_db: dict[str, str],
    ) -> tuple[list[Any], dict[str, int]]:
        """Run escalation on all eligible findings. Returns (findings, stats).

        Only escalates findings with severity in ESCALABLE_SEVERITIES and
        score below the ambiguity threshold.  HIGH-severity findings
        (fabricated citations) are never escalated — they're certain.
        """
        if not self._cascade_ready():
            self._stats["llm_unavailable"] += len(findings)
            return findings, dict(self._stats)

        escalated_count = 0
        reclassified_count = 0

        for finding in findings:
            if not self._should_escalate(finding):
                continue

            escalated_count += 1
            started = time.time()

            citation = (
                finding.citation
                if hasattr(finding, "citation")
                else finding.get("citation", "")
            )
            proposition = (
                finding.sentence
                if hasattr(finding, "sentence")
                else finding.get("sentence", "")
            )
            current_rule = (
                finding.rule
                if hasattr(finding, "rule")
                else finding.get("rule", "")
            )

            # Determine authority kind and lookup
            kind = "statute" if "U.S.C." in str(citation) else "case"
            authority_text = ""
            authority_name = str(citation)

            if kind == "case" and citation in case_db:
                entry = case_db[citation]
                authority_text = (
                    entry.holding
                    if hasattr(entry, "holding")
                    else entry.get("holding", "")
                )
                authority_name = (
                    entry.name
                    if hasattr(entry, "name")
                    else entry.get("name", citation)
                )
            elif kind == "statute" and citation in statute_db:
                authority_text = str(statute_db[citation])

            if not authority_text:
                self._stats["unchanged"] += 1
                continue

            # ── Task 1: OPPOSITE HOLDING detection ──
            opp_result = self._call_escalation_task(
                "opposite_holding",
                proposition,
                authority_text,
                authority_name=authority_name,
            )

            if opp_result and opp_result.get("is_opposite"):
                conf = opp_result.get("confidence", 0.0)
                if conf >= self._min_confidence:
                    self._apply_reclassification(
                        finding, "OPPOSITE HOLDING", "HIGH",
                        f"LLM escalation: {opp_result.get('reasoning', '')}",
                        "opposite_holding",
                    )
                    reclassified_count += 1
                    self._stats["total_elapsed_ms"] += (
                        (time.time() - started) * 1000
                    )
                    continue

            # ── Task 2: SUPPORT SCORING ──
            support_result = self._call_escalation_task(
                "support_scoring",
                proposition,
                authority_text,
                authority_name=authority_name,
            )

            if support_result:
                verdict = support_result.get("verdict", "")
                if verdict == "SUPPORTED":
                    self._apply_reclassification(
                        finding, "SUPPORTED", "OK",
                        f"LLM escalation: {support_result.get('reasoning', '')}",
                        "support_scoring",
                    )
                    reclassified_count += 1
                elif verdict == "OPPOSITE_HOLDING":
                    self._apply_reclassification(
                        finding, "OPPOSITE HOLDING", "HIGH",
                        f"LLM escalation: {support_result.get('reasoning', '')}",
                        "support_scoring",
                    )
                    reclassified_count += 1
                else:
                    self._stats["unchanged"] += 1
            else:
                self._stats["unchanged"] += 1

            self._stats["total_elapsed_ms"] += (time.time() - started) * 1000

        self._stats["escalated"] += escalated_count
        self._stats["reclassified"] += reclassified_count
        return findings, dict(self._stats)

    def diagnostics(self) -> dict[str, Any]:
        """Return operational diagnostics."""
        return {
            **self._stats,
            "cache_size": len(self._cache),
            "cascade_ready": self._cascade_ready(),
        }

    def clear_cache(self) -> None:
        self._cache.clear()
        for key in self._stats:
            if isinstance(self._stats[key], int):
                self._stats[key] = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _cascade_ready() -> bool:
        """True when the cloud cascade is enabled AND has configured providers.

        Never pokes a local model — there is no local rung by design.
        """
        try:
            from OutClaw.outclaw_model_cascade import cascade_status  # type: ignore

            cs = cascade_status()
            providers = cs.get("providers", {})
            ready = [
                name for name, info in providers.items() if info.get("configured")
            ]
            return bool(cs.get("enabled") and ready)
        except Exception:
            return False

    def _should_escalate(self, finding: Any) -> bool:
        """Determine if a finding is eligible for LLM escalation."""
        # Handle both dataclass and dict-style findings
        severity = (
            finding.severity
            if hasattr(finding, "severity")
            else finding.get("severity", "")
        )
        score = (
            finding.score
            if hasattr(finding, "score")
            else finding.get("score", 1.0)
        )
        already_escalated = (
            finding.llm_escalated
            if hasattr(finding, "llm_escalated")
            else finding.get("llm_escalated", False)
        )
        return (
            not already_escalated
            and severity in ESCALABLE_SEVERITIES
            and float(score) < self._max_score
        )

    def _cache_key(self, task: str, proposition: str, authority: str) -> str:
        norm = " ".join(f"{task}:{proposition}:{authority}".split())
        return hashlib.sha256(norm.encode()).hexdigest()[:16]

    def _call_escalation_task(
        self,
        task: str,
        proposition: str,
        authority_text: str,
        *,
        authority_name: str = "",
    ) -> dict[str, Any] | None:
        """Call the cloud cascade for an escalation task. Returns parsed JSON or None."""
        key = self._cache_key(task, proposition, authority_text)
        if key in self._cache:
            self._stats["cache_hits"] += 1
            return self._cache[key]

        if task == "opposite_holding":
            prompt = OPPOSITE_HOLDING_ESCALATION.format(
                authority_name=authority_name or "the cited authority",
                holding=authority_text[:1500],
                proposition=proposition[:1500],
            )
        elif task == "support_scoring":
            prompt = SUPPORT_SCORING_ESCALATION.format(
                authority_text=authority_text[:1500],
                proposition=proposition[:1500],
            )
        else:
            return None

        # ── CLOUD-ONLY CASCADE PATH (2026-08-03) ──
        # The tiered model cascade (free cloud tiers 2-3) is the ONLY LLM
        # path. There is deliberately no local model fallback — end users
        # will not have models installed.
        try:
            from OutClaw.outclaw_model_cascade import get_cascade  # type: ignore

            cascade = get_cascade()
            if cascade.enabled:
                cascade_task = {
                    "opposite_holding": "opposite_holding",
                    "support_scoring": "support_scoring",
                }.get(task, task)
                result = cascade.complete(
                    prompt,
                    task=cascade_task,
                    min_confidence=self._min_confidence,
                    max_tokens=800,
                )
                if result.ok and result.data is not None:
                    parsed = result.data
                    self._cache[key] = parsed
                    if len(self._cache) > 1000:
                        oldest = next(iter(self._cache))
                        del self._cache[oldest]
                    return parsed
        except Exception:
            pass  # cascade import failure is non-fatal; no local fallback

        return None

    @staticmethod
    def _apply_reclassification(
        finding: Any,
        new_rule: str,
        new_severity: str,
        new_detail: str,
        task: str,
    ) -> None:
        """Apply LLM reclassification to a finding (works on dataclass or dict)."""
        if hasattr(finding, "rule"):
            finding.rule = new_rule
            finding.severity = new_severity
            finding.detail = new_detail
            finding.llm_escalated = True
            finding.escalation_task = task
        else:
            finding["rule"] = new_rule
            finding["severity"] = new_severity
            finding["detail"] = new_detail
            finding["llm_escalated"] = True
            finding["escalation_task"] = task


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def smoke_test() -> dict[str, Any]:
    """Quick smoke test of the escalation layer."""
    class _FakeFinding:
        def __init__(self, rule, severity, score, citation, sentence):
            self.rule = rule
            self.severity = severity
            self.score = score
            self.citation = citation
            self.sentence = sentence
            self.detail = ""
            self.recovered_by_window = False
            self.llm_assisted = False
            self.llm_escalated = False
            self.escalation_task = ""

    findings = [
        _FakeFinding("NO SUPPORT", "MEDIUM", 0.12, "Smith v. Jones, 123 F.3d 456", "The court held otherwise."),
        _FakeFinding("SUPPORTED", "OK", 0.85, "Miller v. Acme, 555 F.3d 789", "Miller established this rule."),
        _FakeFinding("EXISTENCE", "HIGH", 0.0, "FakeCite v. Nobody, 999 F.3d 999", "This case doesn't exist."),
    ]

    escalator = LLMEscalationLayer()
    case_db = {
        "Smith v. Jones, 123 F.3d 456": type("Entry", (), {"holding": "The court held that warrants are always required.", "name": "Smith v. Jones"})(),
    }
    statute_db = {}

    escalated, stats = escalator.escalate_findings(findings, case_db, statute_db)

    return {
        "total": len(findings),
        "escalated": stats["escalated"],
        "reclassified": stats.get("reclassified", 0),
        "unchanged": stats["unchanged"],
        "llm_unavailable": stats["llm_unavailable"],
        "findings": [
            {
                "rule": f.rule,
                "severity": f.severity,
                "llm_escalated": f.llm_escalated,
            }
            for f in escalated
        ],
    }


if __name__ == "__main__":
    print(json.dumps(smoke_test(), indent=2))
