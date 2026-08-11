#!/usr/bin/env python3
"""
outclaw_cli.py — OutClaw Command-Line Interface v0.3.

CODE JUDO ELEVATION (2026-07-26): New subcommands chain the full stack:
  audit     — run audit + risk dashboard (+ optional LLM)
  score     — standalone risk dashboard from a report file
  lookup    — CourtListener citation lookup (Predicase gem)
  discover  — scan for undiscovered citations (Predicase gem)
  enhance   — FULL PIPELINE: audit → LLM → score → discover
  regression — conformance suite
  safe-draft — DRAFT-block chain
  demo      — self-rep litigant use cases

Subcommands
-----------

  audit <text-file>
      Run the unified orchestrator on a file. Prints the risk dashboard
      (beautiful terminal output) by default. Pass --json for raw JSON.

  score <report.json>
      Render the risk dashboard from a previously-saved audit report.
      Pipe-friendly: outclaw audit file.txt --json | outclaw score -

  lookup <citation>
      Look up a citation in CourtListener (requires internet).
      Example: outclaw lookup "384 U.S. 436"

  discover <text-file>
      Scan for undiscovered citations not yet in the seed registry.
      Pass --dir to scan a directory of legal texts.

  enhance <text-file>
      The full code-judo pipeline: audit + LLM assist + risk dashboard +
      discovery scan. The one command a self-rep litigant needs before
      submitting any filing to a judge.

  regression
      Run the conformance regression suite.

  safe-draft <intent> <text-file>
      Full DRAFT-block chain: audit + ack_token + safe_generate_document.

  demo
      Run self-represented litigant use cases end-to-end.

  cascade status
      Show the stair-stepped model ladder: which free providers are
      configured (keys present), which tiers/models are live, cache stats.

  cascade test "<prompt>" [--task opposite_holding]
      Fire one prompt through the cascade and print the escalation trail
      (which tier/provider/model served it). Requires OUTCLAW_CASCADE=1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import outclaw_regression as regression  # type: ignore
import outclaw_safety as safety  # type: ignore
import outclaw_unified as unified  # type: ignore
import outclaw_use_cases as use_cases  # type: ignore

# Shared jurisdiction detection: jurisdiction is a FACT of the case and is
# auto-detected from case text when nothing pinned it explicitly.
try:
    from jurisdiction import detect_jurisdiction  # type: ignore
except ImportError:  # imported as OutClaw.outclaw_cli from repo root
    detect_jurisdiction = None  # type: ignore

# ── ANSI helpers (inline to keep CLI self-contained) ──


def _c(code: str, text: str) -> str:
    return f"{code}{text}\033[0m"


_R = "\033[0m"
B = "\033[1m"
D = "\033[2m"
R = "\033[31m"
G = "\033[32m"
Y = "\033[33m"
C = "\033[36m"
M = "\033[35m"
W = "\033[37m"
BR = "\033[91m"
BG = "\033[92m"
BY = "\033[93m"


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Text file not found: {path}")
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except ImportError:
            raise ImportError("pypdf is required to read PDF files. Run 'pip install pypdf'")
    return path.read_text(encoding="utf-8")


def _load_case_profile(profile_path: str | None) -> dict:
    """Load a case profile (case_context.json) or return {}.

    A case profile pins every downstream command to one jurisdiction/case
    (defendant, court, judge, prosecutor, statutes) so results never drift
    to other states. See case_context.json.
    """
    if not profile_path:
        return {}
    p = Path(profile_path)
    if not p.exists() and not p.is_absolute():
        # Fall back to the CLI's own directory so the default profile
        # resolves even when run from another working directory.
        alt = Path(__file__).resolve().parent / p
        if alt.exists():
            p = alt
    if not p.exists():
        raise FileNotFoundError(f"Case profile not found: {profile_path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _resolve_profile_path(args: argparse.Namespace) -> str | None:
    """Profile path for THIS run, in precedence order:
    1. explicit --profile
    2. OUTCLAW_CASE env var (validated — warns loudly if it can't be loaded,
       so a stale env var can never silently unpin a run)
    3. nearest case_context.json above the cwd (workspace auto-load)
    Returns None when nothing applies."""
    explicit = getattr(args, "profile", None)
    if explicit:
        return explicit
    env_case = os.environ.get("OUTCLAW_CASE", "").strip()
    if env_case:
        env_path = Path(env_case)
        if env_path.exists() or (_HERE / env_case).exists():
            print(
                f"  {C}Profile from OUTCLAW_CASE:{_R} {env_case}",
                file=sys.stderr,
            )
            return env_case
        print(
            f"  {R}⚠ OUTCLAW_CASE is set but profile not found:{_R} {env_case} "
            f"— fix the path or unset OUTCLAW_CASE. This run is NOT pinned.",
            file=sys.stderr,
        )
        return None
    try:
        from jurisdiction import find_workspace_profile  # type: ignore
    except ImportError:
        return None
    found = find_workspace_profile(Path(__file__).resolve().parent)
    if found:
        print(
            f"  {C}Profile auto-loaded:{_R} {found} "
            f"(cwd is inside this case workspace)",
            file=sys.stderr,
        )
    return found


def _profile_state(args: argparse.Namespace) -> str | None:
    """State/jurisdiction pinned by the run's case profile (if any).
    Used as a fallback for commands that take --state/--jurisdiction."""
    path = _resolve_profile_path(args)
    if not path:
        return None
    try:
        profile = _load_case_profile(path)
    except FileNotFoundError:
        return None
    jur = (profile.get("research", {}).get("jurisdiction") or "").lower()
    return jur if jur in ("kansas", "oklahoma") else None


# ═══════════════════════════════════════════════════════════════
# AUDIT  —  enhanced with risk dashboard
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  AUDIT
# ═══════════════════════════════════════════════════════════════

def _apply_cascade(args: argparse.Namespace) -> None:
    """Turn on the stair-stepped cascade when --cascade passed.

    IMPORTANT: --cascade must also enable use_llm -- the cascade classification
    branch in the orchestrator is only reached when use_llm=True. Without this,
    `outclaw audit --cascade` would silently do nothing.
    """
    if getattr(args, "cascade", False):
        os.environ["OUTCLAW_CASCADE"] = "1"
        args.llm = True
        # stderr, not stdout: `--json` output must stay parseable when piped.
        print(f"  {D}Model cascade: ON (free cloud tiers){_R}", file=sys.stderr)


def cmd_audit(args: argparse.Namespace) -> int:
    text = _read_text(args.text_file)
    started = time.time()
    _apply_cascade(args)
    report = unified.audit_text(text, use_llm=args.llm, auto_escalate=args.auto_escalate)
    elapsed = (time.time() - started) * 1000
    summary = report.summary

    is_safe = summary["safe_to_draft"]
    if args.strict_high:
        is_safe = all(f.severity != unified.HIGH for f in report.findings)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if is_safe else 2

    # ── Beautiful audit output ──
    risk = None
    try:
        from OutClaw.outclaw_scorer import (  # type: ignore
            AuditRiskScorer,
            render_dashboard,
        )

        scorer = AuditRiskScorer()
        risk = scorer.score_report(report)
        findings_detail = (
            [f.__dict__ for f in report.findings] if report.findings else []
        )
        print(render_dashboard(risk, findings_detail))
    except Exception:
        # Fallback to basic summary
        _print_basic_summary(report, args.text_file)

    # Footer
    escalate_status = "AUTO-ESCALATE" if args.auto_escalate else ("ON" if args.llm else "OFF")
    print(
        f"  {D}File: {args.text_file}  │  Elapsed: {elapsed:.0f}ms  │  "
        f"LLM: {escalate_status}{_R}"
    )
    print()

    return 0 if is_safe else 2


def _print_basic_summary(report, path):
    s = report.summary
    print(f"{B}OutClaw audit:{_R} {path}")
    print(f"  Severity: {s['severity_counts']}")
    print(f"  Safe: {s['safe_to_draft']}")
    if report.findings:
        for f in report.findings:
            tag = (
                "!!"
                if f.severity == unified.HIGH
                else "??"
                if f.severity == unified.MEDIUM
                else "ok"
            )
            print(f"    [{tag}] {f.citation}  {f.rule}")


# ═══════════════════════════════════════════════════════════════
# SCORE  —  standalone risk dashboard from a report file
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  SCORE
# ═══════════════════════════════════════════════════════════════

def cmd_score(args: argparse.Namespace) -> int:
    # Load report
    if str(args.report) == "-":
        data = json.load(sys.stdin)
    else:
        with open(args.report) as f:
            data = json.load(f)

    try:
        from OutClaw.outclaw_scorer import (  # type: ignore
            AuditRiskScorer,
            render_comparison,
            render_dashboard,
        )
    except Exception as e:
        print(f"{R}Scorer unavailable: {e}{_R}", file=sys.stderr)
        return 2

    scorer = AuditRiskScorer()
    risk = scorer.score_report(data)
    findings = data.get("findings", [])
    print(render_dashboard(risk, findings))

    # If comparing
    if args.compare:
        with open(args.compare) as f:
            before_data = json.load(f)
        before = scorer.score_report(before_data)
        print(render_comparison(before, risk))

    return 0 if risk.safe_to_file else 1


# ═══════════════════════════════════════════════════════════════
# LOOKUP  —  CourtListener citation lookup (Predicase gem)
# ═══════════════════════════════════════════════════════════════


def cmd_lookup(args: argparse.Namespace) -> int:
    citation = args.citation.strip()
    print(f"\n{B}🔍 OutClaw Lookup:{_R} {_c(C, citation)}")
    print()

    try:
        from OutClaw.outclaw_courtlistener import CourtListenerScout  # type: ignore

        scout = CourtListenerScout()
        print(f"  {D}Querying CourtListener API (Free Law Project)...{_R}")
        result = scout.lookup_citation(citation)

        if result is None:
            print(
                f"  {Y}⚠  Not found{_R} — citation not in CourtListener or API unreachable."
            )
            print(
                f"  {D}Check: https://www.courtlistener.com/?q={citation.replace(' ', '%20')}{_R}"
            )
            return 1

        print(f"  {G}✓ Found{_R}")
        print(f"  {B}Case:{_R}       {result.get('name', citation)}")
        print(f"  {B}Court:{_R}      {result.get('court', 'Unknown')}")
        print(f"  {B}Date:{_R}       {result.get('date_filed', 'Unknown')}")
        print(f"  {B}Area:{_R}       {result.get('area', 'general')}")
        print(f"  {B}Overruled:{_R}  {'Yes ⚠️' if result.get('overruled') else 'No'}")
        holding = result.get("holding", "")
        if holding:
            print(
                f"  {B}Holding:{_R}    {holding[:200]}{'...' if len(holding) > 200 else ''}"
            )
        print()

        # Offer to expand seed
        if args.expand:
            added = scout.expand_seed_registry(result)
            if added:
                print(f"  {G}✓ Added to seed registry!{_R}")
            else:
                print(f"  {D}Already in seed registry.{_R}")

        return 0
    except Exception as e:
        print(f"  {R}✗ Lookup failed:{_R} {e}")
        return 2


# ═══════════════════════════════════════════════════════════════
# DISCOVER  —  scan for undiscovered citations (Predicase gem)
# ═══════════════════════════════════════════════════════════════


def cmd_discover(args: argparse.Namespace) -> int:
    from OutClaw.outclaw_discover import DiscoveryEngine  # type: ignore

    engine = DiscoveryEngine()

    if args.dir:
        print(f"\n{B}🔎 OutClaw Discover:{_R} scanning {_c(C, args.dir)}")
        result = engine.scan_corpus(args.dir)
        discoveries = result.get("discoveries", [])
        print(f"  {D}Scanned {result.get('files_scanned', 0)} files{_R}")
    else:
        text = _read_text(args.text_file)
        print(f"\n{B}🔎 OutClaw Discover:{_R} scanning {_c(C, str(args.text_file))}")
        discoveries = engine.scan_text(text, source=str(args.text_file))

    # Group by confidence
    high = [d for d in discoveries if d["confidence"] >= 0.7]
    medium = [d for d in discoveries if 0.4 <= d["confidence"] < 0.7]
    low = [d for d in discoveries if d["confidence"] < 0.4]

    print(f"  {G}HIGH confidence:{_R}   {len(high)}")
    print(f"  {Y}MEDIUM confidence:{_R} {len(medium)}")
    print(f"  {D}LOW confidence:{_R}    {len(low)}")
    print()

    if high:
        print(f"  {B}Top discoveries:{_R}")
        for d in high[:10]:
            print(
                f"    {G}●{_R} {_c(B, d['citation']):<30} {D}{d['type']:<15}{_R} conf={d['confidence']:.2f}"
            )
            if d.get("proposition"):
                print(f'      {D}"{d["proposition"][:80]}..."{_R}')
        print()

    if not discoveries:
        print(f"  {D}No new citations discovered — seed registry covers this text.{_R}")
        print()

    print(
        f"  {D}Pending review: {len(engine.pending_review())}  │  Review discoveries with: outclaw discover <file>{_R}"
    )
    return 0


# ═══════════════════════════════════════════════════════════════
# ENHANCE  —  full pipeline: audit + LLM + score + discover
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  ENHANCE — full pipeline
# ═══════════════════════════════════════════════════════════════

def cmd_enhance(args: argparse.Namespace) -> int:
    text = _read_text(args.text_file)
    _apply_cascade(args)

    print(f"\n{B}{'═' * 70}{_R}")
    print(f"{B}  🦅  OUTCLAW ENHANCE — Full Pipeline{_R}")
    print(f"{B}{'═' * 70}{_R}")
    print(f"  {D}File: {args.text_file}{_R}")
    print(f"  {D}LLM:  {'ON (cloud cascade)' if args.llm else 'OFF'}{_R}")
    print(f"  {D}Cascade: {'ON' if getattr(args, 'cascade', False) else 'OFF'}{_R}")
    print()

    total_started = time.time()

    # ── Stage 1: Audit ──
    print(f"  {B}[1/3]{_R} {C}Running citation audit...{_R}")
    t1 = time.time()
    report = unified.audit_text(text, use_llm=args.llm, auto_escalate=args.auto_escalate)
    audit_ms = (time.time() - t1) * 1000
    print(f"       {D}Done in {audit_ms:.0f}ms — {len(report.findings)} finding(s){_R}")

    # ── Stage 2: Risk Score Dashboard ──
    print(f"  {B}[2/3]{_R} {C}Computing risk score...{_R}")
    try:
        from OutClaw.outclaw_scorer import (  # type: ignore
            AuditRiskScorer,
            render_dashboard,
        )

        scorer = AuditRiskScorer()
        risk = scorer.score_report(report)
        findings_detail = (
            [f.__dict__ for f in report.findings] if report.findings else []
        )
        print(f"       {D}Risk: {risk.score}/100 ({risk.tier}){_R}")
        print()
        print(render_dashboard(risk, findings_detail))
    except Exception as e:
        print(f"  {Y}⚠  Scorer unavailable: {e}{_R}")
        # Create a minimal risk for the footer
        from dataclasses import dataclass, field

        @dataclass
        class _FallbackRisk:
            score: int = 50
            tier: str = "ORANGE"
            safe_to_file: bool = False
            fix_actions: list = field(default_factory=list)

        risk = _FallbackRisk()

    # ── Stage 3: Discovery ──
    print(f"  {B}[3/3]{_R} {C}Scanning for undiscovered citations...{_R}")
    try:
        from OutClaw.outclaw_discover import DiscoveryEngine  # type: ignore

        engine = DiscoveryEngine()
        discoveries = engine.scan_text(text, source=str(args.text_file))
        high_disc = [d for d in discoveries if d["confidence"] >= 0.7]

        if high_disc:
            print(f"       {G}Found {len(high_disc)} high-confidence new citations{_R}")
            for d in high_disc[:5]:
                print(
                    f"         {G}●{_R} {_c(B, d['citation'])} {D}({d['type']}, conf={d['confidence']:.2f}){_R}"
                )
        else:
            print(f"       {D}No new citations discovered.{_R}")
    except Exception as e:
        print(f"  {Y}⚠  Discovery engine unavailable: {e}{_R}")

    total_ms = (time.time() - total_started) * 1000

    # ── Footer ──
    print()
    print(f"  {B}{'─' * 70}{_R}")
    print(f"  {B}Pipeline complete{_R} in {total_ms:.0f}ms")
    print(
        f"  {B}Verdict:{_R}        {'✅ SAFE TO FILE' if risk.safe_to_file else '🚫 DO NOT FILE — fix citations first'}"
    )
    if not risk.safe_to_file and risk.fix_actions:
        print(f"  {B}Fix actions:{_R}     {len(risk.fix_actions)} issue(s) to resolve")
        for a in risk.fix_actions[:3]:
            print(f"    {Y}→{_R} {a[:100]}...")
    print(f"  {B}{'─' * 70}{_R}")
    print()

    return 0 if risk.safe_to_file else 1


# ═══════════════════════════════════════════════════════════════
# FULL-AUDIT  —  LWM-integrated complete pipeline
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  FULL AUDIT — LWM pipeline
# ═══════════════════════════════════════════════════════════════

def cmd_full_audit(args: argparse.Namespace) -> int:
    text = _read_text(args.text_file)

    # Kansas-pinned jurisdiction comes from the case profile when present.
    try:
        profile = _load_case_profile(_resolve_profile_path(args))
    except FileNotFoundError as e:
        print(f"{R}✗ {e}{_R}", file=sys.stderr)
        return 2
    research = profile.get("research", {})
    explicit_jurisdiction = args.jurisdiction  # None = not passed by the user
    if explicit_jurisdiction is None:
        args.jurisdiction = research.get("jurisdiction") or "generic"

    # Jurisdiction is a FACT of the case: auto-detect it from the audited
    # text when the user pinned nothing explicitly. (Shown for context —
    # the citation-audit pipeline itself is jurisdiction-agnostic.)
    if (
        detect_jurisdiction
        and explicit_jurisdiction is None
        and args.jurisdiction in ("generic", "federal")
    ):
        detected = detect_jurisdiction(text)
        if detected and detected != "federal":
            args.jurisdiction = detected
            print(
                f"  {C}Jurisdiction auto-detected:{_R} "
                f"{detected.upper()} (from case text)"
            )

    print(f"\n{B}{'═' * 70}{_R}")
    print(f"{B}  🦅  OUTCLAW FULL AUDIT — LWM Pipeline{_R}")
    print(f"{B}{'═' * 70}{_R}")
    print(f"  {D}File:         {args.text_file}{_R}")
    print(f"  {D}Jurisdiction: {args.jurisdiction}{_R}")
    print(f"  {D}LLM:          {'ON (cloud cascade)' if args.llm else 'OFF'}{_R}")
    print(f"  {D}Aura:         {'ON' if not args.no_aura else 'OFF'}{_R}")
    print(f"  {D}Benford:      {'ON' if args.numbers_file else 'OFF'}{_R}")
    print()

    total_started = time.time()

    # Load numeric data for Benford if provided
    numeric_data = None
    if args.numbers_file:
        try:
            nums_path = Path(args.numbers_file)
            if not nums_path.exists():
                print(f"  {Y}⚠  Numbers file not found: {args.numbers_file}{_R}")
            else:
                text_nums = nums_path.read_text(encoding="utf-8")
                numeric_data = [
                    float(line.strip())
                    for line in text_nums.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                print(
                    f"  {G}✓ Loaded {len(numeric_data)} numeric values for Benford analysis{_R}"
                )
        except Exception as e:
            print(f"  {Y}⚠  Failed to load numbers file: {e}{_R}")

    # Run full audit pipeline
    print(f"  {D}Running full pipeline...{_R}")
    result = unified.full_audit_text(
        text,
        use_llm=args.llm,
        enable_aura=not args.no_aura,
        enable_benford=bool(numeric_data),
        numeric_data=numeric_data,
    )

    elapsed = (time.time() - total_started) * 1000

    # ── Citation Audit Results ──
    citation = result["citation_audit"]
    s = citation["summary"]
    print(f"\n  {B}📋 CITATION AUDIT{_R}")
    print(f"  {'─' * 60}")
    print(f"  Findings:   {G if s['safe_to_draft'] else R}{s['severity_counts']}{_R}")
    print(f"  Safe:       {'✅ YES' if s['safe_to_draft'] else '🚫 NO'}")
    if s.get("llm_assisted_count"):
        print(f"  LLM assist: {s['llm_assisted_count']} finding(s)")
    for f in citation["findings"][:5]:
        tag = (
            f"{BR}!!{_R}"
            if f["severity"] == "HIGH"
            else f"{BY}??{_R}"
            if f["severity"] == "MEDIUM"
            else f"{BG}ok{_R}"
        )
        print(f"    [{tag}] {_c(C, f['citation'][:40])}  {f['rule']}")

    # ── Aura Results ──
    aura = result.get("aura", {})
    if aura.get("skipped"):
        print(f"\n  {D}🔍 AURA PATTERN DETECTION — skipped{_R}")
    elif "error" in aura:
        print(f"\n  {Y}🔍 AURA PATTERN DETECTION — unavailable: {aura['error']}{_R}")
    else:
        asum = aura.get("summary", {})
        total_aura = asum.get("total_aura_findings", 0)
        print(f"\n  {B}🔍 AURA PATTERN DETECTION{_R}")
        print(f"  {'─' * 60}")
        print(
            f"  Total hits: {total_aura} across {asum.get('categories_triggered', 0)} categories"
        )
        print(
            f"  HIGH:       {_c(BR, str(asum.get('high_count', 0))) if asum.get('high_count', 0) > 0 else _c(G, '0')}{_R}"
        )
        for cat, count in asum.get("by_category", {}).items():
            if count > 0:
                label = PATTERN_DATABASE_LABELS.get(cat, cat)[:25]
                print(f"    {_c(Y if count > 0 else D, f'{label}: {count}')}{_R}")
        if aura.get("findings"):
            for f in aura["findings"][:3]:
                print(
                    f'    [{f["severity"]}] {f["label"]}: "{f["matched_text"][:60]}..."'
                )

    # ── Benford Results ──
    benford = result.get("benford", {})
    if (
        isinstance(benford, dict)
        and not benford.get("skipped")
        and "error" not in benford
    ):
        bf_prob = benford.get("fraud_probability", 0)
        bf_color = BR if bf_prob > 0.5 else BY if bf_prob > 0.15 else G
        print(f"\n  {B}📊 BENFORD'S LAW ANALYSIS{_R}")
        print(f"  {'─' * 60}")
        print(f"  Sample size:    {benford.get('sample_size', 0)}")
        print(f"  Fraud prob:     {bf_color}{bf_prob:.2%}{_R}")
        print(f"  Verdict:        {benford.get('verdict', 'Unknown')}")
        if benford.get("flagged_digits"):
            print(f"  Flagged digits: {benford['flagged_digits']}")
    elif isinstance(benford, dict) and benford.get("skipped"):
        print(f"\n  {D}📊 BENFORD'S LAW — skipped (no numeric data provided){_R}")

    # ── Risk Score ──
    risk = result.get("risk", {})
    r_score = risk.get("score", 50)
    r_tier = risk.get("tier", "UNKNOWN")
    tier_color = (
        G
        if r_tier == "GREEN"
        else Y
        if r_tier == "YELLOW"
        else BR
        if r_tier in ("ORANGE", "RED")
        else W
    )
    print(f"\n  {B}🎯 RISK SCORE{_R}")
    print(f"  {'─' * 60}")
    print(f"  Score:  {tier_color}{r_score}/100 ({r_tier}){_R}")
    if risk.get("recommendation"):
        print(f"  {risk['recommendation'][:100]}")

    # ── Verdict ──
    verdict = result.get("verdict", "UNKNOWN")
    is_safe = verdict.startswith("✅")
    print(f"\n  {B}{'═' * 70}{_R}")
    print(f"  {B}VERDICT:{_R} {verdict}")
    print(f"  {B}{'═' * 70}{_R}")
    print(f"  {D}Completed in {elapsed:.0f}ms{_R}")
    print()

    return 0 if is_safe else 1


# ═══════════════════════════════════════════════════════════════
#  PATTERN LABELS (imported)
# ═══════════════════════════════════════════════════════════════

# ── Pattern database labels (imported from source of truth) ──
try:
    from OutClaw.outclaw_aura import (
        AURA_LABELS as PATTERN_DATABASE_LABELS,  # type: ignore
    )
except ImportError:
    PATTERN_DATABASE_LABELS = {
        "financial_misconduct": "Financial Misconduct",
        "procedural_violations": "Procedural Violations",
        "abuse_of_power": "Abuse of Power",
        "transparency_issues": "Transparency Issues",
        "civil_rights_violations": "Civil Rights Violations",
        "judicial_misconduct": "Judicial Misconduct",
        "rico_patterns": "RICO / Organized Crime",
    }


# ═══════════════════════════════════════════════════════════════
# FOIA  —  generate FOIA request from audit findings
# ═══════════════════════════════════════════════════════════════


def cmd_foia(args: argparse.Namespace) -> int:
    from OutClaw.outclaw_foia import FOIAGenerator  # type: ignore

    # Kansas-pinned defaults come from the case profile when present.
    try:
        profile = _load_case_profile(_resolve_profile_path(args))
    except FileNotFoundError as e:
        print(f"{R}✗ {e}{_R}", file=sys.stderr)
        return 2
    case = profile.get("case", {})
    foia_cfg = profile.get("foia", {})
    research = profile.get("research", {})

    explicit_jurisdiction = args.jurisdiction  # None = not passed by the user
    jurisdiction = (
        explicit_jurisdiction
        if explicit_jurisdiction is not None
        else foia_cfg.get("jurisdiction")
        or research.get("jurisdiction")
        or "generic"
    )
    agency = args.agency or foia_cfg.get("agency") or "[Agency Name Required]"
    address = args.address or foia_cfg.get("address") or "[Agency Address]"
    default_description = (
        "\n".join(f"- {r}" for r in foia_cfg.get("records", []))
        if foia_cfg.get("records")
        else "[Description Required]"
    )
    subject = (
        f"Case {case.get('case_number', '')} — {case.get('agency', '')}".strip()
        if case
        else ""
    )

    # Jurisdiction is a FACT of the case: auto-detect it from the request
    # subject matter when the user pinned nothing explicitly.
    if detect_jurisdiction and explicit_jurisdiction is None and jurisdiction == "generic":
        detected = detect_jurisdiction(args.description, agency, subject)
        if detected and detected != "federal":
            jurisdiction = detected
            print(
                f"  {C}Jurisdiction auto-detected:{_R} "
                f"{detected.upper()} (from request facts)"
            )

    gen = FOIAGenerator()

    # If reading from stdin (piped audit report)
    if args.stdin:
        data = json.load(sys.stdin)
        findings = data.get("findings", [])
        request = gen.from_audit_findings(
            findings,
            agency=agency,
            jurisdiction=jurisdiction,
        )
    else:
        request = gen.generate(
            agency=agency,
            description=args.description or default_description,
            jurisdiction=jurisdiction,
            requester_name=args.name or "[Your Name]",
            requester_contact=args.contact or "[Your Contact]",
            method=args.method or "CERTIFIED MAIL — RETURN RECEIPT REQUESTED",
            address=address,
            subject=subject,
        )

    print(request)
    return 0


# ═══════════════════════════════════════════════════════════════
# ANALYZE  —  IRAC legal analysis
# ═══════════════════════════════════════════════════════════════


def cmd_analyze(args: argparse.Namespace) -> int:
    from OutClaw.outclaw_irac import IRACAnalyzer  # type: ignore

    analyzer = IRACAnalyzer()

    # Kansas-pinned jurisdiction comes from the case profile when present.
    try:
        profile = _load_case_profile(_resolve_profile_path(args))
    except FileNotFoundError as e:
        print(f"{R}✗ {e}{_R}", file=sys.stderr)
        return 2
    research = profile.get("research", {})
    explicit_jurisdiction = args.jurisdiction  # None = not passed by the user
    jurisdiction = (
        explicit_jurisdiction
        if explicit_jurisdiction is not None
        else research.get("jurisdiction")
        or "federal"
    )

    # Load facts from file if provided
    facts: list = []
    if args.facts:
        facts_path = Path(args.facts)
        if facts_path.exists():
            facts = [
                line.strip()
                for line in facts_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

    # Jurisdiction is a FACT of the case: auto-detect it from the question
    # and facts when the user pinned nothing explicitly.
    if detect_jurisdiction and explicit_jurisdiction is None and jurisdiction == "federal":
        detected = detect_jurisdiction(args.question, "\n".join(facts))
        if detected and detected != "federal":
            jurisdiction = detected
            print(
                f"  {C}Jurisdiction auto-detected:{_R} "
                f"{detected.upper()} (from case facts)"
            )

    brief = analyzer.analyze(
        question=args.question,
        jurisdiction=jurisdiction,
        relevant_facts=facts,
    )

    if args.markdown:
        print(analyzer.to_markdown(brief))
    else:
        print(f"\n{B}{'═' * 70}{_R}")
        print(f"{B}  ⚖️  IRAC LEGAL ANALYSIS{_R}")
        print(f"{B}{'═' * 70}{_R}")
        print(f"  {B}Question:{_R}     {brief.question}")
        print(f"  {B}Jurisdiction:{_R} {brief.jurisdiction.title()}")
        print(f"  {B}Confidence:{_R}   {brief.confidence[:60]}")
        print()
        print(f"  {B}ISSUE{_R}")
        print(f"  {brief.issue}")
        print()
        print(f"  {B}RULE{_R}")
        for r in brief.rules:
            print(f"    {C}{r['citation']}{_R}")
            print(f"    {r['holding'][:120]}")
            print()
        if brief.facts:
            print(f"  {B}FACTS{_R}")
            for f in brief.facts:
                print(f"    • {f}")
            print()
        print(f"  {B}ANALYSIS{_R}")
        for line in brief.analysis.split("\n"):
            print(f"  {line[:100]}")
        print()
        print(f"  {B}CONCLUSION{_R}")
        print(f"  {brief.conclusion[:120]}")
        print()
        if brief.action_steps:
            print(f"  {B}RECOMMENDED ACTIONS{_R}")
            for a in brief.action_steps:
                print(f"    {G}→{_R} {a}")
            print()
        print(f"  {D}{brief.disclaimer}{_R}")
        print()

    return (
        0
        if brief.confidence.startswith("HIGH") or brief.confidence.startswith("MEDIUM")
        else 1
    )


# ═══════════════════════════════════════════════════════════════
# CASE  —  pinned case briefing from a profile
# ═══════════════════════════════════════════════════════════════


def cmd_case(args: argparse.Namespace) -> int:
    """Render a case briefing from a case profile.

    Pass --profile, or run from inside the case workspace (e.g. case_data/) to
    auto-load it. OutClaw scripts stay general outside a workspace; a
    profile scopes one run to one case. This is the window into that case:
    defendant, case number, court, judge, prosecutor, posture, statutes,
    and the exact commands that produce state-pinned results.
    """
    profile_path = _resolve_profile_path(args)
    if not profile_path:
        print(f"{Y}Usage:{_R} outclaw case --profile <path-to-case_context.json>")
        print(
            f"  {D}OutClaw scripts stay general; a profile scopes one run to one case. "
            f"Run from inside the case workspace (e.g. case_data/) to auto-load it, "
            f"or set OUTCLAW_CASE to a case_context.json path.{_R}"
        )
        return 2
    try:
        profile = _load_case_profile(profile_path)
    except FileNotFoundError as e:
        print(f"{R}✗ {e}{_R}", file=sys.stderr)
        print(
            f"  {D}Run from inside the case workspace (e.g. case_data/) to auto-load it, "
            f"or pass --profile <path-to-case_context.json>.{_R}",
            file=sys.stderr,
        )
        return 2
    case = profile.get("case", {})
    research = profile.get("research", {})

    def _val(v):
        if isinstance(v, str) and v.startswith("PLACEHOLDER"):
            return f"{Y}{v}{_R}"
        if v in (None, ""):
            return f"{Y}—{_R}"
        return v

    print()
    print(f"{B}{'═' * 70}{_R}")
    print(f"{B}  🦅  OUTCLAW CASE BRIEFING{_R}")
    print(f"{B}{'═' * 70}{_R}")
    print(f"  {D}{profile.get('profile_name', args.profile)}{_R}")
    print()
    print(f"  {B}Defendant:{_R}       {_val(case.get('defendant'))}")
    print(f"  {B}Case number:{_R}     {_val(case.get('case_number'))}")
    print(f"  {B}Case type:{_R}       {_val(case.get('case_type'))}")
    print(f"  {B}Court:{_R}           {_val(case.get('court'))}")
    print(f"  {B}County/District:{_R} {_val(case.get('county'))} — {_val(case.get('district'))}")
    print(f"  {B}Agency:{_R}          {_val(case.get('agency'))}")
    print(f"  {B}Judge:{_R}           {_val(case.get('judge'))}")
    print(f"  {B}Prosecutor:{_R}      {_val(case.get('prosecutor'))}")
    print(f"  {B}Defense counsel:{_R} {_val(case.get('defense_counsel'))}")
    print(f"  {B}Posture:{_R}         {_val(case.get('posture'))}")
    print()
    print(f"  {B}Statutes:{_R}")
    for s in case.get("statutes", []):
        print(f"    • {s}")
    print()
    print(f"  {B}Research pins:{_R}")
    print(f"    Jurisdiction: {_c(B, str(research.get('jurisdiction', 'kansas')).upper())}  (out-of-state results filtered)")
    print(f"    Court IDs:    {', '.join(research.get('court_ids', [])) or '—'}")
    print(f"    Excludes:     {', '.join(research.get('exclude_states', [])) or '—'}")
    print()
    print(f"  {B}Run these:{_R}")
    print(f"    {C}./run_case_stack.sh{_R}                        full pinned research stack")
    print(f"    {C}python3 scouts/case_law_scout.py --profile case_context.json{_R}")
    print(f"    {C}python3 outclaw_cli.py foia --profile case_context.json{_R}")
    print(f"    {C}python3 outclaw_cli.py analyze \"<question>\" --profile case_context.json{_R}")
    print()
    print(f"  {Y}⚠  Fill the PLACEHOLDER fields in case_context.json to target the judge,{_R}")
    print(f"  {Y}   prosecutor, and defense counsel by name.{_R}")
    print(f"  {D}{'═' * 70}{_R}")
    print()
    return 0


# ═══════════════════════════════════════════════════════════════
# CASEWORK  —  the self-rep arsenal (hidden modules + new casework)
# ═══════════════════════════════════════════════════════════════


def _ensure_lws_modules() -> None:
    """Put LWS_ROOT/modules on sys.path for grievance/impact modules."""
    lws = _HERE.parent.parent / "LWS_ROOT" / "modules"
    p = str(lws)
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_fraud_evidence(evidence_file: str | None, args: argparse.Namespace) -> list:
    """Build FraudEvidence objects from an evidence JSON, an audit report,
    or the single-evidence flags."""
    _ensure_lws_modules()
    from outclaw_grievance_generator import FraudEvidence  # type: ignore

    items: list = []
    if evidence_file:
        data = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("findings"):
            # an `outclaw audit --json` report
            items = [
                {
                    "citation_string": f.get("citation", ""),
                    "issue_type": (f.get("rule") or "fabricated")[:30],
                    "severity": f.get("severity", "MEDIUM"),
                    "description": f.get("detail", f.get("rule", "")),
                    "document_reference": f.get("source", ""),
                }
                for f in data["findings"]
            ]
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError("evidence file must be a JSON list or an audit report")
    if not items and getattr(args, "citation", None):
        items.append(
            {
                "citation_string": args.citation,
                "issue_type": args.issue_type,
                "severity": args.severity,
                "description": args.description,
                "document_reference": getattr(args, "document", ""),
            }
        )
    if not items:
        raise ValueError("No evidence provided — pass --evidence-file or --citation …")
    return [
        FraudEvidence(
            citation_string=it.get("citation_string", ""),
            issue_type=it.get("issue_type", "fabricated"),
            severity=it.get("severity", "MEDIUM"),
            description=it.get("description", ""),
            document_reference=it.get("document_reference", ""),
            page_number=it.get("page_number"),
            verification_attempts=it.get("verification_attempts", []),
            graph_analysis=it.get("graph_analysis"),
        )
        for it in items
    ]


def _load_misconduct_evidence(evidence_file: str) -> list:
    """Build JudicialMisconductEvidence objects from a JSON list."""
    from outclaw_judicial_complaints import (  # type: ignore
        JudicialMisconductEvidence,
    )

    data = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("evidence", [])
    ev = []
    for it in data:
        ev.append(
            JudicialMisconductEvidence(
                incident_date=datetime.fromisoformat(
                    str(it.get("incident_date", date.today().isoformat()))
                ),
                misconduct_type=it.get("misconduct_type", "bias"),
                severity=it.get("severity", "MEDIUM"),
                description=it.get("description", ""),
                transcript_reference=it.get("transcript_reference"),
                page_number=it.get("page_number"),
                witnesses=it.get("witnesses", []),
                supporting_documents=it.get("supporting_documents", []),
                impact=it.get("impact", ""),
            )
        )
    if not ev:
        raise ValueError("No misconduct evidence found in --evidence-file")
    return ev


def cmd_objections(args: argparse.Namespace) -> int:
    """Evidentiary objections with legal basis (Kansas rules included)."""
    from outclaw_objections_engine import (  # type: ignore
        ObjectionContext,
        ObjectionsEngine,
    )

    state = args.state
    if not state and args.jurisdiction in ("kansas", "oklahoma"):
        state = args.jurisdiction
    if not state:
        state = _profile_state(args)
        if state:
            print(
                f"  {C}State from case profile:{_R} {state.upper()}",
                file=sys.stderr,
            )
    if not state and detect_jurisdiction:
        detected = detect_jurisdiction(args.statement)
        if detected in ("kansas", "oklahoma"):
            state = detected
            print(f"  {C}State auto-detected:{_R} {detected.upper()}")
    jurisdiction = "state" if state else (args.jurisdiction or "federal")
    engine = ObjectionsEngine(jurisdiction=jurisdiction, state=state)
    # The engine's purpose gate expects truth/prove/establish — normalize
    # common phrasings ("truth of the matter") into the accepted keys.
    purpose = args.purpose.strip().lower()
    if purpose in ("", "truth of the matter", "truth of the matter asserted"):
        purpose = "truth"
    elif purpose in ("to prove", "prove the matter"):
        purpose = "prove"
    ctx = ObjectionContext(
        statement=args.statement,
        speaker=args.speaker,
        speaker_role=args.role,
        purpose=purpose,
        jurisdiction=jurisdiction,
        state=state,
        trial_phase=args.phase,
        transcript_page=args.page,
        line_number=args.line,
    )
    objections = engine.analyze_statement(ctx)
    print(f"\n{B}⚖️  OBJECTION ANALYSIS{_R}  (state={state or 'federal'})")
    for o in objections:
        print(f"\n  {B}{o.objection_type.value.upper()}{_R}  [{o.severity}]")
        print(f"    {C}Say:{_R}       {o.objection_text}")
        print(f"    {C}Basis:{_R}     {o.legal_basis}")
        print(f"    {C}Why:{_R}       {o.explanation}")
        if o.case_law:
            print(f"    {C}Cases:{_R}     {', '.join(o.case_law[:3])}")
        print(f"    {C}Overruled:{_R} {o.response_to_overruled}")
    print()
    print(engine.generate_objection_script(objections))
    return 0


def cmd_grievance(args: argparse.Namespace) -> int:
    """Generate a bar grievance package from fraud evidence."""
    _ensure_lws_modules()
    from outclaw_grievance_generator import (  # type: ignore
        AttorneyInfo,
        GrievanceGenerator,
    )

    attorney = AttorneyInfo(
        name=args.attorney,
        bar_number=args.bar or "",
        state=args.state or _profile_state(args) or "kansas",
        firm_name=args.firm or None,
        address=args.address or None,
    )
    evidence = _load_fraud_evidence(args.evidence_file, args)
    gen = GrievanceGenerator()
    package = gen.generate_grievance(
        attorney=attorney,
        complainant_name=args.complainant,
        fraud_evidence=evidence,
        case_number=args.case,
    )
    print(package.complaint_text)
    print("\n" + package.evidence_summary)
    print("\n" + package.filing_instructions)
    print(
        f"\n{D}Grievance ID: {package.grievance_id}  │  "
        f"Est. defense cost: ${package.estimated_defense_cost:,}  │  "
        f"Your cost: $0{_R}"
    )
    return 0


def cmd_complaint(args: argparse.Namespace) -> int:
    """Generate a judicial misconduct complaint package."""
    from outclaw_judicial_complaints import (  # type: ignore
        JudgeInfo,
        JudicialComplaintGenerator,
    )

    state = args.state or _profile_state(args)
    judge = JudgeInfo(
        name=args.judge,
        court=args.court,
        jurisdiction="state" if state else "federal",
        state=state,
        case_number=args.case or "",
    )
    if args.evidence_file:
        evidence = _load_misconduct_evidence(args.evidence_file)
    elif args.incident or args.evidence:
        from outclaw_judicial_complaints import JudicialMisconductEvidence  # type: ignore

        if args.date:
            try:
                incident_date = datetime.fromisoformat(args.date)
            except ValueError:
                print(
                    f"{R}✗ Could not parse --date {args.date!r} — use YYYY-MM-DD (e.g. 2026-03-28){_R}",
                    file=sys.stderr,
                )
                return 2
        else:
            incident_date = date.today()
        evidence = [
            JudicialMisconductEvidence(
                incident_date=incident_date,
                misconduct_type="bias",
                severity=args.severity,
                description=args.incident or args.evidence or "",
                supporting_documents=([args.evidence] if args.evidence else []),
            )
        ]
    else:
        print(
            f"{R}✗ Provide --evidence-file, or --incident/--date/--evidence for a single incident{_R}",
            file=sys.stderr,
        )
        return 2
    gen = JudicialComplaintGenerator()
    package = gen.generate_complaint(
        judge=judge,
        complainant_name=args.complainant,
        evidence=evidence,
        case_number=args.case or "",
    )
    print(package["complaint_text"])
    print("\n" + package["filing_instructions"])
    print(
        f"\n{D}Complaint ID: {package['complaint_id']}  │  "
        f"Package: {gen.output_dir / package['complaint_id']}{_R}"
    )
    return 0


def cmd_guide(args: argparse.Namespace) -> int:
    """Pro se survival guide + deadline calculator."""
    from outclaw_pro_se_survival_guide import (  # type: ignore
        ProSeSurvivalGuide,
    )

    guide = ProSeSurvivalGuide()
    if args.list:
        for k in guide.CRITICAL_CONCEPTS:
            print(f"  {C}{k}{_R}")
        return 0
    if args.concept:
        c = guide.CRITICAL_CONCEPTS.get(args.concept)
        if not c:
            print(f"{R}✗ Unknown concept: {args.concept}{_R}", file=sys.stderr)
            print(f"  {D}Try: {' '.join(guide.CRITICAL_CONCEPTS.keys())}{_R}")
            return 2
        print(f"{B}{c.name}{_R}")
        print(f"\n{Y}WHY THIS WILL DESTROY YOUR CASE:{_R}\n{c.why_critical}")
        print(f"\n{Y}WHAT HAPPENS IF YOU DON'T KNOW THIS:{_R}\n{c.what_happens_if_you_dont}")
        print(f"\n{G}HOW TO DO IT:{_R}\n{c.how_to_do_it}")
        if c.deadline:
            print(f"\n{D}Deadline: {c.deadline}{_R}")
        if c.template:
            print(f"\n{D}Template:{_R}\n{c.template}")
        return 0
    if args.deadline:
        trigger = datetime.strptime(args.trigger, "%Y-%m-%d") if args.trigger else datetime.now()
        info = guide.generate_deadline_calculator(
            trigger_date=trigger,
            deadline_days=args.deadline,
            served_by_mail=args.mail,
        )
        print(json.dumps(info, indent=2, default=str))
        return 0
    print(guide.generate_survival_guide())
    return 0


def cmd_course(args: argparse.Namespace) -> int:
    """Plain-language court-mechanics course for self-represented litigants.

    Sub-modes:
      course --list            all lessons + prep tracks
      course --lesson <key>    one lesson
      course --track <key>     one trial-prep track (oral-argument, opening,
                               closing, direct-exam, cross-exam, deposition)
      course --term <term>     plain-language glossary lookup
      course --pack            the full trial-prep pack (all tracks)
    Advisory study material — never legal advice.
    """
    from outclaw_pro_se_course import COURSE  # type: ignore

    if args.json:
        if args.lesson:
            payload = COURSE.get_lesson(args.lesson)
        elif args.track:
            payload = COURSE.prep_track(args.track)
        elif args.term:
            payload = COURSE.lookup_term(args.term)
        elif args.pack:
            payload = COURSE.trial_prep_pack()
        else:
            payload = COURSE.course_index()
        if payload is None:
            print(f"{R}✗ Not found.{_R}", file=sys.stderr)
            return 2
        print(json.dumps(payload, indent=2, default=str))
        return 0

    if args.list or not (args.lesson or args.track or args.term or args.pack):
        idx = COURSE.course_index()
        print(f"\n{B}📚 PRO SE COURT COURSE{_R}  (study material — not legal advice)")
        print(f"\n{B}Lessons:{_R}")
        for lesson in idx["lessons"]:
            print(f"  {C}{lesson['key']:<14}{_R} {lesson['title']}")
        print(f"\n{B}Prep tracks:{_R}")
        for key, title in idx["prep_tracks"].items():
            print(f"  {C}{key:<14}{_R} {title}")
        print(f"\n  {D}Glossary: {idx['glossary_terms']} terms — try: outclaw course --term hearsay{_R}")
        print(f"\n{D}Usage: outclaw course --lesson <key> │ --track <key> │ --term <word> │ --pack{_R}")
        return 0

    if args.lesson:
        lesson = COURSE.get_lesson(args.lesson)
        if not lesson:
            print(f"{R}✗ Unknown lesson: {args.lesson}{_R}", file=sys.stderr)
            print(f"  {D}Try --list for lesson keys.{_R}")
            return 2
        l = lesson["lesson"]
        print(f"\n{B}{l['title']}{_R}")
        print(f"\n{B}Plain language:{_R}")
        for line in l["plain_language"]:
            print(f"  • {line}")
        print(f"\n{B}Why it matters:{_R}")
        for line in l["why_it_matters"]:
            print(f"  • {line}")
        print(f"\n{G}Do this:{_R}")
        for line in l["do_this"]:
            print(f"  ✓ {line}")
        print(f"\n{R}Common mistakes:{_R}")
        for line in l["common_mistakes"]:
            print(f"  ✗ {line}")
        if l["key_terms"]:
            print(f"\n{D}Key terms: {', '.join(l['key_terms'])}{_R}")
        return 0

    if args.track:
        track = COURSE.prep_track(args.track)
        if not track:
            print(f"{R}✗ Unknown track: {args.track}{_R}", file=sys.stderr)
            print(f"  {D}Try --list for track keys.{_R}")
            return 2
        print(f"\n{B}🎯 {track['title'].upper()}{_R}")
        print(f"\n{B}Goal:{_R} {track['goal']}")
        print(f"\n{B}Structure:{_R}")
        for i, step in enumerate(track["structure"], 1):
            print(f"  {i}. {step}")
        print(f"\n{G}Do:{_R}")
        for line in track["do"]:
            print(f"  ✓ {line}")
        print(f"\n{R}Avoid:{_R}")
        for line in track["avoid"]:
            print(f"  ✗ {line}")
        related = COURSE.related_lessons(args.track)["related_lessons"]
        if related:
            print(f"\n{D}Pair with: {', '.join(related)} — outclaw course --lesson <key>{_R}")
        return 0

    if args.term:
        term = COURSE.lookup_term(args.term)
        if not term:
            print(f"{R}✗ Term not in glossary: {args.term}{_R}", file=sys.stderr)
            return 2
        print(f"\n{B}{term['term']}{_R}")
        print(f"  {term['definition']}")
        return 0

    if args.pack:
        pack = COURSE.trial_prep_pack()
        print(f"\n{B}🧰 FULL TRIAL-PREP PACK{_R}  (study material — not legal advice)")
        for key, track in pack["tracks"].items():
            print(f"\n{B}🎯 {track['title'].upper()}{_R}")
            print(f"  {B}Goal:{_R} {track['goal']}")
            for i, step in enumerate(track["structure"], 1):
                print(f"    {i}. {step}")
            print(f"  {G}Do:{_R} {' '.join(track['do'])}")
            print(f"  {R}Avoid:{_R} {' '.join(track['avoid'])}")
        print()
        return 0

def cmd_impact(args: argparse.Namespace) -> int:
    """'So what?' reality check on grievance evidence."""
    _ensure_lws_modules()
    from outclaw_so_what_filter import SoWhatFilter  # type: ignore

    evidence = _load_fraud_evidence(args.evidence_file, args)
    history = {
        "grievance_count": args.grievances or 0,
        "clean_record": not (args.grievances or 0),
    }
    context = {
        "financial_harm": args.financial_harm or 0,
        "court_sanctions": bool(args.sanctions),
        "pro_se_complainant": True,
    }
    rc = SoWhatFilter().apply_reality_check(evidence, history, context)
    print(f"\n{B}IMPACT LEVEL:{_R}  {rc.impact_level.value}")
    print(f"{B}Actionable:{_R}    {'YES' if rc.actionable else 'NO — do not file this'}")
    print(f"\n{B}Why they care:{_R}   {rc.why_they_care}")
    print(f"{B}Why they don't:{_R}  {rc.why_they_dont_care}")
    print(f"{B}Clerk:{_R}          {rc.clerk_reaction}")
    print(f"{B}Attorney:{_R}       {rc.attorney_reaction}")
    print(f"{B}Judge:{_R}          {rc.judge_reaction}")
    print(f"{B}Recommendation:{_R} {rc.recommendation}")
    return 0 if rc.actionable else 1


def cmd_statute(args: argparse.Namespace) -> int:
    """Fetch current Kansas statute text (kslegislature.org)."""
    from outclaw_casework import fetch_statute  # type: ignore

    try:
        result = fetch_statute(args.cite)
    except ValueError as e:
        print(f"{R}✗ {e}{_R}", file=sys.stderr)
        return 2
    print(f"\n{B}K.S.A. {result['cite']} — current text{_R}")
    print(f"{D}Source: {result['url']}  |  Retrieved: {result['retrieved']}{_R}")
    print()
    print(result["text"])
    if args.out:
        Path(args.out).write_text(
            f"K.S.A. {result['cite']}  (retrieved {result['retrieved']})\n"
            f"Source: {result['url']}\n\n{result['text']}\n"
        )
        print(f"\n{D}Saved to: {args.out}{_R}")
    return 0


def cmd_evidence_chart(args: argparse.Namespace) -> int:
    """Statement-by-statement evidence chart."""
    from outclaw_casework import (  # type: ignore
        build_evidence_chart,
        render_chart_csv,
        render_chart_markdown,
    )

    text = _read_text(args.file)
    rows = build_evidence_chart(text)
    out = render_chart_csv(rows) if args.csv else render_chart_markdown(rows)
    print(out)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"\n{D}Saved to: {args.out}{_R}")
    return 0


def cmd_transcript_search(args: argparse.Namespace) -> int:
    """Find key terms in a transcript."""
    from outclaw_casework import (  # type: ignore
        render_search_report,
        search_transcript,
    )

    text = _read_text(args.file)
    terms = [t.strip() for t in (args.terms or "").split(",") if t.strip()] or None
    report = search_transcript(text, terms)
    out = render_search_report(report)
    print(out)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"\n{D}Saved to: {args.out}{_R}")
    return 0


def cmd_record_audit(args: argparse.Namespace) -> int:
    """Run the extraction/ingestion layer over a case record.

    Advisory only: citations/statutes per document, cross-document
    cross-referencing, chronology, contradiction leads, and (when a
    deposition transcript + Statement of Facts are supplied) SOF-vs-record
    validation with page:line cites. Output is evidence for human review —
    never a legal validation or a draft gate.
    """
    from outclaw_extraction import extraction_record_audit  # type: ignore

    if not args.doc:
        print(f"{R}✗ record-audit requires at least one --doc file{_R}", file=sys.stderr)
        return 2
    docs = {path.name: _read_text(path) for path in args.doc}
    sof = _read_text(args.sof) if args.sof else None
    deposition = _read_text(args.deposition) if args.deposition else None
    if (args.sof is None) != (args.deposition is None):
        # Statement-of-Facts validation needs BOTH inputs; warn instead of
        # silently producing a report with no SOF section.
        print(
            f"{D}Note: Statement-of-Facts validation requires BOTH --sof and "
            f"--deposition; validation was skipped.{_R}",
            file=sys.stderr,
        )

    report = extraction_record_audit(
        documents=docs,
        statement_of_facts=sof,
        deposition_transcript=deposition,
        witness=args.witness,
        case_name=args.case,
        use_llm=args.llm,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print(f"\n{B}📋 RECORD AUDIT — extraction layer (advisory only){_R}")
    print(f"  Documents: {', '.join(report['documents_processed'])}")
    for name, meta in report["per_document_extraction"].items():
        print(
            f"    {name}: {meta['total_citations']} citations, "
            f"{meta['total_statutes']} statutes"
        )
    xref = report["cross_reference"]
    print(f"  Shared authorities across docs: {len(xref['shared_cases'])}")
    print(f"  Timeline events: {len(report['chronology']['timeline'])}")
    print(
        f"  Contradiction leads: {report['contradiction_leads']['total_contradictions']}"
    )
    sof_val = report["statement_of_facts_validation"]
    if sof_val:
        v = sof_val["validation"]
        print(
            f"  Statement of Facts: {v['total_assertions']} assertions, "
            f"coverage {v['coverage']} — supported {len(v['supported'])}, "
            f"unsupported {len(v['unsupported'])}, contradicted {len(v['contradicted'])}"
        )
    print(f"\n{D}Extraction output is evidence for human review — not a legal{_R}")
    print(f"{D}validation and not authorization to file or generate a pleading.{_R}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Scan a case folder into case_record.json."""
    from outclaw_casework import scan_case_dir  # type: ignore

    try:
        out = args.out or str(Path(args.dir) / "case_record.json")
        record = scan_case_dir(args.dir, out, ocr=not args.no_ocr)
    except ValueError as e:
        print(f"{R}✗ {e}{_R}", file=sys.stderr)
        return 2
    f = record.get("facts", {})
    print(f"\n{B}📂 INGEST COMPLETE{_R}")
    print(f"  Files:        {record['file_count']}")
    print(f"  OCR status:   {record['ocr_status']}")
    print(f"  Jurisdiction: {f.get('jurisdiction') or '—'}")
    print(f"  Dates:        {', '.join(f.get('dates', [])) or '—'}")
    print(f"  Case numbers: {', '.join(f.get('case_numbers', [])) or '—'}")
    print(f"  Statute cites:{', '.join(f.get('statute_cites', [])) or '—'}")
    if record.get("record_file"):
        print(f"  Record:       {record['record_file']}")
    print()
    return 0


