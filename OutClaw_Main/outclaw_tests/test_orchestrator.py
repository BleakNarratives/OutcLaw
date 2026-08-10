"""
OutClaw orchestrator tests.

Post-review fixes:
  - AckToken objects (not bare strings) are passed end-to-end.
  - Fingerprint-mismatch path is tested as a SECURITY invariant.
  - OPPOSITE HOLDING disambiguation (re-label to NO SUPPORT when the
    actual negation flip is absent) is tested directly.
  - SeverityFromRule unknowns now default to MEDIUM (no silent LOW).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

import outclaw_depth_detector as depth_mod
import outclaw_safety as safety
import outclaw_unified as unified


class TestSeverityFromRule(unittest.TestCase):
    def test_existence_is_high(self):
        self.assertEqual(unified.severity_from_rule("EXISTENCE", False), unified.HIGH)

    def test_negative_treatment_is_high(self):
        self.assertEqual(
            unified.severity_from_rule("NEGATIVE TREATMENT", False), unified.HIGH
        )

    def test_no_support_is_medium(self):
        self.assertEqual(
            unified.severity_from_rule("NO SUPPORT", False), unified.MEDIUM
        )

    def test_misquote_is_high(self):
        self.assertEqual(
            unified.severity_from_rule("MISQUOTE / OPPOSITE", False), unified.HIGH
        )

    def test_supported_is_ok(self):
        self.assertEqual(unified.severity_from_rule("SUPPORTED", True), unified.OK)

    def test_unknown_failure_defaults_to_medium(self):
        # Per code review: never silently downgrade to LOW.
        self.assertEqual(
            unified.severity_from_rule("WEIRD UNKNOWN RULE", False), unified.MEDIUM
        )


class TestOppositeHoldingDisambiguation(unittest.TestCase):
    def test_opposite_holding_relabels_when_no_flip(self):
        # depth_mod labels support==0.0 as OPPOSITE HOLDING, even when
        # there's just no word overlap. The orchestrator must re-check.
        finding = {
            "rule": "OPPOSITE HOLDING",
            "citation": "555 F.3d 789",
            "sentence": "Miller v. Acme Corp., 555 F.3d 789.",
        }
        case_db = {
            "555 F.3d 789": depth_mod.CaseEntry(
                name="Miller v. Acme Corp.",
                holding=(
                    "A plaintiff may recover punitive damages under \u00a7 1983 "
                    "only on proof of malice or reckless disregard."
                ),
                overruled=False,
            ),
        }
        corrected_rule, flip_score = unified._disambiguate_rule(
            finding, case_db, statute_db={}
        )
        self.assertEqual(
            corrected_rule,
            "NO SUPPORT",
            "no negation flip in finding should produce NO SUPPORT",
        )
        self.assertEqual(flip_score, 0.0)

    def test_opposite_holding_kept_when_negation_present(self):
        # If the holding has a 'not' and the proposition drops it, keep
        # OPPOSITE HOLDING.
        finding = {
            "rule": "OPPOSITE HOLDING",
            "citation": "555 F.3d 789",
            "sentence": (
                "Policymakers may not require proof of malice. "
                "Miller v. Acme Corp., 555 F.3d 789."
            ),
        }
        case_db = {
            "555 F.3d 789": depth_mod.CaseEntry(
                name="Miller v. Acme Corp.",
                holding=("Policymakers must not require proof of malice."),
                overruled=False,
            ),
        }
        corrected_rule, flip_score = unified._disambiguate_rule(
            finding, case_db, statute_db={}
        )
        self.assertEqual(
            corrected_rule, "OPPOSITE HOLDING", "real negation flip should be preserved"
        )


class TestSeedLoading(unittest.TestCase):
    def test_seed_loads(self):
        seed = unified.load_seed()
        self.assertIn("cases", seed)
        self.assertIn("statutes", seed)
        self.assertIn("regression", seed)
        self.assertIn("adversarial", seed)
        self.assertGreaterEqual(len(seed["regression"]), 7)

    def test_injection_overrides_default_db(self):
        seed = {
            "cases": {"999 F.3d 111": {"name": "X", "holding": "y", "overruled": True}},
            "statutes": {},
        }
        sv = depth_mod.SemanticValidator()
        self.assertIn("123 F.3d 456", sv.case_db)
        unified.inject_seed_into_seed(sv, seed)
        self.assertIn("999 F.3d 111", sv.case_db)
        self.assertNotIn("123 F.3d 456", sv.case_db)


class TestSentenceWindowAdapter(unittest.TestCase):
    def setUp(self):
        seed = unified.load_seed()
        self.case_db = {
            k: depth_mod.CaseEntry(
                name=v["name"],
                holding=v["holding"],
                overruled=bool(v.get("overruled", False)),
                area=v.get("area", "general"),
            )
            for k, v in seed["cases"].items()
        }
        self.statute_db = dict(seed["statutes"])

    def _mk_finding(self, citation, rule, severity, sentence):
        return {
            "citation": citation,
            "rule": rule,
            "severity": severity,
            "sentence": sentence,
            "detail": "",
            "score": 0.0,
        }

    def test_no_op_on_high_severity(self):
        text = (
            "Police may search a home without a warrant. Smith v. Jones, 123 F.3d 456."
        )
        findings = [
            self._mk_finding(
                "123 F.3d 456",
                "OPPOSITE HOLDING",
                unified.HIGH,
                "Police may search a home without a warrant. Smith v. Jones, 123 F.3d 456.",
            ),
        ]
        out = unified.SentenceWindowAdapter.rescore(
            findings, text, self.case_db, self.statute_db
        )
        self.assertEqual(out[0].severity, unified.HIGH)
        self.assertFalse(out[0].recovered_by_window)

    def test_no_op_on_ok_finding(self):
        text = "Miller v. Acme Corp., 555 F.3d 789 supports this proposition."
        findings = [self._mk_finding("555 F.3d 789", "SUPPORTED", unified.OK, text)]
        out = unified.SentenceWindowAdapter.rescore(
            findings, text, self.case_db, self.statute_db
        )
        self.assertEqual(out[0].severity, unified.OK)
        self.assertFalse(out[0].recovered_by_window)

    def test_no_op_when_sentence_not_in_text(self):
        # If the finding's sentence isn't in our text (it's a different
        # snapshot), don't crash; just leave the finding untouched.
        text = "Some completely different content here. No citations at all."
        findings = [
            self._mk_finding(
                "555 F.3d 789", "NO SUPPORT", unified.MEDIUM, "Ghost sentence."
            )
        ]
        out = unified.SentenceWindowAdapter.rescore(
            findings, text, self.case_db, self.statute_db
        )
        self.assertEqual(out[0].severity, unified.MEDIUM)
        self.assertFalse(out[0].recovered_by_window)


class TestUnifiedReport(unittest.TestCase):
    def test_safe_to_draft_blocks_on_high(self):
        report = unified.UnifiedReport(
            text="x",
            findings=[
                unified.Finding(
                    citation="123 F.3d 456",
                    rule="OPPOSITE HOLDING",
                    severity=unified.HIGH,
                    sentence="...",
                    detail="...",
                ),
                unified.Finding(
                    citation="42 U.S.C. \u00a7 1983",
                    rule="SUPPORTED",
                    severity=unified.OK,
                    sentence="...",
                    detail="...",
                ),
            ],
        )
        self.assertFalse(report.safe_to_draft())

    def test_safe_to_draft_passes_on_clean(self):
        report = unified.UnifiedReport(text="x")
        self.assertTrue(report.safe_to_draft())


class TestAuditText(unittest.TestCase):
    def test_audit_text_clean_case_after_disambiguation(self):
        # Case 6: cross-sentence valid citation. The orchestrator must
        # disambiguate OPPOSITE HOLDING -> NO SUPPORT (MEDIUM), then the
        # sentence-window adapter recovers it to OK.
        text = (
            "A plaintiff may recover punitive damages under \u00a7 1983 only on "
            "proof of malice or reckless disregard. Miller v. Acme Corp., 555 F.3d 789."
        )
        rep = unified.audit_text(text)
        # No HIGH findings, and at least one OK or "SUPPORTED (via sentence-window)".
        rules = {f.rule for f in rep.findings}
        self.assertTrue(
            any("SUPPORTED" in r for r in rules),
            f"expected at least one SUPPORTED finding; got {rules}",
        )
        high = [f for f in rep.findings if f.severity == unified.HIGH]
        self.assertEqual(high, [], "clean case must produce no HIGH findings")

    def test_audit_text_opposite_holding(self):
        text = (
            "Police may search a home without a warrant. Smith v. Jones, 123 F.3d 456."
        )
        rep = unified.audit_text(text)
        self.assertTrue(any(f.severity == unified.HIGH for f in rep.findings))


class TestSafetyShell(unittest.TestCase):
    def test_intent_rejected_on_unknown(self):
        with self.assertRaises(safety.IntentRejected):
            safety.safe_generate_document("draft_random_thing", "Some text", ack=None)

    def test_blocked_on_high_finding(self):
        text = (
            "Police may search a home without a warrant. Smith v. Jones, 123 F.3d 456."
        )
        ack = safety.request_ack_token("draft_1983_complaint", text)
        with self.assertRaises(safety.GenerateDocumentBlocked):
            safety.safe_generate_document("draft_1983_complaint", text, ack=ack)

    def test_blocked_on_clean_without_token(self):
        clean = (
            "A plaintiff may recover punitive damages under \u00a7 1983 only on "
            "proof of malice or reckless disregard. Miller v. Acme Corp., 555 F.3d 789."
        )
        with self.assertRaises(safety.GenerateDocumentBlocked):
            safety.safe_generate_document("draft_1983_complaint", clean, ack=None)

    def test_interactive_gate_audits_before_issuing_token(self):
        text = (
            "Police may search a home without a warrant. Smith v. Jones, 123 F.3d 456."
        )
        with patch.object(safety, "request_ack_token") as request_token:
            with self.assertRaises(safety.GenerateDocumentBlocked) as ctx:
                safety.interactive_request_and_verify("draft_1983_complaint", text)
        request_token.assert_not_called()
        self.assertIn("pre-audit blocked", str(ctx.exception))
        self.assertTrue(ctx.exception.unresolved)

    def test_interactive_gate_audits_exactly_once(self):
        clean = "This clean interactive draft has no citations."
        ack = safety.request_ack_token("draft_affidavit", clean)
        with patch.object(safety, "request_ack_token", return_value=ack):
            with patch("builtins.input", return_value=ack.token):
                with patch.object(
                    safety.unified,
                    "audit_text",
                    wraps=safety.unified.audit_text,
                ) as audit:
                    safety.interactive_request_and_verify("draft_affidavit", clean)
        self.assertEqual(audit.call_count, 1)

    def test_interactive_gate_accepts_matching_token(self):
        clean = "This clean interactive draft has no citations."
        ack = safety.request_ack_token("draft_affidavit", clean)
        with patch.object(safety, "request_ack_token", return_value=ack):
            with patch("builtins.input", return_value=ack.token):
                trace = safety.interactive_request_and_verify("draft_affidavit", clean)
        self.assertEqual(trace.outcome, "audit-clean-ack-verified")
        self.assertTrue(ack.consumed)

    def test_interactive_gate_rejects_mismatched_token(self):
        clean = "This clean interactive draft has no citations."
        ack = safety.request_ack_token("draft_affidavit", clean)
        with patch.object(safety, "request_ack_token", return_value=ack):
            with patch("builtins.input", return_value="0000-0000"):
                with patch.object(
                    safety.unified,
                    "audit_text",
                    wraps=safety.unified.audit_text,
                ) as audit:
                    with self.assertRaises(safety.GenerateDocumentBlocked) as ctx:
                        safety.interactive_request_and_verify("draft_affidavit", clean)
        self.assertEqual(audit.call_count, 1)
        self.assertIn("did not match", str(ctx.exception))
        self.assertFalse(ack.consumed)

    def test_interactive_gate_eof_audits_once(self):
        clean = "This clean interactive draft has no citations."
        ack = safety.request_ack_token("draft_affidavit", clean)
        with patch.object(safety, "request_ack_token", return_value=ack):
            with patch("builtins.input", side_effect=EOFError):
                with patch.object(
                    safety.unified,
                    "audit_text",
                    wraps=safety.unified.audit_text,
                ) as audit:
                    with self.assertRaises(safety.GenerateDocumentBlocked) as ctx:
                        safety.interactive_request_and_verify("draft_affidavit", clean)
        self.assertEqual(audit.call_count, 1)
        self.assertIn("non-interactive", str(ctx.exception))
        self.assertFalse(ack.consumed)

    def test_passes_with_matching_ack_after_clean_audit(self):
        clean = (
            "A plaintiff may recover punitive damages under \u00a7 1983 only on "
            "proof of malice or reckless disregard. Miller v. Acme Corp., 555 F.3d 789."
        )
        ack = safety.request_ack_token("draft_1983_complaint", clean)
        trace = safety.safe_generate_document("draft_1983_complaint", clean, ack=ack)
        self.assertEqual(trace.outcome, "audit-clean-ack-verified")
        self.assertTrue(ack.consumed)

    def test_blocked_when_ack_fingerprint_does_not_match(self):
        # SECURITY: an ack_token emitted for draft T1 must NOT authorize draft T2.
        draft_t1 = (
            "A plaintiff may recover punitive damages under \u00a7 1983 only on "
            "proof of malice or reckless disregard. Miller v. Acme Corp., 555 F.3d 789."
        )
        draft_t2 = (
            "A plaintiff may recover punitive damages under \u00a7 1983 only on "
            "proof of malice. Miller v. Acme Corp., 555 F.3d 789. "  # note: missing "or reckless disregard"
        )
        ack = safety.request_ack_token("draft_1983_complaint", draft_t1)
        # The different draft's fingerprint will differ. safe_generate_document
        # must refuse.
        with self.assertRaises(ValueError) as cm:
            safety.safe_generate_document("draft_1983_complaint", draft_t2, ack=ack)
        self.assertIn("fingerprint", str(cm.exception).lower())

    def test_blocked_when_ack_intent_mismatches(self):
        clean = (
            "A plaintiff may recover punitive damages under \u00a7 1983 only on "
            "proof of malice or reckless disregard. Miller v. Acme Corp., 555 F.3d 789."
        )
        ack = safety.request_ack_token("draft_1983_complaint", clean)
        with self.assertRaises(ValueError):
            # Operator passes an ack scoped to draft_1983_complaint but
            # requests a different intent.
            safety.safe_generate_document("draft_affidavit", clean, ack=ack)

    def test_well_formed_ack_rejects_garbage(self):
        self.assertFalse(safety._is_well_formed_ack("not-a-token"))
        self.assertFalse(safety._is_well_formed_ack("ZZZZ-abcd"))
        self.assertFalse(
            safety._is_well_formed_ack("abcd-ABCD")
        )  # uppercase hex rejected
        self.assertTrue(safety._is_well_formed_ack("abcd-1234"))


if __name__ == "__main__":
    unittest.main()
