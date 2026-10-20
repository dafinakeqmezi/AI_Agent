"""Build the Detyra 1 demo class: three fictional students' git repositories with scripted histories.

    python sample-projects/detyra1-class/make_demo_class.py

Creates projects/detyra1-demo/<student>/ (git repos, gitignored) and projects/detyra1-demo/roster.json.
Then: python -m grader github freeze-all --roster projects/detyra1-demo/roster.json   and   /grade-class detyra1

Planted for the tests (see tests/expected/ for nothing: this class is a demonstration, not an answer key):
  arber-hoti     complete original work, incremental history over 10 days
  blerta-shala   Arber's code with renamed identifiers; README paragraphs copied; one commit authored by Arber's
                 identity with his commit message; everything committed the night before the deadline
  driton-morina  independent but weaker: Sudoku 'bfs' is recursive DFS, Latin square prints the cyclic pattern
                 (no search), no landscape for golfers/latin, only the 8-puzzle tree
"""
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "projects" / "detyra1-demo"
DEADLINE = "2026-10-19T23:59:00+02:00"

ARBER = ("Arber Hoti", "arber.hoti@student.example.edu")
BLERTA = ("Blerta Shala", "blerta.shala@student.example.edu")
DRITON = ("Driton Morina", "driton.morina@student.example.edu")


def read(student, name):
    return (HERE / student / name).read_text(encoding="utf-8")


def git(repo, *args, author=None, date=None):
    env = dict(os.environ)
    if author:
        env.update(GIT_AUTHOR_NAME=author[0], GIT_AUTHOR_EMAIL=author[1], GIT_COMMITTER_NAME=author[0],
                   GIT_COMMITTER_EMAIL=author[1])
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


def build(student, steps):
    repo = OUT / student
    if repo.exists():
        shutil.rmtree(repo, onerror=lambda f, p, _: (os.chmod(p, stat.S_IWRITE), f(p)))
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for date, author, message, files in steps:
        for name, text in files.items():
            (repo / name).write_text(text, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message, author=author, date=date)
    return repo


def main():
    a_readme = read("arber-hoti", "README.md")
    a_draft = a_readme.split("## 2. Sudoku Solver")[0]
    # README before search_trees.py existed (the 4th program was added on 20 October)
    a_readme_v1 = a_readme.replace("python search_trees.py      # Search trees: 8-Puzzle, Missionaries & Cannibals, Rotating Workforce\n", "")
    a_readme_v1 = (a_readme_v1.split("\n\nPemët më poshtë gjenerohen")[0] + "\n"
                   + a_readme_v1.split("python search_trees.py mc` për pemën e plotë deri te qëllimi.\n", 1)[-1])
    build("arber-hoti", [
        ("2026-10-05T18:10:00+02:00", ARBER, "Dokumentimi fillestar: modelimi i Social Golfers", {"README.md": a_draft}),
        ("2026-10-06T20:30:00+02:00", ARBER, "Social Golfers: DFS me backtracking dhe kontroll i zgjidhjes", {"golfers.py": read("arber-hoti", "golfers.py")}),
        ("2026-10-08T19:45:00+02:00", ARBER, "Sudoku: BFS me radhe FIFO dhe pruning", {"sudoku.py": read("arber-hoti", "sudoku.py")}),
        ("2026-10-10T21:00:00+02:00", ARBER, "Latin Square: IDDFS sipas rreshtave me thyerje simetrie", {"latin.py": read("arber-hoti", "latin.py")}),
        ("2026-10-12T17:20:00+02:00", ARBER, "Landscape dhe objective function per te tri problemet", {"README.md": a_readme.split("## 4. Search Trees")[0]}),
        ("2026-10-15T18:05:00+02:00", ARBER, "Search trees: 8-Puzzle, M&C, RWS", {"README.md": a_readme_v1}),
        ("2026-10-20T10:50:00+02:00", ARBER, "Search trees si program: gjenerimi i pemeve me krasitje dhe perseritje",
         {"search_trees.py": read("arber-hoti", "search_trees.py"), "README.md": a_readme}),
    ])
    b_readme = read("blerta-shala", "README.md")
    b_readme_v1 = b_readme.replace(", `pemet.py` (pemët e kërkimit)", "")
    build("blerta-shala", [
        ("2026-10-18T22:41:00+02:00", BLERTA, "Shto zgjidhjet", {f: read("blerta-shala", f) for f in ("golf_dfs.py", "sudoku_bfs.py", "katrori_latin.py")}),
        ("2026-10-18T23:05:00+02:00", ARBER, "Search trees: 8-Puzzle, M&C, RWS", {"README.md": b_readme.split("## 4. Pemët")[0]}),
        ("2026-10-19T23:40:00+02:00", BLERTA, "update", {"README.md": b_readme_v1}),
        ("2026-10-20T11:10:00+02:00", BLERTA, "pemet", {"pemet.py": read("blerta-shala", "pemet.py"), "README.md": b_readme}),
    ])
    d_code = read("driton-morina", "detyra1.py")
    d_parts = d_code.split("# ---------------- ")
    build("driton-morina", [
        ("2026-10-09T16:00:00+02:00", DRITON, "golfers me dfs", {"detyra1.py": d_parts[0] + "# ---------------- " + d_parts[1]}),
        ("2026-10-11T15:30:00+02:00", DRITON, "sudoku", {"detyra1.py": d_parts[0] + "# ---------------- " + d_parts[1] + "# ---------------- " + d_parts[2]}),
        ("2026-10-14T19:10:00+02:00", DRITON, "latin square", {"detyra1.py": d_code}),
        ("2026-10-17T20:00:00+02:00", DRITON, "readme", {"README.md": read("driton-morina", "README.md")}),
    ])
    roster = {"course": "Inteligjenca Artificiale 2026/27 (DEMO, fictional students)", "assignment": "detyra1",
              "deadline": DEADLINE, "students": [
                  {"student": "Arbër Hoti", "repo": str(OUT / "arber-hoti"), "team": [ARBER[1]]},
                  {"student": "Blerta Shala", "repo": str(OUT / "blerta-shala"), "team": [BLERTA[1]]},
                  {"student": "Driton Morina", "repo": str(OUT / "driton-morina"), "team": [DRITON[1]]}]}
    (OUT / "roster.json").write_text(json.dumps(roster, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Built {OUT} (3 repositories) and roster.json")


if __name__ == "__main__":
    main()
