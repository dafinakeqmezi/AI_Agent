"""Tests for git-history analysis (C11), commit evidence validation, GitHub helpers and git-aware freezing.

Builds throw-away git repositories with controlled dates/authors; no network access.
Run: python -m unittest discover -s tests -v
"""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grader import freeze, github, history, state  # noqa: E402
from grader.scc import find_scc  # noqa: E402
from grader.validate import check_evidence  # noqa: E402

DEADLINE = "2026-06-30T23:59:00+00:00"


def git(repo, *args, env=None):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                          env={**os.environ, **(env or {})}).stdout.strip()


def commit(repo, files: dict, msg: str, date: str, author=("Ana", "ana@example.com"), committer_date=None):
    for name, content in files.items():
        p = Path(repo) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg, env={
        "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1], "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_NAME": author[0], "GIT_COMMITTER_EMAIL": author[1],
        "GIT_COMMITTER_DATE": committer_date or date})
    return git(repo, "rev-parse", "HEAD")


def code(n, tag):
    return "\n".join(f"def f_{tag}_{i}(x):\n    return x + {i}\n" for i in range(n))


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "student-repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")

    def tearDown(self):
        for p in self.tmp.rglob("*"):
            if p.is_file():
                os.chmod(p, stat.S_IWRITE | stat.S_IREAD)


class TestHistoryBadProcess(RepoCase):
    """Few commits, generic messages, one bulk last-minute commit, a leaked key, a missing team member."""

    def setUp(self):
        super().setUp()
        commit(self.repo, {"README.md": "# Project\n"}, "initial commit", "2026-05-01T10:00:00+00:00")
        commit(self.repo, {"src/config.py": 'OPENAI_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\n'}, "update",
               "2026-06-29T22:00:00+00:00")
        self.bulk = commit(self.repo, {"src/model.py": code(150, "m"), "src/data.py": code(60, "d"),
                                       "report.md": "# Report\nWe iterated for months.\n"}, "Add files via upload",
                           "2026-06-30T21:00:00+00:00")
        self.late = commit(self.repo, {"src/fix.py": code(2, "x")}, "fix", "2026-07-02T09:00:00+00:00")
        self.h = history.analyze(self.repo, deadline=DEADLINE, team=["ana@example.com", "ben@example.com"],
                                 out=self.tmp / "out")
        self.types = {s["type"] for s in self.h["signals"]}

    def test_process_signals(self):
        for t in ["bulk_commit", "web_upload_commit", "few_commits", "few_active_days", "last_minute_development",
                  "generic_messages", "secret_in_history", "team_member_without_commits", "commit_after_deadline"]:
            self.assertIn(t, self.types)
        bulk = next(s for s in self.h["signals"] if s["type"] == "bulk_commit")
        self.assertEqual(bulk["location"], f"commit {self.bulk[:7]}")
        self.assertEqual(bulk["file"], "(git history)")

    def test_secret_is_redacted(self):
        sec = next(s for s in self.h["signals"] if s["type"] == "secret_in_history")
        self.assertNotIn("abcdefghijklmnop", sec["quote"])

    def test_outputs_written(self):
        md = (self.tmp / "out" / "history.md").read_text(encoding="utf-8")
        self.assertIn("Weekly activity", md)
        self.assertIn(self.bulk[:7], md)
        self.assertTrue((self.tmp / "out" / "history.json").exists())

    @unittest.skipUnless(find_scc(), "scc not installed")
    def test_scc_code_measure(self):
        self.assertEqual(self.h["metrics"]["code_measure"], "scc")
        self.assertGreater(self.h["metrics"]["final_code_lines"], 300)
        bulk = next(c for c in self.h["commits"] if c["sha"] == self.bulk)
        self.assertGreater(bulk["code_delta"], 300)


class TestHistoryGoodProcess(RepoCase):
    """Regular, descriptive, balanced team work: no process signals."""

    def test_no_process_signals(self):
        members = [("Ana", "ana@example.com"), ("Ben", "ben@example.com")]
        commit(self.repo, {".gitignore": "data/\n"}, "Set up project structure and gitignore", "2026-03-02T10:00:00+00:00")
        for week in range(12):
            for k, who in enumerate(members):
                day = 2 + week * 7 + k * 2
                month, dd = (3, day) if day <= 31 else ((4, day - 31) if day <= 61 else (5, day - 61))
                commit(self.repo, {f"src/{who[0].lower()}_{week}.py": code(8, f"{week}{k}")},
                       f"Implement feature {week}.{k}: preprocessing step and unit test", f"2026-{month:02d}-{dd:02d}T10:00:00+00:00",
                       author=who)
        h = history.analyze(self.repo, deadline=DEADLINE, team=["ana@example.com", "ben@example.com"])
        bad = {"bulk_commit", "few_commits", "few_active_days", "last_minute_development", "generic_messages",
               "team_member_without_commits", "unbalanced_contribution", "author_outside_team", "commit_after_deadline"}
        self.assertEqual({s["type"] for s in h["signals"]} & bad, set())
        self.assertEqual(h["metrics"]["commits"], 25)
        self.assertTrue(h["metrics"]["has_gitignore"])


