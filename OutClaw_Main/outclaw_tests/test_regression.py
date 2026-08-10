"""
OutClaw regression runner tests (post-review):
  - test_case_six_matches_expected_after_window now requires OK (was permissive)
  - seed structure validated
  - dynamic injection verified
  - regression runner handles the full 11-case suite without dead code
"""

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOP = _HERE.parent.parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_TOP))

import outclaw_depth_detector as depth_mod
import outclaw_regression as regression
import outclaw_unified as unified


class TestSeedStructure(unittest.TestCase):
    def test_regression_has_7_baseline(self):
        seed = unified.load_seed()
        self.assertEqual(len(seed["regression"]), 7)

    def test_adversarial_min_4(self):
        seed = unified.load_seed()
        self.assertGreaterEqual(len(seed["adversarial"]), 4)

    def test_case_ids_unique(self):
        seed = unified.load_seed()
        all_cases = seed["regression"] + seed["adversarial"]
        ids = [c["id"] for c in all_cases]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate ids in seed: {ids}")

    def test_every_case_has_expected_severity(self):
        seed = unified.load_seed()
        for c in seed["regression"] + seed["adversarial"]:
            self.assertIn(c["expected_severity"], unified.SEVERITY_ORDER)


class TestDynamicSeedInjection(unittest.TestCase):
    def test_seed_keys_present_in_depth_validator(self):
        seed = unified.load_seed()
        sv = depth_mod.SemanticValidator()
        unified.inject_seed_into_seed(sv, seed)
        for citation in seed["cases"].keys():
            self.assertIn(
                " ".join(citation.split()),
                sv.case_db,
                f"seed case '{citation}' missing from case_db after injection",
            )

    def test_seed_injection_overrides_default(self):
        # Sanity: the default CASE_DB has Smith v. Jones; ours has the same
        # key but a different holding. Override must take.
        seed = unified.load_seed()
        sv = depth_mod.SemanticValidator()
        unified.inject_seed_into_seed(sv, seed)
        # If default DB still in place, would still see 123 F.3d 456 = Smith v Jones.
        # After override, the holding should match seed phrases about 4th Amendment.
        self.assertIn("123 F.3d 456", sv.case_db)
        self.assertIn("Fourth Amendment", sv.case_db["123 F.3d 456"].holding)


class TestConformance(unittest.TestCase):
    def test_runner_returns_rows(self):
        rows = regression._run_all()
        seed = unified.load_seed()
        expected_total = len(seed["regression"]) + len(seed["adversarial"])
        self.assertEqual(len(rows), expected_total)

    def test_case_six_matches_ok_after_disambiguation_and_window(self):
        # The orchestrator MUST mark case 6 (cross-sentence valid citation) as OK.
        # Earlier permissive assertion accepted {OK, MEDIUM}; after the
        # disambiguator + sentence-window adapter, OK is the only acceptable.
        rows = regression._run_all()
        row = next(r for r in rows if r["case_id"] == 6)
        self.assertEqual(row["expected"], "OK")
        self.assertEqual(
            row["unified"]["highest_severity"],
            "OK",
            f"case 6 must be OK after orchestrator disambiguation + window; "
            f"got {row['unified']['highest_severity']}",
        )

    def test_runner_command_full_conformance(self):
        import contextlib
        from io import StringIO

        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            rc = regression.main([])
        # All 11 cases should match — if any don't, rc=1 and stdout surfaces the delta.
        self.assertEqual(rc, 0, f"runner exited {rc}; stdout:\n{buf.getvalue()[-400:]}")


if __name__ == "__main__":
    unittest.main()
