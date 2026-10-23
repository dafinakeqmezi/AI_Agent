"""Local repository roster input; registering a repo never fetches or grades it."""
from pathlib import Path
import re

from .common import assignment_files, load_json, write_json
from .github import parse_repo


def read(path: Path) -> dict:
    roster = load_json(path) if path.exists() else {"students": []}
    if not isinstance(roster, dict) or not isinstance(roster.get("students"), list):
        raise ValueError("Roster must be an object with a students list.")
    if any(not isinstance(s, dict) or not isinstance(s.get("repo"), str)
           for s in roster["students"]):
        raise ValueError("Every roster entry must contain a repository string.")
    return roster


def branch_name(value: str = "main") -> str:
    if not isinstance(value, str):
        raise ValueError("Enter a Git branch name")
    value = value.strip() or "main"
    if (value == "@" or re.search(r"[\\\s~^:?*\[\x00-\x1f\x7f]", value)
            or any(part.startswith((".", "-")) or part.endswith(".lock") or not part
                   for part in value.split("/"))
            or any(part in value for part in ("..", "@{", "//")) or value.endswith(".")):
        raise ValueError("Enter a valid Git branch name")
    return value


def add(path: Path, repo: str, student: str, assignment: str, branch: str = "main") -> dict:
    branch = branch_name(branch)
    parsed = parse_repo(repo)
    if not parsed:
        raise ValueError("Enter a GitHub URL or owner/repo.")
    if any(part in {".", ".."} for part in parsed):
        raise ValueError("Enter a valid GitHub repository name.")
    student = student.strip()
    if not student:
        raise ValueError("Student name must not be empty.")
    assignment_files(assignment)  # validate before writing
    roster = read(path)
    canonical = "/".join(parsed)
    for entry in roster["students"]:
        existing = parse_repo(entry["repo"])
        if existing and "/".join(existing).casefold() == canonical.casefold():
            raise ValueError(f"Repository already registered: {canonical}. Existing entry was preserved.")
    entry = {"repo": canonical, "student": student, "assignment": assignment,
             "team": [], "ref": branch}
    roster["students"].append(entry)
    write_json(path, roster)
    return entry
