"""Version snapshot recorded in every review and evaluation, so any result can be reconstructed."""
from __future__ import annotations

import hashlib

from . import __version__
from .common import AGENTS_DIR, INTEGRITY_FILE, KB, KB_MANIFEST_FILE, assignment_files, load_json, sha256_file


def _short(h: str) -> str:
    return h[:12]


def kb_content_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(KB.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(KB).as_posix().encode())
            h.update(sha256_file(p).encode())
    return h.hexdigest()


def _doc(path, id_key):
    d = load_json(path)
    return {"id": d.get(id_key), "version": d.get("version"), "status": d.get("status"),
            "sha256": _short(sha256_file(path))}


def collect_versions(assignment: str | None = None) -> dict:
    af = assignment_files(assignment)
    agents = {}
    if AGENTS_DIR.exists():
        for p in sorted(AGENTS_DIR.glob("*.md")):
            agents[p.stem] = _short(sha256_file(p))
    manifest = load_json(KB_MANIFEST_FILE)
    return {
        "grader_tool": __version__,
        "assignment": af["id"],
        "rubric": _doc(af["rubric"], "rubric_id"),
        "requirements": _doc(af["requirements"], "requirements_id"),
        "dod": _doc(af["dod"], "dod_id"),
        "integrity_policy": _doc(INTEGRITY_FILE, "policy_id"),
        "knowledge_base": {"version": manifest.get("knowledge_base_version"),
                           "content_sha256": _short(kb_content_hash())},
        "agent_prompts": agents,
    }
