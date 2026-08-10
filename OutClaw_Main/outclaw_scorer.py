#!/usr/bin/env python3
"""
OutClaw/outclaw_scorer.py — Multi-Signal Audit Risk Scorer v1.1.

PREDICASE GEM + CODE JUDO ELEVATION (2026-07-26): Adapted from Predicase's
Combiner Brain, then elevated with:
  - Beautiful terminal risk dashboard (color-coded, emoji indicators)
  - Fix recommendations per finding (not just "something is wrong")
  - Trend tracking with delta computation
  - Pipe-friendly JSON output mode
  - Before/after comparison scoring
  - Severity-to-risk mapping with specific actionable guidance

Scoring matrix:
  EXISTENCE failure       → 30 pts (fabricated — maximum severity)
  NEGATIVE TREATMENT      → 25 pts (overruled cited as good law)
  OPPOSITE HOLDING         → 25 pts (cited for opposite of holding)
  MISQUOTE / OPPOSITE      → 20 pts (statute text inverted)
  NO SUPPORT               → 10 pts (real cite, unrelated to claim)
  Compound penalty         → 10 pts per extra HIGH finding
  Recovery via LLM         → -10 pts

Tiers: GREEN(0-24) YELLOW(25-49) ORANGE(50-74) RED(75-100)

Usage:
    python3 OutClaw/outclaw_scorer.py <report.json   # pipe in audit JSON
    python3 OutClaw/outclaw_scorer.py --dashboard     # beautiful terminal view
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# ANSI color palette — terminal judo
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════
#  OUTCLAW_SCORER
# ═══════════════════════════════════════════════════════════════

class Color:
    """Terminal color codes for beautiful output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_ORANGE = "\033[48;5;208m"
    BG_GRAY = "\033[48;5;236m"

    TIER_COLORS = {
        "GREEN": BRIGHT_GREEN,
        "YELLOW": BRIGHT_YELLOW,
        "ORANGE": "\033[38;5;208m",
        "RED": BRIGHT_RED,
    }
    TIER_BG = {
        "GREEN": BG_GREEN,
        "YELLOW": BG_YELLOW,
        "ORANGE": BG_ORANGE,
        "RED": BG_RED,
    }
    TIER_ICONS = {
        "GREEN": "✅",
        "YELLOW": "⚠️",
        "ORANGE": "🔶",
        "RED": "🚫",
    }

    @staticmethod
    def paint(text: str, color: str) -> str:
        return f"{color}{text}{Color.RESET}"

    @staticmethod
    def tier_badge(tier: str) -> str:
        icon = Color.TIER_ICONS.get(tier, "?")
        color = Color.TIER_COLORS.get(tier, Color.WHITE)
        return f"{color}{icon} {tier}{Color.RESET}"


# ---------------------------------------------------------------------------
# Scoring matrix
# ---------------------------------------------------------------------------

RULE_WEIGHTS: dict[str, int] = {
    "EXISTENCE": 30,
    "NEGATIVE TREATMENT": 25,
    "OPPOSITE HOLDING": 25,
    "MISQUOTE / OPPOSITE": 20,
    "NO SUPPORT": 10,
    "SUPPORTED": 0,
}

COMPOUND_PENALTY = 10
RECOVERY_DISCOUNT = 10

RISK_TIERS: list[tuple[int, str, str, str]] = [
    (
        0,
        "GREEN",
        "Safe to file",
        "All citations are properly supported. No judge-sanctionable issues detected.",
    ),
    (
        25,
        "YELLOW",
        "Review recommended",
        "Minor issues detected. Review before filing — a tangential citation could draw scrutiny.",
    ),
    (
        50,
        "ORANGE",
        "Do not file without revision",
        "Significant citation problems. A judge would likely notice and may sanction.",
    ),
    (
        75,
        "RED",
        "CRITICAL — Do not file",
        "Contains sanctionable citations. Filing this document risks judicial sanctions, adverse inferences, or Rule 11 penalties.",
    ),
]

