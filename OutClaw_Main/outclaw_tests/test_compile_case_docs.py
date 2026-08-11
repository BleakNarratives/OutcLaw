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

    def test_batch_publishes_manifest_last_and_leaves_no_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case.txt"
            output = root / "filings"
            source.write_text("CASE: 24-001", encoding="utf-8")

            with patch.object(compiler, "_validate", return_value={"evidence_match": True}):
                result = compiler.compile_cases([source], output)

            self.assertTrue(Path(result["manifest"]).exists())
            self.assertFalse((output / compiler._RECOVERY_NAME).exists())
            self.assertFalse(any(p.name.startswith(compiler._STAGE_PREFIX) for p in output.iterdir()))
            self.assertFalse(any(p.name.startswith(compiler._BACKUP_PREFIX) for p in output.iterdir()))
            self.assertTrue((output / compiler._LOCK_NAME).exists())

    def test_validation_error_publishes_no_partial_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_one = root / "one.txt"
            source_two = root / "two.txt"
            output = root / "filings"
            source_one.write_text("one", encoding="utf-8")
            source_two.write_text("two", encoding="utf-8")

            def validate(source, _text):
                if source == source_two:
                    raise ValueError("synthetic validator failure")
                return {"evidence_match": True}

            with patch.object(compiler, "_validate", side_effect=validate):
                with self.assertRaises(RuntimeError):
                    compiler.compile_cases([source_one, source_two], output)

            self.assertFalse((output / "compile_manifest.json").exists())
            self.assertFalse(list(output.glob("*.review.txt")))
            self.assertFalse(list(output.glob("*.audit.json")))
            self.assertFalse((output / compiler._RECOVERY_NAME).exists())

    def test_publish_failure_preserves_recovery_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "filings"
            output.mkdir()
            existing = output / "existing.review.txt"
            existing.write_text("old", encoding="utf-8")
            staging = output / f"{compiler._STAGE_PREFIX}publisher"
            staging.mkdir()
            (staging / existing.name).write_text("new", encoding="utf-8")
            (staging / "compile_manifest.json").write_text("{}", encoding="utf-8")

            with patch.object(
                compiler,
                "_recover_interrupted_commit",
                side_effect=OSError("rollback unavailable"),
            ):
                with self.assertRaises(OSError):
                    compiler._publish_batch(
                        output,
                        staging,
                        [existing.name, "missing.audit.json", "compile_manifest.json"],
                        force=True,
                    )

            journal = output / compiler._RECOVERY_NAME
            self.assertTrue(journal.exists())
            recovery = json.loads(journal.read_text(encoding="utf-8"))
            backup = output / recovery["backup_dir"] / existing.name
            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), "old")

    def test_failed_recovery_preserves_journal_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "filings"
            output.mkdir()
            target = output / "existing.review.txt"
            target.write_text("partial", encoding="utf-8")
            staging = output / f"{compiler._STAGE_PREFIX}failed"
            backup = output / f"{compiler._BACKUP_PREFIX}failed"
            staging.mkdir()
            backup.mkdir()
            backup_copy = backup / target.name
            backup_copy.write_text("old", encoding="utf-8")
            compiler._write_recovery_journal(
                output, staging, backup, [target.name], [target.name]
            )

            with patch.object(compiler, "_remove_file", side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    compiler._recover_interrupted_commit(output)

            self.assertTrue((output / compiler._RECOVERY_NAME).exists())
            self.assertTrue(backup_copy.exists())

    def test_unjournaled_directories_are_left_for_manual_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "filings"
            output.mkdir()
            stage = output / f"{compiler._STAGE_PREFIX}unowned"
            backup = output / f"{compiler._BACKUP_PREFIX}unowned"
            stage.mkdir()
            backup.mkdir()

            with compiler._output_lock(output):
                pass

            self.assertTrue(stage.exists())
            self.assertTrue(backup.exists())

    def test_recovery_restores_existing_outputs_and_removes_new_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "filings"
            output.mkdir()
            existing = output / "existing.review.txt"
            existing.write_text("old", encoding="utf-8")
            new = output / "new.audit.json"
            staging = output / f"{compiler._STAGE_PREFIX}interrupted"
            backup = output / f"{compiler._BACKUP_PREFIX}interrupted"
            staging.mkdir()
            backup.mkdir()
            (backup / existing.name).write_text("old", encoding="utf-8")
            existing.write_text("partial replacement", encoding="utf-8")
            new.write_text("partial new", encoding="utf-8")
            compiler._write_recovery_journal(
                output,
                staging,
                backup,
                [existing.name, new.name],
                [existing.name],
            )

            with compiler._output_lock(output):
                pass

            self.assertEqual(existing.read_text(encoding="utf-8"), "old")
            self.assertFalse(new.exists())
            self.assertFalse((output / compiler._RECOVERY_NAME).exists())
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())


if __name__ == "__main__":
    unittest.main()
