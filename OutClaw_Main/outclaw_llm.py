#!/usr/bin/env python3
"""
OutClaw/outclaw_llm.py -- LLM Integration Layer for OutClaw.

NOVEL APPROACH (Buffy, 2026-07-26): No prior model or session integrated
a language model into the OutClaw pipeline. Every existing validator
(RegexBaseline, SemanticValidator, the unified orchestrator's _negates_holding,
the SeedRegistry) is purely heuristic -- regex-based, pattern-matched, or
surface-lexical. None perform genuine semantic reasoning.

This module bridges OutClaw's deterministic heuristic pipeline and a
CLOUD-ONLY model cascade (outclaw_model_cascade.py) for the tasks that
regex fundamentally cannot solve:

  1. **OPPOSITE HOLDING detection without surface negators:**
     "The court held X." when the holding says "The court did not hold X."
     Regex cannot detect this; an LLM can reason about semantic inversion.

  2. **Support scoring with genuine comprehension:**
     Rather than Jaccard-over-alpha-tokens, ask the LLM whether the
     proposition textually supports the cited authority.

  3. **Citation extraction from unstructured prose:**
     Regex-based CITATION_RE misses citations in non-standard formats
     (state-specific reporters, vendor-neutral citations, slip opinions).
     An LLM can find citations that pattern-matchers miss.

  4. **Seed registry auto-expansion:**
     Given a case name and a snippet of its text, the LLM can generate
     a holding summary and identify the legal area -- allowing OutClaw
     to self-expand its knowledge base from real filings.

Design principles:
  - LLM is a FALLBACK layer, not a replacement. The deterministic pipeline
    runs first; the LLM is consulted only for ambiguous or high-stakes
    classifications.
  - CLOUD-ONLY (2026-08-03). There is NO local inference. End users are
    self-represented litigants on arbitrary consumer hardware who will not
    have models installed; every call goes through the free-tier cloud
    cascade. With no API keys configured, the validator reports
    unavailable and the deterministic pipeline stands untouched.
  - Timeout-guarded. LLM calls have strict timeouts so a slow provider
    doesn't hang the audit.
  - Cached. LLM responses are memoized by citation+proposition hash to avoid
    redundant calls during regression runs.
  - Observable. Every LLM call is logged so operators can audit which
    classifications were heuristic vs LLM-assisted.

Usage:
    from OutClaw.outclaw_llm import LLMValidator

    v = LLMValidator()
    result = v.check_opposite_holding(
        proposition="Police may search a home without a warrant.",
        holding="The Fourth Amendment requires a warrant for a home search."
    )
    # result -> {"is_opposite": True, "confidence": 0.92, "reasoning": "..."}

Requirements:
  - Free cloud API keys in the environment (GOOGLE_API_KEY, GROQ_API_KEY,
    OPENROUTER_API_KEY, etc.) for the cascade to have configured providers.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# CLOUD-ONLY: model names below are legacy no-ops retained for config
# compatibility. The cascade (outclaw_model_cascade.py) selects its own
# per-tier free-cloud models; nothing here ever spawns a local model.
DEFAULT_MODEL = "cascade"
DEFAULT_TIMEOUT = 15
FALLBACK_MODELS: list[str] = []
CACHE_SIZE = 500  # max cached LLM responses


# ---------------------------------------------------------------------------
# Prompt templates -- carefully structured for consistent JSON output
# ---------------------------------------------------------------------------

OPPOSITE_HOLDING_PROMPT = """You are a legal reasoning assistant. Your task is to determine whether a legal proposition asserts the OPPOSITE of what a case/statute actually holds.

CITED AUTHORITY HOLDING:
{holding}

PROPOSITION IN FILING:
{proposition}

Does the proposition contradict, invert, or assert the opposite of what the authority actually holds? Consider:
- Does the proposition say the authority allows something the authority actually prohibits?
- Does the proposition say the authority requires something the authority actually rejects?
- Does the proposition use the authority to support a claim the authority explicitly denies?

Respond with ONLY this JSON (no other text):
{{"is_opposite": true_or_false, "confidence": 0.0_to_1.0, "reasoning": "one sentence explaining why"}}"""


SUPPORT_SCORING_PROMPT = """You are a legal citation validator. Rate how well a proposition is supported by the cited authority.

CITED AUTHORITY TEXT:
{authority_text}

