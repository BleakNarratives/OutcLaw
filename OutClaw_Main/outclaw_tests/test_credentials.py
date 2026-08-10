"""Tests for the local-only OutClaw credential runtime."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest import mock

import outclaw_credentials as credentials


class TestOutClawCredentials(unittest.TestCase):
    def _write(self, text: str, mode: int = 0o600) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
        handle.write(text)
        handle.close()
        path = Path(handle.name)
        path.chmod(mode)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_file_loads_only_missing_environment_values(self):
        path = self._write(
            "# local-only\nOUTCLAW_CASCADE=1\nGROQ_API_KEY='file-key'\n"
        )
        env = {"GROQ_API_KEY": "environment-key"}
        result = credentials.load_credentials(env, path=path)
        self.assertEqual(result["loaded"], ["OUTCLAW_CASCADE"])
        self.assertEqual(env["GROQ_API_KEY"], "environment-key")
        self.assertEqual(env["OUTCLAW_CASCADE"], "1")
        self.assertNotIn("file-key", str(result))

    def test_unsafe_permissions_are_rejected_without_loading(self):
        path = self._write("GROQ_API_KEY=file-key\n", mode=0o644)
        env: dict[str, str] = {}
        result = credentials.load_credentials(env, path=path)
        self.assertEqual(result["loaded"], [])
        self.assertEqual(result["error"], "PermissionError")
        self.assertNotIn("GROQ_API_KEY", env)

    def test_unknown_names_are_rejected_without_secret_leak(self):
        path = self._write("PAYPAL_CLIENT_SECRET=not-an-outclaw-key\n")
        result = credentials.load_credentials({}, path=path)
        self.assertEqual(result["loaded"], [])
        self.assertEqual(result["error"], "ValueError")
        self.assertNotIn("not-an-outclaw-key", str(result))

    def test_missing_file_is_a_clean_noop(self):
        result = credentials.load_credentials({}, path=Path(tempfile.gettempdir()) / "does-not-exist-outclaw.env")
        self.assertEqual(result["loaded"], [])
        self.assertNotIn("error", result)

    def test_cascade_reads_file_and_reports_only_masked_runtime_metadata(self):
        path = self._write("OUTCLAW_CASCADE=1\nGROQ_API_KEY=file-key\n")
        provider_keys = {
            "GOOGLE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
            "OPENROUTER_API_KEY", "CEREBRAS_API_KEY", "CF_API_TOKEN",
            "CF_ACCOUNT_ID", "HF_TOKEN", "OUTCLAW_CASCADE",
        }
        with mock.patch.dict(
            os.environ,
            {"OUTCLAW_CREDENTIALS_PATH": str(path)},
            clear=True,
        ):
            from outclaw_model_cascade import ModelCascade

            cascade = ModelCascade(config={})
            status = cascade.status()
            self.assertTrue(status["enabled"])
            self.assertTrue(status["providers"]["groq"]["configured"])
            self.assertEqual(status["credential_runtime"]["path"], str(path))
            self.assertNotIn("file-key", str(status))
            # The loader may populate the process environment internally, but
            # only the provider names are observable through status metadata.
            self.assertEqual(
                {key for key in os.environ if key in provider_keys},
                {"OUTCLAW_CASCADE", "GROQ_API_KEY"},
            )

    def test_environment_value_wins_over_file_value(self):
        path = self._write("GROQ_API_KEY=file-key\n")
        env = {"GROQ_API_KEY": "environment-key"}
        result = credentials.load_credentials(env, path=path)
        self.assertEqual(result["loaded"], [])
        self.assertEqual(env["GROQ_API_KEY"], "environment-key")

    def test_symlink_is_rejected(self):
        target = self._write("GROQ_API_KEY=file-key\n")
        link = Path(tempfile.mktemp(prefix="outclaw-link-"))
        self.addCleanup(link.unlink, missing_ok=True)
        link.symlink_to(target)
        result = credentials.load_credentials({}, path=link)
        self.assertEqual(result["error"], "PermissionError")

    def test_read_only_mapping_is_rejected_without_claiming_load(self):
        path = self._write("GROQ_API_KEY=file-key\n")
        result = credentials.load_credentials(
            MappingProxyType({"GROQ_API_KEY": ""}), path=path
        )
        self.assertEqual(result["error"], "TypeError")
        self.assertEqual(result["loaded"], [])

    def test_runtime_reload_replaces_and_removes_only_loader_values(self):
        first = self._write("GROQ_API_KEY=first-key\n")
        second = self._write("GROQ_API_KEY=second-key\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            credentials.load_credentials(path=first)
            self.assertEqual(os.environ["GROQ_API_KEY"], "first-key")
            credentials.load_credentials(path=second)
            self.assertEqual(os.environ["GROQ_API_KEY"], "second-key")
            credentials.load_credentials(path=Path(tempfile.gettempdir()) / "missing-outclaw-rotate.env")
            self.assertNotIn("GROQ_API_KEY", os.environ)

    def test_runtime_reload_preserves_explicit_override(self):
        path = self._write("GROQ_API_KEY=file-key\n")
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "operator-key"}, clear=True):
            credentials.load_credentials(path=path)
            self.assertEqual(os.environ["GROQ_API_KEY"], "operator-key")
            credentials.load_credentials(path=Path(tempfile.gettempdir()) / "missing-outclaw-override.env")
            self.assertEqual(os.environ["GROQ_API_KEY"], "operator-key")


if __name__ == "__main__":
    unittest.main()
