"""Citation verification: extract DOIs / arXiv IDs / reference entries and check them against Crossref and arXiv.

Statuses:
  VERIFIED      identifier resolves and the title matches the reference text
  MISMATCH      identifier resolves to a different title (possible fabrication -> human review)
  NOT_FOUND     identifier does not resolve (possible fabrication -> human review)
  NO_IDENTIFIER reference entry without DOI/arXiv; agent must verify by title (cite --title)
  UNVERIFIED    could not check (offline / network error)
Output: <out>/citations.json
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .common import iter_files, now_iso, read_text_safe, rel, write_json
from .scan import load_extracted_docs

UA = "aiml-project-grader/0.1 (academic project review tool)"
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>{}]+)", re.I)
ARXIV_RE = re.compile(r"(?i)(?:arxiv[:\s]*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?")
REF_HEADING_RE = re.compile(r"(?i)^\s*(#+\s*|\\section\*?\{)?\s*(\d+\.?\s*)?(references|bibliography|literatura|referencat)\s*\}?\s*$")
STOP = {"the", "and", "for", "with", "from", "into", "via", "using", "based", "over", "under", "towards", "toward", "about"}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3 and w not in STOP}


def title_overlap(title: str, context: str) -> float:
    tw = _words(title)
    return len(tw & _words(context)) / len(tw) if tw else 0.0


def _get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def crossref_doi(doi: str) -> tuple[str, dict | None]:
    try:
        data = json.loads(_get("https://api.crossref.org/works/" + urllib.parse.quote(doi)))
        m = data["message"]
        return "FOUND", {
            "title": (m.get("title") or [""])[0],
            "authors": [a.get("family", "") for a in m.get("author", [])][:6],
            "year": ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0],
            "venue": (m.get("container-title") or [""])[0],
        }
    except urllib.error.HTTPError as e:
        return ("NOT_FOUND", None) if e.code == 404 else ("ERROR", {"error": f"HTTP {e.code}"})
    except Exception as e:  # network/parse errors -> UNVERIFIED, never a false accusation
        return "ERROR", {"error": str(e)}


def arxiv_id(aid: str) -> tuple[str, dict | None]:
    try:
        xml = _get("http://export.arxiv.org/api/query?id_list=" + aid)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = ET.fromstring(xml).find("a:entry", ns)
        if entry is None or entry.find("a:title", ns) is None:
            return "NOT_FOUND", None
        title = " ".join(entry.find("a:title", ns).text.split())
        if title.lower() == "error":
            return "NOT_FOUND", None
        authors = [" ".join(a.find("a:name", ns).text.split()) for a in entry.findall("a:author", ns)][:6]
        year = (entry.find("a:published", ns).text or "")[:4]
        return "FOUND", {"title": title, "authors": authors, "year": year, "venue": "arXiv"}
    except Exception as e:
        return "ERROR", {"error": str(e)}


def crossref_title_search(title: str, rows: int = 3) -> list[dict]:
    q = urllib.parse.urlencode({"query.bibliographic": title, "rows": rows})
    data = json.loads(_get("https://api.crossref.org/works?" + q))
    out = []
    for m in data["message"]["items"]:
        t = (m.get("title") or [""])[0]
        out.append({"title": t, "doi": m.get("DOI"),
                    "year": ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0],
                    "authors": [a.get("family", "") for a in m.get("author", [])][:4],
                    "title_overlap": round(title_overlap(title, t), 2)})
    return out


def _documents(root: Path, out: Path | None) -> list[tuple[str, str]]:
    docs = []
    for p in iter_files(root):
        if p.suffix.lower() in {".md", ".txt", ".tex", ".rst", ".bib"}:
            docs.append((rel(p, root), read_text_safe(p)))
        elif p.suffix.lower() == ".ipynb":
            try:
                nb = json.loads(read_text_safe(p, 200_000_000))
                md = ["".join(c["source"]) if isinstance(c.get("source"), list) else c.get("source", "")
                      for c in nb.get("cells", []) if c.get("cell_type") == "markdown"]
                docs.append((rel(p, root) + " (markdown cells)", "\n".join(md)))
            except (json.JSONDecodeError, KeyError):
                pass
    if out is not None:
        docs += load_extracted_docs(out)
    return docs


# A list marker must be followed by whitespace: "*Journal of ...*" on a wrapped line is not a new entry.
ENTRY_START_RE = re.compile(r"^\s*(\[\d+\]|\d+[.)](?=\s)|[-*•](?=\s)|@\w+\{)\s*")


def _entry_context(lines: list[str], idx: int) -> str:
    """Text of the reference entry containing line idx: the line itself, extended upwards for wrapped entries."""
    parts = [lines[idx]]
    j = idx
    while (len(_words(DOI_RE.sub("", " ".join(parts)))) < 6 and j > 0 and idx - j < 3
           and not ENTRY_START_RE.match(lines[j]) and lines[j - 1].strip()):
        j -= 1
        parts.insert(0, lines[j])
    return " ".join(parts)


def _reference_entries(text: str) -> list[tuple[int, str, set[int]]]:
    """Entries of the References section as (first line no, text, line numbers spanned).

    Entries are delimited by list markers ([1], 1., -) when present, otherwise by blank lines."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if REF_HEADING_RE.match(l)), None)
    if start is None:
        return []
    section = []
    for i in range(start + 1, len(lines)):
        if re.match(r"^\s*(#+\s|\\section)", lines[i]):
            break
        section.append((i + 1, lines[i]))
    use_markers = any(ENTRY_START_RE.match(l) for _, l in section)
    entries, cur = [], None
    for ln, l in section:
        if not l.strip():
            if not use_markers:
                cur = None
            continue
        if cur is None or (use_markers and ENTRY_START_RE.match(l)):
            cur = [ln, l.strip(), {ln}]
            entries.append(cur)
        else:
            cur[1] += " " + l.strip()
            cur[2].add(ln)
    return [(ln, t, s) for ln, t, s in entries if len(t) > 25]


