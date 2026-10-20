"""Roster registration must preserve existing student data and reject duplicates."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grader import cli, roster
from grader.common import load_json, write_json


class RosterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "projects" / "roster.json"

    def test_append_preserves_metadata_and_existing_entries(self):
        original = {"course": "AI", "deadline": "2026-11-01T23:59:00+01:00",
                    "students": [{"repo": "owner/old", "student": "Old", "team": ["old"]}]}
        write_json(self.path, original)
        roster.add(self.path, "https://github.com/owner/new.git", " New ", "detyra1")
        saved = load_json(self.path)
        self.assertEqual(saved["deadline"], original["deadline"])
        self.assertEqual(saved["students"][0], original["students"][0])
        self.assertEqual(saved["students"][1]["repo"], "owner/new")
        self.assertEqual(saved["students"][1]["student"], "New")
        self.assertEqual(saved["students"][1]["assignment"], "detyra1")

    def test_duplicate_does_not_overwrite(self):
        roster.add(self.path, "owner/repo", "First", "detyra1")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already registered"):
            roster.add(self.path, "https://github.com/OWNER/REPO/", "Other", "ml-project")
        self.assertEqual(before, self.path.read_bytes())

    def test_bad_input_does_not_create_roster(self):
        for repo, student, assignment in [("https://example.com/o/r", "Name", "detyra1"),
                                           ("owner/repo", " ", "detyra1"),
                                           ("owner/..", "Name", "detyra1"),
                                           ("owner/repo", "Name", "unknown-assignment")]:
            with self.subTest(repo=repo, student=student, assignment=assignment):
                with self.assertRaises((ValueError, SystemExit)):
                    roster.add(self.path, repo, student, assignment)
                self.assertFalse(self.path.exists())

    def test_malformed_existing_file_is_preserved(self):
        write_json(self.path, {"students": "wrong"})
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            roster.add(self.path, "owner/repo", "Name", "detyra1")
        self.assertEqual(before, self.path.read_bytes())

    def test_interactive_input(self):
        from argparse import Namespace
        args = Namespace(repo=None, student=None, assignment=None, roster=str(self.path))
        with patch("builtins.input", side_effect=["owner/repo", "Name", "detyra1"]):
            with patch("builtins.print"):
                cli.cmd_roster_add(args)
        self.assertEqual(load_json(self.path)["students"][0]["repo"], "owner/repo")

    def test_cancel_does_not_create_file(self):
        from argparse import Namespace
        args = Namespace(repo=None, student=None, assignment=None, roster=str(self.path))
        with patch("builtins.input", side_effect=EOFError):
            with self.assertRaises(SystemExit):
                cli.cmd_roster_add(args)
        self.assertFalse(self.path.exists())