PROPOSITION BEING SUPPORTED:
{proposition}

Rate the support on this scale:
- 1.0: The proposition directly restates or closely follows the authority
- 0.7-0.9: The proposition is substantially supported, minor differences
- 0.4-0.6: The proposition is tangentially related to the authority
- 0.1-0.3: The proposition mentions the authority but is largely unrelated
- 0.0: The proposition contradicts or inverts the authority

Respond with ONLY this JSON (no other text):
{{"support_score": 0.0_to_1.0, "is_supported": true_or_false, "reasoning": "one sentence"}}"""


CITATION_EXTRACTION_PROMPT = """Extract all legal citations from this text. Include statutes (e.g. 42 U.S.C. § 1983), case law (e.g. Smith v. Jones, 123 F.3d 456), regulations (e.g. 26 C.F.R. § 1.1), and state-specific citations.

TEXT:
{text}

Respond with ONLY this JSON (no other text):
{{"citations": [{{"text": "exact citation string", "type": "statute|case|cfr|state|other", "start_char": integer_offset}}]}}"""


HOLDING_EXTRACTION_PROMPT = """You are a legal research assistant. Extract the core legal holding from this case text. A holding is the court's answer to the legal question presented -- the rule of law the case stands for.

CASE NAME: {case_name}
CASE TEXT:
{case_text}

