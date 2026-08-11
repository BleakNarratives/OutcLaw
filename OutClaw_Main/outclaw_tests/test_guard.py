"""Tests for the repo integrity guard (outclaw_guard.py).

The guard fails the build if any private client identifier or third-party
product name reappears in the repository. These tests lock that behavior in
so the guard itself stays honest and the repo stays clean.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent


class TestGuard(unittest.TestCase):
    def _run(self, *args, cwd=_ROOT):
        return subprocess.run(
            [sys.executable, "outclaw_guard.py", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )

    def _clean_tree(self, tmp):
        """Return a temp dir with the guard + one clean file (no forbidden
        tokens), so tests scan a controlled tree instead of the whole repo."""
        root = Path(tmp)
        (root / "outclaw_guard.py").write_bytes(
            (_ROOT / "outclaw_guard.py").read_bytes()
        )
        (root / "draft.txt").write_text(
            "The complaint was filed on time.", encoding="utf-8"
        )
        return root

    def test_clean_repo_passes(self):
        # The real-repo scan is the guard's core guarantee: it must pass on the
        # actual tree (fast enough now to run in the local suite, not just CI).
        run = self._run()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("GUARD OK", run.stdout)

    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clean_tree(tmp)
            run = self._run(cwd=root)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("GUARD OK", run.stdout)

    def test_json_output_is_clean_on_clean_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clean_tree(tmp)
            run = self._run("--json", cwd=root)
            self.assertEqual(run.returncode, 0)
            payload = json.loads(run.stdout)
            self.assertTrue(payload["clean"])
            self.assertEqual(payload["hits"], [])

    def test_guard_catches_content_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Copy the guard so it can scan this temp tree.
            (root / "outclaw_guard.py").write_bytes(
                (_ROOT / "outclaw_guard.py").read_bytes()
            )
            (root / "leak.txt").write_text(
                "The settlement for Melissa Stewart was approved.", encoding="utf-8"
            )
            run = self._run("--json", cwd=root)
            self.assertEqual(run.returncode, 1)
            payload = json.loads(run.stdout)
            self.assertFalse(payload["clean"])
            idents = {h["identifier"] for h in payload["hits"]}
            self.assertIn("melissa", idents)
            self.assertIn("stewart", idents)

    def test_guard_catches_path_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outclaw_guard.py").write_bytes(
                (_ROOT / "outclaw_guard.py").read_bytes()
            )
            leak_dir = root / "forbidden_melissa_folder"
            leak_dir.mkdir()
            (leak_dir / "notes.txt").write_text("nothing here", encoding="utf-8")
            run = self._run("--json", cwd=root)
            self.assertEqual(run.returncode, 1)
            payload = json.loads(run.stdout)
            kinds = {h["kind"] for h in payload["hits"]}
            self.assertIn("path", kinds)

    def test_guard_skips_venv_and_git(self):
        # A forbidden token inside a skipped dependency dir must NOT fail the
        # guard — the guard only scans the project tree, not vendored deps.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outclaw_guard.py").write_bytes(
                (_ROOT / "outclaw_guard.py").read_bytes()
            )
            venv = root / ".venv" / "lib" / "python3" / "site-packages"
            venv.mkdir(parents=True)
            (venv / "dep.py").write_text(
                "import baymax  # third-party dep", encoding="utf-8"
            )
            run = self._run("--json", cwd=root)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            payload = json.loads(run.stdout)
            self.assertTrue(payload["clean"])


if __name__ == "__main__":
    unittest.main()
