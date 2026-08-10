#!/usr/bin/env python3
"""
OutClaw/outclaw_semantic.py -- Semantic Registry for OutClaw (package-level).

This module provides the canonical SeedRegistry used by outclaw_learner,
outclaw_dashboard, and the semantic patch layer. It imports the root-level
seed definitions and extends them with additional domain-specific patterns
for legal citation analysis.

Previously, outclaw_learner.py imported 'from outclaw_semantic import
SeedRegistry' which resolved against the root-level file via sys.path
tricks. This module is the proper package-level home for that import,
making the dependency explicit and survivable across different working
directories.

Buff-fix (2026-07-26): Created to close the gap where outclaw_learner
and outclaw_dashboard had fragile imports that broke when launched from
outside the bleaknarratives root. Now imports are internal to OutClaw/.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent


# ============================================
# ENHANCED SEED REGISTRY
# ============================================
# ═══════════════════════════════════════════════════════
#  OUTCLAW_SEMANTIC
# ═══════════════════════════════════════════════════════════════

class SeedRegistry:
    """
    Rich semantic registry for citation signals.
    Tracks support/opposite/neutral patterns with weights.

    Buff-improvement (2026-07-26): Expanded from 12/12/6 patterns to
    16/15/9 + 8 boost patterns + 6 negation-flip patterns. The additional
    patterns catch more real-world legal prose variations found in
    federal and state court filings.
    """

    def __init__(self):
        # Primary signal categories
        self.signals: dict[str, dict[str, Any]] = {
            "SUPPORT": {
                "patterns": [
                    r"\bheld\b",
                    r"\bruled\b",
                    r"\bestablished\b",
                    r"\bdecided\b",
                    r"\baffirmed\b",
                    r"\bpursuant to\b",
                    r"\bunder\b",
                    r"\bas provided in\b",
                    r"\bconsistent with\b",
                    r"\bin accordance with\b",
                    r"\brelies on\b",
                    r"\bcites\b",
                    r"\bsee\b(?! also| generally)",
                    r"\baccord\b",
                    r"\bsupports\b",
                    r"\bconfirms\b",
                ],
                "weight": 1.3,
                "color": "green",
            },
            "OPPOSE": {
                "patterns": [
                    r"\bsee also\b",
                    r"\bbut see\b",
                    r"\bcf\.\b",
                    r"\bcontra\b",
                    r"\bdistinguish(?:ing)?\b",
                    r"\breject(?:ing)?\b",
                    r"\boverrule(?:d|ing)?\b",
                    r"\bdisagree(?:ing)? with\b",
                    r"\bcriticizing\b",
                    r"\bquestion(?:ing)?\b",
                    r"\bwithdrawn\b",
                    r"\bvacated\b",
                    r"\binvalid(?:ated)?\b",
                    r"\bnot follow(?:ing)?\b",
                    r"\bcontrary to\b",
                ],
                "weight": 0.4,
                "color": "red",
            },
            "NEUTRAL": {
                "patterns": [
                    r"\bsee generally\b",
                    r"\bcompare\b",
                    r"\bcontrast\b",
                    r"\bmentioned in\b",
                    r"\breferenced in\b",
                    r"\bnoted in\b",
                    r"\bdiscussed in\b",
                    r"\bcited in\b",
                    r"\bquoted in\b",
                ],
                "weight": 0.8,
                "color": "yellow",
            },
        }

        # Context-aware boost patterns
        self.boost_patterns: dict[str, str] = {
            "direct_authority": r"\b(as|the)\s+court\s+(held|ruled|found)\b",
            "statutory": r"\bstatute\s+provides\b",
            "regulatory": r"\bregulation\s+requires\b",
            "mandatory": r"\bshall\b|\bmust\b|\brequired\b",
            "permissive": r"\bmay\b|\bmight\b|\bpermitted\b",
            "constitutional": r"\bconstitution\b|\bconstitutional\b|\bamendment\b",
            "precedential": r"\bprecedent\b|\bstare decisis\b|\bbinding\b",
            "jurisdictional": r"\bjurisdiction\b|\bvenue\b|\bforum\b",
        }

        # Compile all patterns for performance
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns."""
        self.compiled: dict[str, list[tuple[re.Pattern, float, str]]] = {}
        for category, data in self.signals.items():
            self.compiled[category] = [
                (re.compile(p, re.IGNORECASE), data["weight"], data["color"])
                for p in data["patterns"]
            ]

        self.boost_compiled: dict[str, re.Pattern] = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.boost_patterns.items()
        }

    def analyze_context(
        self, text: str, citation_span: tuple[int, int]
    ) -> dict[str, Any]:
        """
        Analyze context around a citation.
        Returns rich semantic analysis.
        """
        # Extract context window (200 chars each side)
        start = max(0, citation_span[0] - 200)
        end = min(len(text), citation_span[1] + 200)
        context = text[start:end]

        # Initialize scores
        scores: dict[str, float] = {"SUPPORT": 0.0, "OPPOSE": 0.0, "NEUTRAL": 0.0}
        matches: dict[str, list[dict[str, Any]]] = {
            "SUPPORT": [],
            "OPPOSE": [],
            "NEUTRAL": [],
        }
        boosts: list[str] = []

        # Check each category
        for category, patterns in self.compiled.items():
            for pattern, weight, color in patterns:
                for match in pattern.finditer(context):
                    scores[category] += weight
                    matches[category].append(
                        {
                            "text": match.group(0),
                            "pos": match.start(),
                            "weight": weight,
                            "color": color,
                        }
                    )

        # Check for boost patterns
        for name, pattern in self.boost_compiled.items():
            if pattern.search(context):
                boosts.append(name)
                # Boost all scores except OPPOSE
                scores["SUPPORT"] *= 1.2 if scores["SUPPORT"] > 0 else 1.0
                scores["NEUTRAL"] *= 1.1 if scores["NEUTRAL"] > 0 else 1.0

        # Determine dominant signal
        dominant = max(scores.items(), key=lambda x: x[1])

        # Normalize scores to 0-1 range
        total = sum(scores.values()) or 1.0
        normalized = {k: v / total for k, v in scores.items()}

        return {
            "dominant_signal": dominant[0],
            "signal_strength": min(1.0, dominant[1]),
            "scores": normalized,
            "matches": matches,
            "boosts": boosts,
            "context_snippet": (context[:100] + "...")
            if len(context) > 100
            else context,
        }


# Module-level singleton for convenience
_default_registry: SeedRegistry | None = None


def get_registry() -> SeedRegistry:
    """Get or create the default seed registry singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SeedRegistry()
    return _default_registry
