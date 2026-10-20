"""Artifact processor: inventories a project and extracts text so agents can cite exact locations.

Outputs (in <out>/):
  inventory.json                 every file with kind, size, sha256, line count
  extracted/<path>.cells.md      notebooks rendered as numbered cells ("cell <n>" locations)
  extracted/<path>.txt           text extracted from .docx (stdlib) and .pdf (if pypdf is installed)
  git-log.txt                    commit history, when the project is a git repo
"""
from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path

from .common import iter_files, now_iso, read_text_safe, rel, sha256_file, write_json, write_text

KINDS = {
    "code": {".py", ".r", ".jl", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".scala", ".sh", ".m", ".go", ".rs"},
    "notebook": {".ipynb"},
    "document": {".pdf", ".docx", ".doc", ".tex", ".md", ".txt", ".rst", ".bib", ".odt"},
    "data": {".csv", ".tsv", ".parquet", ".xlsx", ".xls", ".h5", ".hdf5", ".npy", ".npz", ".pkl", ".pickle",
             ".feather", ".arrow", ".jsonl", ".json", ".zip", ".gz", ".tar", ".sqlite", ".db"},
    "model": {".pt", ".pth", ".ckpt", ".onnx", ".joblib", ".safetensors", ".keras", ".pb", ".bin"},
    "image": {".png", ".jpg", ".jpeg", ".svg", ".gif", ".bmp", ".webp", ".tif", ".tiff"},
    "presentation": {".pptx", ".ppt", ".key", ".odp"},
    "config": {".yml", ".yaml", ".toml", ".cfg", ".ini", ".lock", ".env"},
}
CONFIG_NAMES = {"requirements.txt", "dockerfile", "makefile", "pipfile", "setup.py", "environment.yml",
                ".python-version", "runtime.txt"}
TEXT_KINDS = {"code", "document", "config"}


def classify(path: Path) -> str:
    name = path.name.lower()
    if name in CONFIG_NAMES or name.startswith("requirements") and name.endswith(".txt"):
        return "config"
    ext = path.suffix.lower()
    for kind, exts in KINDS.items():
        if ext in exts:
            return kind
    return "other"


def notebook_to_cells(path: Path) -> tuple[str, dict]:
    """Render a notebook as markdown with stable 'cell <n>' headers (n = 1-based index over all cells)."""
    try:
        nb = json.loads(read_text_safe(path, 200_000_000))
    except json.JSONDecodeError as e:
        return f"<<could not parse notebook: {e}>>\n", {"parse_error": str(e)}
    cells = nb.get("cells", [])
    out = [f"# {path.name} (extracted; cite as 'cell <n>')\n"]
    exec_counts, code_cells, code_lines = [], 0, 0
    for i, cell in enumerate(cells, start=1):
        src = cell.get("source", "")
        src = "".join(src) if isinstance(src, list) else src
        ctype = cell.get("cell_type", "?")
        ec = cell.get("execution_count")
        header = f"\n## cell {i} [{ctype}" + (f", exec {ec}" if ctype == "code" else "") + "]\n"
        out.append(header)
        if ctype == "code":
            code_cells += 1
            code_lines += src.count("\n") + (1 if src else 0)
            exec_counts.append(ec)
            out.append("```python\n" + src + "\n```\n")
            texts = []
            for o in cell.get("outputs", []):
                if "text" in o:
                    t = o["text"]
                    texts.append("".join(t) if isinstance(t, list) else t)
                elif "data" in o and "text/plain" in o["data"]:
                    t = o["data"]["text/plain"]
                    texts.append("".join(t) if isinstance(t, list) else t)
                elif o.get("output_type") == "error":
                    texts.append(f"ERROR {o.get('ename')}: {o.get('evalue')}")
            if texts:
                joined = "\n".join(texts)
                if len(joined) > 4000:
                    joined = joined[:4000] + "\n... [output truncated]"
                out.append("Output:\n```\n" + joined + "\n```\n")
        else:
            out.append(src + "\n")
    executed = [c for c in exec_counts if c is not None]
    meta = {
        "cells": len(cells),
        "code_cells": code_cells,
        "code_lines": code_lines,
        "executed_cells": len(executed),
        "execution_in_order": executed == sorted(executed),
        "kernel": (nb.get("metadata", {}).get("kernelspec", {}) or {}).get("name"),
    }
    return "".join(out), meta


def docx_to_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError) as e:
        return f"<<could not extract docx: {e}>>"
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(a, b)
    return text


def pdf_to_text(path: Path) -> str | None:
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            pages.append(f"\n===== p. {i} =====\n{page.extract_text() or ''}")
        return "".join(pages)
    except Exception as e:  # pypdf raises many exception types on malformed files
        return f"<<could not extract pdf: {e}>>"


def git_log(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "log", "--date=iso", "--format=%h|%ad|%an|%s", "--shortstat"],
            capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_inventory(root: Path, out: Path) -> dict:
    root, out = Path(root).resolve(), Path(out)
    files, notes = [], []
    extracted_dir = out / "extracted"
    for p in iter_files(root):
        kind = classify(p)
        entry = {"path": rel(p, root), "kind": kind, "size": p.stat().st_size, "sha256": sha256_file(p)}
        if kind in TEXT_KINDS and p.suffix.lower() not in {".pdf", ".docx", ".doc", ".odt"}:
            entry["lines"] = read_text_safe(p).count("\n") + 1
        if kind == "notebook":
            md, meta = notebook_to_cells(p)
            target = extracted_dir / (entry["path"] + ".cells.md")
            write_text(target, md)
            entry["extracted"] = rel(target, out)
            entry["notebook"] = meta
        elif p.suffix.lower() == ".docx":
            target = extracted_dir / (entry["path"] + ".txt")
            write_text(target, docx_to_text(p))
            entry["extracted"] = rel(target, out)
        elif p.suffix.lower() == ".pdf":
            text = pdf_to_text(p)
            if text is None:
                notes.append(f"{entry['path']}: pypdf not installed; read the PDF directly with the Read tool (pages=...).")
            else:
                target = extracted_dir / (entry["path"] + ".txt")
                write_text(target, text)
                entry["extracted"] = rel(target, out)
        files.append(entry)

    log = git_log(root)
    if log is None and (root.parent / "metadata" / "git-log.txt").exists():
        log = read_text_safe(root.parent / "metadata" / "git-log.txt")  # frozen submission
    if log:
        write_text(out / "git-log.txt", log)

    counts: dict[str, int] = {}
    for f in files:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    inv = {
        "root": str(root),
        "generated_at": now_iso(),
        "file_count": len(files),
        "counts_by_kind": counts,
        "git_history": "git-log.txt" if log else None,
        "notes": notes,
        "files": files,
    }
    write_json(out / "inventory.json", inv)
    return inv


def inventory_paths(inv: dict) -> set[str]:
    return {f["path"] for f in inv.get("files", [])}
