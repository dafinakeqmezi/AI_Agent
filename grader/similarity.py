"""Class-wide comparison of submissions: shared code, shared text and shared git history between students.

Produces RISK INDICATORS for the professor (INT-016, INT-017), never findings, and never changes a score.

Method (MOSS-like, stdlib only):
  code  - language-agnostic tokens; identifiers -> V, strings -> S, numbers -> N (renaming variables does not hide a
          copy); k-gram hashes selected by winnowing; fingerprints that appear in many submissions (common helpers,
          course examples) or in the professor's base code are ignored.
  text  - the same on lower-cased words of README/report/notebook-markdown and text extracted from PDF/DOCX.
  git   - from the history analysed at freeze time: identical commit SHAs, commits authored by another student's
          identity, identical non-trivial files, identical non-generic commit messages, and when each matched file
          first appeared in each repository (who had it first).

Output: evaluations/_class/<assignment>/similarity-<ts>/similarity.json + similarity.md
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from .common import (DEFAULT_ASSIGNMENT, EVALUATIONS, INTEGRITY_FILE, SUBMISSIONS, assignment_files, iter_files,
                     load_json, now_iso, project_key, read_text_safe, rel, stamp, write_json, write_text)

CODE_EXT = {".py", ".java", ".c", ".h", ".cpp", ".cc", ".hpp", ".cs", ".js", ".ts", ".go", ".kt", ".rb", ".php",
            ".m", ".r", ".jl", ".swift", ".scala", ".rs"}
HASH_COMMENT = {".py", ".r", ".rb", ".jl"}
DOC_EXT = {".md", ".txt", ".tex", ".rst"}
GENERIC_MSG = re.compile(r"(?i)^(update|fix|wip|commit|changes?|initial commit|first commit|add files via upload|"
                         r"upload|merge.*|minor|test|\.+|done|final)\s*\S{0,3}$")

KEYWORDS = set("""
and as assert async await break class continue def del elif else except finally for from global if import in is
lambda nonlocal not or pass raise return try while with yield True False None self
abstract boolean byte case catch char const default do double enum extends final float goto implements instanceof
int interface long native new package private protected public short static super switch synchronized this throw
throws transient void volatile auto extern register signed sizeof struct typedef union unsigned include define
bool string var let function null undefined typeof of std vector map set namespace using template typename
""".split())
# Library/API names keep their identity (students rarely rename them); everything else becomes V.
KEEP = set("""
print range len list dict set tuple int str float bool min max sum abs sorted enumerate zip map filter any all open
append pop popleft appendleft extend insert remove copy deepcopy deque Queue PriorityQueue heapq heappush heappop
queue collections itertools permutations combinations product numpy np random time sys math isinstance
System out println printf scanf cout cin endl push_back size console log
""".split())

TOKEN_RE = re.compile(r'''("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|'''
                      r'''\d+(?:\.\d+)?|[A-Za-z_]\w*|==|!=|<=|>=|\+=|-=|\*=|/=|->|::|&&|\|\||<<|>>|\*\*|//|[^\s\w])''')


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


def strip_comments(text: str, ext: str) -> str:
    """Blank out comments but keep line structure (so line numbers stay correct)."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    if ext in HASH_COMMENT:
        return re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|#[^\n]*',
                      lambda m: m.group(0) if m.group(1) else blank(m), text)
    return re.sub(r'("(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m.group(0) if m.group(1) else blank(m), text)


def code_tokens(text: str, ext: str) -> list[tuple[str, int]]:
    """[(normalized token, line number)]"""
    text = strip_comments(text, ext)
    out, line, pos = [], 1, 0
    for m in TOKEN_RE.finditer(text):
        line += text.count("\n", pos, m.start())
        pos = m.start()
        t = m.group(0)
        if t[0] in "\"'":
            tok = "S"
        elif t[0].isdigit():
            tok = "N"
        elif t[0].isalpha() or t[0] == "_":
            tok = t if (t in KEYWORDS or t in KEEP) else "V"
        else:
            tok = t
        out.append((tok, line))
    return out


def word_tokens(text: str) -> list[tuple[str, int]]:
    out = []
    for ln, line in enumerate(text.splitlines(), start=1):
        for w in re.findall(r"[^\W\d_]{2,}|\d+", line.lower()):
            out.append((w, ln))
    return out


def winnow(tokens: list[tuple[str, int]], k: int, w: int) -> dict[int, tuple[int, int]]:
    """Fingerprints {hash: (first line, last line)} selected by winnowing (Schleimer et al., 2003)."""
    if len(tokens) < k:
        return {}
    grams = [(_h(" ".join(t for t, _ in tokens[i:i + k])), tokens[i][1], tokens[i + k - 1][1])
             for i in range(len(tokens) - k + 1)]
    fps: dict[int, tuple[int, int]] = {}
    last = None
    for i in range(max(1, len(grams) - w + 1)):
        window = grams[i:i + w]
        j = min(range(len(window)), key=lambda x: (window[x][0], -x))
        pick = i + j
        if pick != last:
            hv, a, b = grams[pick]
            fps.setdefault(hv, (a, b))
            last = pick
    return fps


# ------------------------------------------------------------------ loading submissions

def _notebook(path: Path) -> tuple[str, str]:
    """(code with '# cell n' markers kept as blank lines, markdown text)"""
    try:
        nb = json.loads(read_text_safe(path, 200_000_000))
    except json.JSONDecodeError:
        return "", ""
    code, md = [], []
    for cell in nb.get("cells", []):
        src = cell.get("source", "")
        src = "".join(src) if isinstance(src, list) else src
        (code if cell.get("cell_type") == "code" else md).append(src)
    return "\n".join(code), "\n".join(md)


def _extracted_docs(sid: str, files_dir: Path) -> list[tuple[str, str]]:
    """Text of PDF/DOCX documents: from the latest evaluation's artifacts, else extracted now."""
    runs = sorted((EVALUATIONS / sid).glob("eval-*/artifacts/extracted")) if (EVALUATIONS / sid).exists() else []
    ex = runs[-1] if runs else None
    if ex is None:
        from .inventory import build_inventory
        tmp = Path(tempfile.mkdtemp(prefix="sim-"))
        try:
            build_inventory(files_dir, tmp)
        except Exception:  # extraction is best effort
            return []
        ex = tmp / "extracted"
    if not ex.exists():
        return []
    return [(p.relative_to(ex).as_posix()[:-4], read_text_safe(p)) for p in sorted(ex.rglob("*.txt"))]


def load_submission(sid: str, cfg: dict) -> dict:
    sub_dir = SUBMISSIONS / sid
    files_dir = sub_dir / "files"
    sub = load_json(sub_dir / "submission.json")
    code_fp: dict[int, list] = defaultdict(list)
    doc_fp: dict[int, list] = defaultdict(list)
    lines_cache: dict[str, list[str]] = {}
    for p in iter_files(files_dir):
        r, ext = rel(p, files_dir), p.suffix.lower()
        if ext in CODE_EXT:
            text = read_text_safe(p)
            lines_cache[r] = text.splitlines()
            for hv, span in winnow(code_tokens(text, ext), cfg["code_k_tokens"], cfg["code_window"]).items():
                code_fp[hv].append((r, *span))
        elif ext == ".ipynb":
            code, md = _notebook(p)
            lines_cache[r + " (code cells)"] = code.splitlines()
            for hv, span in winnow(code_tokens(code, ".py"), cfg["code_k_tokens"], cfg["code_window"]).items():
                code_fp[hv].append((r + " (code cells)", *span))
            lines_cache[r + " (markdown cells)"] = md.splitlines()
            for hv, span in winnow(word_tokens(md), cfg["doc_k_words"], cfg["doc_window"]).items():
                doc_fp[hv].append((r + " (markdown cells)", *span))
        elif ext in DOC_EXT:
            text = read_text_safe(p)
            lines_cache[r] = text.splitlines()
            for hv, span in winnow(word_tokens(text), cfg["doc_k_words"], cfg["doc_window"]).items():
                doc_fp[hv].append((r, *span))
    for name, text in _extracted_docs(sid, files_dir):
        lines_cache[name] = text.splitlines()
        for hv, span in winnow(word_tokens(text), cfg["doc_k_words"], cfg["doc_window"]).items():
            doc_fp[hv].append((name, *span))
    manifest = load_json(sub_dir / "manifest.json")
    hist = load_json(sub_dir / "metadata" / "history.json") if (sub_dir / "metadata" / "history.json").exists() else {}
    return {"sid": sid, "project": sub.get("project"), "student": sub.get("student"), "team": sub.get("team") or [],
            "code": dict(code_fp), "docs": dict(doc_fp), "lines": lines_cache,
            "files": {f["path"]: f for f in manifest.get("files", [])},
            "commits": hist.get("commits") or [], "authors": hist.get("authors") or []}


def _base_fingerprints(base: Path | None, cfg: dict) -> set[int]:
    if not base:
        return set()
    fps = set()
    for p in iter_files(Path(base)):
        ext = p.suffix.lower()
        if ext in CODE_EXT:
            fps |= set(winnow(code_tokens(read_text_safe(p), ext), cfg["code_k_tokens"], cfg["code_window"]))
        elif ext in DOC_EXT:
            fps |= set(winnow(word_tokens(read_text_safe(p)), cfg["doc_k_words"], cfg["doc_window"]))
    return fps


# ------------------------------------------------------------------ comparison

def _regions(a: dict, b: dict, shared: set[int], la: dict, lb: dict, limit: int = 8) -> list[dict]:
    """Merge matched fingerprints into line regions per file pair, largest first, with short quotes."""
    pairs: dict[tuple[str, str], list] = defaultdict(list)
    for hv in shared:
        for fa, a1, a2 in a[hv]:
            for fb, b1, b2 in b[hv]:
                pairs[(fa, fb)].append((a1, a2, b1, b2))
    regions = []
    for (fa, fb), spans in pairs.items():
        spans.sort()
        cur = None
        for a1, a2, b1, b2 in spans:
            if cur and a1 <= cur[1] + 2:
                cur = [cur[0], max(cur[1], a2), min(cur[2], b1), max(cur[3], b2), cur[4] + 1]
            else:
                if cur:
                    regions.append((fa, fb, *cur))
                cur = [a1, a2, b1, b2, 1]
        if cur:
            regions.append((fa, fb, *cur))
    regions.sort(key=lambda r: -r[6])

    def quote(lines, s, e):
        body = [x.rstrip() for x in lines[s - 1:e] if x.strip()]
        return "\n".join(body[:5])[:400]

    out = []
    for fa, fb, a1, a2, b1, b2, n in regions[:limit]:
        out.append({"file_a": fa, "lines_a": f"L{a1}-L{a2}", "file_b": fb, "lines_b": f"L{b1}-L{b2}", "fingerprints": n,
                    "quote_a": quote(la.get(fa, []), a1, a2), "quote_b": quote(lb.get(fb, []), b1, b2)})
    return out


def _containment(shared: set, a: dict, b: dict) -> tuple[float, float]:
    na, nb = len(a), len(b)
    if not na or not nb:
        return 0.0, 0.0
    return round(len(shared) / min(na, nb), 3), round(len(shared) / len(set(a) | set(b)), 3)


def _first_seen(commits: list[dict], path: str) -> str | None:
    dates = [c.get("author_date") for c in commits if path in (c.get("paths") or []) and c.get("author_date")]
    return min(dates) if dates else None


def _own(s: dict, c: dict) -> bool:
    """Is commit c by the repository's own student? Roster team (emails/logins) if given, else the top author."""
    if s["team"]:
        team = {t.lower() for t in s["team"]}
        return any(str(x).lower() in team for x in (c.get("identity"), c.get("author_email"), c.get("login")) if x)
    top = max(s["authors"], key=lambda a: a.get("commits") or 0, default={}).get("identity")
    return c.get("identity") == top


def _git(a: dict, b: dict, cfg: dict, common_files: set[str]) -> dict:
    shas_a = {c["sha"] for c in a["commits"] if not c.get("merge")}
    shared_commits = sorted(shas_a & {c["sha"] for c in b["commits"] if not c.get("merge")})
    foreign = []
    for x, y in ((a, b), (b, a)):
        x_ids = {c.get("identity") for c in x["commits"] if _own(x, c)}
        for c in y["commits"]:
            # a commit in y's repository written by x's own student, and not by y's student
            if c.get("identity") in x_ids and not _own(y, c) and c.get("sha") not in shared_commits:
                foreign.append({"identity": c["identity"], "of": x["sid"], "commit_in": y["sid"], "commit": c.get("short"),
                                "date": c.get("author_date"), "subject": c.get("subject")})
    identical = []
    by_hash_b = defaultdict(list)
    for path, f in b["files"].items():
        by_hash_b[f["sha256"]].append(path)
    for path, f in a["files"].items():
        if f["size"] < cfg["min_identical_file_bytes"] or f["sha256"] in common_files:
            continue
        for pb in by_hash_b.get(f["sha256"], []):
            identical.append({"file_a": path, "file_b": pb, "bytes": f["size"],
                              "first_seen_a": _first_seen(a["commits"], path), "first_seen_b": _first_seen(b["commits"], pb)})
    msgs = lambda s: {c["subject"].strip() for c in s["commits"]
                      if c.get("subject") and len(c["subject"].strip()) >= 15 and not GENERIC_MSG.match(c["subject"].strip())}
    return {"shared_commits": shared_commits[:20], "shared_commit_count": len(shared_commits),
            "foreign_identity_commits": foreign[:20], "identical_files": identical[:30],
            "shared_commit_messages": sorted(msgs(a) & msgs(b))[:20]}


def _level(code_c: float, doc_c: float, git: dict, cfg: dict) -> tuple[str, list[str]]:
    reasons = []
    level = "NONE"
    order = ["NONE", "LOW", "MEDIUM", "HIGH"]
    for name in ("LOW", "MEDIUM", "HIGH"):
        t = cfg["levels"][name]
        if code_c >= t["code_containment"] or doc_c >= t["doc_containment"]:
            level = name
    if code_c >= cfg["levels"]["LOW"]["code_containment"]:
        reasons.append(f"code containment {code_c:.0%}")
    if doc_c >= cfg["levels"]["LOW"]["doc_containment"]:
        reasons.append(f"text containment {doc_c:.0%}")
    for key in cfg["always_high"]:
        n = git["shared_commit_count"] if key == "shared_commits" else len(git[key])
        if n:
            level = "HIGH"
            reasons.append(f"{key.replace('_', ' ')}: {n}")
    for key in cfg["at_least_medium"]:
        if git[key]:
            level = max(level, "MEDIUM", key=order.index)
            reasons.append(f"{key.replace('_', ' ')}: {len(git[key])}")
    return level, reasons


def roster_projects(roster: Path | str) -> set[str]:
    """Project keys of the repos in a roster (GitHub owner/repo -> mirror key, local folder -> folder key)."""
    from . import github
    keys = set()
    for st in load_json(roster).get("students", []):
        spec = str(st.get("repo") or "")
        parsed = github.parse_repo(spec) if github.is_repo_spec(spec) else None
        keys.add(project_key(github.mirror_dir(*parsed)) if parsed else project_key(spec))
    return keys


def class_submissions(assignment: str | None = None, ids: list[str] | None = None,
                      roster: Path | str | None = None) -> list[str]:
    """Latest frozen submission per project for the assignment, optionally limited to a roster's repos."""
    if ids:
        return ids
    aid = assignment_files(assignment)["id"]
    only = roster_projects(roster) if roster else None
    latest: dict[str, tuple[str, str]] = {}
    for d in sorted(SUBMISSIONS.iterdir()) if SUBMISSIONS.exists() else []:
        if not (d / "submission.json").exists():
            continue
        s = load_json(d / "submission.json")
        if (s.get("assignment") or DEFAULT_ASSIGNMENT) != aid:
            continue
        key = s.get("project") or d.name
        if only is not None and key not in only:
            continue
        if key not in latest or (s.get("frozen_at") or "") > latest[key][1]:
            latest[key] = (d.name, s.get("frozen_at") or "")
    return sorted(v[0] for v in latest.values())


def run(assignment: str | None = None, ids: list[str] | None = None, base: Path | None = None,
        out: Path | None = None, roster: Path | str | None = None) -> dict:
    aid = assignment_files(assignment)["id"]
    cfg = load_json(INTEGRITY_FILE)["cross_submission_similarity"]
    sids = class_submissions(aid, ids, roster)
    subs = [load_submission(s, cfg) for s in sids]
    n = len(subs)
    base_fps = _base_fingerprints(base, cfg)

    def common(kind: str) -> set[int]:
        df = defaultdict(int)
        for s in subs:
            for hv in s[kind]:
                df[hv] += 1
        limit = max(2, cfg["common_fraction"] * n)
        return {hv for hv, c in df.items() if n >= cfg["common_min_submissions"] and c >= limit} | base_fps

    common_code, common_docs = common("code"), common("docs")
    file_df = defaultdict(int)
    for s in subs:
        for h in {f["sha256"] for f in s["files"].values()}:
            file_df[h] += 1
    common_files = {h for h, c in file_df.items() if n >= cfg["common_min_submissions"] and c >= max(2, cfg["common_fraction"] * n)}

    pairs = []
    for a, b in itertools.combinations(subs, 2):
        ca = {h: v for h, v in a["code"].items() if h not in common_code}
        cb = {h: v for h, v in b["code"].items() if h not in common_code}
        da = {h: v for h, v in a["docs"].items() if h not in common_docs}
        db = {h: v for h, v in b["docs"].items() if h not in common_docs}
        sc, sd = set(ca) & set(cb), set(da) & set(db)
        code_c, code_j = _containment(sc, ca, cb)
        doc_c, doc_j = _containment(sd, da, db)
        git = _git(a, b, cfg, common_files)
        level, reasons = _level(code_c, doc_c, git, cfg)
        pairs.append({
            "a": a["sid"], "b": b["sid"], "project_a": a["project"], "project_b": b["project"],
            "student_a": a["student"], "student_b": b["student"], "level": level, "reasons": reasons,
            "code": {"containment": code_c, "jaccard": code_j, "shared_fingerprints": len(sc),
                     "fingerprints_a": len(ca), "fingerprints_b": len(cb),
                     "regions": _regions(ca, cb, sc, a["lines"], b["lines"]) if sc else []},
            "docs": {"containment": doc_c, "jaccard": doc_j, "shared_fingerprints": len(sd),
                     "regions": _regions(da, db, sd, a["lines"], b["lines"], limit=5) if sd else []},
            "git": git,
        })
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
    pairs.sort(key=lambda p: (order[p["level"]], -max(p["code"]["containment"], p["docs"]["containment"])))
    result = {"generated_at": now_iso(), "assignment": aid, "submissions": sids, "n": n,
              "roster": str(roster) if roster else None,
              "students": {s["sid"]: {"student": s["student"], "project": s["project"]} for s in subs},
              "config": cfg, "base_code": str(base) if base else None,
              "ignored_common_fingerprints": {"code": len(common_code), "docs": len(common_docs)},
              "counts": {lv: sum(1 for p in pairs if p["level"] == lv) for lv in order},
              "pairs": pairs,
              "disclaimer": load_json(INTEGRITY_FILE)["mandatory_disclaimer"] +
                            " Similarity is a review priority for the professor, not proof of copying; "
                            "short standard algorithms are naturally similar."}
    out = Path(out) if out else EVALUATIONS / "_class" / aid / f"similarity-{stamp()}"
    write_json(out / "similarity.json", result)
    write_text(out / "similarity.md", render(result))
    result["out_dir"] = str(out)
    return result


def latest(assignment: str) -> dict | None:
    runs = sorted((EVALUATIONS / "_class" / assignment).glob("similarity-*/similarity.json"))
    return load_json(runs[-1]) if runs else None


def render(r: dict) -> str:
    name = lambda sid: f"{r['students'][sid]['student'] or '?'} ({sid})"
    L = [f"# Class similarity report: {r['assignment']}", "",
         f"Generated {r['generated_at']} · {r['n']} submissions · {len(r['pairs'])} pairs · "
         f"HIGH {r['counts']['HIGH']}, MEDIUM {r['counts']['MEDIUM']}, LOW {r['counts']['LOW']}", "",
         f"> {r['disclaimer']}", "",
         f"Ignored as common (in at least {r['config']['common_fraction']:.0%} of submissions, or base code): "
         f"{r['ignored_common_fingerprints']['code']} code and {r['ignored_common_fingerprints']['docs']} text fingerprints.", "",
         "| Level | Student A | Student B | Code | Text | Git |", "|---|---|---|---|---|---|"]
    for p in r["pairs"]:
        g = p["git"]
        gs = ", ".join(x for x in [f"{g['shared_commit_count']} shared commits" if g["shared_commit_count"] else "",
                                   f"{len(g['foreign_identity_commits'])} foreign-identity commits" if g["foreign_identity_commits"] else "",
                                   f"{len(g['identical_files'])} identical files" if g["identical_files"] else "",
                                   f"{len(g['shared_commit_messages'])} shared messages" if g["shared_commit_messages"] else ""] if x) or "-"
        L.append(f"| {p['level']} | {name(p['a'])} | {name(p['b'])} | {p['code']['containment']:.0%} | {p['docs']['containment']:.0%} | {gs} |")
    for p in r["pairs"]:
        if p["level"] in ("NONE", "LOW"):
            continue
        L += ["", f"## {p['level']}: {name(p['a'])} and {name(p['b'])}", "", "Reasons: " + "; ".join(p["reasons"]), ""]
        for kind in ("code", "docs"):
            for x in p[kind]["regions"]:
                L += [f"- {kind}: `{x['file_a']}` {x['lines_a']} ↔ `{x['file_b']}` {x['lines_b']} ({x['fingerprints']} fingerprints)",
                      "", "  ```", *["  " + ln for ln in x["quote_a"].splitlines()], "  ```"]
        g = p["git"]
        for f in g["identical_files"]:
            L.append(f"- identical file: `{f['file_a']}` = `{f['file_b']}` ({f['bytes']} bytes); first seen A {f['first_seen_a'] or '?'}, B {f['first_seen_b'] or '?'}")
        for c in g["foreign_identity_commits"]:
            L.append(f"- commit {c['commit']} in {c['commit_in']} authored by {c['identity']} (main author of {c['of']}), {c['date']}: {c['subject']}")
        if g["shared_commit_count"]:
            L.append(f"- {g['shared_commit_count']} identical commit SHAs (copied history), e.g. {', '.join(s[:7] for s in g['shared_commits'][:5])}")
        for m in g["shared_commit_messages"]:
            L.append(f"- identical commit message: \"{m}\"")
    return "\n".join(L) + "\n"
