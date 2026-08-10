"""Offline regression tests for the web dashboard upload boundary."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent
_ROOT = _PROJECT.parent.parent
for _path in (str(_PROJECT), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from flask import Flask  # noqa: F401
except ModuleNotFoundError as exc:  # optional web profile is not core-test required
    web_app = None
    _WEB_IMPORT_ERROR = exc
else:
    from dashboard import web_app
    _WEB_IMPORT_ERROR = None


@unittest.skipIf(
    web_app is None,
    f"optional web dashboard dependencies unavailable: {_WEB_IMPORT_ERROR}",
)
class TestDashboardUploadAggregation(unittest.TestCase):
    def setUp(self) -> None:
        self.client = web_app.app.test_client()
        self.upload_dir = tempfile.TemporaryDirectory()
        self.previous_upload_folder = web_app.app.config["UPLOAD_FOLDER"]
        self.previous_orchestrator = web_app.orchestrator
        web_app.app.config["UPLOAD_FOLDER"] = self.upload_dir.name

        calls = []

        def audit_file(path: str, use_llm: bool = False):
            web_app.SecureInput.validate_file_path(path, must_exist=True)
            calls.append((path, use_llm))
            if path.endswith(".pdf"):
                return SimpleNamespace(
                    success=False,
                    error="PDF could not be read",
                    data={},
                )
            return SimpleNamespace(
                success=True,
                error=None,
                data={
                    "findings": [],
                    "summary": {},
                    "risk": {},
                },
            )

        web_app.orchestrator = SimpleNamespace(audit_file=audit_file)
        self.audit_calls = calls

    def tearDown(self) -> None:
        web_app.orchestrator = self.previous_orchestrator
        web_app.app.config["UPLOAD_FOLDER"] = self.previous_upload_folder
        self.upload_dir.cleanup()

    def test_multi_file_upload_sanitizes_names_aggregates_warning_and_cleans_up(self):
        response = self.client.post(
            "/api/audit-case",
            data={
                "files": [
                    (io.BytesIO(b"clean legal text"), "Good (2024) §1.txt"),
                    (io.BytesIO(b"not a real pdf"), "Bad & Corrupt #2.pdf"),
                ]
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertEqual(data["file_count"], 2)
        self.assertEqual(data["files_checked"], 1)
        self.assertEqual(data["files_failed"], 1)
        self.assertEqual(data["verdict"]["level"], "yellow")
        self.assertEqual(data["plain_findings"][-1]["severity_label"], "Not checked")

        self.assertEqual(len(self.audit_calls), 2)
        captured_names = [Path(path).name for path, _ in self.audit_calls]
        self.assertTrue(
            any(
                name.startswith("outclaw_Good (2024) §1_") and name.endswith(".txt")
                for name in captured_names
            )
        )
        self.assertTrue(
            any(
                name.startswith("outclaw_Bad _ Corrupt #2_") and name.endswith(".pdf")
                for name in captured_names
            )
        )
        self.assertTrue(all("&" not in name for name in captured_names))
        # The endpoint's finally block must remove both files after auditing.
        self.assertEqual(list(Path(self.upload_dir.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
