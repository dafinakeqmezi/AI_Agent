"""scc (Sloc Cloc and Code, github.com/boyter/scc) integration: code/comment/blank lines and complexity per commit.

Each analysed commit's tree is exported with `git archive` into a temp dir and counted with scc, giving the real
code size over time (comments, blanks and data files excluded), which is a better measure than raw added lines.
Optional: when scc is not installed, history analysis falls back to git numstat.
Install: winget install BenBoyter.scc | brew install scc | go install github.com/boyter/scc/v3@latest
"""
from __future__ import annotations

import glob
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

# Languages that are not program code (documents, data, config) are counted separately.
DOC_LANGS = {"Markdown", "Plain Text", "TeX", "ReStructuredText", "AsciiDoc", "Org", "BibTeX", "License"}
NON_CODE_LANGS = DOC_LANGS | {"JSON", "JSONL", "CSV", "TSV", "YAML", "TOML", "XML", "SVG", "INI", "Properties File",
                              "Gitignore", "Docker ignore", "Happy", "HTML", "CSS", "Batch"}


def find_scc() -> str | None:
    if os.environ.get("SCC_PATH") and Path(os.environ["SCC_PATH"]).exists():
        return os.environ["SCC_PATH"]
    found = shutil.which("scc")
    if found:
        return found
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages", "BenBoyter.scc*", "scc.exe")
    hits = glob.glob(pattern)
    return hits[0] if hits else None


def count_dir(path: Path, scc_bin: str) -> dict:
    r = subprocess.run([scc_bin, "--format", "json", "--no-cocomo", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    langs = json.loads(r.stdout or "[]") if r.returncode == 0 else []
    snap = {"code": 0, "comment": 0, "blank": 0, "complexity": 0, "files": 0, "doc_lines": 0, "languages": {}}
    for lang in langs:
        name = lang["Name"]
        if name in DOC_LANGS:
            snap["doc_lines"] += lang["Code"]
            continue
        if name in NON_CODE_LANGS:
            continue
        snap["code"] += lang["Code"]
        snap["comment"] += lang["Comment"]
        snap["blank"] += lang["Blank"]
        snap["complexity"] += lang["Complexity"]
        snap["files"] += lang["Count"]
        snap["languages"][name] = lang["Code"]
    return snap


def count_commit(repo: Path, sha: str, scc_bin: str) -> dict:
    """Count the tree of one commit without touching the working copy."""
    data = subprocess.run(["git", "archive", "--format=tar", sha], cwd=repo, capture_output=True).stdout
    with tempfile.TemporaryDirectory(prefix="scc-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            try:
                tar.extractall(tmp, filter="data")
            except TypeError:  # Python without tarfile extraction filters
                tar.extractall(tmp)
        return count_dir(Path(tmp), scc_bin)


def snapshots(repo: Path, shas: list[str], scc_bin: str) -> dict[str, dict]:
    return {sha: count_commit(repo, sha, scc_bin) for sha in shas}