FIX_RECOMMENDATIONS: dict[str, str] = {
    "EXISTENCE": "Remove this citation entirely or verify it against a real legal database (CourtListener, Google Scholar, Westlaw). A fabricated citation is the fastest path to sanctions.",
    "NEGATIVE TREATMENT": "This case has been overruled. Replace with the overruling authority or find a different case that supports your proposition. Check the seed registry for alternatives.",
    "OPPOSITE HOLDING": "This case holds the OPPOSITE of what you're citing it for. Either rephrase your argument to match the holding, or find a case that actually supports your claim.",
    "MISQUOTE / OPPOSITE": "This statute does not say what your filing claims it says. Read the actual statutory text (available in the seed registry) and revise your proposition.",
    "NO SUPPORT": "This citation is real but unrelated to your claim. Either connect it explicitly to your argument, or remove it and cite a more directly relevant authority.",
    "SUPPORTED": "Good citation — no changes needed.",
}

SEVERITY_ORDER = {"OK": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


# ---------------------------------------------------------------------------
# Risk result
# ---------------------------------------------------------------------------


@dataclass
class AuditRisk:
    score: int
    tier: str
    tier_label: str
    tier_description: str
    breakdown: dict[str, int]
    high_count: int
    medium_count: int
    ok_count: int
    total_findings: int
    llm_assisted: bool
    safe_to_file: bool
    recommendation: str
    fix_actions: list[str] = field(default_factory=list)
    scored_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "tier": self.tier,
            "tier_label": self.tier_label,
            "tier_description": self.tier_description,
            "breakdown": self.breakdown,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "ok_count": self.ok_count,
            "total_findings": self.total_findings,
            "llm_assisted": self.llm_assisted,
            "safe_to_file": self.safe_to_file,
            "recommendation": self.recommendation,
            "fix_actions": self.fix_actions,
        }


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class AuditRiskScorer:
    """Computes an Audit Risk Score from an OutClaw UnifiedReport."""

    def __init__(self):
        self._score_history: list[AuditRisk] = []

    def score_report(self, report: Any) -> AuditRisk:
        findings = self._extract_findings(report)
        breakdown: dict[str, int] = {rule: 0 for rule in RULE_WEIGHTS}
        high_count = 0
        medium_count = 0
        ok_count = 0
        llm_assisted = False
        fix_actions: list[str] = []
        seen_rules: set = set()

        for f in findings:
            rule = f.get("rule", "NO SUPPORT")
            severity = f.get("severity", "MEDIUM")

            if severity == "HIGH":
                high_count += 1
                if rule not in seen_rules:
                    fix_actions.append(
                        FIX_RECOMMENDATIONS.get(rule, "Review this citation.")
                    )
                    seen_rules.add(rule)
            elif severity == "MEDIUM":
                medium_count += 1
                if rule not in seen_rules:
                    fix_actions.append(
                        FIX_RECOMMENDATIONS.get(rule, "Review this citation.")
                    )
                    seen_rules.add(rule)
            elif severity == "OK":
                ok_count += 1

            if rule in breakdown:
                breakdown[rule] += 1
            if f.get("llm_assisted", False):
                llm_assisted = True

        # Compute weighted score
        score = 0
        for rule, count in breakdown.items():
            score += RULE_WEIGHTS.get(rule, 5) * count
        if high_count > 1:
            score += COMPOUND_PENALTY * (high_count - 1)
        if llm_assisted:
            score = max(0, score - RECOVERY_DISCOUNT)
        score = min(100, score)

        # Determine tier
        tier, tier_label, tier_desc = "GREEN", "Safe to file", ""
        for threshold, t, label, desc in reversed(RISK_TIERS):
            if score >= threshold:
                tier, tier_label, tier_desc = t, label, desc
                break

        safe = score < 50

        recommendation = f"{tier_label}. " + (
            f"{high_count} HIGH, {medium_count} MEDIUM, {ok_count} OK."
            if high_count or medium_count
            else "All citations properly supported."
        )

        result = AuditRisk(
            score=score,
            tier=tier,
            tier_label=tier_label,
            tier_description=tier_desc,
            breakdown=breakdown,
            high_count=high_count,
            medium_count=medium_count,
            ok_count=ok_count,
            total_findings=len(findings),
            llm_assisted=llm_assisted,
            safe_to_file=safe,
            recommendation=recommendation,
            fix_actions=fix_actions,
        )
        self._score_history.append(result)
        return result

    def score_dict(self, findings: list[dict[str, Any]]) -> AuditRisk:
        return self.score_report({"findings": findings})

    def history(self, n: int = 10) -> list[AuditRisk]:
        return self._score_history[-n:]

    def compare(self, before: AuditRisk, after: AuditRisk) -> dict[str, Any]:
        """Compare two scores — how much did the fix improve things?"""
        delta = before.score - after.score
        if delta > 0:
            verdict = f"Improved by {delta} points"
        elif delta < 0:
            verdict = f"Worsened by {abs(delta)} points"
        else:
            verdict = "No change"
        return {
            "before": before.score,
            "after": after.score,
            "delta": delta,
            "verdict": verdict,
            "before_tier": before.tier,
            "after_tier": after.tier,
            "tier_changed": before.tier != after.tier,
        }

    @staticmethod
    def _extract_findings(report: Any) -> list[dict[str, Any]]:
        if hasattr(report, "findings"):
            raw = report.findings
            if raw and hasattr(raw[0], "__dict__"):
                return [f.__dict__ for f in raw]
            return raw if raw else []
        if isinstance(report, dict):
            return report.get("findings", [])
        return []

    def quick_score(self, severity_counts: dict[str, int]) -> int:
        score = severity_counts.get("HIGH", 0) * RULE_WEIGHTS["EXISTENCE"]
        score += severity_counts.get("MEDIUM", 0) * RULE_WEIGHTS["NO SUPPORT"]
        if severity_counts.get("HIGH", 0) > 1:
            score += COMPOUND_PENALTY * (severity_counts["HIGH"] - 1)
        return min(100, score)


