"""Freeze a project into an immutable FINAL_SUBMISSION (hash manifest + read-only copy) and verify it later."""
from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path

from . import history, state
from .common import (SUBMISSIONS, assignment_files, iter_files, load_json, now_iso, project_key, rel, sha256_file, sha256_text, stamp,
                     write_json, write_text)
from .inventory import git_log
from .versions import collect_versions


def manifest_digest(files: list[dict]) -> str:
    return sha256_text("\n".join(f"{f['path']}:{f['sha256']}" for f in files))


def freeze(project_dir: str | Path, student: str | None = None, submission_id: str | None = None,
           max_file_mb: float = 200.0, force: bool = False, deadline: str | None = None,
           team: list[str] | None = None, source: dict | None = None, github_meta: dict | None = None,
           assignment: str | None = None) -> dict:
    """Freeze a project folder (or a GitHub mirror checked out at the selected commit).

    source: provenance (e.g. {"type": "github", "repo": ..., "sha": ..., "branch_ref": ...}) from github.fetch().
    github_meta: API metadata (logins, push activity, PRs) from github.repo_metadata(); used in the history analysis.
    """
    aid = assignment_files(assignment)["id"]  # validates the assignment id before anything is copied
    src = Path(project_dir).resolve()
    if not src.is_dir():
        raise SystemExit(f"Not a directory: {src}")
    project = project_key(src)
    sid = submission_id or f"{project}-{stamp()}"
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sid):
        raise SystemExit(f"Invalid submission id {sid!r}")
    dest = SUBMISSIONS / sid
    if dest.exists():
        raise SystemExit(f"Submission {sid} already exists; submissions are immutable.")

    warnings = []
    current = state.get(project)
    if current and current["state"] != "READY_FOR_FINAL_REVIEW" and not force:
        warnings.append(f"Project state is {current['state']}, not READY_FOR_FINAL_REVIEW (frozen anyway; professor decision).")
    elif not current:
        warnings.append("Project was never reviewed by Agent 1 (no state recorded).")

    files, skipped = [], []
    for p in iter_files(src):
        r = rel(p, src)
        size = p.stat().st_size
        if size > max_file_mb * 1024 * 1024:
            skipped.append({"path": r, "size": size, "sha256": sha256_file(p), "reason": f"> {max_file_mb} MB, not copied"})
            continue
        target = dest / "files" / r
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        files.append({"path": r, "size": size, "sha256": sha256_file(target)})

    log = git_log(src)
    if log:
        write_text(dest / "metadata" / "git-log.txt", log)
    hist = None
    if (src / ".git").exists():
        hist = history.analyze(src, ref="HEAD", deadline=deadline, team=team, github=github_meta,
                               branch_ref=(source or {}).get("branch_ref"), out=dest / "metadata")
    if github_meta:
        write_json(dest / "metadata" / "github.json", github_meta)
    metadata = [{"path": rel(p, dest / "metadata"), "sha256": sha256_file(p)}
                for p in sorted((dest / "metadata").rglob("*")) if p.is_file()] if (dest / "metadata").exists() else []

    manifest = {"submission_id": sid, "files": files, "skipped_large_files": skipped, "metadata": metadata,
                "manifest_sha256": manifest_digest(files + metadata)}
    write_json(dest / "manifest.json", manifest)
    sub = {
        "submission_id": sid,
        "project": project,
        "student": student,
        "assignment": aid,
        "source_path": str(src),
        "source": source or {"type": "local", "path": str(src)},
        "git_commit": hist["head_sha"] if hist and hist.get("available") else None,
        "deadline": deadline,
        "team": team or [],
        "frozen_at": now_iso(),
        "state": "FINAL_SUBMISSION",
        "file_count": len(files),
        "manifest_sha256": manifest["manifest_sha256"],
        "versions_at_freeze": collect_versions(aid),
        "warnings": warnings,
    }
    write_json(dest / "submission.json", sub)

    # Make the frozen copy read-only (the PreToolUse hook additionally blocks agent edits).
    for p in [*(dest / "files").rglob("*"), *(dest / "metadata").rglob("*")]:
        if p.is_file():
            os.chmod(p, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    state.set_state(project, "FINAL_SUBMISSION", ref=sid)
    return sub


def verify(submission_id: str) -> dict:
    dest = SUBMISSIONS / submission_id
    manifest = load_json(dest / "manifest.json")
    problems = []
    expected = {f["path"]: f["sha256"] for f in manifest["files"]}
    actual = {rel(p, dest / "files"): p for p in iter_files(dest / "files")}
    for path, h in expected.items():
        if path not in actual:
            problems.append({"path": path, "problem": "missing"})
        elif sha256_file(actual[path]) != h:
            problems.append({"path": path, "problem": "modified"})
    for path in actual:
        if path not in expected:
            problems.append({"path": path, "problem": "added after freeze"})
    for m in manifest.get("metadata", []):
        mp = dest / "metadata" / m["path"]
        if not mp.exists():
            problems.append({"path": "metadata/" + m["path"], "problem": "missing"})
        elif sha256_file(mp) != m["sha256"]:
            problems.append({"path": "metadata/" + m["path"], "problem": "modified"})
    return {"submission_id": submission_id, "intact": not problems, "problems": problems,
            "manifest_sha256": manifest["manifest_sha256"], "checked_at": now_iso()}