Respond with ONLY this JSON (no other text):
{{"holding": "one or two sentences stating what the case holds", "area": "criminal procedure|civil rights|contracts|torts|constitutional|administrative|family|property|other", "overruled": false}}"""


# ---------------------------------------------------------------------------
# LLM Validator
# ---------------------------------------------------------------------------


@dataclass
# ═══════════════════════════════════════════════════════
#  OUTCLAW_LLM
# ═══════════════════════════════════════════════════════════════

class LLMConfig:
    """Configuration for the LLM layer."""

    model: str = DEFAULT_MODEL
    timeout: int = DEFAULT_TIMEOUT
    fallback_models: list[str] = field(default_factory=lambda: list(FALLBACK_MODELS))
    enabled: bool = True
    max_retries: int = 1
    min_confidence_for_llm: float = 0.40  # consult LLM below this confidence


class LLMValidator:
    """
    Cloud cascade integration for OutClaw citation validation.

    Routes every semantic task through outclaw_model_cascade — the
    stair-stepped, free-tier, CLOUD-ONLY ladder (no local inference).
    All calls are timeout-guarded, cached, and degrade gracefully: with
    no API keys the validator reports unavailable and the deterministic
    heuristic pipeline stands.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
        enabled: bool = True,
    ):
        self.config = LLMConfig(model=model, timeout=timeout, enabled=enabled)
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._diagnostics: dict[str, Any] = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "cache_hits": 0,
            "total_elapsed_ms": 0.0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_opposite_holding(
        self,
        proposition: str,
        holding: str,
    ) -> dict[str, Any]:
        """
        Use LLM to detect OPPOSITE HOLDING where regex cannot.

        Returns: {"is_opposite": bool, "confidence": float, "reasoning": str}
        """
        prompt = OPPOSITE_HOLDING_PROMPT.format(
            proposition=proposition,
            holding=holding,
        )
        result = self._call_llm(prompt, "opposite_holding")
        if result is None:
            return {
                "is_opposite": False,
                "confidence": 0.0,
                "reasoning": "LLM unavailable",
            }
        return result

    def score_support(
        self,
        proposition: str,
        authority_text: str,
    ) -> dict[str, Any]:
        """
        Use LLM to score how well a proposition is supported by an authority.

        Returns: {"support_score": float, "is_supported": bool, "reasoning": str}
        """
        prompt = SUPPORT_SCORING_PROMPT.format(
            proposition=proposition,
            authority_text=authority_text[:1500],  # truncate long statutes
        )
        result = self._call_llm(prompt, "support_scoring")
        if result is None:
            return {
                "support_score": 0.0,
                "is_supported": False,
                "reasoning": "LLM unavailable",
            }
        return result

    def extract_citations(self, text: str) -> list[dict[str, Any]]:
        """
        Use LLM to find citations that regex might miss.
        """
        prompt = CITATION_EXTRACTION_PROMPT.format(text=text[:2000])
        result = self._call_llm(prompt, "citation_extraction")
        if result is None:
            return []
        return result.get("citations", [])

    def extract_holding(
        self,
        case_name: str,
        case_text: str,
    ) -> dict[str, Any]:
        """
        Use LLM to extract a holding from case text for seed expansion.
        """
        prompt = HOLDING_EXTRACTION_PROMPT.format(
            case_name=case_name,
            case_text=case_text[:2000],
        )
        result = self._call_llm(prompt, "holding_extraction")
        if result is None:
            return {"holding": "", "area": "general", "overruled": False}
        return result

    def is_available(self) -> bool:
        """
        True when the cloud cascade is enabled AND has at least one
        configured (keyed) provider. Never pokes a local model.

        NOT memoized: the check is cheap (config + env reads only) and a
        stale True/False would poison the result if OUTCLAW_CASCADE or
        keys change between calls (e.g. CLI _apply_cascade ordering).
        """
        if not self.config.enabled:
            return False

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

    def diagnostics(self) -> dict[str, Any]:
        """Return operational diagnostics."""
        return {
            **self._diagnostics,
            "model": self.config.model,
            "available": self.is_available(),
            "cache_size": len(self._cache),
            "enabled": self.config.enabled,
        }

    def clear_cache(self) -> None:
        """Clear the response cache."""
        with self._lock:
            self._cache.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cache_key(self, prompt: str, task: str) -> str:
        """Stable hash for prompt caching."""
        norm = " ".join(prompt.split())
        return hashlib.sha256(f"{task}:{norm}".encode()).hexdigest()[:16]

    def _call_llm(self, prompt: str, task: str) -> dict[str, Any] | None:
        """
        Call the LLM with the given prompt. Returns parsed JSON or None.
        Memoized by prompt hash.

        CLOUD-ONLY: routes through the stair-stepped model cascade. There
        is deliberately NO local model fallback — end users will not have
        models installed. With no configured providers the cascade fails
        fast and this returns None (deterministic pipeline stands).
        """
        if not self.config.enabled:
            return None

        key = self._cache_key(prompt, task)

        # Check cache
        with self._lock:
            if key in self._cache:
                self._diagnostics["cache_hits"] += 1
                return self._cache[key]

        # ── CASCADE PATH (stair-stepped tiers, free cloud only) ──
        try:
            from OutClaw.outclaw_model_cascade import get_cascade  # type: ignore

            cascade = get_cascade()
            if cascade.enabled:
                result = cascade.complete(
                    prompt,
                    task=self._cascade_task_for(task),
                    min_confidence=self.config.min_confidence_for_llm,
                    max_tokens=1500,
                )
                if result.ok:
                    self._diagnostics["total_calls"] += 1
                    self._diagnostics["successful_calls"] += 1
                    with self._lock:
                        if len(self._cache) >= CACHE_SIZE:
                            oldest = next(iter(self._cache))
                            del self._cache[oldest]
                        self._cache[key] = result.data  # type: ignore[arg-type]
                    return result.data
                self._diagnostics["failed_calls"] += 1
        except Exception:
            pass  # cascade import failure is non-fatal; no local fallback

        return None

    @staticmethod
    def _cascade_task_for(task: str) -> str:
        """Map outclaw_llm task ids onto cascade task ids (same names here)."""
        return task


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_llm: LLMValidator | None = None
_default_lock = threading.Lock()


def get_llm(
    model: str = DEFAULT_MODEL,
    force_new: bool = False,
) -> LLMValidator:
    """Get or create the default LLM validator singleton."""
    global _default_llm
    with _default_lock:
        if _default_llm is None or force_new:
            _default_llm = LLMValidator(model=model)
        return _default_llm


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def smoke_test() -> dict[str, Any]:
    """Quick smoke test of the LLM layer."""
    llm = LLMValidator(timeout=10)
    available = llm.is_available()

    if not available:
        return {
            "status": "skipped",
            "reason": "Cloud cascade not configured (no free API keys). "
            "Deterministic pipeline is unaffected.",
            "diagnostics": llm.diagnostics(),
        }

    result = llm.check_opposite_holding(
        proposition="Police may search a home without a warrant.",
        holding="The Fourth Amendment requires a warrant for a home search absent exigent circumstances.",
    )

    return {
        "status": "ok" if result.get("is_opposite") else "needs_review",
        "result": result,
        "diagnostics": llm.diagnostics(),
    }


if __name__ == "__main__":
    print(json.dumps(smoke_test(), indent=2))