# ---------------------------------------------------------------------------
# Beautiful Terminal Dashboard — code judo centerpiece
# ---------------------------------------------------------------------------


def risk_bar(score: int, width: int = 40, colored: bool = True) -> str:
    """Render a color-coded risk bar."""
    filled = int(width * score / 100)
    empty = width - filled
    tier = (
        "RED"
        if score >= 75
        else "ORANGE"
        if score >= 50
        else "YELLOW"
        if score >= 25
        else "GREEN"
    )
    if colored:
        color = Color.TIER_COLORS.get(tier, Color.WHITE)
        bar = f"{color}{'█' * filled}{Color.DIM}{'░' * empty}{Color.RESET}"
    else:
        bar = f"{'█' * filled}{'░' * empty}"
    return f"{bar} {score}/100 {Color.tier_badge(tier) if colored else tier}"


def render_dashboard(
    risk: AuditRisk, findings_detail: list[dict[str, Any]] | None = None
) -> str:
    """Render a beautiful terminal dashboard for an audit risk assessment."""
    lines: list[str] = []

    # ── Header ──
    tier_color = Color.TIER_COLORS.get(risk.tier, Color.WHITE)
    icon = Color.TIER_ICONS.get(risk.tier, "?")

    lines.append("")
    lines.append(f"{tier_color}{Color.BOLD}╔{'═' * 68}╗{Color.RESET}")
    lines.append(
        f"{tier_color}{Color.BOLD}║{Color.RESET}  {icon}  {Color.BOLD}OUTCLAW AUDIT RISK DASHBOARD{Color.RESET}"
        + " " * 27
        + f"{tier_color}{Color.BOLD}║{Color.RESET}"
    )
    lines.append(f"{tier_color}{Color.BOLD}╚{'═' * 68}╝{Color.RESET}")
    lines.append("")

    # ── Risk score with bar ──
    lines.append(
        f"  {Color.BOLD}Risk Score:{Color.RESET}  {risk_bar(risk.score, width=42)}"
    )
    lines.append(
        f"  {Color.BOLD}Tier:{Color.RESET}        {Color.tier_badge(risk.tier)}  —  {risk.tier_label}"
    )
    lines.append(
        f"  {Color.BOLD}Safe to file:{Color.RESET}  {Color.GREEN}✓ YES{Color.RESET}"
        if risk.safe_to_file
        else f"  {Color.BOLD}Safe to file:{Color.RESET}  {Color.RED}✗ NO{Color.RESET}"
    )
    lines.append("")

    # ── Finding counts ──
    lines.append(f"  {Color.BOLD}Findings:{Color.RESET}")
    lines.append(
        f"    {Color.BRIGHT_RED}● HIGH:   {risk.high_count:>3}{Color.RESET}    {Color.BRIGHT_YELLOW}● MEDIUM: {risk.medium_count:>3}{Color.RESET}    {Color.BRIGHT_GREEN}● OK:     {risk.ok_count:>3}{Color.RESET}"
    )
    lines.append("")

    # ── Breakdown by rule ──
    if any(v > 0 for v in risk.breakdown.values()):
        lines.append(f"  {Color.BOLD}Breakdown:{Color.RESET}")
        for rule, count in risk.breakdown.items():
            if count > 0:
                weight = RULE_WEIGHTS.get(rule, 0)
                bar_w = min(20, count * 5)
                bar_filled = "▓" * bar_w
                color = Color.RED if rule != "SUPPORTED" else Color.GREEN
                lines.append(
                    f"    {color}{bar_filled:<20}{Color.RESET}  {rule:<22} x{count}  ({weight}pts each)"
                )
        lines.append("")

    # ── Fix actions ──
    if risk.fix_actions:
        lines.append(
            f"  {Color.BOLD}{Color.BRIGHT_YELLOW}🔧  FIX ACTIONS:{Color.RESET}"
        )
        for i, action in enumerate(risk.fix_actions, 1):
            lines.append(f"    {Color.CYAN}{i}.{Color.RESET} {action}")
        lines.append("")

    # ── Detailed findings (if provided) ──
    if findings_detail:
        lines.append(f"  {Color.BOLD}Citation Details:{Color.RESET}")
        for f in findings_detail:
            sev = f.get("severity", "OK")
            icon_s = "!!" if sev == "HIGH" else "??" if sev == "MEDIUM" else "✓"
            color = (
                Color.RED
                if sev == "HIGH"
                else Color.YELLOW
                if sev == "MEDIUM"
                else Color.GREEN
            )
            cit = f.get("citation", "?")
            rule = f.get("rule", "?")
            detail = f.get("detail", "")[:100]
            lines.append(
                f"    {color}[{icon_s}]{Color.RESET} {Color.BOLD}{cit}{Color.RESET}  {Color.DIM}{rule}{Color.RESET}"
            )
            if detail:
                lines.append(f"        {Color.DIM}{detail}{Color.RESET}")
            if f.get("llm_assisted"):
                lines.append(
                    f"        {Color.MAGENTA}🤖 LLM-verified classification{Color.RESET}"
                )
            if f.get("recovered_by_window"):
                lines.append(
                    f"        {Color.CYAN}↻ Recovered via sentence-window context{Color.RESET}"
                )
        lines.append("")

    # ── Footer ──
    lines.append(
        f"  {Color.DIM}Scored at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(risk.scored_at))}{Color.RESET}"
    )
    if risk.llm_assisted:
        lines.append(
            f"  {Color.MAGENTA}🤖 LLM-assisted classifications present — uncertainty discounted{Color.RESET}"
        )
    lines.append("")

    return "\n".join(lines)


