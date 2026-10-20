"""Tests for assignments, cross-student similarity and the class ranking. Run: python -m unittest discover -s tests -v"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grader import freeze, ranking, score, similarity, state  # noqa: E402
from grader.common import assignment_files, list_assignments, load_json, write_json  # noqa: E402

ORIGINAL = '''from collections import deque

def is_valid(grid, row, col, value):
    for i in range(9):
        if grid[row][i] == value or grid[i][col] == value:
            return False
    box_r, box_c = 3 * (row // 3), 3 * (col // 3)
    for r in range(box_r, box_r + 3):
        for c in range(box_c, box_c + 3):
            if grid[r][c] == value:
                return False
    return True

def next_empty(grid):
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                return r, c
    return None

def solve_bfs(start):
    frontier = deque([start])
    expanded = 0
    while frontier:
        grid = frontier.popleft()
        expanded += 1
        cell = next_empty(grid)
        if cell is None:
            return grid, expanded
        row, col = cell
        for value in range(1, 10):
            if is_valid(grid, row, col, value):
                child = [line[:] for line in grid]
                child[row][col] = value
                frontier.append(child)
    return None, expanded
'''

# Same program: identifiers renamed, comments added, blank lines changed.
RENAMED = '''from collections import deque

# kontrollon a vlen numri
def eshte_valid(tabela, rr, kk, numri):
    for j in range(9):
        if tabela[rr][j] == numri or tabela[j][kk] == numri:
            return False

    kr, kc = 3 * (rr // 3), 3 * (kk // 3)
    for a in range(kr, kr + 3):
        for b in range(kc, kc + 3):
            if tabela[a][b] == numri:
                return False
    return True

def qeliza_bosh(tabela):
    for a in range(9):
        for b in range(9):
            if tabela[a][b] == 0:
                return a, b
    return None

# BFS me backtracking
def zgjidh(fillimi):
    radha = deque([fillimi])
    numeruesi = 0
    while radha:
        tab = radha.popleft()
        numeruesi += 1
        q = qeliza_bosh(tab)
        if q is None:
            return tab, numeruesi
        rr, kk = q
        for numri in range(1, 10):
            if eshte_valid(tab, rr, kk, numri):
                femija = [rresht[:] for rresht in tab]
                femija[rr][kk] = numri
                radha.append(femija)
    return None, numeruesi
'''

INDEPENDENT = '''import itertools

class LatinSquare:
    def __init__(self, n):
        self.n = n
        self.grid = [[None] * n for _ in range(n)]

    def ok(self, i, j, v):
        return all(self.grid[i][k] != v for k in range(self.n)) and all(self.grid[k][j] != v for k in range(self.n))

    def dls(self, pos, limit):
        if pos == self.n * self.n:
            return True
        if pos >= limit:
            return False
        i, j = divmod(pos, self.n)
        for v in range(1, self.n + 1):
            if self.ok(i, j, v):
                self.grid[i][j] = v
                if self.dls(pos + 1, limit):
                    return True
                self.grid[i][j] = None
        return False

    def iddfs(self):
        for limit in itertools.count(1):
            if self.dls(0, limit):
                return self.grid
'''


def git(cwd, *args, author=("Student", "s@example.edu"), date="2026-10-10T10:00:00+02:00"):
    env = dict(os.environ, GIT_AUTHOR_NAME=author[0], GIT_AUTHOR_EMAIL=author[1], GIT_COMMITTER_NAME=author[0],
               GIT_COMMITTER_EMAIL=author[1], GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def make_repo(root: Path, files: dict, commits: list[tuple[str, tuple, str]]):
    """commits: [(message, (name, email), date)]; all files are committed in the first commit, later commits touch NOTES.md."""
    root.mkdir(parents=True)
    git(root, "init", "-q")
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    for i, (msg, author, date) in enumerate(commits):
        if i:
            (root / "NOTES.md").write_text(f"note {i}\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", msg, author=author, date=date)


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.subs, self.evals = self.tmp / "submissions", self.tmp / "evaluations"
        for mod, attrs in ((freeze, ["SUBMISSIONS"]), (score, ["SUBMISSIONS"]), (similarity, ["SUBMISSIONS", "EVALUATIONS"]),
                           (ranking, ["SUBMISSIONS", "EVALUATIONS"])):
            for a in attrs:
                p = mock.patch.object(mod, a, self.subs if a == "SUBMISSIONS" else self.evals)
                p.start()
                self.addCleanup(p.stop)
        p = mock.patch.object(state, "STATE_FILE", self.tmp / "state" / "registry.json")
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(ranking, "STUDENTS_FILE", self.tmp / "students.json")
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        def onerror(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(self.tmp, onerror=onerror)


class Assignments(unittest.TestCase):
    def test_detyra1_is_registered_and_consistent(self):
        self.assertIn("detyra1", list_assignments())
        af = assignment_files("detyra1")
        reqs = load_json(af["requirements"])["requirements"]
        self.assertEqual(score.check_config(load_json(af["rubric"]), reqs), [])
        self.assertTrue(all(r.get("source") for r in reqs), "every Detyra 1 requirement cites the course text")
        self.assertEqual({r["criterion_id"] for r in reqs}, {"C1", "C2", "C3", "C4"})
        dod = load_json(af["dod"])
        self.assertTrue(set(dod["conditions"]["must_pass"]) <= {r["id"] for r in reqs})

    def test_default_assignment_keeps_the_ml_files(self):
        af = assignment_files(None)
        self.assertEqual(af["id"], "ml-project")
        self.assertTrue(af["requirements"].exists())

    def test_unknown_assignment_fails(self):
        with self.assertRaises(SystemExit):
            assignment_files("does-not-exist")


class Similarity(Sandbox):
    def freeze(self, name, files, commits=None, student=None):
        src = self.tmp / "src" / name
        if commits:
            make_repo(src, files, commits)
        else:
            src.mkdir(parents=True)
            for f, t in files.items():
                (src / f).write_text(t, encoding="utf-8")
        return freeze.freeze(src, student=student or name, assignment="detyra1")["submission_id"]

    def test_renamed_copy_is_found_and_independent_work_is_not(self):
        a = self.freeze("arber", {"sudoku.py": ORIGINAL})
        b = self.freeze("blerta", {"sudoku_bfs.py": RENAMED})
        c = self.freeze("driton", {"latin.py": INDEPENDENT})
        r = similarity.run("detyra1", out=self.tmp / "out")
        pairs = {frozenset((p["a"], p["b"])): p for p in r["pairs"]}
        ab, ac = pairs[frozenset((a, b))], pairs[frozenset((a, c))]
        self.assertEqual(ab["level"], "HIGH")
        self.assertGreaterEqual(ab["code"]["containment"], 0.6)
        self.assertTrue(ab["code"]["regions"] and ab["code"]["regions"][0]["quote_a"])
        self.assertIn(ac["level"], ("NONE", "LOW"))
        self.assertTrue((self.tmp / "out" / "similarity.md").exists())

    def test_assignment_filter(self):
        self.freeze("arber", {"sudoku.py": ORIGINAL})
        src = self.tmp / "src" / "ml"
        src.mkdir(parents=True)
        (src / "x.py").write_text(ORIGINAL, encoding="utf-8")
        freeze.freeze(src, student="ml")  # default assignment: must not be compared with detyra1
        self.assertEqual(len(similarity.class_submissions("detyra1")), 1)

    def test_roster_limits_the_class(self):
        self.freeze("arber", {"sudoku.py": ORIGINAL})
        b = self.freeze("blerta", {"sudoku_bfs.py": RENAMED})
        self.freeze("driton", {"latin.py": INDEPENDENT})
        roster = self.tmp / "roster.json"
        write_json(roster, {"students": [{"student": "B", "repo": str(self.tmp / "src" / "blerta")},
                                         {"student": "X", "repo": "someone/not-frozen"}]})
        self.assertEqual(similarity.class_submissions("detyra1", roster=roster), [b])

    def test_foreign_identity_commit_and_identical_file(self):
        arber = ("Arber Hoti", "arber@example.edu")
        blerta = ("Blerta Shala", "blerta@example.edu")
        a = self.freeze("arber", {"sudoku.py": ORIGINAL, "README.md": "Detyra 1\n" * 30},
                        [("Sudoku BFS me backtracking", arber, "2026-10-05T10:00:00+02:00"),
                         ("Dokumentimi i modelit", arber, "2026-10-06T10:00:00+02:00")])
        b = self.freeze("blerta", {"sudoku.py": ORIGINAL, "README.md": "Detyra ime\n"},
                        [("initial", blerta, "2026-10-18T22:00:00+02:00"),
                         ("Sudoku BFS me backtracking", arber, "2026-10-18T22:30:00+02:00")])
        r = similarity.run("detyra1", out=self.tmp / "out")
        p = r["pairs"][0]
        self.assertEqual(p["level"], "HIGH")
        foreign = p["git"]["foreign_identity_commits"]
        # exactly Arber's one commit inside Blerta's repo; Arber's own commits in his own repo are not "foreign"
        self.assertEqual([(c["identity"], c["commit_in"]) for c in foreign], [("arber@example.edu", b)])
        files = {(f["file_a"], f["file_b"]) for f in p["git"]["identical_files"]}
        self.assertIn(("sudoku.py", "sudoku.py"), files)
        self.assertIn("Sudoku BFS me backtracking", p["git"]["shared_commit_messages"])
        same = [f for f in p["git"]["identical_files"] if f["file_a"] == "sudoku.py"][0]
        self.assertLess(same["first_seen_a"], same["first_seen_b"])  # A had the file first


class Ranking(Sandbox):
    def graded(self, name, total, grade):
        src = self.tmp / "src" / name
        src.mkdir(parents=True)
        (src / "main.py").write_text(f"print({total})\n", encoding="utf-8")
        sid = freeze.freeze(src, student=name.title(), assignment="detyra1")["submission_id"]
        write_json(self.evals / sid / "eval-20261020-000000" / "final.json",
                   {"total": total, "grade": grade, "review_status": "PROVISIONAL", "criteria": [{"id": "C1", "score": total / 4}],
                    "integrity": {"risk_level": "NONE_FOUND"}, "meta": {"evaluator": "Prof. Vale"}})
        return sid

    def test_order_ties_and_ungraded(self):
        self.graded("a", 70.0, 7)
        self.graded("b", 91.0, 10)
        self.graded("c", 70.0, 7)
        src = self.tmp / "src" / "d"
        src.mkdir(parents=True)
        (src / "x.py").write_text("x = 1\n", encoding="utf-8")
        freeze.freeze(src, student="D", assignment="detyra1")
        r = ranking.compute("detyra1")
        self.assertEqual([(x["student"], x["rank"]) for x in r["rows"]], [("B", 1), ("A", 2), ("C", 2), ("D", None)])

    def test_smoke_test_evaluations_are_ignored(self):
        sid = self.graded("a", 50.0, 5)
        write_json(self.evals / sid / "eval-20261021-000000" / "final.json",
                   {"total": 99.0, "grade": 10, "criteria": [], "meta": {"evaluator": "smoke test"}})
        self.assertEqual(ranking.compute("detyra1")["rows"][0]["total"], 50.0)


if __name__ == "__main__":
    unittest.main()