def cmd_briefify(args: argparse.Namespace) -> int:
    """Plain-English briefing from research + record."""
    from outclaw_casework import briefify  # type: ignore

    dossier = record = profile = None
    if args.research:
        dossier = json.loads(Path(args.research).read_text(encoding="utf-8"))
    if args.record:
        record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    profile_path = _resolve_profile_path(args)
    if profile_path:
        try:
            profile = _load_case_profile(profile_path)
        except FileNotFoundError as e:
            print(f"{R}✗ {e}{_R}", file=sys.stderr)
            return 2
    issues = (profile or {}).get("research", {}).get("issues") or None
    out = briefify(dossier, record, issues, profile)
    print(out)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"\n{D}Saved to: {args.out}{_R}")
    return 0


# ═══════════════════════════════════════════════════════════════
# REGRESSION, SAFE-DRAFT, DEMO  (existing subcommands, preserved)
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  SAFETY & REGRESSION
# ═══════════════════════════════════════════════════════════════

def cmd_cascade(args: argparse.Namespace) -> int:
    """Cascade subcommand: status / live test of the stair-stepped ladder."""
    try:
        from OutClaw.outclaw_model_cascade import (  # type: ignore
            TIER_NAMES as TIER_NAME_LOOKUP,
            cascade_status,
            get_cascade,
        )
    except Exception as e:
        print(f"{R}✗ Cascade module unavailable: {e}{_R}", file=sys.stderr)
        return 2

    if args.test:
        status = cascade_status()
        if not status.get("enabled"):
            print(f"  {Y}⚠  Cascade is DISABLED (set OUTCLAW_CASCADE=1 or config.yaml cascade.enabled){_R}")
            print(f"  {D}Running anyway with force (single-shot test)...{_R}")
        if args.json:
            print(f"\n{B}Testing cascade (task={args.task})...{_R}")
        cascade = get_cascade()
        result = cascade.complete(
            args.test,
            task=args.task,
            min_confidence=args.min_confidence,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
            return 0 if result.ok else 1
        print(f"\n{B}🧪 CASCADE TEST — {_c(C, args.task)}{_R}")
        print(f"  {'─' * 60}")
        if result.ok:
            print(f"  {G}✓ RESOLVED{_R}  tier={result.tier} ({TIER_NAME_LOOKUP.get(result.tier, result.tier)})")
            print(f"  {B}Provider:{_R}   {result.provider}  /  {result.model}")
            print(f"  {B}Confidence:{_R} {result.confidence:.2f}")
            if result.data:
                print(f"  {B}Response:{_R}   {json.dumps(result.data, indent=4)[:600]}")
        else:
            print(f"  {R}✗ UNRESOLVED{_R} — every tier/provider failed or confidence unmet")
        print(f"\n  {B}Escalation trail:{_R}")
        for step in result.escalation:
            print(f"    {D}↳{_R} {step}")
        for a in result.attempts:
            if not a.ok:
                print(f"    {D}  ({a.provider}/{a.model}: {a.reason[:80]}){_R}")
        print()
        return 0 if result.ok else 1

    status = cascade_status()
    if args.json:
        print(json.dumps(status, indent=2))
        return 0

    enabled = status.get("enabled", False)
    print(f"\n{B}{'═' * 70}{_R}")
    print(f"{B}  🪜  OUTCLAW MODEL CASCADE — Stair-Stepped Tier Ladder{_R}")
    print(f"{B}{'═' * 70}{_R}")
    print(f"  {B}Enabled:{_R}       {'✅ ON' if enabled else '⛔ OFF (set OUTCLAW_CASCADE=1 or config.yaml)'}")
    print(f"  {B}Cache:{_R}         {status.get('cache_size', 0)} entries")
    print()

    print(f"  {B}PROVIDER READINESS{_R}  (all free tiers, no credit card, cloud-only)")
    print(f"  {'─' * 60}")
    for name, info in status.get("providers", {}).items():
        if info.get("configured"):
            print(f"    {G}✓ {name:<12}{_R} ready  {D}{info.get('rate_limit_hint', '')[:55]}{_R}")
        else:
            missing = ", ".join(info.get("missing_env", [])) or "keys"
            print(f"    {D}· {name:<12} no key ({missing})  {D}{info.get('rate_limit_hint', '')[:40]}{_R}")
    print()
    if not any(p.get("configured") for p in status.get("providers", {}).values()):
        print(f"  {Y}⚠  No free cloud keys configured — the cascade stays OFF and the{_R}")
        print(f"  {Y}   deterministic heuristic pipeline remains the source of truth.{_R}")
        print()

    print(f"  {B}TIER LADDERS{_R}  (order = failover within tier; escalate up on failure)")
    print(f"  {'─' * 60}")
    for tier_name in ("extraction", "classification", "adjudication"):
        ladder = status.get("tiers", {}).get(tier_name, [])
        print(f"    {B}{tier_name:<16}{_R}")
        for step in ladder:
            mark = (
                G if status.get("providers", {}).get(step["provider"], {}).get("configured")
                else D
            )
            print(f"      {mark}→{_R} {step['provider']:<12} {step['model']}")
    print()
    print(f"  {B}Stats:{_R} {status.get('stats')}")
    print()
    print(
        f"  {D}Tip: run `outclaw cascade --test \"Is X the opposite of Y?\" --task opposite_holding`{_R}"
    )
    print()
    return 0


def cmd_regression(args: argparse.Namespace) -> int:
    return regression.main([])


def cmd_safe_draft(args: argparse.Namespace) -> int:
    text = _read_text(args.text_file)
    try:
        trace = safety.interactive_request_and_verify(args.intent, text)
    except safety.IntentRejected as e:
        print(f"!! Intent rejected: {e}", file=sys.stderr)
        return 64
    except safety.GenerateDocumentBlocked as e:
        print(f"!! GenerateDocumentBlocked: {e}", file=sys.stderr)
        if e.unresolved:
            print("    Unresolved findings:", file=sys.stderr)
            for u in e.unresolved[:10]:
                print(
                    f"      - {u.get('citation', '')}: {u.get('rule', '')}",
                    file=sys.stderr,
                )
        return 65
    except ValueError as e:
        print(f"!! Invalid ack_token: {e}", file=sys.stderr)
        return 66
    print("OK -- audit clean and ack verified.")
    print(json.dumps(trace.to_dict(), indent=2))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    print(f"\n{B}{'═' * 70}{_R}")
    print(f"{B}  OutClaw Demo: self-represented litigant use cases{_R}")
    print(f"{B}{'═' * 70}{_R}")
    print()

    if args.list_only:
        for u in use_cases.USE_CASES:
            print(f"  {C}{u.name}{_R}: {u.title}")
            print(f"      {D}{u.description}{_R}")
        return 0

    names = [args.use_case] if args.use_case else use_cases.list_use_cases()
    failures = 0
    for n in names:
        verdict = use_cases.run_use_case(n)
        case = use_cases.get_use_case(n)
        if case is None:
            print(f"  {R}!! Unknown use case: {n}{_R}")
            return 2
        tag = f"{G}PASS{_R}" if verdict["passed"] else f"{R}FAIL{_R}"
        print(f"  [{tag}] {n}")
        print(f"      {case.title}")
        print(
            f"      expected: {verdict['expected_min_severity']} | actual: {verdict['actual_highest']}"
        )
        if verdict["missed_rules"]:
            print(f"      {R}MISSED: {verdict['missed_rules']}{_R}")
        if not verdict["passed"]:
            failures += 1

    print()
    if failures:
        print(f"  {R}{failures}/{len(names)} FAILED{_R}")
        return 1
    print(
        f"  {G}All {len(names)} use case(s) matched expectation. Demo run is GREEN.{_R}"
    )
    return 0


# ═══════════════════════════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="outclaw",
        description="OutClaw — Citation-Fraud Audit Tool for Self-Represented Litigants",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # ── audit ──
    p_audit = sub.add_parser("audit", help="Audit a legal text file for citation fraud")
    p_audit.add_argument("text_file", type=Path, help="Path to legal text file")
    p_audit.add_argument("--json", action="store_true", help="Output raw JSON report")
    p_audit.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM-assisted classification (cloud cascade, free keys)",
    )
    p_audit.add_argument(
        "--strict-high",
        action="store_true",
        help="Exit 0 on MEDIUM findings (legacy mode)",
    )
    p_audit.add_argument(
        "--auto-escalate",
        action="store_true",
        help="Auto-escalate ambiguous findings to the LLM (cloud cascade) for reclassification",
    )
    p_audit.add_argument(
        "--cascade",
        action="store_true",
        help="Enable the stair-stepped model cascade (free cloud tiers only)",
    )
    p_audit.set_defaults(func=cmd_audit, auto_escalate=False)

    # ── score ──
    p_score = sub.add_parser(
        "score", help="Render risk dashboard from a saved audit report"
    )
    p_score.add_argument("report", help="JSON report file (or '-' for stdin)")
    p_score.add_argument(
        "--compare", metavar="BEFORE.json", help="Compare with a previous report"
    )
    p_score.set_defaults(func=cmd_score)

    # ── lookup ──
    p_lookup = sub.add_parser(
        "lookup", help="Look up a citation in CourtListener (Predicase gem)"
    )
    p_lookup.add_argument("citation", help="Citation string, e.g. '384 U.S. 436'")
    p_lookup.add_argument(
        "--expand", action="store_true", help="Add result to seed registry"
    )
    p_lookup.set_defaults(func=cmd_lookup)

    # ── discover ──
    p_disc = sub.add_parser(
        "discover", help="Scan for undiscovered citations (Predicase gem)"
    )
    p_disc.add_argument("text_file", type=Path, nargs="?", help="Text file to scan")
    p_disc.add_argument(
        "--dir", help="Scan a directory of legal texts instead of a single file"
    )
    p_disc.set_defaults(func=cmd_discover)

    # ── enhance ──
    p_enh = sub.add_parser(
        "enhance", help="Full pipeline: audit + LLM + risk score + discovery"
    )
    p_enh.add_argument("text_file", type=Path, help="Path to legal text file")
    p_enh.add_argument(
        "--llm", action="store_true", help="Enable LLM-assisted classification"
    )
    p_enh.add_argument(
        "--auto-escalate",
        action="store_true",
        help="Auto-escalate ambiguous findings to the LLM (cloud cascade) for reclassification",
    )
    p_enh.add_argument(
        "--cascade",
        action="store_true",
        help="Enable the stair-stepped model cascade (free cloud tiers only)",
    )
    p_enh.set_defaults(func=cmd_enhance, auto_escalate=False)

    # ── full-audit ──
    p_full = sub.add_parser(
        "full-audit", help="LWM full pipeline: audit + aura + benford + risk score"
    )
    p_full.add_argument("text_file", type=Path, help="Path to legal text file")
    p_full.add_argument(
        "--llm", action="store_true", help="Enable LLM-assisted classification"
    )
    p_full.add_argument(
        "--no-aura", action="store_true", help="Skip Aura pattern detection"
    )
    p_full.add_argument(
        "--numbers-file",
        type=Path,
        help="Path to numeric data file for Benford analysis (one number per line)",
    )
    p_full.add_argument(
        "--jurisdiction",
        default=None,
        help="Jurisdiction for context (auto-detected from the case text when omitted)",
    )
    p_full.add_argument(
        "--profile",
        help="Optional case profile (case_context.json) — pins THIS run to that case; omit for generic use",
    )
    p_full.set_defaults(func=cmd_full_audit)

    # ── foia ──
    p_foia = sub.add_parser("foia", help="Generate FOIA/Open Records request (LWM gem)")
    p_foia.add_argument(
        "--stdin",
        action="store_true",
        help="Read audit findings from stdin (pipe: outclaw audit file.txt --json | outclaw foia --stdin)",
    )
    p_foia.add_argument("--agency", help="Agency/department name")
    p_foia.add_argument("--description", help="Description of records requested")
    p_foia.add_argument(
        "--jurisdiction",
        default=None,
        choices=["federal", "oklahoma", "kansas", "generic"],
        help="Jurisdiction for statutory language (auto-detected from the request facts when omitted)",
    )
    p_foia.add_argument(
        "--profile",
        help="Optional case profile (case_context.json) — pins THIS run to that case; omit for generic use",
    )
    p_foia.add_argument("--name", help="Requester name")
    p_foia.add_argument("--contact", help="Requester contact info")
    p_foia.add_argument("--method", help="Delivery method")
    p_foia.add_argument("--address", help="Agency mailing address")
    p_foia.set_defaults(func=cmd_foia, stdin=False)

    # ── analyze ──
    p_analyze = sub.add_parser(
        "analyze", help="IRAC legal analysis of a question (LWM gem)"
    )
    p_analyze.add_argument("question", help="Legal question to analyze")
    p_analyze.add_argument(
        "--jurisdiction",
        default=None,
        help="Jurisdiction (auto-detected from the question/facts when omitted)",
    )
    p_analyze.add_argument(
        "--profile",
        help="Optional case profile (case_context.json) — pins THIS run to that case; omit for generic use",
    )
    p_analyze.add_argument("--facts", help="File with relevant facts (one per line)")
    p_analyze.add_argument("--markdown", action="store_true", help="Output as Markdown")
    p_analyze.set_defaults(func=cmd_analyze)

    # ── regression ──
    p_reg = sub.add_parser("regression", help="Run conformance regression suite")
    p_reg.set_defaults(func=cmd_regression)

    # ── safe-draft ──
    p_safe = sub.add_parser(
        "safe-draft", help="DRAFT-blocked chain: audit + ack + generate"
    )
    p_safe.add_argument("intent", choices=sorted(safety.ACCEPTED_INTENTS))
    p_safe.add_argument("text_file", type=Path)
    p_safe.set_defaults(func=cmd_safe_draft)

    # ── demo ──
    p_demo = sub.add_parser("demo", help="Run self-rep litigant use cases")
    p_demo.add_argument("use_case", nargs="?", help="Specific use case name")
    p_demo.add_argument(
        "--list", dest="list_only", action="store_true", help="List cases and exit"
    )
    p_demo.set_defaults(func=cmd_demo, list_only=False)

    # ── record-audit (extraction layer, advisory) ──
    p_rec = sub.add_parser(
        "record-audit",
        help="extraction layer over a case record: citations, cross-reference, chronology, SOF-vs-record validation (advisory)",
    )
    p_rec.add_argument(
        "--doc", action="append", type=Path, default=[], help="Record document (.txt/.md); repeatable"
    )
    p_rec.add_argument("--sof", type=Path, help="Statement of Facts text file")
    p_rec.add_argument("--deposition", type=Path, help="Deposition transcript text file")
    p_rec.add_argument("--witness", help="Deponent name for --deposition")
    p_rec.add_argument("--case", help="Case name for deposition citations")
    p_rec.add_argument(
        "--llm", action="store_true",
        help="Enable model-backed semantic checks (free cloud cascade; requires keys)",
    )
    p_rec.add_argument("--json", action="store_true", help="Output raw JSON report")
    p_rec.set_defaults(func=cmd_record_audit)

    # ── case ──
    # No implicit profile: OutClaw stays general; the use case is named
    # explicitly on every invocation.
    p_case = sub.add_parser(
        "case", help="Render a case briefing from a profile (pass --profile)"
    )
    p_case.add_argument(
        "--profile",
        help="Path to a case profile JSON (e.g. case_context.json)",
    )
    p_case.set_defaults(func=cmd_case)

    # ── objections ──
    p_obj = sub.add_parser(
        "objections", help="Evidentiary objections with legal basis (Kansas rules included)"
    )
    p_obj.add_argument("--statement", required=True, help="The statement to analyze")
    p_obj.add_argument("--speaker", default="Witness", help="Who said it")
    p_obj.add_argument(
        "--role",
        choices=["witness", "attorney", "prosecutor", "judge"],
        default="witness",
    )
    p_obj.add_argument("--purpose", default="", help="Purpose offered: truth of the matter, impeachment, etc.")
    p_obj.add_argument("--jurisdiction", default=None, help="federal, kansas, oklahoma (auto-detected from the statement when omitted)")
    p_obj.add_argument("--state", default=None, help="State code (e.g. kansas) for state rules")
    p_obj.add_argument("--phase", default="trial", help="trial, voir_dire, opening, closing")
    p_obj.add_argument("--page", type=int, default=None, help="Transcript page")
    p_obj.add_argument("--line", type=int, default=None, help="Transcript line")
    p_obj.set_defaults(func=cmd_objections)

    # ── course (plain-language court-mechanics course for pro se litigants) ──
    p_course = sub.add_parser(
        "course",
        help="Plain-language court-mechanics course: lessons, prep tracks, glossary (advisory study material)",
    )
    p_course.add_argument(
        "--list", action="store_true", help="List all lessons and prep tracks"
    )
    p_course.add_argument("--lesson", help="Lesson key (e.g. the_record, objections)")
    p_course.add_argument(
        "--track",
        help="Prep track key (oral-argument, opening, closing, direct-exam, cross-exam, deposition)",
    )
    p_course.add_argument("--term", help="Plain-language glossary term lookup")
    p_course.add_argument("--pack", action="store_true", help="Full trial-prep pack (all tracks)")
    p_course.add_argument("--json", action="store_true", help="Output raw JSON")
    p_course.set_defaults(func=cmd_course)

    # ── grievance ──
    p_gr = sub.add_parser(
        "grievance", help="Generate a bar grievance package (citation fraud etc.)"
    )
    p_gr.add_argument("--attorney", required=True, help="Attorney name being grieved")
    p_gr.add_argument("--bar", help="Bar number")
    p_gr.add_argument("--state", default=None, help="State for the bar discipline body (default: profile state or kansas)")
    p_gr.add_argument("--firm", help="Firm name")
    p_gr.add_argument("--address")
    p_gr.add_argument("--case", help="Case number")
    p_gr.add_argument("--complainant", default="Pro Se Litigant")
    p_gr.add_argument("--evidence-file", help="JSON list of fraud-evidence dicts, or an `outclaw audit --json` report")
    p_gr.add_argument("--citation", help="Citation string for a single evidence item")
    p_gr.add_argument("--issue-type", default="fabricated")
    p_gr.add_argument("--severity", default="HIGH")
    p_gr.add_argument("--description", default="")
    p_gr.add_argument("--document", default="", help="Where the citation appeared")
    p_gr.set_defaults(func=cmd_grievance)

    # ── complaint ──
    p_cp = sub.add_parser(
        "complaint", help="Generate a judicial misconduct complaint (state commissions incl. Kansas)"
    )
    p_cp.add_argument("--judge", required=True, help="Judge name")
    p_cp.add_argument("--court", default="Sumner County District Court")
    p_cp.add_argument("--state", default=None, help="State (e.g. kansas) for the state judicial commission")
    p_cp.add_argument("--case", help="Case number")
    p_cp.add_argument("--complainant", default="Pro Se Litigant")
    p_cp.add_argument("--evidence-file", help="JSON list of misconduct-evidence dicts")
    p_cp.add_argument("--incident", help="Single incident description (no evidence-file needed)")
    p_cp.add_argument("--date", help="Incident date, ISO format (default: today)")
    p_cp.add_argument("--evidence", help="Supporting evidence note (e.g. 'Transcript p.12')")
    p_cp.add_argument("--severity", default="MEDIUM", choices=["HIGH", "MEDIUM", "LOW"])
    p_cp.set_defaults(func=cmd_complaint)

    # ── guide ──
    p_gd = sub.add_parser(
        "guide", help="Pro se survival guide + deadline calculator"
    )
    p_gd.add_argument("--concept", help="Print one concept (see --list)")
    p_gd.add_argument("--list", action="store_true", help="List concept keys")
    p_gd.add_argument("--deadline", type=int, help="Calculate a deadline: days allowed")
    p_gd.add_argument("--trigger", help="Trigger date YYYY-MM-DD (default today)")
    p_gd.add_argument("--mail", action="store_true", help="Add mail-service days")
    p_gd.set_defaults(func=cmd_guide)

    # ── impact ──
    p_im = sub.add_parser(
        "impact", help="'So what?' reality check on grievance evidence"
    )
    p_im.add_argument("--evidence-file", help="JSON list of fraud-evidence dicts")
    p_im.add_argument("--grievances", type=int, default=0, help="Prior grievance count")
    p_im.add_argument("--financial-harm", type=float, default=0)
    p_im.add_argument("--sanctions", action="store_true", help="Court sanctions already imposed")
    p_im.add_argument("--citation", help="Single citation string")
    p_im.add_argument("--issue-type", default="fabricated")
    p_im.add_argument("--severity", default="HIGH")
    p_im.add_argument("--description", default="")
    p_im.set_defaults(func=cmd_impact)

    # ── statute ──
    p_st = sub.add_parser(
        "statute", help="Fetch current Kansas statute text (kslegislature.org)"
    )
    p_st.add_argument("cite", help="e.g. 'K.S.A. 21-5413' or '22-3716'")
    p_st.add_argument("--out", help="Save text to file")
    p_st.set_defaults(func=cmd_statute)

    # ── evidence-chart ──
    p_ec = sub.add_parser(
        "evidence-chart", help="Statement-by-statement evidence chart"
    )
    p_ec.add_argument("file", type=Path, help="Transcript or narrative text file")
    p_ec.add_argument("--out", help="Save chart to file")
    p_ec.add_argument("--csv", action="store_true", help="CSV output")
    p_ec.set_defaults(func=cmd_evidence_chart)

    # ── transcript-search ──
    p_ts = sub.add_parser(
        "transcript-search", help="Find key terms in a transcript"
    )
    p_ts.add_argument("file", type=Path, help="Transcript text file")
    p_ts.add_argument("--terms", help="Comma-separated terms (default: good cause, unavailable, confront, cross-examine, hearsay, objection, sustained, overruled, unsworn, foundation)")
    p_ts.add_argument("--out", help="Save report to file")
    p_ts.set_defaults(func=cmd_transcript_search)

    # ── ingest ──
    p_in = sub.add_parser(
        "ingest", help="Scan a case folder into case_record.json (OCR when available)"
    )
    p_in.add_argument("--dir", default="mel", help="Case folder (default: mel)")
    p_in.add_argument("--out", help="Output record path (default: <dir>/case_record.json)")
    p_in.add_argument("--no-ocr", action="store_true", help="Skip OCR of images (faster on big folders)")
    p_in.set_defaults(func=cmd_ingest)

    # ── briefify ──
    p_bf = sub.add_parser(
        "briefify", help="Plain-English briefing from research + record"
    )
    p_bf.add_argument("--research", help="Research dossier JSON (case_law_*.json)")
    p_bf.add_argument("--record", help="case_record.json from ingest")
    p_bf.add_argument("--profile", help="Case profile for header/issues")
    p_bf.add_argument("--out", help="Save briefing to file")
    p_bf.set_defaults(func=cmd_briefify)

    # ── cascade ──
    p_cascade = sub.add_parser(
        "cascade",
        help="Stair-stepped model cascade: status, live test",
    )
    p_cascade.add_argument(
        "--test", metavar="PROMPT",
        help="Fire a prompt through the cascade and print the escalation trail",
    )
    p_cascade.add_argument(
        "--task", default="opposite_holding",
        help="Cascade task id for --test (default: opposite_holding)",
    )
    p_cascade.add_argument(
        "--min-confidence", type=float, default=0.0,
        help="Minimum confidence to accept a tier result (0.0-1.0)",
    )
    p_cascade.add_argument(
        "--json", action="store_true", help="Output raw JSON status",
    )
    p_cascade.set_defaults(func=cmd_cascade)

    return p


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