def render_comparison(before: AuditRisk, after: AuditRisk) -> str:
    """Render a before/after comparison dashboard."""
    delta = before.score - after.score
    arrow = "↓" if delta > 0 else "↑" if delta < 0 else "→"
    color = Color.GREEN if delta > 0 else Color.RED if delta < 0 else Color.YELLOW

    lines = [
        "",
        f"{Color.BOLD}╔{'═' * 68}╗{Color.RESET}",
        f"{Color.BOLD}║{Color.RESET}  📊  {Color.BOLD}OUTCLAW RISK COMPARISON — Before & After{Color.RESET}"
        + " " * 10
        + f"{Color.BOLD}║{Color.RESET}",
        f"{Color.BOLD}╚{'═' * 68}╝{Color.RESET}",
        "",
        f"  {Color.DIM}BEFORE:{Color.RESET}  {risk_bar(before.score, width=30)}  ({before.tier})",
        f"  {Color.DIM}AFTER: {Color.RESET}  {risk_bar(after.score, width=30)}  ({after.tier})",
        f"  {Color.BOLD}DELTA:{Color.RESET}   {color}{arrow} {abs(delta)} points{Color.RESET}  {'🎉 Improvement!' if delta > 0 else '⚠️  Regression' if delta < 0 else '— No change'}",
        "",
        f"  HIGH:   {before.high_count} → {after.high_count}   MEDIUM: {before.medium_count} → {after.medium_count}   OK: {before.ok_count} → {after.ok_count}",
        f"  Tier:   {Color.TIER_COLORS.get(before.tier, '')}{before.tier}{Color.RESET} → {Color.TIER_COLORS.get(after.tier, '')}{after.tier}{Color.RESET}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def score_audit(report: Any) -> AuditRisk:
    return AuditRiskScorer().score_report(report)


def dashboard_from_report(report: Any) -> str:
    """One-liner: score a report and render a dashboard."""
    scorer = AuditRiskScorer()
    risk = scorer.score_report(report)
    findings = scorer._extract_findings(report)
    return render_dashboard(risk, findings)


# ---------------------------------------------------------------------------
# CLI — pipe-friendly
# ---------------------------------------------------------------------------


def _cli_main() -> int:
    """CLI entry: read JSON from stdin or file, render dashboard."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="outclaw-scorer", description="OutClaw Audit Risk Scorer"
    )
    parser.add_argument(
        "input", nargs="?", help="JSON report file (or stdin if omitted)"
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        default=True,
        help="Render dashboard (default)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON instead of dashboard"
    )
    parser.add_argument("--bare", action="store_true", help="Score only, no formatting")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="Compare two report JSON files",
    )
    args = parser.parse_args()

    # Comparison mode
    if args.compare:
        with open(args.compare[0]) as f:
            before_data = json.load(f)
        with open(args.compare[1]) as f:
            after_data = json.load(f)
        scorer = AuditRiskScorer()
        before = scorer.score_report(before_data)
        after = scorer.score_report(after_data)
        print(render_comparison(before, after))
        return 0

    # Load input
    if args.input:
        with open(args.input) as f:
            data = json.load(f)
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
    else:
        # Smoke test with sample findings
        data = {
            "findings": [
                {
                    "rule": "EXISTENCE",
                    "severity": "HIGH",
                    "citation": "99 U.S.C. § 9999",
                    "detail": "Not in registry.",
                },
                {
                    "rule": "NO SUPPORT",
                    "severity": "MEDIUM",
                    "citation": "18 U.S.C. § 2511",
                    "detail": "Unrelated.",
                },
                {
                    "rule": "SUPPORTED",
                    "severity": "OK",
                    "citation": "42 U.S.C. § 1983",
                    "detail": "Correct.",
                },
            ]
        }

    scorer = AuditRiskScorer()
    risk = scorer.score_report(data)

    if args.json:
        print(json.dumps(risk.to_dict(), indent=2))
    elif args.bare:
        print(f"{risk.score}/100 {risk.tier}")
    else:
        findings = scorer._extract_findings(data)
        print(render_dashboard(risk, findings))

    return 0 if risk.safe_to_file else 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