class TestNoGit(unittest.TestCase):
    def test_no_history(self):
        with tempfile.TemporaryDirectory() as d:
            h = history.analyze(Path(d))
        self.assertFalse(h["available"])
        self.assertEqual(h["signals"][0]["type"], "no_git_history")


class TestCommitEvidence(unittest.TestCase):
    known = {"a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"}

    def errors(self, ev, commits=known):
        errs = []
        check_evidence([ev], {"README.md"}, "x", errs, commits)
        return errs

    def test_known_commit_ok(self):
        self.assertEqual(self.errors({"file": "(git history)", "location": "commit a1b2c3d"}), [])

    def test_invented_commit_rejected(self):
        self.assertTrue(self.errors({"file": "(git history)", "location": "commit deadbee"}))

    def test_commit_without_history_rejected(self):
        self.assertTrue(self.errors({"file": "(git history)", "location": "commit a1b2c3d"}, commits=None))

    def test_bad_location_rejected(self):
        self.assertTrue(self.errors({"file": "(git history)", "location": "L12"}))


class TestGitHubHelpers(RepoCase):
    def test_parse_repo(self):
        for spec in ["octo/ml-project", "https://github.com/octo/ml-project", "https://github.com/octo/ml-project.git",
                     "git@github.com:octo/ml-project.git"]:
            self.assertEqual(github.parse_repo(spec), ("octo", "ml-project"))
        self.assertIsNone(github.parse_repo("not a repo"))

    def test_deadline_requires_timezone(self):
        with self.assertRaises(SystemExit):
            github.parse_time("2026-06-30T23:59:00")

    def test_push_time_of(self):
        a = commit(self.repo, {"a.py": "1\n"}, "Add a", "2026-06-01T10:00:00+00:00")
        b = commit(self.repo, {"b.py": "2\n"}, "Add b", "2026-06-29T10:00:00+00:00")
        c = commit(self.repo, {"c.py": "3\n"}, "Add c", "2026-06-30T10:00:00+00:00")
        activity = [{"timestamp": "2026-06-02T00:00:00Z", "type": "push", "before": "0" * 40, "after": a},
                    {"timestamp": "2026-07-03T00:00:00Z", "type": "push", "before": a, "after": c}]
        self.assertEqual(github.push_time_of(a, activity, self.repo)[0], "2026-06-02T00:00:00Z")
        # b carries a June timestamp but only reached GitHub with the July push
        self.assertEqual(github.push_time_of(b, activity, self.repo)[0], "2026-07-03T00:00:00Z")
        # oldest logged push already contained it -> pushed earlier, time unknown (never "late")
        self.assertIsNone(github.push_time_of(a, activity[1:], self.repo)[0])

    def test_pushed_after_deadline_signal(self):
        commit(self.repo, {"a.py": "1\n"}, "Add a", "2026-06-01T10:00:00+00:00")
        b = commit(self.repo, {"b.py": "2\n"}, "Add b", "2026-06-29T10:00:00+00:00")
        meta = {"repo": {}, "activity": [{"timestamp": "2026-07-03T00:00:00Z", "type": "push", "before": "0" * 40, "after": b}]}
        h = history.analyze(self.repo, deadline=DEADLINE, github=meta)
        self.assertIn("pushed_after_deadline", {s["type"] for s in h["signals"]})


class TestFreezeGitRepo(RepoCase):
    def test_freeze_records_history_and_protects_metadata(self):
        subs = self.tmp / "submissions"
        with mock.patch.object(freeze, "SUBMISSIONS", subs), \
                mock.patch.object(state, "STATE_FILE", self.tmp / "state.json"):
            sha = commit(self.repo, {"src/a.py": code(3, "a")}, "Add model code", "2026-06-01T10:00:00+00:00")
            sub = freeze.freeze(self.repo, student="Ana", submission_id="ana-test", deadline=DEADLINE, team=["ana@example.com"])
            self.assertEqual(sub["git_commit"], sha)
            self.assertTrue((subs / "ana-test" / "metadata" / "history.json").exists())
            self.assertFalse((subs / "ana-test" / "files" / ".git").exists())
            self.assertTrue(freeze.verify("ana-test")["intact"])
            h = subs / "ana-test" / "metadata" / "history.json"
            os.chmod(h, stat.S_IWRITE | stat.S_IREAD)
            h.write_text("{}", encoding="utf-8")
            res = freeze.verify("ana-test")
            self.assertFalse(res["intact"])
            self.assertEqual(res["problems"][0]["path"], "metadata/history.json")


if __name__ == "__main__":
    unittest.main()
