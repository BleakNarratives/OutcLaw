"""Tests for the vendored ``extraction_kit`` package and ``outclaw_extraction`` layer.

Covers:
  * vendored package loads standalone and via the OutClaw namespace
  * citation/statute extraction (text_extraction_core)
  * deposition ingest + Statement-of-Facts validation (deposition_tools)
  * cross-referencing, chronology, contradiction leads (extraction_validation)
  * semantic citation check (WRAP AND EXTEND: lexical fallback is default)
  * composed extraction_record_audit stays advisory
  * outclaw_unified.audit_text surfaces extraction metadata without
    changing safe_to_draft semantics
"""

from __future__ import annotations

import builtins
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import extraction_kit  # noqa: E402
import outclaw_extraction as ob  # noqa: E402
import outclaw_unified as unified  # noqa: E402

SAMPLE_TRANSCRIPT = """\
Page 1
1  Q. Please state your name for the record.
2  A. My name is John Smith.
3  Q. And where do you work, Mr. Smith?
4  A. I work at ABC Corporation as a manager.
5  Q. How long have you been employed there?
6  A. About five years now.
Page 2
1  Q. Do you recall the events of January 15, 2024?
2  A. Yes, I remember that day clearly.
3  Q. What happened that morning?
4  A. I arrived at work around 8:00 a.m. and went
5  straight to my office. Around 9:30, I heard a
6  loud noise from the warehouse.
7  Q. What did you do then?
8  A. I immediately went to investigate.
"""

STATEMENT_OF_FACTS = """\
On January 15, 2024, John Smith arrived at work at approximately 8:00 a.m.
He went directly to his office. At approximately 9:30 a.m., Smith heard a
loud noise coming from the warehouse area. Smith has been employed at ABC
Corporation for approximately five years.
"""


