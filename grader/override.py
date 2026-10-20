"""Human (professor) override log. Append-only; the grade is recomputed after each entry."""
from __future__ import annotations

from pathlib import Path

from .common import load_json, now_iso, write_json


def add(eval_dir: Path, entry: dict) -> dict:
    path = Path(eval_dir) / "overrides.json"
    data = load_json(path) if path.exists() else {"overrides": []}
    entry = {"id": f"OVR-{len(data['overrides']) + 1:03d}", "at": now_iso(), **entry}
    data["overrides"].append(entry)
    write_json(path, data)
    return entry
