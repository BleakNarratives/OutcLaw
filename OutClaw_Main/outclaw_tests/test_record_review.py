"""Tests for OutClaw's native extraction and record-review helpers."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import outclaw_record_review as review
import outclaw_unified as unified


class TestRecordReview(unittest.TestCase):
    def test_extracts_metadata_without_adjudicating(self):
        result = review.extract_text_metadata(
            "The court applied 42 U.S.C. § 1983 and Smith v. Jones, 123 F.3d 456."
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["citation_count"], 1)
        self.assertEqual(result["statute_count"], 1)
        self.assertIn("123 F.3d 456", result["citations"])

    def test_record_review_returns_human_review_leads(self):
        result = review.review_records(
            {
                "record-a.txt": "John Smith was present at the hearing on January 1, 2024.",
                "record-b.txt": "John Smith was not present at the hearing on January 1, 2024.",
            }
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["potential_contradictions"])
        self.assertIn("human verification", result["disclaimer"])

    def test_deposition_store_has_explicit_clear_lifecycle(self):
        store = review.DepositionStore()
        result = store.ingest(
            "Page 1\n12 Q. Where were you?\n13 A. I was at work.",
            "John Smith",
        )
        self.assertEqual(result["entries"], 1)
        matches = store.search("work", "John Smith")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["witness"], "John Smith")
        self.assertEqual(matches[0]["citation"], "Smith Dep. 1:12-13")
        store.clear()
        self.assertEqual(store.search("work"), [])

    def test_unified_audit_exposes_advisory_metadata_only(self):
        clean_text = "This draft contains no citations."
        report = unified.audit_text(clean_text)
        payload = report.to_dict()
        self.assertEqual(payload["extraction_metadata"]["status"], "ok")
        self.assertEqual(payload["extraction_metadata"]["statute_count"], 0)
        self.assertTrue(report.safe_to_draft())
        json.dumps(payload)

    def test_package_and_direct_invocation_imports(self):
        root = _HERE.parent.parent.parent
        package = subprocess.run(
            [sys.executable, "-c", "import OutClaw.outclaw_record_review"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(package.returncode, 0, package.stderr)
        direct = subprocess.run(
            [sys.executable, "-c", "import outclaw_record_review"],
            cwd=_HERE.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(direct.returncode, 0, direct.stderr)


if __name__ == "__main__":
    unittest.main()
