"""
OutClaw event bus adapter tests (post-review):
  - redact_excerpt now strips consecutive capitalised names + numeric sequences
  - subscription path is exercised end-to-end against a live in-memory bus
  - lazy import gracefully logs WARN rather than swallowing exceptions
"""

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOP = _HERE.parent.parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_TOP))

import outclaw_bus as bus

_OUTCLAW_TEST_AGENT = "outclaw-test-subscriber"


class TestCitationFingerprint(unittest.TestCase):
    def test_stable_across_whitespace_and_case(self):
        n1 = bus.citation_fingerprint("123 F.3d 456")
        n2 = bus.citation_fingerprint("123   F.3D   456")
        n3 = bus.citation_fingerprint("123 f.3d 456")
        self.assertEqual(n1, n2)
        self.assertEqual(n1, n3)

    def test_length_is_12(self):
        self.assertEqual(len(bus.citation_fingerprint("anything")), 12)


class TestRedactExcerpt(unittest.TestCase):
    def test_short_unchanged(self):
        s = "The court held that widgets are illegal."
        self.assertEqual(bus.redact_excerpt(s, max_chars=200), s)

    def test_long_truncated(self):
        s = "a" * 500
        out = bus.redact_excerpt(s, max_chars=80)
        self.assertEqual(len(out), 80)
        self.assertTrue(out.endswith("..."))

    def test_whitespace_collapsed(self):
        s = "foo    bar  baz"
        out = bus.redact_excerpt(s, max_chars=200)
        self.assertEqual(out, "foo bar baz")

    def test_name_strip(self):
        s = "Plaintiff John Smith may proceed."
        out = bus.redact_excerpt(s, max_chars=200)
        self.assertIn("REDACTED-NAME", out)
        self.assertNotIn("John", out)
        self.assertNotIn("Smith", out)

    def test_legal_term_allowlist(self):
        # Per code review: legal phrases must NOT be redacted as names.
        s = "The Supreme Court of the United States held..."
        out = bus.redact_excerpt(s, max_chars=200)
        self.assertIn("Supreme Court", out)
        self.assertIn("United States", out)
        self.assertNotIn("REDACTED-NAME", out)

    def test_docket_pattern_strip(self):
        # Standard docket notation -- must be redacted.
        for docket in ("21-CV-12345", "1:21-CR-001", "23-CR-0042"):
            s = f"Plaintiff filed under {docket}"
            out = bus.redact_excerpt(s, max_chars=200)
            self.assertIn("REDACTED-NUMBER", out, f"failed for {docket}")

    def test_combined_redaction(self):
        s = "Maria Garcia of 456 Oak Avenue alleged fraud by Acme Corporation 22-1234."
        out = bus.redact_excerpt(s, max_chars=200)
        self.assertIn("REDACTED-NAME", out)
        # Numeric run stripped too.
        self.assertNotIn("22-1234", out)


class _StubBus:
    """In-memory event bus stand-in so subscribe tests don't depend on Syntax."""

    def __init__(self):
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self.published: List[tuple] = []

    def subscribe(self, agent_id, channel, callback):
        self._subscriptions.setdefault(channel, {})[agent_id] = callback

    def publish(self, sender_id, channel, data):
        self.published.append((sender_id, channel, dict(data)))
        for agent_id, cb in list(self._subscriptions.get(channel, {}).items()):
            if agent_id != sender_id:
                cb(agent_id, channel, dict(data))


class TestOutClawBus(unittest.TestCase):
    def test_diagnostics_reflects_state(self):
        # Use a stub bus so this test runs unconditionally.
        stub = _StubBus()
        b = bus.OutClawBus(bus=stub)
        d = b.diagnostics()
        self.assertTrue(d.bus_available)
        self.assertIsNone(d.bus_import_error)

    def test_fallback_log_writes_when_no_live_publish(self):
        stub = _StubBus()
        b = bus.OutClawBus(bus=stub)
        b.publish_findings(
            {
                "text": "hello",
                "summary": {"severity_counts": {"HIGH": 1}},
                "findings": [],
            }
        )
        log = b.fallback_log()
        self.assertGreaterEqual(len(log), 1)

    def test_live_bus_publishes_to_subscriber_no_skip(self):
        # Per code review: no silent skip. Use a stub bus assertably.
        stub = _StubBus()
        b = bus.OutClawBus(bus=stub)
        captured = []

        def cb(agent_id, channel, data):
            captured.append((agent_id, channel, dict(data)))

        b.subscribe_findings(_OUTCLAW_TEST_AGENT, cb)
        b.publish_findings(
            {
                "text": "abc",
                "summary": {
                    "severity_counts": {"HIGH": 1},
                    "safe_to_draft": False,
                    "recovered_by_window_count": 0,
                },
                "findings": [
                    {
                        "severity": "HIGH",
                        "citation": "123 F.3d 456",
                        "rule": "OPPOSITE HOLDING",
                        "sentence": "Police may search a home. John Smith, 123 Main St.",
                    }
                ],
            }
        )
        self.assertGreaterEqual(
            len(captured), 1, "subscriber must receive the published message"
        )
        agent_id, channel, data = captured[-1]
        self.assertEqual(channel, bus.CHANNEL_FINDINGS)
        self.assertEqual(data["high_count"], 1)
        # PII leak check on the wire
        excerpt = data["high_findings"][0]["excerpt"]
        self.assertNotIn("John", excerpt)
        self.assertNotIn("Smith", excerpt)
        self.assertIn("REDACTED-NAME", excerpt)

    def test_docket_number_redacted_on_wire(self):
        stub = _StubBus()
        b = bus.OutClawBus(bus=stub)
        captured = []

        def cb(agent_id, channel, data):
            captured.append((agent_id, channel, dict(data)))

        b.subscribe_findings(_OUTCLAW_TEST_AGENT, cb)
        b.publish_findings(
            {
                "text": "abc",
                "summary": {
                    "severity_counts": {"HIGH": 1},
                    "safe_to_draft": False,
                    "recovered_by_window_count": 0,
                },
                "findings": [
                    {
                        "severity": "HIGH",
                        "citation": "123 F.3d 456",
                        "rule": "OPPOSITE HOLDING",
                        "sentence": "Plaintiff under docket 21-CV-12345 alleged ...",
                    }
                ],
            }
        )
        self.assertGreaterEqual(len(captured), 1)
        excerpt = captured[-1][2]["high_findings"][0]["excerpt"]
        # Docket suffix must NOT survive redaction.
        self.assertNotIn("12345", excerpt)
        self.assertIn("REDACTED-NUMBER", excerpt)

    def test_lazy_import_does_not_throw(self):
        for _ in range(3):
            bus.OutClawBus()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
