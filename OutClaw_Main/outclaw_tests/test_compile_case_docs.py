import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import compile_case_docs as compiler


class TestCompileCaseDocs(unittest.TestCase):
    def test_evidence_match_writes_human_review_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "clean.txt"
            output = root / "filings"
            source.write_text("CASE: 24-001\nReviewed evidence.", encoding="utf-8")

            with patch.object(compiler, "_validate", return_value={
                "validator": "outclaw_validator.validate_document",
                "metadata": {"case_number": "24-001"},
                "evidence_match": True,
                "safe_to_generate": False,
            }):
                result = compiler.compile_cases([source], output)

            self.assertEqual(result["counts"]["evidence_matches"], 1)
            packet = Path(result["results"][0]["packet"])
            audit = Path(result["results"][0]["audit"])
            self.assertIn("EVIDENCE MATCH — HUMAN REVIEW REQUIRED", packet.read_text())
            self.assertIn("NOT A FILED PLEADING", packet.read_text())
            self.assertTrue(audit.exists())
            self.assertEqual(
                json.loads(audit.read_text())["source_sha256"],
                compiler._sha256(source.read_text()),
            )

    def test_missing_evidence_is_blocked_not_filed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "unsafe.txt"
            output = root / "filings"
            source.write_text("This draft has no matching case evidence.", encoding="utf-8")

            result = compiler.compile_cases([source], output)

            self.assertEqual(result["counts"]["blocked"], 1)
            packet = Path(result["results"][0]["packet"])
            self.assertTrue(packet.name.endswith(".review.txt"))
            self.assertIn("BLOCKED", packet.read_text())
            self.assertIn("safe_to_generate", packet.read_text())

    def test_main_returns_nonzero_for_blocked_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "blocked.txt"
            source.write_text("No matching evidence.", encoding="utf-8")
            self.assertEqual(
                compiler.main(["--input", str(source), "--output-dir", str(root / "out")]),
                1,
            )

    def test_missing_input_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                compiler.compile_cases([root / "missing.txt"], root / "filings")
            self.assertFalse((root / "filings").exists())


if __name__ == "__main__":
    unittest.main()
