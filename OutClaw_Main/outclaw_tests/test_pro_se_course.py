"""Tests for ``outclaw_pro_se_course`` — the plain-language court-mechanics
course for self-represented litigants.

Covers: lesson/glossary/track content integrity, advisory labeling, JSON
safety, and the CLI ``course`` subcommand surface.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import outclaw_pro_se_course as course  # noqa: E402


class TestCourseIndex(unittest.TestCase):
    def test_index_is_advisory_and_json_safe(self):
        idx = course.COURSE.course_index()
        self.assertTrue(idx["advisory"])
        self.assertTrue(idx["study_material_only"])
        self.assertGreaterEqual(len(idx["lessons"]), 6)
        self.assertGreaterEqual(idx["glossary_terms"], 20)
        json.dumps(idx)

    def test_lessons_have_all_fields(self):
        for lesson in course.COURSE.LESSONS.values():
            self.assertTrue(lesson.plain_language)
            self.assertTrue(lesson.why_it_matters)
            self.assertTrue(lesson.do_this)
            self.assertTrue(lesson.common_mistakes)
            self.assertTrue(lesson.key_terms)

    def test_prep_tracks_have_full_structure(self):
        for key, track in course.COURSE.PREP_TRACKS.items():
            self.assertIn("title", track)
            self.assertIn("goal", track)
            self.assertGreaterEqual(len(track["structure"]), 3)
            self.assertTrue(track["do"])
            self.assertTrue(track["avoid"])


class TestLessonLookup(unittest.TestCase):
    def test_get_known_lesson(self):
        result = course.COURSE.get_lesson("the_record")
        self.assertIsNotNone(result)
        self.assertTrue(result["advisory"])
        self.assertEqual(result["lesson"]["key"], "the_record")
        json.dumps(result)

    def test_get_unknown_lesson_returns_none(self):
        self.assertIsNone(course.COURSE.get_lesson("not-a-lesson"))


class TestGlossary(unittest.TestCase):
    def test_lookup_case_insensitive(self):
        result = course.COURSE.lookup_term("HEARSAY")
        self.assertIsNotNone(result)
        self.assertEqual(result["term"], "hearsay")
        self.assertIn("out-of-court", result["definition"])

    def test_lookup_unknown_returns_none(self):
        self.assertIsNone(course.COURSE.lookup_term("flibbertigibbet"))


class TestPrepTracks(unittest.TestCase):
    def test_all_tracks_resolve(self):
        for key in course.COURSE.PREP_TRACKS:
            result = course.COURSE.prep_track(key)
            self.assertIsNotNone(result, f"track {key} missing")
            self.assertTrue(result["advisory"])
            json.dumps(result)

    def test_related_lessons_map(self):
        related = course.COURSE.related_lessons("cross-exam")
        self.assertIn("objections", related["related_lessons"])

    def test_full_pack_is_json_safe(self):
        pack = course.COURSE.trial_prep_pack()
        self.assertTrue(pack["advisory"])
        self.assertEqual(len(pack["tracks"]), len(course.COURSE.PREP_TRACKS))
        json.dumps(pack)


class TestCliCourseSubcommand(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "outclaw_cli.py", "course", *args],
            cwd=_HERE.parent,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_list(self):
        run = self._run("--list")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("PRO SE COURT COURSE", run.stdout)
        self.assertIn("oral-argument", run.stdout)

    def test_lesson(self):
        run = self._run("--lesson", "the_record")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("The record is everything", run.stdout)

    def test_track(self):
        run = self._run("--track", "cross-exam")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("CROSS-EXAMINATION", run.stdout)
        self.assertIn("leading questions", run.stdout.lower())

    def test_term(self):
        run = self._run("--term", "burden of proof")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("beyond a reasonable doubt", run.stdout)

    def test_json_lesson(self):
        run = self._run("--lesson", "jurisdiction", "--json")
        self.assertEqual(run.returncode, 0, run.stderr)
        payload = json.loads(run.stdout)
        self.assertTrue(payload["advisory"])
        self.assertEqual(payload["lesson"]["key"], "jurisdiction")

    def test_unknown_lesson_exits_2(self):
        run = self._run("--lesson", "nope")
        self.assertEqual(run.returncode, 2)

    def test_pack(self):
        run = self._run("--pack")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("FULL TRIAL-PREP PACK", run.stdout)
        self.assertIn("DEPOSITION PREP", run.stdout)


if __name__ == "__main__":
    unittest.main()
