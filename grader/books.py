"""Add a textbook PDF to the shared knowledge base as a searchable, citable reference.

knowledge-base/literature/books/<key>/
  <key>.pdf        the book (local copy; git-ignored)
  book.json        bibliographic metadata, sha256, page count
  toc.json         full outline: level, section number, title, pdf page
  INDEX.md         chapters and sections with pdf page ranges (what agents read first)
  text/NN-*.txt    extracted text per chapter with "===== pdf p. N =====" markers (git-ignored; for Grep)

Agents retrieve by topic: INDEX.md (or TOPICS.md) -> Grep text/ -> Read the exact pages.
Requires pypdf (pip install pypdf).
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

from .common import KB, now_iso, sha256_file, write_json, write_text

BOOKS = KB / "literature" / "books"


def _page_text(reader, p: int) -> str:
    """Page text with ligatures (ﬁ, ﬂ) normalized (NFKC) so that Grep finds e.g. 'overfitting'."""
    return unicodedata.normalize("NFKC", reader.pages[p - 1].extract_text() or "")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50]


def _outline(reader) -> list[dict]:
    out = []

    def walk(items, depth):
        for it in items:
            if isinstance(it, list):
                walk(it, depth + 1)
                continue
            try:
                page = reader.get_destination_page_number(it) + 1
            except Exception:  # broken bookmark
                continue
            title = " ".join(str(it.title).split())
            m = re.match(r"^(?:Chapter\s+)?(\d+(?:\.\d+)*|[A-Z]\.\d+)\s+(.*)$", title)
            out.append({"level": depth, "number": m.group(1) if m else None,
                        "title": m.group(2) if m else title, "pdf_page": page})
    walk(reader.outline, 0)
    return out


def add_book(pdf: Path, key: str, meta: dict) -> dict:
    from pypdf import PdfReader  # optional dependency, needed only here

    pdf = Path(pdf)
    d = BOOKS / key
    (d / "text").mkdir(parents=True, exist_ok=True)
    target = d / f"{key}.pdf"
    if pdf.resolve() != target.resolve():
        shutil.copy2(pdf, target)
    reader = PdfReader(str(target))
    n = len(reader.pages)
    toc = _outline(reader)

    # chapters = the outline level that has the most numbered entries (e.g. "Chapter 19 ...")
    levels = {}
    for e in toc:
        if e["number"] and "." not in e["number"]:
            levels[e["level"]] = levels.get(e["level"], 0) + 1
    chap_level = max(levels, key=levels.get) if levels else 0
    top = [e for e in toc if e["level"] <= chap_level]
    for i, e in enumerate(top):
        nxt = next((t["pdf_page"] for t in top[i + 1:] if t["pdf_page"] > e["pdf_page"]), n + 1)
        e["end_page"] = nxt - 1
    for e in toc:  # section end pages
        if "end_page" not in e:
            later = [t["pdf_page"] for t in toc if t["pdf_page"] > e["pdf_page"] and t["level"] <= e["level"]]
            e["end_page"] = (min(later) - 1) if later else n

    chapters = [e for e in toc if e["level"] == chap_level]
    chunks = chapters if chapters else [{"number": None, "title": "full text", "pdf_page": 1, "end_page": n}]
    covered = set()
    for i, ch in enumerate(chunks, start=1):
        parts = []
        for p in range(ch["pdf_page"], ch["end_page"] + 1):
            covered.add(p)
            parts.append(f"\n===== pdf p. {p} =====\n{_page_text(reader, p)}")
        name = f"{i:02d}-{'ch' + ch['number'] + '-' if ch['number'] else ''}{_slug(ch['title'])}.txt"
        ch["text_file"] = f"text/{name}"
        write_text(d / "text" / name, f"# {meta.get('short_cite', key)}: {ch['number'] or ''} {ch['title']} "
                                      f"(pdf pp. {ch['pdf_page']}-{ch['end_page']})\n" + "".join(parts))
    rest = [p for p in range(1, n + 1) if p not in covered]
    if rest:  # front matter, appendices, bibliography, index
        write_text(d / "text" / "99-other-pages.txt", "".join(
            f"\n===== pdf p. {p} =====\n{_page_text(reader, p)}" for p in rest))

    book = {**meta, "key": key, "file": target.name, "pdf_pages": n, "sha256": sha256_file(target),
            "added_at": now_iso(), "chapter_level": chap_level}
    write_json(d / "book.json", book)
    write_json(d / "toc.json", toc)

    L = [f"# {meta.get('title', key)}", "",
         f"{', '.join(meta.get('authors', []))}. {meta.get('edition', '')} {meta.get('publisher', '')} {meta.get('year', '')}. "
         f"Cite as **{meta.get('short_cite', key)}, §<section>** (section numbers are stable; pdf page numbers are this file's).", "",
         "How to use (topic retrieval, do not read the whole book):",
         f"1. Find the section below (or in TOPICS.md if present).",
         f"2. `Grep` the chapter text in `text/` for the concept to get exact pdf pages.",
         f"3. `Read` `{target.name}` with `pages: \"a-b\"` (max 20 pages per call) or read the text file around the marker.", "",
         "| Section | Title | pdf pages | Text |", "|---|---|---|---|"]
    for e in toc:
        if e["level"] > chap_level + 1:
            continue
        indent = "&nbsp;&nbsp;" * max(0, e["level"] - chap_level)
        txt = f"`{e['text_file']}`" if e.get("text_file") else ""
        L.append(f"| {indent}{e['number'] or ''} | {indent}{e['title']} | {e['pdf_page']}-{e['end_page']} | {txt} |")
    write_text(d / "INDEX.md", "\n".join(L) + "\n")
    return {"key": key, "dir": str(d), "pages": n, "outline_entries": len(toc), "chapters": len(chapters)}
