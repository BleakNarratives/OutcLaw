#!/usr/bin/env python3
"""
OutClaw/outclaw_aura.py — Aura Scout Bridge for OutClaw.

LWM INTEGRATION (2026-07-26): Bridges the Aura Scout's 7-category pattern
recognition database into OutClaw's audit pipeline. OutClaw catches bad
citations; Aura catches bad patterns. Together: complete legal audit surface.

Pattern categories (extracted from legal-scout/scripts/aura_scout.py):
  1. financial_misconduct — embezzlement, kickbacks, fraudulent billing
  2. procedural_violations — circumventing protocols, regulatory breaches
  3. abuse_of_power — exceeding authority, intimidation, retaliation
  4. transparency_issues — concealment, redaction abuse, FOIA obstruction
  5. civil_rights_violations — discrimination, excessive force, profiling
  6. judicial_misconduct — bias, ex parte communication, improper recusal
  7. rico_patterns — organized crime, racketeering, systematic corruption

Usage:
    from OutClaw.outclaw_aura import AuraBridge

    bridge = AuraBridge()
    findings = bridge.scan_text(legal_document_text)
    for f in findings:
        print(f"  [{f['severity']}] {f['category']}: {f['context'][:80]}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Pattern Database — extracted from aura_scout.py
# ---------------------------------------------------------------------------

PATTERN_DATABASE: dict[str, dict[str, Any]] = {
    "financial_misconduct": {
        "label": "Financial Misconduct",
        "severity": "HIGH",
        "description": "Misappropriation of funds, embezzlement, fraudulent billing, kickbacks",
        "patterns": [
            r"(?:misappropriat(?:e|ed|ion)|embezzl(?:e|ed|ement))\s+(?:of\s+)?(?:funds|money|resources)",
            r"(?:divert(?:ed|ing)?|redirect(?:ed|ing)?)\s+(?:funds|money|resources)",
            r"(?:fraudulent|improper|suspicious)\s+(?:billing|invoic(?:e|ing)|reimbursement)",
            r"(?:kickback|bribe|payoff|slush\s+fund)",
            r"conflict\s+of\s+interest",
        ],
    },
    "procedural_violations": {
        "label": "Procedural Violations",
        "severity": "MEDIUM",
        "description": "Violations of established protocols, procedures, or regulations",
        "patterns": [
            r"(?:violat(?:e|ed|ion)|breach(?:ed)?)\s+(?:of\s+)?(?:protocol|procedure|policy|regulation)",
            r"(?:circumvent(?:ed|ing)?|bypass(?:ed|ing)?)\s+(?:protocol|procedure|policy|regulation|oversight)",
            r"(?:fail(?:ed|ure)|neglect(?:ed)?)\s+to\s+(?:follow|adhere\s+to|comply\s+with)",
            r"(?:irregular|improper|unauthorized)\s+(?:approval|authorization|process)",
        ],
    },
    "abuse_of_power": {
        "label": "Abuse of Power",
        "severity": "HIGH",
        "description": "Misuse of authority, exceeding jurisdiction, intimidation",
        "patterns": [
            r"(?:abuse|misuse|exploit(?:ation)?)\s+(?:of\s+)?(?:power|authority|position|office)",
            r"(?:exceed(?:ed|ing)?|overstep(?:ped|ping)?)\s+(?:authority|jurisdiction|power)",
            r"(?:pressure|coerce|intimidate|threaten)\s+(?:subordinate|employee|witness|victim)",
            r"(?:retaliat(?:e|ed|ion)|revenge)\s+(?:against|toward)?",
        ],
    },
    "transparency_issues": {
        "label": "Transparency / Concealment",
        "severity": "MEDIUM",
        "description": "Concealment of information, misleading statements, obstruction",
        "patterns": [
            r"(?:conceal(?:ed|ing|ment)?|hide|hiding|cover(?:\s*up|ed\s*up)|obscur(?:e|ed|ing))\s+(?:information|data|evidence|document|fact)",
            r"(?:mislead(?:ing)?|deceiv(?:e|ed|ing)|misrepresent(?:ed|ing|ation))\s+(?:public|oversight|committee|investigator)",
            r"(?:refus(?:e|ed|al)|declin(?:e|ed))\s+to\s+(?:disclose|reveal|provide|share)",
            r"(?:redact(?:ed|ion)|censor(?:ed|ship)|withh(?:o|e)ld(?:ing)?)\s+(?:information|data|evidence|document)",
        ],
    },
    "civil_rights_violations": {
        "label": "Civil Rights Violations",
        "severity": "HIGH",
        "description": "Discrimination, excessive force, constitutional violations",
        "patterns": [
            r"(?:violat(?:e|ed|ion)|infring(?:e|ed|ement))\s+(?:of\s+)?(?:civil|constitutional|human)\s+rights",
            r"(?:discriminat(?:e|ed|ion|ory)|bias(?:ed)?)\s+(?:treatment|action|policy|practice)",
            r"(?:racial|ethnic|gender|religious|age)\s+(?:profiling|discrimination|bias)",
            r"(?:excessive|unreasonable|disproportionate)\s+(?:force|violence|response)",
        ],
    },
    "judicial_misconduct": {
        "label": "Judicial Misconduct",
        "severity": "HIGH",
        "description": "Judicial bias, ex parte communication, improper recusal",
        "patterns": [
            r"(?:judicial|judge)\s+(?:misconduct|impropriety|bias|prejudice)",
            r"(?:ex\s+parte|private)\s+(?:communication|meeting|discussion)",
            r"(?:conflict|appearance)\s+of\s+interest",
            r"(?:improper|inappropriate)\s+(?:recusal|failure\s+to\s+recuse)",
            r"(?:prejudicial|biased|unfair)\s+(?:ruling|decision|judgment|treatment)",
        ],
    },
    "rico_patterns": {
        "label": "RICO / Organized Crime",
        "severity": "HIGH",
        "description": "Pattern of organized criminal activity, racketeering",
        "patterns": [
            r"(?:pattern|history|series)\s+of\s+(?:criminal|illegal|unlawful)\s+(?:activity|conduct|behavior)",
            r"(?:organiz(?:ed|ation)|structur(?:ed|e)|systemat(?:ic|ized))\s+(?:criminal|illegal|unlawful)",
            r"(?:racketeer(?:ing)?|extortion|blackmail|protection\s+racket)",
            r"(?:criminal|illegal)\s+(?:enterprise|syndicate|organization|network)",
            r"(?:conspiracy|collusion|collaboration)\s+to\s+(?:commit|engage\s+in|perform)",
        ],
    },
}

# Compile all patterns for performance
COMPILED_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {}
for cat, data in PATTERN_DATABASE.items():
    COMPILED_PATTERNS[cat] = [
        (re.compile(p, re.IGNORECASE), data["severity"]) for p in data["patterns"]
    ]

# Lightweight label lookup for CLI / external consumers
AURA_LABELS: dict[str, str] = {
    cat: data["label"] for cat, data in PATTERN_DATABASE.items()
}


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


@dataclass
# ═══════════════════════════════════════════════════════
#  OUTCLAW_AURA
# ═══════════════════════════════════════════════════════════════

class AuraFinding:
    category: str
    label: str
    severity: str
    matched_text: str
    context: str
    pattern: str
    start_pos: int
    end_pos: int


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class AuraBridge:
    """
    Bridges Aura Scout pattern recognition into OutClaw's audit pipeline.

    Scans legal text for 7 categories of misconduct patterns and returns
    findings compatible with OutClaw's UnifiedReport format.
    """

    def __init__(self):
        self._findings: list[AuraFinding] = []
        self._pattern_hits: dict[str, int] = {cat: 0 for cat in PATTERN_DATABASE}

    def scan_text(self, text: str) -> list[dict[str, Any]]:
        """Scan text for all 7 categories of misconduct patterns."""
        self._findings = []
        self._pattern_hits = {cat: 0 for cat in PATTERN_DATABASE}

        for category, patterns in COMPILED_PATTERNS.items():
            for pattern, severity in patterns:
                for match in pattern.finditer(text):
                    context = self._get_context(text, match.start(), match.end())
                    finding = AuraFinding(
                        category=category,
                        label=PATTERN_DATABASE[category]["label"],
                        severity=severity,
                        matched_text=match.group(0),
                        context=context,
                        pattern=pattern.pattern,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                    self._findings.append(finding)
                    self._pattern_hits[category] += 1

        return self.to_dicts()

    def to_dicts(self) -> list[dict[str, Any]]:
        """Convert findings to dicts compatible with OutClaw report format."""
        return [
            {
                "category": f.category,
                "label": f.label,
                "severity": f.severity,
                "matched_text": f.matched_text,
                "context": f.context[:120],
                "start_pos": f.start_pos,
                "end_pos": f.end_pos,
            }
            for f in self._findings
        ]

    def summary(self) -> dict[str, Any]:
        """Return summary counts by category."""
        total = sum(self._pattern_hits.values())
        return {
            "total_aura_findings": total,
            "by_category": dict(self._pattern_hits),
            "high_count": sum(
                count
                for cat, count in self._pattern_hits.items()
                if PATTERN_DATABASE[cat]["severity"] == "HIGH"
            ),
            "categories_triggered": sum(
                1 for v in self._pattern_hits.values() if v > 0
            ),
        }

    @staticmethod
    def _get_context(text: str, start: int, end: int, window: int = 80) -> str:
        """Extract context around a match."""
        ctx_start = max(0, start - window)
        ctx_end = min(len(text), end + window)
        return text[ctx_start:ctx_end].replace("\n", " ").strip()


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def scan_for_misconduct(text: str) -> dict[str, Any]:
    """One-liner: scan text and return findings + summary."""
    bridge = AuraBridge()
    findings = bridge.scan_text(text)
    return {
        "findings": findings,
        "summary": bridge.summary(),
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = """
    The judge engaged in ex parte communications with opposing counsel.
    County officials diverted funds from the public health budget for personal use.
    The officer used excessive force during the arrest and then concealed the body camera footage.
    There is a pattern of criminal activity coordinated across multiple agencies.
    """
    bridge = AuraBridge()
    findings = bridge.scan_text(sample)
    summary = bridge.summary()

    print(
        f"Found {summary['total_aura_findings']} pattern hits across {summary['categories_triggered']} categories:"
    )
    for cat, count in summary["by_category"].items():
        if count > 0:
            print(
                f"  {PATTERN_DATABASE[cat]['label']}: {count} ({PATTERN_DATABASE[cat]['severity']})"
            )

    print(f"\nHIGH severity: {summary['high_count']}")
    if findings:
        print("\nSample findings:")
        for f in findings[:5]:
            print(f'  [{f["severity"]}] {f["label"]}: "{f["matched_text"][:60]}..."')
