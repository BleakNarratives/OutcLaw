"""
test_use_cases.py -- Conformance tests for OutClaw self-rep use cases.

Each scenario must:
  1. Produce a HIGH-severity finding (audit not silent).
  2. Surface every expected rule (no missed expectation).
  3. Yield safe_to_draft=False (the DRAFT-block chain would refuse to file).

If any test here fails, the value-prop of the demo collapses -- the
audit would have let the bad cite slip past a self-rep litigant.
"""

import sys
import unittest
from pathlib import Path

# Add OutClaw/ to sys.path so 'outclaw_use_cases' resolves from this test
# file's location (OutClaw/outclaw_tests/). Mirrors the existing pattern in
# test_orchestrator.py / test_bus.py / test_regression.py.
_HERE = Path(__file__).resolve().parent
_OUTCLAW = _HERE.parent
for _p in (str(_OUTCLAW), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import outclaw_use_cases as use_cases


class TestUseCaseSchema(unittest.TestCase):
    def test_three_use_cases_are_registered(self):
        names = use_cases.list_use_cases()
        self.assertEqual(
            names,
            [
                "landlord_retaliation",
                "debt_collection_standing",
                "employment_discrimination_ada",
            ],
        )

    def test_each_use_case_has_nonempty_text(self):
        for name in use_cases.list_use_cases():
            case = use_cases.get_use_case(name)
            self.assertIsNotNone(case)
            self.assertGreater(
                len(case.sample_text.strip()),
                50,
                f"{name} sample text is too short to be a real draft",
            )
            self.assertGreater(len(case.title), 5)
            self.assertGreater(len(case.description), 20)


class TestUseCaseVerdicts(unittest.TestCase):
    """One test per scenario. Failing here = demo is no longer GREEN."""

    def _assert_passed(self, name: str):
        case = use_cases.get_use_case(name)
        self.assertIsNotNone(
            case,
            f"Unknown use case: {name!r}. Available: {use_cases.list_use_cases()}",
        )
        verdict = use_cases.run_use_case(name)
        self.assertTrue(
            verdict["passed"],
            f"Use case {name} did not pass: {verdict}",
        )
        # Dynamic: read expected_min_severity per use case (round 23 fix).
        # Read the configured threshold per scenario; fixtures intentionally
        # cover both fabricated/opposite HIGH findings and overruled HIGH
        # findings without hardcoding one global rule.
        self.assertEqual(
            verdict["actual_highest"],
            case.expected_min_severity,
            f"{name} should be {case.expected_min_severity} "
            f"but is {verdict['actual_highest']}",
        )
        self.assertEqual(
            verdict["safe_to_draft"],
            False,
            f"{name} should NOT be safe_to_draft",
        )
        # HIGH-expected cases must surface at least one HIGH finding;
        # otherwise match_severity could pass against a degenerate
        # orchestrator.
        if case.expected_min_severity == "HIGH":
            self.assertGreaterEqual(
                verdict["high_count"],
                1,
                f"{name} expects HIGH but orchestrator emitted 0 HIGH findings",
            )
        for r in verdict["expected_rules"]:
            self.assertIn(
                r,
                verdict["actual_rules"],
                f"{name} expected rule {r!r} missing (actual: {verdict['actual_rules']})",
            )

    def test_landlord_retaliation(self):
        self._assert_passed("landlord_retaliation")

    def test_debt_collection_standing(self):
        self._assert_passed("debt_collection_standing")

    def test_employment_discrimination_ada(self):
        self._assert_passed("employment_discrimination_ada")


class TestUseCaseNegative(unittest.TestCase):
    def test_unknown_use_case_raises(self):
        with self.assertRaises(ValueError):
            use_cases.run_use_case("nonexistent_use_case")


if __name__ == "__main__":
    unittest.main()
