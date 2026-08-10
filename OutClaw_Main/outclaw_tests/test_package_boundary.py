"""Regression tests for the canonical OutClaw package boundary."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent
# Run the subprocess from the repository root so the root compatibility
# package (and SyntaxIntelligence) are both importable in the nested layout.
_ROOT = _PROJECT.parent.parent


class TestPackageBoundary(unittest.TestCase):
    def test_root_namespace_loads_canonical_modules(self):
        script = """
from pathlib import Path
import OutClaw.outclaw_unified as unified
import OutClaw.outclaw_bus as bus
import OutClaw.outclaw_safety as safety
for module in (unified, bus, safety.unified):
    path = Path(module.__file__).resolve()
    assert 'OutClaw_Main' in path.parts, path
assert callable(unified.audit_text)
assert callable(unified.load_seed)
assert safety.unified is unified
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"root import failed:\nstdout={completed.stdout}\nstderr={completed.stderr}",
        )

    def test_ack_token_cannot_be_replayed(self):
        import outclaw_safety as safety

        text = "This draft contains no citations."
        ack = safety.request_ack_token(
            "draft_1983_complaint", text, sink=lambda _message: None
        )
        first = safety.safe_generate_document("draft_1983_complaint", text, ack=ack)
        self.assertEqual(first.outcome, "audit-clean-ack-verified")
        with self.assertRaises(safety.GenerateDocumentBlocked) as raised:
            safety.safe_generate_document("draft_1983_complaint", text, ack=ack)
        self.assertIn("consumed", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
