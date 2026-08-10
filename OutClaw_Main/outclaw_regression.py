#!/usr/bin/env python3
"""
outclaw_regression.py -- conformance runner for the OutClaw regression suite.

Reads outclaw_seed.json for both the original 7-case recovery suite AND the
4 adversarial ops (extracted from depth_detector.py at build time), then
runs every case through the depth detector standalone AND through the
OutClaw unified orchestrator. Reports the conformance delta as a single
table so an operator can see exactly what the orchestrator's adapter
recovers (and what it doesn't).

Post-review fixes (this revision):
  * Removed the dead "_CaseOutcome" @dataclass-comment class. Rows are
    always returned as plain dicts, by convention since the runner only
    feeds them into the table renderer.
  * Cached seed load at module top -- not per-case.
  * Tighter default failure exit (1) so CI pickup is deterministic.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import outclaw_depth_detector as depth_mod  # type: ignore
import outclaw_unified as unified  # type: ignore

SEVERITY_RANK = {"OK": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


# Module-level cached seed -- opens the JSON file once at import time so a
# regression expansion (e.g. 200 cases) does not re-parse per case.
_SEED: dict[str, Any] | None = None


# ═══════════════════════════════════════════════════════
#  OUTCLAW_REGRESSION
# ═══════════════════════════════════════════════════════════════

def _get_seed() -> dict[str, Any]:
    global _SEED
    if _SEED is None:
        _SEED = unified.load_seed()
    return _SEED


def _depth_only_outcome(text: str) -> tuple[bool, list[str]]:
    """Run depth_mod standalone and report pass/fail + failing-citation reasons."""
    semantic = depth_mod.SemanticValidator()
    unified.inject_seed_into_seed(semantic, _get_seed())
    rep = semantic.validate_text(text)
    failed = [f for f in rep["findings"] if not f["ok"]]
    return (len(failed) == 0), [f"{f['citation']}|{f['rule']}" for f in failed]


def _unified_outcome(text: str) -> dict[str, Any]:
    """Run the unified orchestrator and shape the verdict for the runner."""
    rep = unified.audit_text(text, seed=_get_seed())
    return {
        "highest_severity": max(
            (f.severity for f in rep.findings),
            default=unified.OK,
            key=lambda s: SEVERITY_RANK[s],
        ),
        "findings_count": len(rep.findings),
        "safe_to_draft": rep.safe_to_draft(),
        "recovered_by_window": sum(1 for f in rep.findings if f.recovered_by_window),
        "high_count": sum(1 for f in rep.findings if f.severity == unified.HIGH),
    }


def _run_all() -> list[dict[str, Any]]:
    seed = _get_seed()
    cases = seed["regression"] + seed["adversarial"]

    rows: list[dict[str, Any]] = []
    for case in cases:
        text = case["text"]
        expected = case["expected_severity"]
        depth_passed, depth_reasons = _depth_only_outcome(text)
        uo = _unified_outcome(text)
        match = uo["highest_severity"] == expected
        notes = (
            ["OK"]
            if match
            else [
                f"severity {uo['highest_severity']} differs from expected {expected}",
                f"depth-only reasons: {depth_reasons}",
            ]
        )
        rows.append(
            {
                "case_id": case["id"],
                "label": case["label"],
                "expected": expected,
                "depth_only": "PASS" if depth_passed else "FAIL",
                "depth_reasons": depth_reasons,
                "unified": uo,
                "notes": notes,
            }
        )
    return rows


def _table(rows: list[dict[str, Any]]) -> str:
    headers = ["ID", "label", "expected", "depth-only", "unified", "delta"]
    lines = [f"  {h:<26}" for h in headers]
    lines[0] = lines[0].rstrip()
    lines.append("-" * 130)
    for r in rows:
        u = r["unified"]
        u_summary = (
            f"{u['highest_severity']} "
            f"(R={u['recovered_by_window']}; H={u['high_count']})"
        )
        delta = "OK" if u["highest_severity"] == r["expected"] else "FAIL"
        lines.append(
            f"  {r['case_id']:<26}"
            f"  {r['label'][:26]:<26}"
            f"  {r['expected']:<26}"
            f"  {r['depth_only']:<26}"
            f"  {u_summary:<26}"
            f"  {delta:<26}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    started = time.time()
    rows = _run_all()
    print(_table(rows))
    print()
    coverage = sum(1 for r in rows if r["unified"]["highest_severity"] == r["expected"])
    total = len(rows)
    elapsed = time.time() - started
    print(f"Conformance: {coverage}/{total} cases matched expected severity.")
    print(f"Elapsed:     {elapsed:.3f}s")
    if coverage != total:
        for r in rows:
            if r["unified"]["highest_severity"] != r["expected"]:
                print(
                    f"  case {r['case_id']} ({r['label']}): expected {r['expected']}, "
                    f"got {r['unified']['highest_severity']}; notes: {r['notes']}"
                )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