class TestVendoredPackageLoads(unittest.TestCase):
    def test_direct_import_from_outclaw_main(self):
        package = subprocess.run(
            [sys.executable, "-c", "import extraction_kit, outclaw_extraction"],
            cwd=_HERE.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(package.returncode, 0, package.stderr)

    def test_namespace_import_from_workspace_root(self):
        package = subprocess.run(
            [sys.executable, "-c", "import OutClaw.extraction_kit; import OutClaw.outclaw_extraction"],
            cwd=_HERE.parent.parent.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(package.returncode, 0, package.stderr)

    def test_explicit_public_surface(self):
        for name in (
            "extract_citations_from_text",
            "ingest_deposition",
            "validate_facts_against_record",
            "cross_reference_citations",
            "build_chronology",
            "extract_judge_patterns",
            "extract_circuit_law",
        ):
            self.assertTrue(hasattr(extraction_kit, name), f"extraction_kit missing {name}")


class TestCitationExtraction(unittest.TestCase):
    def test_extracts_citations_and_statutes(self):
        result = ob.extract_citation_metadata(
            "The court applied 42 U.S.C. § 1983 and Smith v. Jones, 123 F.3d 456."
        )
        self.assertTrue(result["advisory"])
        self.assertEqual(result["total_citations"], 1)
        self.assertEqual(result["total_statutes"], 1)
        joined = " ".join(c["citation"] for c in result["citations"])
        self.assertIn("123 F.3d 456", joined)
        statute_text = result["statutes"][0]["statute"]
        self.assertIn("42 U.S.C.", statute_text)

    def test_clean_text_has_zero_citations(self):
        result = ob.extract_citation_metadata("This draft contains no citations.")
        self.assertEqual(result["total_citations"], 0)
        self.assertEqual(result["total_statutes"], 0)


class TestDepositionTools(unittest.TestCase):
    def setUp(self):
        ob.reset_deposition_store()

    def test_ingest_parses_qa_pairs_with_page_line_cites(self):
        result = ob.ingest_deposition_text(
            SAMPLE_TRANSCRIPT, "John Smith", "2024-03-15", "Doe v. ABC Corp"
        )
        self.assertTrue(result["_meta"]["extraction_complete"])
        self.assertGreaterEqual(result["result"]["total_entries"], 5)
        sample = result["result"]["sample_entries"][0]
        # The answer-end line is the line where the next question appears.
        self.assertEqual(sample["full_cite"], "Smith Dep. 1:1-3")

    def test_search_deposition_by_topic(self):
        ob.ingest_deposition_text(SAMPLE_TRANSCRIPT, "John Smith")
        matches = ob.search_deposition_query("warehouse", witness="John Smith")
        self.assertGreaterEqual(len(matches["results"]), 1)
        top = matches["results"][0]
        self.assertIn("warehouse", (top["question"] + " " + top["answer"]).lower())

    def test_validate_facts_against_record(self):
        ob.ingest_deposition_text(SAMPLE_TRANSCRIPT, "John Smith")
        validation = ob.validate_facts_against_record(STATEMENT_OF_FACTS)
        body = validation["validation"]
        self.assertGreaterEqual(body["total_assertions"], 1)
        for key in ("supported", "unsupported", "contradicted"):
            self.assertIn(key, body)
            self.assertIsInstance(body[key], list)
        json.dumps(validation)

    def test_store_lifecycle(self):
        ob.ingest_deposition_text(SAMPLE_TRANSCRIPT, "John Smith")
        self.assertEqual(ob.list_depositions()["total"], 1)
        ob.reset_deposition_store()
        self.assertEqual(ob.list_depositions()["total"], 0)


class TestRecordAnalysis(unittest.TestCase):
    def test_cross_reference_finds_shared_authority(self):
        # Note: the vendored regex greedily treats any sentence lead-in before
        # "v." as part of the case name, so citations should lead the sentence
        # for reliable case-name extraction. See extraction_kit/README.md (known limit).
        docs = {
            "brief-a.txt": "Smith v. Jones, 123 F.3d 456 controls this argument.",
            "brief-b.txt": "Smith v. Jones, 123 F.3d 456 is the same authority.",
        }
        result = ob.cross_reference_documents(docs)
        self.assertEqual(result["documents_analyzed"], ["brief-a.txt", "brief-b.txt"])
        self.assertGreaterEqual(len(result["shared_cases"]), 1)
        self.assertEqual(
            set(result["shared_cases"][0]["docs"]), {"brief-a.txt", "brief-b.txt"}
        )

    def test_chronology_builds_timeline(self):
        docs = {
            "record.txt": (
                "On January 15, 2024, the incident occurred. "
                "On February 1, 2024, the complaint was filed."
            )
        }
        result = ob.build_timeline(docs)
        self.assertGreaterEqual(len(result["timeline"]), 2)
        self.assertEqual(result["documents_processed"], ["record.txt"])

    def test_contradiction_scan_returns_leads(self):
        docs = {
            "record-a.txt": "John Smith was present at the hearing on January 1, 2024.",
            "record-b.txt": "John Smith was not present at the hearing on January 1, 2024.",
        }
        result = ob.detect_contradictions(docs)
        self.assertIn("total_contradictions", result)
        self.assertIn("contradictions", result)
        self.assertIn("potential_omissions", result)
        json.dumps(result)

    def test_record_facts_shape(self):
        result = ob.record_facts(
            "On January 15, 2024, John Smith testified that Exhibit 1 was accurate.",
            "smith-dep.txt",
        )
        self.assertEqual(result["document"], "smith-dep.txt")
        self.assertIsInstance(result["facts"], list)
        self.assertIsInstance(result["witnesses_mentioned"], list)


class TestSemanticCheck(unittest.TestCase):
    def test_lexical_fallback_is_default_and_deterministic(self):
        check = ob.semantic_citation_check(
            "A warrant is required for a home search.",
            "The Fourth Amendment requires a warrant for a home search absent exigent circumstances.",
            use_llm=False,
        )
        self.assertTrue(check["advisory"])
        self.assertEqual(check["semantic_backend"], "lexical")
        self.assertGreater(check["lexical_score"], 0.0)
        self.assertIsNone(check["semantic_verdict"])

    def test_citation_accuracy_wrapper_stays_advisory(self):
        result = ob.validate_citation_accuracy(
            "A warrant is required. See Smith v. Jones, 123 F.3d 456.",
            case_texts={"Smith v. Jones": "The court held that a warrant is required for a home search."},
            use_llm=False,
        )
        self.assertTrue(result["advisory"])
        self.assertIn("total_citations_found", result)
        self.assertEqual(result["semantic_extended_count"], 0)

    # --- Semantic cascade path (round 3 validation) ---------------------
    # No API keys in the test env: the path is validated with a faked
    # cascade so the code path (import -> enabled check -> complete ->
    # verdict/confidence extraction) is locked without network access.

    class _FakeCascadeResult:
        def __init__(self, ok, data):
            self.ok = ok
            self.data = data

    class _FakeCascade:
        def __init__(self, enabled=True, ok=True, data=None):
            self.enabled = enabled
            self._ok = ok
            self._data = data or {
                "verdict": "opposite",
                "confidence": 0.87,
                "reasoning": "the holding is the opposite of the proposition",
            }
            self.calls = []

        def complete(self, prompt, task, min_confidence=0.0, max_tokens=2048):
            self.calls.append(
                {"task": task, "min_confidence": min_confidence, "max_tokens": max_tokens}
            )
            result = TestSemanticCheck._FakeCascadeResult(self._ok, self._data)
            return result

    def _patch_cascade(self, fake):
        return patch(
            "OutClaw.outclaw_model_cascade.get_cascade",
            return_value=fake,
        )

    def test_semantic_path_uses_cascade_when_enabled(self):
        fake = self._FakeCascade(enabled=True)
        with self._patch_cascade(fake):
            check = ob.semantic_citation_check(
                "The defendant had no duty to act.",
                "The court held the defendant had a duty to act.",
                use_llm=True,
            )
        self.assertEqual(check["semantic_backend"], "cascade")
        self.assertEqual(check["semantic_verdict"], "opposite")
        self.assertEqual(check["confidence"], 0.87)
        self.assertEqual(fake.calls[0]["task"], "citation_support")
        self.assertEqual(fake.calls[0]["min_confidence"], 0.60)

    def test_semantic_path_falls_back_to_lexical_when_disabled(self):
        fake = self._FakeCascade(enabled=False)
        with self._patch_cascade(fake):
            check = ob.semantic_citation_check(
                "A warrant is required.",
                "A warrant is required for a home search.",
                use_llm=True,
            )
        self.assertEqual(check["semantic_backend"], "lexical")
        self.assertIsNone(check["semantic_verdict"])
        self.assertFalse(fake.calls)  # disabled cascade is never called

    def test_semantic_path_falls_back_when_cascade_fails(self):
        fake = self._FakeCascade(enabled=True, ok=False, data=None)
        with self._patch_cascade(fake):
            check = ob.semantic_citation_check(
                "A warrant is required.",
                "A warrant is required for a home search.",
                use_llm=True,
            )
        self.assertEqual(check["semantic_backend"], "lexical")
        self.assertIsNone(check["semantic_verdict"])

    def test_semantic_path_falls_back_when_verdict_unrecognized(self):
        fake = self._FakeCascade(
            enabled=True, data={"verdict": "maybe", "confidence": 0.9}
        )
        with self._patch_cascade(fake):
            check = ob.semantic_citation_check(
                "A warrant is required.",
                "A warrant is required for a home search.",
                use_llm=True,
            )
        self.assertEqual(check["semantic_backend"], "lexical")
        self.assertIsNone(check["semantic_verdict"])

    def test_semantic_path_rejects_bool_confidence(self):
        # bool is an int subclass; confidence must not coerce True to 1.0.
        fake = self._FakeCascade(
            enabled=True,
            data={"verdict": "supported", "confidence": True},
        )
        with self._patch_cascade(fake):
            check = ob.semantic_citation_check(
                "A warrant is required.",
                "A warrant is required for a home search.",
                use_llm=True,
            )
        self.assertEqual(check["semantic_verdict"], "supported")
        self.assertIsNone(check["confidence"])

    def test_semantic_path_use_llm_off_never_touches_cascade(self):
        fake = self._FakeCascade(enabled=True)
        with self._patch_cascade(fake):
            check = ob.semantic_citation_check(
                "A warrant is required.",
                "A warrant is required for a home search.",
                use_llm=False,
            )
        self.assertEqual(check["semantic_backend"], "lexical")
        self.assertFalse(fake.calls)


class TestDeepContradictionScan(unittest.TestCase):
    def test_detects_negation_conflict(self):
        docs = {
            "dep.txt": "John Smith was present at the hearing on January 15, 2024.",
            "record.txt": "John Smith was not present at the hearing on January 15, 2024.",
        }
        result = ob.deep_contradiction_scan(docs)
        types = {lead["type"] for lead in result["leads"]}
        self.assertIn("negation_conflict", types)
        self.assertEqual(result["total_leads"], len(result["leads"]))
        self.assertTrue(result["advisory"])

    def test_detects_date_conflict(self):
        docs = {
            "dep.txt": "John Smith arrived at the warehouse on January 15, 2024.",
            "record.txt": "John Smith arrived at the warehouse on January 16, 2024.",
        }
        result = ob.deep_contradiction_scan(docs)
        types = {lead["type"] for lead in result["leads"]}
        self.assertIn("date_conflict", types)

    def test_detects_time_conflict(self):
        docs = {
            "dep.txt": "John Smith arrived at the warehouse at 8:00 a.m.",
            "record.txt": "John Smith arrived at the warehouse at 9:00 a.m.",
        }
        result = ob.deep_contradiction_scan(docs)
        types = {lead["type"] for lead in result["leads"]}
        self.assertIn("time_conflict", types)

    def test_detects_amount_conflict(self):
        docs = {
            "brief.txt": "The settlement paid to John Smith was $5,000.",
            "record.txt": "The settlement paid to John Smith was $50,000.",
        }
        result = ob.deep_contradiction_scan(docs)
        types = {lead["type"] for lead in result["leads"]}
        self.assertIn("amount_conflict", types)

    def test_approximate_values_do_not_conflict(self):
        docs = {
            "dep.txt": "John Smith arrived around 8:00 a.m.",
            "record.txt": "John Smith arrived at 8:00 a.m.",
        }
        result = ob.deep_contradiction_scan(docs)
        self.assertEqual(result["total_leads"], 0)

    def test_equivalent_value_formats_do_not_conflict(self):
        # 8:00 a.m. == 8:00 am; $5,000 == $5,000.00; Jan 15 == 1/15.
        docs = {
            "dep.txt": "John Smith arrived at the hearing at 8:00 a.m. on January 15, 2024.",
            "record.txt": "John Smith arrived at the hearing at 8:00 am on 1/15/2024.",
        }
        result = ob.deep_contradiction_scan(docs)
        self.assertEqual(result["total_leads"], 0)
        docs2 = {
            "dep.txt": "The settlement paid to John Smith was $5,000.",
            "record.txt": "The settlement paid to John Smith was $5,000.00.",
        }
        self.assertEqual(ob.deep_contradiction_scan(docs2)["total_leads"], 0)

    def test_never_does_not_match_nevertheless(self):
        docs = {
            "dep.txt": "John nevertheless arrived at the warehouse on January 15, 2024.",
            "record.txt": "John Smith arrived at the warehouse on January 15, 2024.",
        }
        result = ob.deep_contradiction_scan(docs)
        self.assertEqual(result["total_leads"], 0)

    def test_different_verbs_are_not_a_conflict(self):
        # Arriving at 8 and leaving at 9 are different events, not a
        # contradiction — the shared person alone must not produce a lead.
        docs = {
            "dep.txt": "John Smith arrived at the warehouse at 8:00 a.m.",
            "record.txt": "John Smith left the warehouse at 9:00 a.m.",
        }
        result = ob.deep_contradiction_scan(docs)
        types = {lead["type"] for lead in result["leads"]}
        self.assertNotIn("time_conflict", types)

    def test_amount_context_noun_anchors_without_entity(self):
        # "The settlement was $5,000" vs "$50,000" has no proper noun;
        # the shared amount-context noun must still anchor the conflict.
        docs = {
            "dep.txt": "The settlement was $5,000.",
            "record.txt": "The settlement was $50,000.",
        }
        result = ob.deep_contradiction_scan(docs)
        types = {lead["type"] for lead in result["leads"]}
        self.assertIn("amount_conflict", types)

    def test_consistent_documents_produce_no_leads(self):
        docs = {
            "dep.txt": "John Smith arrived at the warehouse at 8:00 a.m. on January 15, 2024.",
            "record.txt": "John Smith arrived at the warehouse at 8:00 a.m. on January 15, 2024.",
        }
        result = ob.deep_contradiction_scan(docs)
        self.assertEqual(result["total_leads"], 0)

    def test_detect_contradictions_composes_deep_scan(self):
        docs = {
            "dep.txt": "John Smith was present at the hearing on January 15, 2024.",
            "record.txt": "John Smith was not present at the hearing on January 15, 2024.",
        }
        result = ob.detect_contradictions(docs)
        # Vendored top-level keys preserved.
        self.assertIn("total_contradictions", result)
        self.assertIn("contradictions", result)
        self.assertIn("potential_omissions", result)
        # Deep scan composed underneath.
        self.assertIn("deep_scan", result)
        self.assertEqual(result["deep_scan"]["scan"], "outclaw-deep-factual-v1")
        self.assertGreaterEqual(result["deep_scan"]["total_leads"], 1)
        json.dumps(result)

    def test_deep_scan_json_safe(self):
        docs = {
            "a.txt": "John Smith received $5,000 on January 15, 2024 at 8:00 a.m.",
            "b.txt": "John Smith received $50,000 on January 16, 2024 at 9:00 a.m.",
        }
        result = ob.deep_contradiction_scan(docs)
        json.dumps(result)
        self.assertGreaterEqual(result["total_leads"], 3)

    def test_composed_audit_carries_deep_scan(self):
        docs = {
            "dep.txt": "John Smith arrived at the warehouse at 8:00 a.m. on January 15, 2024.",
            "record.txt": "John Smith arrived at the warehouse at 9:00 a.m. on January 15, 2024.",
        }
        report = ob.extraction_record_audit(documents=docs)
        self.assertIn("deep_scan", report["contradiction_leads"])
        self.assertGreaterEqual(
            report["contradiction_leads"]["deep_scan"]["total_leads"], 1
        )

    def test_cascade_status_is_advisory_and_json_safe(self):
        status = ob.semantic_cascade_status()
        self.assertTrue(status["advisory"])
        self.assertIn("enabled", status)
        self.assertIsInstance(status["enabled"], bool)
        json.dumps(status)

    def test_composed_audit_reports_cascade_status(self):
        report = ob.extraction_record_audit({"a.txt": "No citations here."})
        checks = report["semantic_checks"]
        self.assertEqual(checks["use_llm"], False)
        self.assertIn("cascade_status", checks)
        self.assertIn("enabled", checks["cascade_status"])


class TestComposedAudit(unittest.TestCase):
    def test_extraction_record_audit_composes_advisory_report(self):
        ob.reset_deposition_store()
        docs = {
            "record-a.txt": "On January 15, 2024, John Smith arrived at work at 8:00 a.m.",
            "record-b.txt": "The court cited Smith v. Jones, 123 F.3d 456.",
        }
        report = ob.extraction_record_audit(
            documents=docs,
            statement_of_facts=STATEMENT_OF_FACTS,
            deposition_transcript=SAMPLE_TRANSCRIPT,
            witness="John Smith",
        )
        self.assertTrue(report["advisory"])
        self.assertEqual(report["documents_processed"], ["record-a.txt", "record-b.txt"])
        self.assertIn("cross_reference", report)
        self.assertIn("chronology", report)
        self.assertIn("contradiction_leads", report)
        self.assertIsNotNone(report["statement_of_facts_validation"])
        json.dumps(report)

    def test_record_audit_without_sof_skips_validation(self):
        report = ob.extraction_record_audit({"a.txt": "No citations here."})
        self.assertIsNone(report["statement_of_facts_validation"])
        self.assertTrue(report["advisory"])

    def test_composed_audit_scopes_deposition_store_per_case(self):
        # The composed audit owns the in-memory store while it ingests: a
        # stale deposition from a prior case under the same witness name must
        # never leak into the next case's SOF validation.
        ob.reset_deposition_store()
        transcript_stale = (
            "Page 1\n1  Q. Where do you work?\n2  A. I work at XYZ as an accountant."
        )
        transcript_fresh = (
            "Page 1\n1  Q. What did you have for breakfast?\n2  A. Toast and coffee."
        )
        ob.extraction_record_audit(
            documents={"dep.txt": transcript_stale},
            statement_of_facts="Jane Roe worked at XYZ as an accountant.",
            deposition_transcript=transcript_stale,
            witness="Jane Roe",
        )
        # Second case, same witness name, unrelated testimony. The stale XYZ
        # transcript must NOT be in the store for this audit.
        ob.extraction_record_audit(
            documents={"dep.txt": transcript_fresh},
            statement_of_facts="Jane Roe worked at XYZ as an accountant.",
            deposition_transcript=transcript_fresh,
            witness="Jane Roe",
        )
        self.assertEqual(ob.list_depositions()["total"], 1)
        validation = ob.validate_facts_against_record(
            "Jane Roe worked at XYZ as an accountant."
        )
        body = validation["validation"]
        # With a leak, the stale transcript would SUPPORT this assertion;
        # with correct scoping it is unsupported against the fresh record.
        self.assertEqual(len(body["supported"]), 0)


class TestUtilitySurfaces(unittest.TestCase):
    def test_cli_record_audit_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "record.txt"
            doc.write_text(
                "Smith v. Jones, 123 F.3d 456 controls. "
                "On January 15, 2024, the incident occurred.",
                encoding="utf-8",
            )
            sof = root / "sof.txt"
            sof.write_text(
                "John Smith arrived at work at 8:00 a.m. on January 15, 2024.",
                encoding="utf-8",
            )
            dep = root / "dep.txt"
            dep.write_text(SAMPLE_TRANSCRIPT, encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable, "outclaw_cli.py", "record-audit",
                    "--doc", str(doc), "--sof", str(sof),
                    "--deposition", str(dep), "--witness", "John Smith",
                    "--json",
                ],
                cwd=_HERE.parent,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            payload = json.loads(run.stdout)
            self.assertTrue(payload["advisory"])
            self.assertEqual(payload["documents_processed"], ["record.txt"])
            self.assertIsNotNone(payload["statement_of_facts_validation"])

    def test_cli_record_audit_requires_a_doc(self):
        run = subprocess.run(
            [sys.executable, "outclaw_cli.py", "record-audit"],
            cwd=_HERE.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(run.returncode, 2)

    def test_cli_warns_when_sof_or_deposition_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "record.txt"
            doc.write_text("Smith v. Jones, 123 F.3d 456.", encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable, "outclaw_cli.py", "record-audit",
                    "--doc", str(doc), "--sof", str(doc),
                ],
                cwd=_HERE.parent,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0)
            self.assertIn("requires BOTH --sof and --deposition", run.stderr)

    def test_compile_sidecar_carries_advisory_extraction(self):
        import compile_case_docs as compiler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "brief.txt"
            output = root / "out"
            source.write_text(
                "The court applied 42 U.S.C. § 1983 and "
                "Smith v. Jones, 123 F.3d 456.",
                encoding="utf-8",
            )
            result = compiler.compile_cases([source], output)
            sidecar = json.loads(
                Path(result["results"][0]["audit"]).read_text(encoding="utf-8")
            )
            extraction_meta = sidecar["audit"]["extraction"]
            self.assertTrue(extraction_meta["advisory"])
            self.assertEqual(extraction_meta["total_citations"], 1)
            self.assertEqual(extraction_meta["total_statutes"], 1)

    def test_compile_extraction_import_failure_degrades_not_blocks(self):
        # Fail-closed guarantee: if the extraction layer cannot be imported, the
        # sidecar section degrades to unavailable and the batch still runs.
        import compile_case_docs as compiler

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("OutClaw.outclaw_extraction", "outclaw_extraction"):
                raise ImportError("simulated extraction layer failure")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = compiler._extraction_section("42 U.S.C. § 1983.")
        self.assertEqual(result["status"], "unavailable")


class TestUnifiedWiring(unittest.TestCase):
    def test_audit_text_surfaces_extraction_metadata(self):
        report = unified.audit_text("This draft cites Smith v. Jones, 123 F.3d 456.")
        payload = report.to_dict()
        extraction_meta = payload["extraction_metadata"]["extraction"]
        self.assertTrue(extraction_meta["advisory"])
        self.assertEqual(extraction_meta["total_citations"], 1)
        json.dumps(payload)

    def test_audit_text_extraction_metadata_never_blocks_draft_by_itself(self):
        # The extraction layer is metadata-only: a draft with zero findings but
        # extraction present must still be safe to draft.
        report = unified.audit_text("This draft contains no citations.")
        payload = report.to_dict()
        self.assertIn("extraction", payload["extraction_metadata"])
        self.assertTrue(report.safe_to_draft())


if __name__ == "__main__":
    unittest.main()
