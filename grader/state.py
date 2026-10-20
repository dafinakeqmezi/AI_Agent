"""Submission lifecycle: DRAFT -> UNDER_REVIEW -> READY_FOR_FINAL_REVIEW -> FINAL_SUBMISSION -> GRADED."""
from __future__ import annotations

from .common import STATE_FILE, STATES, load_json, now_iso, write_json


def _load() -> dict:
    return load_json(STATE_FILE) if STATE_FILE.exists() else {"projects": {}}


def get(project: str) -> dict | None:
    return _load()["projects"].get(project)


def set_state(project: str, state: str, ref: str | None = None, note: str | None = None) -> dict:
    if state not in STATES:
        raise ValueError(f"Unknown state {state!r}; expected one of {STATES}")
    reg = _load()
    p = reg["projects"].setdefault(project, {"state": "DRAFT", "history": []})
    p["state"] = state
    p["updated_at"] = now_iso()
    entry = {"state": state, "at": p["updated_at"]}
    if ref:
        entry["ref"] = ref
    if note:
        entry["note"] = note
    p["history"].append(entry)
    write_json(STATE_FILE, reg)
    return p


def all_projects() -> dict:
    return _load()["projects"]
