"""Shared paths and helpers for the grader toolkit (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("GRADER_DATA_ROOT") or ROOT).resolve()
KB = ROOT / "knowledge-base"
REQUIREMENTS_FILE = KB / "requirements" / "requirements.json"
DOD_FILE = KB / "requirements" / "dod.json"
RUBRIC_FILE = KB / "rubric" / "rubric.json"
INTEGRITY_FILE = KB / "policies" / "integrity-policy.json"
KB_MANIFEST_FILE = KB / "manifest.json"
AGENTS_DIR = ROOT / ".claude" / "agents"
SUBMISSIONS = DATA_ROOT / "submissions"
REVIEWS = DATA_ROOT / "reviews"
EVALUATIONS = DATA_ROOT / "evaluations"
STATE_FILE = DATA_ROOT / "state" / "registry.json"

# Assignments: each has its own requirements/rubric/DoD. The ML project keeps the historical paths above;
# every other assignment lives in knowledge-base/assignments/<id>/ (assignment.json, requirements.json, rubric.json, dod.json).
ASSIGNMENTS_DIR = KB / "assignments"
DEFAULT_ASSIGNMENT = "ml-project"


def assignment_files(assignment: str | None = None) -> dict:
    aid = assignment or DEFAULT_ASSIGNMENT
    if aid == DEFAULT_ASSIGNMENT:
        return {"id": aid, "dir": None, "meta": None, "requirements": REQUIREMENTS_FILE, "rubric": RUBRIC_FILE,
                "dod": DOD_FILE}
    d = ASSIGNMENTS_DIR / aid
    if aid not in list_assignments() or not (d / "assignment.json").exists():
        known = ", ".join(list_assignments())
        raise SystemExit(f"Unknown assignment {aid!r}. Known: {known}")
    return {"id": aid, "dir": d, "meta": d / "assignment.json", "requirements": d / "requirements.json",
            "rubric": d / "rubric.json", "dod": d / "dod.json"}


def list_assignments() -> list[str]:
    extra = sorted(p.parent.name for p in ASSIGNMENTS_DIR.glob("*/assignment.json")) if ASSIGNMENTS_DIR.exists() else []
    return [DEFAULT_ASSIGNMENT, *extra]


def assignment_of(run_dir: Path) -> str:
    """Assignment of a review/evaluation run: run.json, else the frozen submission, else the default."""
    run_dir = Path(run_dir)
    run = load_json(run_dir / "run.json") if (run_dir / "run.json").exists() else {}
    if run.get("assignment"):
        return run["assignment"]
    sid = run.get("submission_id")
    if sid and (SUBMISSIONS / sid / "submission.json").exists():
        return load_json(SUBMISSIONS / sid / "submission.json").get("assignment") or DEFAULT_ASSIGNMENT
    return DEFAULT_ASSIGNMENT

# Directories never treated as part of a student project.
EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".ipynb_checkpoints", ".venv", "venv", "env",
    "node_modules", ".mypy_cache", ".pytest_cache", ".idea", ".vscode", ".DS_Store",
}

STATES = ["DRAFT", "UNDER_REVIEW", "READY_FOR_FINAL_REVIEW", "FINAL_SUBMISSION", "GRADED"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stamp() -> str:
    """Filesystem-safe UTC timestamp used for run directory names."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def load_json(path: Path | str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path | str, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_text(path: Path | str, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def iter_files(root: Path):
    """Yield project files (sorted, deterministic), skipping excluded directories."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name in EXCLUDE_DIRS:
                continue
            yield Path(dirpath) / name


def rel(path: Path, root: Path) -> str:
    return Path(path).relative_to(root).as_posix()


def read_text_safe(path: Path, limit_bytes: int = 5_000_000) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(limit_bytes)
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


IDENTITIES_FILE = KB / "identities.json"


def identity(agent: str) -> dict:
    """Name/title/signature of an agent ('ml-reviewer' or 'professor') from knowledge-base/identities.json."""
    fallback = {"ml-reviewer": {"name": "Agent 1", "title": "AI/ML Project Reviewer", "greeting": "", "signature": "Agent 1 (automated reviewer)"},
                "professor": {"name": "Agent 2", "title": "Professor / Final Evaluator", "greeting": "", "signature": "Agent 2 (automated examiner)"}}
    try:
        return load_json(IDENTITIES_FILE)["agents"][agent]
    except (OSError, KeyError, ValueError):
        return fallback[agent]


def project_key(path: Path | str) -> str:
    """Stable project identifier derived from the project folder name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(path).resolve().name).strip("-").lower() or "project"


def requirements_by_id() -> dict:
    return {r["id"]: r for r in load_json(REQUIREMENTS_FILE)["requirements"]}