def verify_project(root: Path, out: Path, offline: bool = False) -> dict:
    root, out = Path(root).resolve(), Path(out)
    results, seen = [], set()
    for fname, text in _documents(root, out):
        lines = text.splitlines()
        entries = _reference_entries(text)
        entry_of_line = {n: entry for _, entry, span in entries for n in span}
        id_lines = set()
        for i, line in enumerate(lines, start=1):
            ids = [("doi", m.group(1).rstrip(".,;)]}'\"")) for m in DOI_RE.finditer(line)]
            ids += [("arxiv", m.group(1)) for m in ARXIV_RE.finditer(line)]
            for kind, ident in ids:
                id_lines.add(i)
                key = (kind, ident.lower())
                if key in seen:
                    continue
                seen.add(key)
                # compare against the whole (possibly wrapped) reference entry; fall back to nearby lines in body text
                context = entry_of_line.get(i) or _entry_context(lines, i - 1)
                rec = {"file": fname, "location": f"L{i}", "kind": kind, "identifier": ident,
                       "reference_text": context.strip()[:400]}
                if offline:
                    rec["status"] = "UNVERIFIED"
                    rec["note"] = "offline mode"
                else:
                    found, meta = crossref_doi(ident) if kind == "doi" else arxiv_id(ident)
                    time.sleep(0.2)
                    if found == "FOUND":
                        ov = title_overlap(meta["title"], context)
                        rec["registry_record"] = meta
                        rec["title_overlap"] = round(ov, 2)
                        rec["status"] = "VERIFIED" if ov >= 0.6 else "MISMATCH"
                        if rec["status"] == "MISMATCH":
                            rec["note"] = "Identifier resolves to a different title than the reference text. Check manually (possible INT-009)."
                    elif found == "NOT_FOUND":
                        rec["status"] = "NOT_FOUND"
                        rec["note"] = "Identifier does not resolve. Search the title manually before flagging (possible INT-001)."
                    else:
                        rec["status"] = "UNVERIFIED"
                        rec["note"] = (meta or {}).get("error", "network error")
                results.append(rec)
        for ln, entry, span in entries:
            if span & id_lines:  # already checked via its DOI/arXiv id
                continue
            results.append({"file": fname, "location": f"L{ln}", "kind": "entry", "identifier": None,
                            "reference_text": entry[:400], "status": "NO_IDENTIFIER",
                            "note": 'Verify by title: python -m grader cite --title "<title>" (or WebSearch the exact title).'})
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    data = {"generated_at": now_iso(), "offline": offline, "counts": counts, "citations": results,
            "disclaimer": "NOT_FOUND / MISMATCH are risk indicators requiring human review, not proof of fabrication."}
    write_json(out / "citations.json", data)
    return data
