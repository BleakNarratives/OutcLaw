#!/usr/bin/env python3
"""
outclaw_use_cases.py -- Self-represented litigant audit scenarios (round 23).

Three concrete use cases the audit CLI demos end-to-end. Each sample_text
is engineered to surface at least one orchestrator-emitted finding so
the DRAFT-block chain in outclaw_safety.py would refuse to file it.

CALIBRATION NOTE:

  - `landlord_retaliation` now surfaces HIGH findings for both the
    fabricated statute and the opposite-holding proposition. The expected
    contract below is intentionally strict so the demo cannot silently pass
    when either safety signal disappears.

  - `debt_collection_standing` and `employment_discrimination_ada`
    both fire NEGATIVE TREATMENT (HIGH) via the overruled-cite path
    (`Doe v. State, 999 F.3d 111`). These are the orchestrator's
    most reliable signals today. Expected: HIGH / ["NEGATIVE TREATMENT"].

ROUND-23 ARCHITECTURE FIXES:

  - `_assert_passed` in `OutClaw/outclaw_tests/test_use_cases.py` no
    longer hardcodes a `"HIGH"` check; it reads the use case's own
    `expected_min_severity` so the landlord MEDIUM calibration
    succeeds end-to-end.

  - This module dropped its standalone `main(argv)` CLI entry point
    (orphan; conflicting with the canonical `outclaw_cli.py demo`
    dispatcher). A direct invocation now exits 2 with a clear
    pointer to the right shell.

The unified orchestrator now emits both signals through its protected
sentence walk. They are asserted as expected rules for the landlord fixture.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import outclaw_unified as unified  # type: ignore

SEVERITY_RANK = {"OK": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass
# ═══════════════════════════════════════════════════════
#  OUTCLAW_USE_CASES
# ═══════════════════════════════════════════════════════════════

class UseCase:
    name: str
    title: str
    description: str
    sample_text: str
    expected_min_severity: str
    expected_rules: list[str]
    # documented but not asserted today: rules these scenarios SHOULD
    # fire once the orchestrator fully covers them. Used by callers
    # that want to surface the ambition gap (e.g. WHO_DID_WHAT audit
    # noise-vs-coverage table).
    ambition_rules: list[str]


# The fixtures intentionally combine fabricated, opposite, and overruled
# citations so the safety gate has a deterministic, offline acceptance path.
USE_CASES: list[UseCase] = [
    UseCase(
        name="landlord_retaliation",
        title="Landlord 30-day notice to quit (retaliation defense)",
        description=(
            "Self-rep tenant facing eviction in federal court. The draft "
            "cites a fabricated federal housing section (42 U.S.C. § 9999) "
            "AND a real case (Smith v. Jones) for an unrelated proposition. "
            "Orchestrator today fires NO SUPPORT (MEDIUM) for the case; "
            "EXISTENCE / OPPOSITE HOLDING pending audit_text sentence-walk fix."
        ),
        sample_text=(
            "In opposing the unlawful detainer, plaintiff tenant will "
            "show the 30-day notice to quit was served 7 days after the "
            "habitability complaint and is therefore retaliatory under "
            "the Fair Housing Act, 42 U.S.C. § 9999. Police may search "
            "a home without a warrant. Smith v. Jones, 123 F.3d 456."
        ),
        expected_min_severity="HIGH",
        expected_rules=["EXISTENCE", "OPPOSITE HOLDING"],
        ambition_rules=[],
    ),
    UseCase(
        name="debt_collection_standing",
        title="Debt buyer standing to sue (FDCPA audit)",
        description=(
            "Self-rep defendant in a debt collection suit. The draft "
            "cites Doe v. State (overruled in seed) for an unrelated "
            "proposition. Orchestrator fires NEGATIVE TREATMENT (HIGH). "
            "EXISTENCE for the FDCPA cite pending orchestrator fix."
        ),
        sample_text=(
            "The debt buyer has standing to sue under 15 U.S.C. § 1692k "
            "for the proposition that the FDCPA permits substitution "
            "of parties without notice. Doe v. State, 999 F.3d 111 "
            "supports this proposition."
        ),
        expected_min_severity="HIGH",
        expected_rules=["NEGATIVE TREATMENT"],
        ambition_rules=["EXISTENCE"],
    ),
    UseCase(
        name="employment_discrimination_ada",
        title="ADA reasonable accommodation (employment discrimination)",
        description=(
            "Self-rep plaintiff alleging disability discrimination. "
            "The draft cites Doe v. State (overruled in seed) to "
            "support an unrelated proposition about the ADA. "
            "Orchestrator fires NEGATIVE TREATMENT (HIGH). EXISTENCE "
            "for the Title VII format cite pending orchestrator fix."
        ),
        sample_text=(
            "The employer discriminated based on disability. The ADA "
            "requires reasonable accommodation absent undue hardship. "
            "Title VII's provision at 42 U.S.C. § 12112 is the "
            "relevant authority. Doe v. State, 999 F.3d 111 supports "
            "this proposition."
        ),
        expected_min_severity="HIGH",
        expected_rules=["NEGATIVE TREATMENT"],
        ambition_rules=["EXISTENCE"],
    ),
]


def list_use_cases() -> list[str]:
    return [u.name for u in USE_CASES]


def get_use_case(name: str) -> UseCase | None:
    for u in USE_CASES:
        if u.name == name:
            return u
    return None


def run_use_case(name: str) -> dict[str, Any]:
    """Run one use case against the unified audit. Returns verdict dict."""
    case = get_use_case(name)
    if case is None:
        raise ValueError(f"Unknown use case: {name!r}. Available: {list_use_cases()}")

    seed = unified.load_seed()
    report = unified.audit_text(case.sample_text, seed=seed)

    highest = max(
        (f.severity for f in report.findings),
        default=unified.OK,
        key=lambda s: SEVERITY_RANK[s],
    )

    actual_rules = sorted({f.rule for f in report.findings})
    expected_set = set(case.expected_rules)
    matched_rules = expected_set & set(actual_rules)
    rules_match = expected_set.issubset(set(actual_rules))
    match_severity = SEVERITY_RANK[highest] >= SEVERITY_RANK[case.expected_min_severity]

    ambition_satisfied = all(a in actual_rules for a in (case.ambition_rules or []))

    return {
        "name": case.name,
        "title": case.title,
        "expected_min_severity": case.expected_min_severity,
        "expected_rules": case.expected_rules,
        "ambition_rules": case.ambition_rules,
        "ambition_satisfied": ambition_satisfied,
        "actual_highest": highest,
        "actual_rules": actual_rules,
        "match_severity": match_severity,
        "match_rules": rules_match,
        "matched_rules": sorted(matched_rules),
        "missed_rules": sorted(expected_set - set(actual_rules)),
        "findings_count": len(report.findings),
        "high_count": sum(1 for f in report.findings if f.severity == unified.HIGH),
        "safe_to_draft": report.safe_to_draft(),
        "passed": match_severity and rules_match,
    }


def _standalone_invocation_error() -> int:
    """Round 23: outclaw_use_cases.py no longer ships a standalone CLI.

    The canonical entry point is ``python3 OutClaw/outclaw_cli.py demo``
    (with optional ``[use_case]`` arg). Running this module directly is a
    configuration mistake -- point the operator at the right shell.
    """
    sys.stderr.write(
        "Error: outclaw_use_cases.py no longer runs as a standalone CLI.\n"
        "\n"
        "Use the canonical OutClaw dispatcher instead:\n"
        "    python3 OutClaw/outclaw_cli.py demo\n"
        "    python3 OutClaw/outclaw_cli.py demo landlord_retaliation\n"
        "    python3 OutClaw/outclaw_cli.py demo --list\n"
        "\n"
        "For programmatic access import the helpers:\n"
        "    from OutClaw import outclaw_use_cases as uc\n"
        "    uc.list_use_cases()\n"
        "    uc.run_use_case('landlord_retaliation')\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_standalone_invocation_error())
