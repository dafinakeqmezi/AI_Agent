"""Local read-only dashboard: one self-contained HTML file built from state/, reviews/, submissions/ and evaluations/.

The page loads nothing from the network (student grades never leave the machine) and changes nothing:
it only displays what the toolkit and the agents already wrote. Rebuild it after every run:
    python -m grader dashboard            # writes dashboard.html and opens it in the browser

Student names come from projects/students.json, else the frozen submission (`freeze --student`), else projects/roster.json.
Integrity indicators are shown as risk indicators with their evidence, never as a finding of misconduct.
"""
from __future__ import annotations

import json
import os
import webbrowser
from pathlib import Path

from . import ranking, similarity, state
from .common import (DEFAULT_ASSIGNMENT, EVALUATIONS, INTEGRITY_FILE, KB, REVIEWS, ROOT, STATES, SUBMISSIONS,
                     assignment_files, list_assignments, load_json, now_iso, write_text)

DEFAULT_OUT = ROOT / "dashboard.html"
ROSTER_FILE = ROOT / "projects" / "roster.json"
STUDENTS_FILE = ROOT / "projects" / "students.json"  # {"students": {"<project key>": "<name>"}}; display names only
TEXT_MAX = 400


def _load(path: Path):
    try:
        return load_json(path)
    except (OSError, ValueError):
        return None


def _cut(s, n: int = TEXT_MAX):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _dirs(p: Path) -> list[Path]:
    return sorted(d for d in p.iterdir() if d.is_dir()) if p.is_dir() else []


def _links(run: Path, base: Path, names: list[str]) -> dict:
    return {n: Path(os.path.relpath(run / n, base)).as_posix() for n in names if (run / n).exists()}


def _evidence(items, n: int = 4) -> list[dict]:
    return [{"file": e.get("file"), "location": e.get("location"), "quote": _cut(e.get("quote"), 220)}
            for e in (items or [])[:n] if isinstance(e, dict)]


def _integrity(integ: dict) -> dict:
    return {"risk": integ.get("risk_level"), "disclaimer": integ.get("disclaimer"),
            "indicators": [{"id": i.get("indicator_id"), "text": _cut(i.get("description"), 700),
                            "evidence": _evidence(i.get("evidence"))} for i in integ.get("indicators", [])]}


def _check(run: Path) -> dict | None:
    c = _load(run / "expected-check.json")
    if not c:
        return None
    return {"verdict": c.get("verdict"), "agreement": c.get("agreement"), "failures": c.get("failures", []),
            "expected": {r["requirement_id"]: [r["expected"], *r.get("also_acceptable", [])] for r in c.get("rows", [])}}


def _review_run(run: Path, base: Path) -> dict:
    rd = _load(run / "readiness.json") or {}
    return {"id": run.name, "assignment": (_load(run / "run.json") or {}).get("assignment") or DEFAULT_ASSIGNMENT,
            "complete": (run / "review.json").exists(), "verdict": rd.get("verdict"),
            "counts": rd.get("counts"), "risk": rd.get("integrity_risk_level"), "check": _check(run),
            "links": _links(run, base, ["review.md", "readiness.md", "expected-check.md"])}


def _review_detail(run: Path) -> dict:
    rv = _load(run / "review.json") or {}
    statuses = {}
    for a in rv.get("requirements", []):
        if not a.get("requirement_id"):
            continue
        st = {"s": a.get("status"), "finding": _cut(a.get("finding")), "severity": a.get("severity")}
        if a.get("status") == "BLOCKER":
            st["evidence"] = _evidence(a.get("evidence"), 3)
        statuses[a["requirement_id"]] = st
    return {
        "id": run.name,
        "reviewer": (rv.get("meta") or {}).get("reviewer"),
        "reviewed_at": (rv.get("meta") or {}).get("reviewed_at"),
        "statuses": statuses,
        "recommendations": [{"priority": r.get("priority"), "rid": r.get("requirement_id"), "action": _cut(r.get("action"))}
                            for r in sorted(rv.get("recommendations", []), key=lambda r: r.get("priority") or 99)][:8],
        "reproducibility": rv.get("reproducibility"),
        "integrity": _integrity(rv.get("integrity") or {}),
    }


def _evaluation(run: Path, base: Path) -> dict:
    f = _load(run / "final.json")
    if not f:
        return {"id": run.name, "complete": False, "links": _links(run, base, ["report.md", "discrepancies.md"])}
    p1 = _load(run / "final.phase1.json")
    meta = f.get("meta") or {}
    # Toolkit wiring/smoke tests write hand-made evaluations; they are shown as TEST and never count as a grade.
    test = any(w in f"{meta.get('evaluator', '')} {f.get('justification', '')}".lower() for w in ("smoke", "wiring test"))
    return {
        "id": run.name, "complete": True, "test": test, "total": f.get("total"), "total_points": f.get("total_points"),
        "grade": f.get("grade"), "status": f.get("review_status"), "approved_by": f.get("approved_by"),
        "scored_at": f.get("scored_at"), "phase1_total": (p1 or {}).get("total"),
        "evaluator": (f.get("meta") or {}).get("evaluator"),
        "criteria": [{"id": c["id"], "name": c["name"], "points": c["points"], "score": c["score"]} for c in f["criteria"]],
        "statuses": {q["requirement_id"]: {"s": q["status"], "credit": q.get("credit"), "reason": _cut(q.get("deduction_reason")),
                                           "na": _cut(q.get("na_reason")), "override": bool(q.get("override"))}
                     for c in f["criteria"] for q in c["requirements"]},
        "critical": [_cut(x, 700) for x in f.get("critical_issues", [])],
        "strengths": [_cut(x) for x in f.get("strengths", [])],
        "weaknesses": [_cut(x) for x in f.get("weaknesses", [])],
        "integrity": _integrity(f.get("integrity") or {}),
        "warnings": f.get("warnings", []),
        "intact": (f.get("integrity_check") or {}).get("intact"),
        "check": _check(run),
        "links": _links(run, base, ["report.md", "discrepancies.md", "expected-check.md", "final.json"]),
    }


def _roster_names() -> dict[str, str]:
    """project key -> student name from projects/roster.json (repo 'owner/name' -> key 'owner__name')."""
    roster = _load(ROSTER_FILE) or {}
    out = {}
    for s in roster.get("students", []):
        if s.get("student") and s.get("repo"):
            out[str(s["repo"]).strip("/").replace("/", "__").lower()] = s["student"]
        if s.get("student") and s.get("project"):
            out[str(s["project"]).lower()] = s["student"]
    return out


def collect(base: Path = ROOT) -> dict:
    """Everything the page shows. `base` is the folder the HTML is written to (for relative links)."""
    ids = _load(KB / "identities.json") or {}
    policy = _load(INTEGRITY_FILE) or {}
    projects: dict[str, dict] = {}

    def proj(name: str) -> dict:
        return projects.setdefault(name, {"name": name, "student": None, "state": "DRAFT", "updated_at": None,
                                          "history": [], "reviews": [], "review": None, "submissions": [],
                                          "evaluation": None})

    for name, p in state.all_projects().items():
        rec = proj(name)
        rec.update(state=p.get("state", "DRAFT"), updated_at=p.get("updated_at"),
                   history=[{"state": h.get("state"), "at": h.get("at"), "note": h.get("note")} for h in p.get("history", [])])

    for pdir in _dirs(REVIEWS):
        rec = proj(pdir.name)
        runs = _dirs(pdir)
        rec["reviews"] = [_review_run(r, base) for r in reversed(runs)]
        done = [r for r in runs if (r / "review.json").exists()]
        if done:
            rec["review"] = _review_detail(done[-1])

    latest_eval = {}
    for sdir in _dirs(SUBMISSIONS):
        sub = _load(sdir / "submission.json")
        if not sub:
            continue
        rec = proj(sub.get("project") or sdir.name)
        evals = [_evaluation(e, base) for e in reversed(_dirs(EVALUATIONS / sdir.name))]
        rec["submissions"].append({"id": sdir.name, "student": sub.get("student"), "frozen_at": sub.get("frozen_at"),
                                   "assignment": sub.get("assignment") or DEFAULT_ASSIGNMENT,
                                   "file_count": sub.get("file_count"), "team": sub.get("team") or [],
                                   "manifest": str(sub.get("manifest_sha256") or "")[:12], "evaluations": evals})
        for e in evals:
            if e["complete"] and not e.get("test") and (rec["name"] not in latest_eval
                                  or (e.get("scored_at") or "") > (latest_eval[rec["name"]].get("scored_at") or "")):
                latest_eval[rec["name"]] = e
    for name, e in latest_eval.items():
        projects[name]["evaluation"] = e

    roster = _roster_names()
    display = {str(k).lower(): v for k, v in ((_load(STUDENTS_FILE) or {}).get("students") or {}).items() if v}
    for rec in projects.values():
        rec["submissions"].sort(key=lambda s: s.get("frozen_at") or "", reverse=True)
        named = [s["student"] for s in rec["submissions"] if s.get("student")]
        # students.json (edited by the professor) wins over the name typed at freeze time, then the roster
        rec["student"] = display.get(rec["name"].lower()) or (named[0] if named else roster.get(rec["name"].lower()))
        rec["assignment"] = (rec["submissions"][0]["assignment"] if rec["submissions"]
                             else (rec["reviews"][0]["assignment"] if rec["reviews"] else DEFAULT_ASSIGNMENT))

    assignments, rankings, sims = {}, {}, {}
    for aid in list_assignments():
        af = assignment_files(aid)
        rub, rq = load_json(af["rubric"]), load_json(af["requirements"])
        meta = _load(af["meta"]) if af["meta"] else {}
        assignments[aid] = {
            "id": aid, "title": (meta or {}).get("title") or "AI/ML project", "course": (meta or {}).get("course"),
            "status": rub.get("status") if rub.get("status") == "PLACEHOLDER" else rq.get("status"),
            "rubric": {"version": rub.get("version"), "status": rub.get("status"),
                       "bands": rub.get("grade_scale", {}).get("bands", []),
                       "criteria": [{"id": c["id"], "name": c["name"], "points": c["points"]} for c in rub["criteria"]]},
            "requirements": [{"id": r["id"], "criterion": r["criterion_id"], "category": r["category"],
                              "mandatory": r["mandatory"], "points": r["points"], "text": r["requirement"]}
                             for r in rq["requirements"]],
            "requirements_status": rq.get("status")}
        if any(p["assignment"] == aid and p["submissions"] for p in projects.values()):
            rankings[aid] = ranking.compute(aid)
        rep_ = similarity.latest(aid)
        if rep_:
            sims[aid] = {k: rep_[k] for k in ("generated_at", "n", "counts", "students", "disclaimer", "ignored_common_fingerprints")}
            sims[aid]["pairs"] = [p for p in rep_["pairs"] if p["level"] != "NONE"]

    agents = ids.get("agents", {})
    return {
        "generated_at": now_iso(),
        "states": STATES,
        "agents": {"reviewer": (agents.get("ml-reviewer") or {}).get("name", "Agent 1"),
                   "professor": (agents.get("professor") or {}).get("name", "Agent 2")},
        "assignments": assignments, "rankings": rankings, "similarity": sims,
        "integrity_names": {i["id"]: i["name"] for i in policy.get("indicators", []) if i.get("id")},
        "integrity_disclaimer": policy.get("mandatory_disclaimer"),
        "projects": sorted(projects.values(), key=lambda p: ((p["student"] or "~").lower(), p["name"])),
    }


def render(data: dict) -> str:
    # Every "<" becomes < (still valid JSON), so no project text can close the <script> element or open "<!--".
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return TEMPLATE.replace("/*__DATA__*/null", payload)


def build(out: Path = DEFAULT_OUT, open_browser: bool = True) -> Path:
    out = Path(out).resolve()
    write_text(out, render(collect(out.parent)))
    if open_browser:
        webbrowser.open(out.as_uri())
    return out


TEMPLATE = r"""<!doctype html>
<html lang="sq">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grading Dashboard</title>
<style>
:root {
  --bg: #f6f6f3; --surface: #ffffff; --surface-2: #f0f0ec; --text: #1c1c1e; --muted: #66665f;
  --border: #e2e2dc; --accent: #2b59c3; --accent-soft: #e6edfb;
  --pass: #1d6b38; --pass-bg: #e2f2e7; --partial: #7c5300; --partial-bg: #fbefd5;
  --missing: #a13a12; --missing-bg: #fde6da; --blocker: #ffffff; --blocker-bg: #c42b2b;
  --na: #5f5f58; --na-bg: #ebebe6; --bar: #2b59c3; --bar-track: #e8e8e2;
  --shadow: 0 1px 2px rgba(0,0,0,.05), 0 1px 1px rgba(0,0,0,.03);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #141415; --surface: #1c1c1e; --surface-2: #242427; --text: #ececec; --muted: #a0a09a;
    --border: #313134; --accent: #8fb0ff; --accent-soft: #23304d;
    --pass: #7fd69b; --pass-bg: #173322; --partial: #f2c46b; --partial-bg: #3a2c10;
    --missing: #ff9f7a; --missing-bg: #3d2017; --blocker: #ffffff; --blocker-bg: #b02525;
    --na: #b5b5ae; --na-bg: #2c2c2f; --bar: #8fb0ff; --bar-track: #2c2c2f; --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #141415; --surface: #1c1c1e; --surface-2: #242427; --text: #ececec; --muted: #a0a09a;
  --border: #313134; --accent: #8fb0ff; --accent-soft: #23304d;
  --pass: #7fd69b; --pass-bg: #173322; --partial: #f2c46b; --partial-bg: #3a2c10;
  --missing: #ff9f7a; --missing-bg: #3d2017; --blocker: #ffffff; --blocker-bg: #b02525;
  --na: #b5b5ae; --na-bg: #2c2c2f; --bar: #8fb0ff; --bar-track: #2c2c2f; --shadow: none;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code { font-family: ui-monospace, Consolas, monospace; font-size: 12px; background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
.wrap { max-width: 1240px; margin: 0 auto; padding: 24px 16px 64px; }
header.top { display: flex; flex-wrap: wrap; gap: 12px; align-items: baseline; justify-content: space-between; margin-bottom: 20px; }
.top-actions { display: flex; gap: 8px; }
h1 { font-size: 22px; margin: 0; letter-spacing: -.01em; }
h2 { font-size: 16px; margin: 0 0 12px; }
h3 { font-size: 13px; margin: 0 0 8px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.muted { color: var(--muted); }
.small { font-size: 12px; }
.warn { background: var(--partial-bg); color: var(--partial); border-radius: 8px; padding: 8px 12px; margin-bottom: 16px; font-size: 13px; }
.note { background: var(--surface-2); border-radius: 8px; padding: 10px 12px; font-size: 13px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; box-shadow: var(--shadow); }
.card.alert { border-color: var(--blocker-bg); }
.grid { display: grid; gap: 16px; }
.tiles { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin-bottom: 16px; }
.tile .n { font-size: 26px; font-weight: 650; letter-spacing: -.02em; }
.two { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
input[type=search], select { padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); font: inherit; min-width: 0; }
input[type=search] { flex: 1 1 220px; }
select { flex: 0 1 220px; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; flex-wrap: wrap; }
.seg button { border: 0; background: var(--surface); color: var(--text); padding: 7px 11px; font: inherit; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--border); }
.seg button.on { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { font-size: 12px; color: var(--muted); font-weight: 600; white-space: nowrap; }
tr.click { cursor: pointer; }
tr.click:hover td { background: var(--surface-2); }
tr.group td { background: var(--surface-2); font-weight: 600; font-size: 12px; }
tr.disagree td:first-child { box-shadow: inset 3px 0 0 var(--blocker-bg); }
.chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.t-ok { color: var(--pass); background: var(--pass-bg); }
.t-warn { color: var(--partial); background: var(--partial-bg); }
.t-bad { color: var(--missing); background: var(--missing-bg); }
.t-crit { color: var(--blocker); background: var(--blocker-bg); }
.t-na { color: var(--na); background: var(--na-bg); }
.t-info { color: var(--accent); background: var(--accent-soft); }
.grade { display: inline-flex; align-items: baseline; gap: 6px; }
.grade .g { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.big { font-size: 40px; font-weight: 700; letter-spacing: -.03em; line-height: 1; }
.kv { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; margin: 8px 0; }
.bar-row { display: grid; grid-template-columns: minmax(110px, 1.2fr) 3fr 64px; gap: 10px; align-items: center; margin: 5px 0; font-size: 13px; }
.bar { height: 8px; border-radius: 4px; background: var(--bar-track); overflow: hidden; }
.bar > span { display: block; height: 100%; background: var(--bar); border-radius: 4px; }
.num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.steps { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 18px; }
.step { padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border); font-size: 12px; color: var(--muted); }
.step.done { color: var(--text); }
.step.now { background: var(--accent); border-color: var(--accent); color: var(--surface); font-weight: 600; }
ul.plain { margin: 0; padding-left: 18px; }
ul.plain li { margin: 4px 0; }
.detail-text { font-size: 12px; color: var(--muted); margin-top: 3px; max-width: 560px; }
.back { display: inline-block; margin-bottom: 12px; }
.section { margin-top: 16px; }
.empty { padding: 24px; text-align: center; color: var(--muted); }
.btn { border: 1px solid var(--border); background: var(--surface); color: var(--text); border-radius: 8px; padding: 5px 10px; font: inherit; cursor: pointer; }
.issue { border-top: 1px solid var(--border); padding: 12px 0; }
.issue:first-of-type { border-top: 0; padding-top: 4px; }
.issue-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 4px; }
.issue-title { font-weight: 600; }
.ev { margin: 6px 0 0; padding: 0; list-style: none; }
.ev li { font-size: 12px; margin: 3px 0; padding-left: 10px; border-left: 2px solid var(--border); color: var(--muted); }
.ev q { color: var(--text); font-style: italic; }
.student { font-weight: 600; }
.nav { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
.nav a { padding: 8px 14px; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; font-weight: 500; }
.nav a.on { color: var(--accent); border-bottom-color: var(--accent); }
.nav a:hover { text-decoration: none; color: var(--text); }
.cmp { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; margin-top: 8px; }
.code { font-family: ui-monospace, Consolas, monospace; font-size: 12px; background: var(--surface-2); border-radius: 8px;
  padding: 8px 10px; white-space: pre; overflow-x: auto; margin: 4px 0 0; }
.pair { border-top: 1px solid var(--border); padding: 14px 0; }
.pair:first-of-type { border-top: 0; }
@media (max-width: 640px) { .bar-row { grid-template-columns: 1fr 64px; } .bar-row .bar { grid-column: 1 / -1; order: 3; } .big { font-size: 32px; } }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div><h1 id="title"></h1><div class="muted small" id="gen"></div></div>
    <div class="top-actions"><button class="btn" id="lang" type="button"></button><button class="btn" id="theme" type="button"></button></div>
  </header>
  <div id="app"></div>
</div>
<script id="data" type="application/json">/*__DATA__*/null</script>
<script>
(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("data").textContent);
  var app = document.getElementById("app");
  var ui = { q: "", student: "", stateFilter: "ALL", reqFilter: "ALL", assignment: "ALL" };
  function A(aid) { return D.assignments[aid] || D.assignments["ml-project"]; }
  function aids() { return Object.keys(D.assignments); }
  function critOf(aid, id) { return A(aid).rubric.criteria.filter(function (c) { return c.id === id; })[0] || {}; }
  function studentOfProject(name) { var p = D.projects.filter(function (x) { return x.name === name; })[0]; return p ? p.student : null; }

  var L = {
    sq: {
      title: "Paneli i vlerësimit", generated: "Gjeneruar", rubric: "rubrika", rebuild: "rifresko me", theme: "Tema", other: "EN",
      placeholder: "Rubrika dhe kërkesat janë versione PLACEHOLDER: notat këtu nuk janë zyrtare.",
      tProjects: "Projekte", tStudents: "Studentë", tReview: "Në rishikim", tReady: "Gati për vlerësim final", tGraded: "Të vlerësuar",
      tPass: "Kalojnë (nota ≥ 6)", tFail: "Nuk kalojnë (nota 5)", tHigh: "Integritet: shqetësim i lartë",
      search: "Kërko projekt ose student", allStudents: "Të gjithë studentët", all: "Të gjitha",
      hStudent: "Studenti", hProject: "Projekti", hState: "Statusi", hA1: "(Agjenti 1)", hPoints: "Pikët", hGrade: "Nota",
      hIntegrity: "Integriteti", hProblems: "Problemet", hKey: "Çelësi i përgjigjeve",
      noName: "pa emër", noReview: "pa rishikim", notGraded: "pa vlerësim", noMatch: "Asnjë projekt nuk përputhet.",
      blockers: "bllokues", missing: "mungojnë", partial: "pjesërisht", critical: "gabime kritike", indicators: "tregues integriteti",
      copy: "kopjim", fabrication: "fabrikim", none: "asnjë",
      back: "← Të gjithë projektet", notFound: "Projekti nuk u gjet.", submission: "dorëzimi", files: "skedarë", notFrozen: "Ende nuk është dorëzuar (freeze)",
      a1card: "rishikimi i Agjentit 1", a2card: "vlerësimi i Agjentit 2", repro: "Riprodhueshmëria", run: "Ekzekutimi", evaluation: "Vlerësimi",
      noReviewLong: "Nuk ka rishikim të përfunduar. Ekzekuto <code>/review</code>.", notGradedLong: "Ende pa vlerësim. Ekzekuto <code>/freeze</code> dhe pastaj <code>/grade</code>.",
      phase1: "Faza 1", afterCheck: "pas kontrollit të mospërputhjeve", intact: "i paprekur", notVerified: "i paverifikuar", sub: "Dorëzimi",
      approve: "mirato me /override <eval-dir> --approve", scale: "Shkalla e notave",
      problemsTitle: "Përmbledhja e problemeve", errorsTitle: "Gabime kritike", noErrors: "Nuk u gjet asnjë gabim kritik.",
      foundBy: "gjetur nga", integrityTitle: "Tregues të integritetit akademik", noIndicators: "Nuk u gjet asnjë tregues integriteti. Kjo nuk është certifikim i integritetit.",
      disclaimer: "Këta janë tregues rreziku për shqyrtim nga profesori, JO provë se studenti ka kopjuar ose mashtruar. Mund të kenë shpjegim të pafajshëm (p.sh. një referencë e kopjuar gabim). Vendimin e merr vetëm profesori.",
      evidence: "Dëshmia", reqs: "Kërkesat", fAll: "Të gjitha", fProblems: "Vetëm problemet", fDisagree: "Agjenti 1 ≠ Agjenti 2", fOffkey: "Jashtë çelësit",
      reqNote: "BLLOKUES (Agjenti 1) llogaritet si MUNGON (Agjenti 2). Vija e kuqe = mospërputhje mes agjentëve.",
      hId: "ID", hReq: "Kërkesa", hExpected: "E pritur", mandatory: "e detyrueshme", offkey: "jashtë çelësit", notAsserted: "pa pritje",
      nothing: "Asgjë për këtë filtër.", actions: "veprimet kryesore për studentin", weaknesses: "dobësitë", strengths: "Pikat e forta",
      history: "Historiku i ekzekutimeve", hRun: "Ekzekutimi", hType: "Lloji", hResult: "Rezultati", hFiles: "Skedarët",
      review: "Rishikim", frozen: "Dorëzim i ngrirë", incomplete: "i papërfunduar", key: "çelësi", report: "raporti", discrepancies: "mospërputhjet", keycheck: "kontrolli i çelësit",
      grade: "nota", agreement: "përputhja", testRun: "test teknik i sistemit, jo notë",
      tabProjects: "Projektet", tabRanking: "Renditja", tabSimilarity: "Ngjashmëria (kopjimi)", allAssignments: "Të gjitha detyrat",
      hAssignment: "Detyra", hRank: "Vendi", hSimilarity: "Ngjashmëria", hStatus: "Statusi",
      noRanking: "Asnjë dorëzim i vlerësuar për këtë detyrë ende.",
      rankNote: "Renditja sipas pikëve të llogaritura nga sistemi (python -m grader score). Ngjashmëria dhe integriteti janë tregues për profesorin; nuk e ndryshojnë renditjen as pikët.",
      noSimilarity: "Nuk ka raport ngjashmërie për këtë detyrë. Ekzekuto: python -m grader similarity --assignment ",
      simNote: "Ngjashmëria është prioritet shqyrtimi për profesorin, JO provë kopjimi. Algoritmet e shkurtra standarde (p.sh. backtracking si në libër) natyrshëm ngjajnë; pjesët e përbashkëta për shumë studentë dhe kodi bazë i profesorit janë hequr nga krahasimi.",
      submissions: "Dorëzime", pairs: "çifte", reasons: "Arsyet", codeRegions: "Kod i përbashkët", textRegions: "Tekst i përbashkët",
      identicalFiles: "Skedarë identikë", foreignCommits: "Commit-e të shkruara nga studenti tjetër", sharedCommits: "Commit-e identike (histori e përbashkët)",
      timelineTitle: "Historiku i kodit të përbashkët", exactVersion: "Version identik i skedarit", normalizedFragments: "Fragmente kodi me emra të normalizuar", timelineNote: "Datat e commit-eve nuk provojnë autorësinë ose drejtimin e kopjimit. Kontrollo burimet e përbashkëta dhe bashkëpunimin. Pa objektet Git ose me përputhje vetëm të pjesshme, rendi mund të mbetet i panjohur.",
      earlierA: "A ka versionin e regjistruar më herët", earlierB: "B ka versionin e regjistruar më herët", sameTime: "E njëjta kohë e regjistruar", unknownOrder: "Rendi i panjohur", limitedHistory: "Historik i kufizuar ose i padisponueshëm",
      sharedMessages: "Mesazhe identike commit-esh", firstSeen: "prekja e parë e shtegut (jo ky version)", similarTo: "Ngjashmëri me studentë të tjerë",
      noPairs: "Asnjë çift me ngjashmëri mbi pragun.", codeShort: "kodi", textShort: "teksti", openSim: "shih krahasimin",
      generatedSim: "Raporti", ignoredCommon: "fragmente të përbashkëta të hequra"
    },
    en: {
      title: "Grading Dashboard", generated: "Generated", rubric: "rubric", rebuild: "rebuild with", theme: "Theme", other: "SQ",
      placeholder: "The rubric/requirements are PLACEHOLDER versions: grades shown here are not official.",
      tProjects: "Projects", tStudents: "Students", tReview: "Under review", tReady: "Ready for final review", tGraded: "Graded",
      tPass: "Passing (grade ≥ 6)", tFail: "Failing (grade 5)", tHigh: "Integrity: high concern",
      search: "Search projects or students", allStudents: "All students", all: "All",
      hStudent: "Student", hProject: "Project", hState: "State", hA1: "(Agent 1)", hPoints: "Points", hGrade: "Grade",
      hIntegrity: "Integrity", hProblems: "Problems", hKey: "Answer key",
      noName: "no name", noReview: "no review", notGraded: "not graded", noMatch: "No projects match.",
      blockers: "blockers", missing: "missing", partial: "partial", critical: "critical errors", indicators: "integrity indicators",
      copy: "copying", fabrication: "fabrication", none: "none",
      back: "← All projects", notFound: "Project not found.", submission: "submission", files: "files", notFrozen: "Not frozen yet",
      a1card: "Agent 1 review", a2card: "Agent 2 evaluation", repro: "Reproducibility", run: "Run", evaluation: "Evaluation",
      noReviewLong: "No completed review. Run <code>/review</code>.", notGradedLong: "Not graded yet. Run <code>/freeze</code> then <code>/grade</code>.",
      phase1: "Phase 1", afterCheck: "after the discrepancy check", intact: "intact", notVerified: "not verified", sub: "Submission",
      approve: "approve with /override <eval-dir> --approve", scale: "Grade scale",
      problemsTitle: "Problem summary", errorsTitle: "Critical errors", noErrors: "No critical errors found.",
      foundBy: "found by", integrityTitle: "Academic integrity indicators", noIndicators: "No integrity indicators found. This is not a certification of integrity.",
      disclaimer: "These are risk indicators for the professor to review, NOT proof that the student copied or cheated. They may have an innocent explanation (e.g. a mis-copied reference). Only the professor decides.",
      evidence: "Evidence", reqs: "Requirements", fAll: "All", fProblems: "Problems only", fDisagree: "Agent 1 ≠ Agent 2", fOffkey: "Off answer key",
      reqNote: "BLOCKER (Agent 1) counts as MISSING (Agent 2). A red edge marks a disagreement between the agents.",
      hId: "ID", hReq: "Requirement", hExpected: "Expected", mandatory: "mandatory", offkey: "off key", notAsserted: "not asserted",
      nothing: "Nothing to show for this filter.", actions: "top actions for the student", weaknesses: "weaknesses", strengths: "Strengths",
      history: "Run history", hRun: "Run", hType: "Type", hResult: "Result", hFiles: "Files",
      review: "Review", frozen: "Frozen submission", incomplete: "incomplete", key: "key", report: "report", discrepancies: "discrepancies", keycheck: "key check",
      grade: "grade", agreement: "agreement", testRun: "toolkit test, not a grade",
      tabProjects: "Projects", tabRanking: "Ranking", tabSimilarity: "Similarity (copying)", allAssignments: "All assignments",
      hAssignment: "Assignment", hRank: "Rank", hSimilarity: "Similarity", hStatus: "Status",
      noRanking: "No graded submissions for this assignment yet.",
      rankNote: "Ranked by the totals computed by the toolkit (python -m grader score). Similarity and integrity are indicators for the professor; they do not change the order or any score.",
      noSimilarity: "No similarity report for this assignment. Run: python -m grader similarity --assignment ",
      simNote: "Similarity is a review priority for the professor, NOT proof of copying. Short standard algorithms (textbook backtracking) are naturally similar; fragments common to many students and the professor's base code are excluded.",
      submissions: "Submissions", pairs: "pairs", reasons: "Reasons", codeRegions: "Shared code", textRegions: "Shared text",
      identicalFiles: "Identical files", foreignCommits: "Commits authored by the other student", sharedCommits: "Identical commits (shared history)",
      timelineTitle: "Matching-version commit timeline", exactVersion: "Identical file version", normalizedFragments: "Code fragments with normalized names", timelineNote: "Commit dates do not prove authorship or copying direction. Check shared sources and collaboration. Missing Git objects or partial matches may leave order unknown.",
      earlierA: "A has the earlier recorded version", earlierB: "B has the earlier recorded version", sameTime: "Same recorded time", unknownOrder: "Unknown order", limitedHistory: "Limited or unavailable history",
      sharedMessages: "Identical commit messages", firstSeen: "first path touch (not this version)", similarTo: "Similarity with other students",
      noPairs: "No pair above the threshold.", codeShort: "code", textShort: "text", openSim: "see comparison",
      generatedSim: "Report", ignoredCommon: "common fragments removed"
    }
  };
  var LABELS = {
    sq: {
      PASS: "Plotësuar", PARTIAL: "Pjesërisht", MISSING: "Mungon", BLOCKER: "Bllokues", NOT_APPLICABLE: "Nuk aplikohet",
      DRAFT: "Draft", UNDER_REVIEW: "Në rishikim", READY_FOR_FINAL_REVIEW: "Gati për vlerësim", FINAL_SUBMISSION: "Dorëzuar", GRADED: "Vlerësuar",
      NOT_READY: "Jo gati", NONE_FOUND: "Asnjë tregues", NEEDS_REVIEW: "Kërkon shqyrtim", HIGH_CONCERN: "Shqetësim i lartë",
      PROVISIONAL: "Provizore", APPROVED: "Miratuar", REEVALUATION_REQUESTED: "Rivlerësim i kërkuar", FAIL: "FAIL",
      HIGH: "E lartë", MEDIUM: "Mesatare", LOW: "E ulët", NONE: "Asnjë"
    },
    en: {}
  };
  var GRADE_NAMES = {
    sq: { 10: "Shkëlqyeshëm", 9: "Shumë mirë", 8: "Mirë", 7: "Mjaft mirë", 6: "Kalueshëm", 5: "Dobët – nuk kalon" },
    en: { 10: "Excellent", 9: "Very good", 8: "Good", 7: "Satisfactory", 6: "Sufficient", 5: "Fail" }
  };
  var INT_SQ = {
    "INT-001": "Citimi nuk ekziston", "INT-002": "Citimi nuk e mbështet pohimin", "INT-003": "Pasazhe të kopjuara / formulim identik",
    "INT-004": "Kod i kopjuar pa atribuim", "INT-005": "Raporti përshkruan kod që nuk ekziston", "INT-006": "Rezultatet nuk riprodhohen / bien ndesh me output-in",
    "INT-007": "Figurat nuk përputhen me të dhënat", "INT-008": "Metrika të pabesueshme", "INT-009": "Referenca të fabrikuara",
    "INT-010": "Përshkrimi i dataset-it nuk përputhet me dataset-in", "INT-011": "Arkitektura ndryshon mes kodit dhe raportit"
  };
  // Grouping only for display; the indicator ids and evidence come from the agents' output.
  var INT_KIND = { "INT-003": "copy", "INT-004": "copy",
    "INT-001": "fabrication", "INT-002": "fabrication", "INT-005": "fabrication", "INT-006": "fabrication", "INT-007": "fabrication",
    "INT-009": "fabrication", "INT-010": "fabrication", "INT-011": "fabrication" };
  var TONE = { PASS: "ok", READY_FOR_FINAL_REVIEW: "ok", NONE_FOUND: "ok", APPROVED: "ok", GRADED: "ok",
    PARTIAL: "warn", NOT_READY: "warn", NEEDS_REVIEW: "warn", PROVISIONAL: "warn", UNDER_REVIEW: "warn", REEVALUATION_REQUESTED: "warn",
    MISSING: "bad", BLOCKER: "crit", FAIL: "crit", HIGH_CONCERN: "crit", FINAL_SUBMISSION: "info",
    HIGH: "crit", MEDIUM: "bad", LOW: "warn", NONE: "ok" };

  var lang = "sq";
  try { lang = localStorage.getItem("dash-lang") || "sq"; } catch (e) {}
  function T(k) { return (L[lang] && L[lang][k]) || L.en[k] || k; }
  function lbl(s) { return (LABELS[lang] && LABELS[lang][s]) || String(s).replace(/_/g, " "); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function chip(s, label, tone) {
    if (!s && !label) return '<span class="chip t-na">—</span>';
    return '<span class="chip t-' + (tone || TONE[s] || "na") + '" title="' + esc(s || "") + '">' + esc(label || lbl(s)) + "</span>"; }
  function norm(s) { return s === "BLOCKER" ? "MISSING" : s; }
  function link(href, label) { return href ? '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(label) + "</a>" : ""; }
  function intName(id) { return (lang === "sq" && INT_SQ[id]) || D.integrity_names[id] || id; }
  function gradeHtml(g, big) {
    if (g == null) return '<span class="muted">—</span>';
    var name = (GRADE_NAMES[lang] || GRADE_NAMES.en)[g] || "";
    return '<span class="grade"><span class="g"' + (big ? ' style="font-size:28px"' : "") + ">" + esc(g) + "</span>" +
      chip(null, name, g >= 6 ? (g >= 8 ? "ok" : "warn") : "crit") + "</span>";
  }

  try { var t = localStorage.getItem("dash-theme"); if (t) document.documentElement.setAttribute("data-theme", t); } catch (e) {}
  document.getElementById("theme").onclick = function () {
    var cur = document.documentElement.getAttribute("data-theme");
    var dark = cur ? cur === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    var next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("dash-theme", next); } catch (e) {}
  };
  document.getElementById("lang").onclick = function () {
    lang = lang === "sq" ? "en" : "sq";
    try { localStorage.setItem("dash-lang", lang); } catch (e) {}
    route();
  };

  function chrome() {
    document.documentElement.setAttribute("lang", lang);
    document.title = T("title");
    document.getElementById("title").textContent = T("title");
    document.getElementById("lang").textContent = T("other");
    document.getElementById("theme").textContent = T("theme");
    document.getElementById("gen").textContent = T("generated") + " " + String(D.generated_at).replace("T", " ").slice(0, 16) +
      (D.live ? " UTC · Live" : " UTC · " + T("rebuild") + ": python -m grader dashboard");
  }
  function warnings(aid) {
    var list = aid ? [aid] : aids();
    var ph = list.some(function (x) { var a = A(x); return a.rubric.status === "PLACEHOLDER" || a.requirements_status === "PLACEHOLDER"; });
    return ph ? '<div class="warn">' + esc(T("placeholder")) + "</div>" : "";
  }
  function nav(active) {
    return '<div class="nav">' + [["#/", T("tabProjects"), "list"], ["#/ranking", T("tabRanking"), "ranking"], ["#/similarity", T("tabSimilarity"), "similarity"]]
      .map(function (t) { return '<a href="' + t[0] + '" class="' + (active === t[2] ? "on" : "") + '">' + esc(t[1]) + "</a>"; }).join("") + "</div>";
  }
  function assignSelect(allowAll) {
    var opts = (allowAll ? [["ALL", T("allAssignments")]] : []).concat(aids().map(function (a) { return [a, A(a).title + " (" + a + ")"]; }));
    return '<select id="as">' + opts.map(function (o) { return '<option value="' + esc(o[0]) + '"' + (ui.assignment === o[0] ? " selected" : "") + ">" + esc(o[1]) + "</option>"; }).join("") + "</select>";
  }
  function bindAssign() { var el = document.getElementById("as"); if (el) el.onchange = function () { ui.assignment = this.value; route(); }; }
  function currentAid() {
    if (ui.assignment !== "ALL" && D.assignments[ui.assignment]) return ui.assignment;
    var withData = aids().filter(function (a) { return D.rankings[a] || D.similarity[a]; });
    return withData.length ? withData[withData.length - 1] : aids()[0];
  }
  function simPairs(p) {
    var S = D.similarity[p.assignment]; if (!S) return [];
    var mine = p.submissions.map(function (s) { return s.id; });
    return S.pairs.filter(function (x) { return mine.indexOf(x.a) >= 0 || mine.indexOf(x.b) >= 0; }).map(function (x) {
      var other = mine.indexOf(x.a) >= 0 ? x.b : x.a;
      return { level: x.level, other: other, project: (S.students[other] || {}).project, pair: x }; });
  }
  function simLabel(S, sid) { var s = S.students[sid] || {}; return studentOfProject(s.project) || s.student || sid; }
  function a1(p) { return p.reviews.filter(function (r) { return r.complete; })[0] || null; }

  // Indicators of both agents merged by id: [{id, by: {reviewer: ind, professor: ind}}]
  function indicators(p) {
    var out = {}, order = [];
    function add(src, who) {
      (src && src.integrity ? src.integrity.indicators : []).forEach(function (i) {
        if (!out[i.id]) { out[i.id] = { id: i.id, by: {} }; order.push(i.id); }
        out[i.id].by[who] = i;
      });
    }
    add(p.evaluation, "professor"); add(p.review, "reviewer");
    return order.map(function (id) { return out[id]; });
  }
  function blockers(p) {
    if (!p.review) return [];
    return Object.keys(p.review.statuses).filter(function (k) { return p.review.statuses[k].s === "BLOCKER"; })
      .map(function (k) { return { rid: k, st: p.review.statuses[k] }; });
  }
  function criticalCount(p) { return Math.max(p.evaluation ? p.evaluation.critical.length : 0, blockers(p).length); }
  function riskOf(p) { var e = p.evaluation, r = a1(p); return (e && e.integrity.risk) || (r && r.risk) || null; }

  function tile(n, label) { return '<div class="card tile"><div class="n">' + esc(n) + '</div><div class="muted small">' + esc(label) + "</div></div>"; }

  function listView() {
    var P = D.projects;
    var count = function (f) { return P.filter(f).length; };
    var students = []; P.forEach(function (p) { if (p.student && students.indexOf(p.student) < 0) students.push(p.student); });
    students.sort(function (a, b) { return a.localeCompare(b); });
    P = P.filter(function (p) { return ui.assignment === "ALL" || p.assignment === ui.assignment; });
    var h = nav("list") + warnings(ui.assignment === "ALL" ? null : ui.assignment);
    h += '<div class="grid tiles">' +
      tile(students.length, T("tStudents")) + tile(P.length, T("tProjects")) +
      tile(count(function (p) { return p.state === "UNDER_REVIEW"; }), T("tReview")) +
      tile(count(function (p) { return p.state === "GRADED"; }), T("tGraded")) +
      tile(count(function (p) { return p.evaluation && p.evaluation.grade >= 6; }), T("tPass")) +
      tile(count(function (p) { return p.evaluation && p.evaluation.grade < 6; }), T("tFail")) +
      tile(count(function (p) { return riskOf(p) === "HIGH_CONCERN"; }), T("tHigh")) + "</div>";
    h += '<div class="card"><div class="toolbar"><input type="search" id="q" placeholder="' + esc(T("search")) + '" value="' + esc(ui.q) + '">' + assignSelect(true) +
      '<select id="st"><option value="">' + esc(T("allStudents")) + "</option>" + students.map(function (s) {
        return '<option value="' + esc(s) + '"' + (ui.student === s ? " selected" : "") + ">" + esc(s) + "</option>"; }).join("") + "</select>" +
      '<div class="seg" id="sf">' + ["ALL"].concat(D.states).map(function (s) {
        return '<button type="button" data-v="' + s + '" class="' + (ui.stateFilter === s ? "on" : "") + '">' + esc(s === "ALL" ? T("all") : lbl(s)) + "</button>"; }).join("") +
      "</div></div>";
    var rows = P.filter(function (p) {
      return (ui.stateFilter === "ALL" || p.state === ui.stateFilter) && (!ui.student || p.student === ui.student) &&
        (!ui.q || (p.name + " " + (p.student || "")).toLowerCase().indexOf(ui.q.toLowerCase()) >= 0);
    });
    if (!rows.length) h += '<div class="empty">' + esc(T("noMatch")) + "</div>";
    else {
      h += '<div class="tbl-wrap"><table><thead><tr><th>' + esc(T("hStudent")) + "</th><th>" + esc(T("hProject")) + "</th><th>" + esc(T("hAssignment")) + "</th><th>" + esc(T("hState")) +
        "</th><th>" + esc(D.agents.reviewer + " " + T("hA1")) + "</th><th>" + esc(T("hPoints")) + "</th><th>" + esc(T("hGrade")) +
        "</th><th>" + esc(T("hIntegrity")) + "</th><th>" + esc(T("hProblems")) + "</th><th>" + esc(T("hKey")) + "</th></tr></thead><tbody>";
      rows.forEach(function (p) {
        var r = a1(p), e = p.evaluation, c = r && r.counts;
        var ind = indicators(p);
        var kinds = { copy: 0, fabrication: 0 };
        ind.forEach(function (i) { var k = INT_KIND[i.id]; if (k) kinds[k]++; });
        var crit = criticalCount(p);
        var probs = [];
        if (crit) probs.push(chip(null, crit + " " + T("critical"), "crit"));
        if (ind.length) probs.push(chip(null, ind.length + " " + T("indicators"), kinds.copy || kinds.fabrication ? "bad" : "warn") +
          '<div class="detail-text">' + esc(T("copy")) + ": " + kinds.copy + " · " + esc(T("fabrication")) + ": " + kinds.fabrication + "</div>");
        var sp = simPairs(p).filter(function (x) { return x.level === "HIGH" || x.level === "MEDIUM"; });
        if (sp.length) probs.push(chip(sp[0].level, T("hSimilarity") + ": " + lbl(sp[0].level)) +
          '<div class="detail-text">' + sp.map(function (x) { return esc(studentOfProject(x.project) || x.other); }).join(", ") + "</div>");
        var checks = [];
        if (r && r.check) checks.push("A1 " + chip(r.check.verdict));
        if (e && e.check) checks.push("A2 " + chip(e.check.verdict));
        h += '<tr class="click" data-p="' + esc(p.name) + '"><td>' + (p.student ? '<span class="student">' + esc(p.student) + "</span>" : '<span class="muted">' + esc(T("noName")) + "</span>") +
          "</td><td>" + esc(p.name) + "</td><td>" + chip(null, p.assignment, "info") + "</td><td>" + chip(p.state) + "</td><td>" +
          (r ? chip(r.verdict) + (c ? '<div class="detail-text">' + c.blockers + " " + esc(T("blockers")) + " · " + c.missing + " " + esc(T("missing")) + " · " + c.partial + " " + esc(T("partial")) + "</div>" : "") : '<span class="muted">' + esc(T("noReview")) + "</span>") +
          "</td><td>" + (e ? '<b class="num">' + esc(e.total) + "</b>/" + esc(e.total_points) + '<div class="detail-text">' + chip(e.status) + "</div>" : '<span class="muted">' + esc(T("notGraded")) + "</span>") +
          "</td><td>" + (e ? gradeHtml(e.grade) : '<span class="muted">—</span>') +
          "</td><td>" + chip(riskOf(p)) + "</td><td>" + (probs.join(" ") || '<span class="muted">' + esc(T("none")) + "</span>") +
          "</td><td>" + (checks.join(" ") || '<span class="muted">—</span>') + "</td></tr>";
      });
      h += "</tbody></table></div>";
    }
    h += "</div>";
    app.innerHTML = h;
    var q = document.getElementById("q");
    q.oninput = function () { ui.q = q.value; listView(); var n = document.getElementById("q"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); };
    document.getElementById("st").onchange = function () { ui.student = this.value; listView(); };
    bindAssign();
    document.querySelectorAll("#sf button").forEach(function (b) { b.onclick = function () { ui.stateFilter = b.getAttribute("data-v"); listView(); }; });
    document.querySelectorAll("tr.click").forEach(function (tr) { tr.onclick = function () { location.hash = "#/p/" + encodeURIComponent(tr.getAttribute("data-p")); }; });
  }

  function evList(ev) {
    if (!ev || !ev.length) return "";
    return '<ul class="ev">' + ev.map(function (x) {
      return "<li><code>" + esc(x.file) + "</code> " + esc(x.location || "") + (x.quote ? " · <q>" + esc(x.quote) + "</q>" : "") + "</li>"; }).join("") + "</ul>";
  }

  function problemsCard(p) {
    var e = p.evaluation, bl = blockers(p), ind = indicators(p);
    var h = '<div class="card section' + (bl.length || (e && e.critical.length) || ind.length ? " alert" : "") + '"><h2>' + esc(T("problemsTitle")) + "</h2>";
    // Critical errors
    h += "<h3>" + esc(T("errorsTitle")) + "</h3>";
    if (!bl.length && !(e && e.critical.length)) h += '<div class="muted small">' + esc(T("noErrors")) + "</div>";
    if (e) e.critical.forEach(function (x) {
      h += '<div class="issue"><div class="issue-head">' + chip(null, D.agents.professor, "info") + "</div><div>" + esc(x) + "</div></div>"; });
    bl.forEach(function (b) {
      var req = A(p.assignment).requirements.filter(function (r) { return r.id === b.rid; })[0] || {};
      h += '<div class="issue"><div class="issue-head">' + chip("BLOCKER") + '<span class="issue-title">' + esc(b.rid) + "</span>" + chip(null, D.agents.reviewer, "info") +
        '<span class="small muted">' + esc(req.text || "") + "</span></div><div>" + esc(b.st.finding) + "</div>" + evList(b.st.evidence) + "</div>";
    });
    // Integrity indicators
    h += '<h3 style="margin-top:18px">' + esc(T("integrityTitle")) + " " + chip(riskOf(p)) + "</h3>";
    h += '<div class="note" style="margin-bottom:8px">' + esc(T("disclaimer")) + "</div>";
    if (!ind.length) h += '<div class="muted small">' + esc(T("noIndicators")) + "</div>";
    ind.forEach(function (i) {
      var kind = INT_KIND[i.id];
      var who = Object.keys(i.by).map(function (k) { return chip(null, D.agents[k], "info"); }).join(" ");
      var main = i.by.professor || i.by.reviewer;
      h += '<div class="issue"><div class="issue-head"><span class="issue-title">' + esc(i.id) + " · " + esc(intName(i.id)) + "</span>" +
        (kind ? chip(null, T(kind), kind === "copy" ? "crit" : "bad") : "") + '<span class="small muted">' + esc(T("foundBy")) + "</span> " + who + "</div>" +
        "<div>" + esc(main.text) + "</div>" + evList(main.evidence) + "</div>";
    });
    return h + "</div>";
  }

  function projectView(name) {
    var p = D.projects.filter(function (x) { return x.name === name; })[0];
    if (!p) { app.innerHTML = '<a class="back" href="#/">' + esc(T("back")) + '</a><div class="empty">' + esc(T("notFound")) + "</div>"; return; }
    var r = p.review, rr = a1(p), e = p.evaluation, sub = p.submissions[0];
    var h = nav("list") + '<a class="back" href="#/">' + esc(T("back")) + "</a>" + warnings(p.assignment);
    h += '<h2 style="font-size:22px;margin-bottom:2px">' + (p.student ? esc(p.student) : '<span class="muted">' + esc(T("noName")) + "</span>") + "</h2>";
    h += '<div style="font-size:15px;margin-bottom:2px">' + esc(p.name) + " " + chip(null, A(p.assignment).title, "info") + "</div>";
    h += '<div class="muted small">' + (sub ? esc(T("submission")) + " " + esc(sub.id) + " · " + esc(sub.file_count) + " " + esc(T("files")) + " · manifest " + esc(sub.manifest) : esc(T("notFrozen"))) + "</div>";
    var idx = D.states.indexOf(p.state);
    h += '<div class="steps">' + D.states.map(function (s, i) {
      return '<span class="step ' + (i === idx ? "now" : i < idx ? "done" : "") + '">' + esc(lbl(s)) + "</span>"; }).join("") + "</div>";

    h += '<div class="grid two">';
    h += '<div class="card"><h3>' + esc(D.agents.reviewer) + " · " + esc(T("a1card")) + "</h3>";
    if (rr) {
      var c = rr.counts || {};
      h += '<div class="kv">' + chip(rr.verdict) + '<span class="small muted">' + esc(c.blockers) + " " + esc(T("blockers")) + " · " + esc(c.missing) + " " + esc(T("missing")) + " · " + esc(c.partial) + " " + esc(T("partial")) + "</span></div>";
      if (r && r.reproducibility) h += '<div class="kv small"><span class="muted">' + esc(T("repro")) + "</span><b>" + esc(r.reproducibility.score) + "/" + esc(r.reproducibility.max || 10) + "</b></div>";
      h += '<div class="kv small"><span class="muted">' + esc(T("hIntegrity")) + "</span>" + chip(rr.risk) + "</div>";
      if (rr.check) h += '<div class="kv small"><span class="muted">' + esc(T("hKey")) + "</span>" + chip(rr.check.verdict) + '<span class="muted">' + esc(T("agreement")) + " " + esc(rr.check.agreement) + "</span></div>";
      h += '<div class="kv small">' + [link(rr.links["review.md"], "review.md"), link(rr.links["readiness.md"], "readiness.md"), link(rr.links["expected-check.md"], "expected-check.md")].join(" ") + "</div>";
      h += '<div class="muted small">' + esc(T("run")) + " " + esc(rr.id) + "</div>";
    } else h += '<div class="muted">' + T("noReviewLong") + "</div>";
    h += "</div>";
    h += '<div class="card"><h3>' + esc(D.agents.professor) + " · " + esc(T("a2card")) + "</h3>";
    if (e) {
      h += '<div class="kv"><span class="big num">' + esc(e.total) + '</span><span class="muted">/ ' + esc(e.total_points) + "</span>" +
        '<span style="margin-left:10px" class="muted">' + esc(T("hGrade")) + "</span>" + gradeHtml(e.grade, true) + chip(e.status) + "</div>";
      if (e.phase1_total != null && e.phase1_total !== e.total) h += '<div class="small muted">' + esc(T("phase1")) + " " + esc(e.phase1_total) + " → " + esc(e.total) + " " + esc(T("afterCheck")) + "</div>";
      e.criteria.forEach(function (cr) {
        var pct = cr.points ? Math.max(0, Math.min(100, cr.score / cr.points * 100)) : 0;
        h += '<div class="bar-row"><span title="' + esc(cr.id) + '">' + esc(cr.name) + '</span><div class="bar"><span style="width:' + pct.toFixed(1) + '%"></span></div><span class="num">' + esc(cr.score) + "/" + esc(cr.points) + "</span></div>";
      });
      h += '<div class="kv small"><span class="muted">' + esc(T("hIntegrity")) + "</span>" + chip(e.integrity.risk) + '<span class="muted">' + esc(T("sub")) + "</span>" +
        chip(null, e.intact ? T("intact") : T("notVerified"), e.intact ? "ok" : "crit") + "</div>";
      if (e.check) h += '<div class="kv small"><span class="muted">' + esc(T("hKey")) + "</span>" + chip(e.check.verdict) + '<span class="muted">' + esc(T("agreement")) + " " + esc(e.check.agreement) + "</span></div>";
      h += '<div class="kv small">' + [link(e.links["report.md"], "report.md"), link(e.links["discrepancies.md"], "discrepancies.md"), link(e.links["expected-check.md"], "expected-check.md")].join(" ") + "</div>";
      h += '<div class="muted small">' + esc(T("evaluation")) + " " + esc(e.id) + (e.status === "PROVISIONAL" ? " · " + esc(T("approve")) : "") + "</div>";
      h += '<div class="muted small" style="margin-top:6px">' + esc(T("scale")) + ": " + A(p.assignment).rubric.bands.map(function (b) {
        return esc(b.grade) + " (≥" + esc(b.min) + ")"; }).join(" · ") + "</div>";
    } else h += '<div class="muted">' + T("notGradedLong") + "</div>";
    h += "</div></div>";

    h += problemsCard(p);
    var sps = simPairs(p);
    if (D.similarity[p.assignment]) {
      h += '<div class="card section' + (sps.some(function (x) { return x.level === "HIGH"; }) ? " alert" : "") + '"><h2>' + esc(T("similarTo")) + "</h2>";
      h += '<div class="note" style="margin-bottom:8px">' + esc(T("simNote")) + "</div>";
      if (!sps.length) h += '<div class="muted small">' + esc(T("noPairs")) + "</div>";
      sps.forEach(function (x) {
        h += '<div class="issue"><div class="issue-head">' + chip(x.level, lbl(x.level)) + '<span class="issue-title">' + esc(studentOfProject(x.project) || x.other) + "</span>" +
          '<span class="small muted">' + esc(T("codeShort")) + " " + Math.round(x.pair.code.containment * 100) + "% · " + esc(T("textShort")) + " " + Math.round(x.pair.docs.containment * 100) + "%</span> " +
          '<a href="#/similarity">' + esc(T("openSim")) + "</a></div><div class=\"small\">" + esc(x.pair.reasons.join("; ")) + "</div></div>";
      });
      h += "</div>";
    }

    var check = (e && e.check) || (rr && rr.check);
    var expected = check ? check.expected : null;
    h += '<div class="card section"><h2>' + esc(T("reqs")) + '</h2><div class="toolbar"><div class="seg" id="rf">' +
      [["ALL", T("fAll")], ["PROBLEMS", T("fProblems")], ["DISAGREE", T("fDisagree")]].concat(expected ? [["OFFKEY", T("fOffkey")]] : []).map(function (o) {
        return '<button type="button" data-v="' + o[0] + '" class="' + (ui.reqFilter === o[0] ? "on" : "") + '">' + esc(o[1]) + "</button>"; }).join("") +
      '</div><span class="small muted">' + esc(T("reqNote")) + "</span></div>";
    h += '<div class="tbl-wrap"><table><thead><tr><th>' + esc(T("hId")) + "</th><th>" + esc(T("hReq")) + "</th><th>" + esc(D.agents.reviewer) + "</th><th>" + esc(D.agents.professor) + "</th>" + (expected ? "<th>" + esc(T("hExpected")) + "</th>" : "") + "</tr></thead><tbody>";
    var lastCrit = null, shown = 0;
    A(p.assignment).requirements.forEach(function (q) {
      var s1 = r && r.statuses[q.id], s2 = e && e.statuses[q.id];
      var disagree = s1 && s2 && norm(s1.s) !== norm(s2.s);
      var exp = expected && expected[q.id];
      var offkey = exp && ((s2 && exp.map(norm).indexOf(norm(s2.s)) < 0) || (!s2 && s1 && exp.indexOf(s1.s) < 0));
      var problem = [s1 && s1.s, s2 && s2.s].some(function (s) { return s === "PARTIAL" || s === "MISSING" || s === "BLOCKER"; });
      if (ui.reqFilter === "PROBLEMS" && !problem) return;
      if (ui.reqFilter === "DISAGREE" && !disagree) return;
      if (ui.reqFilter === "OFFKEY" && !offkey) return;
      if (q.criterion !== lastCrit) {
        lastCrit = q.criterion;
        var cs = e && e.criteria.filter(function (c) { return c.id === q.criterion; })[0];
        h += '<tr class="group"><td colspan="' + (expected ? 5 : 4) + '">' + esc(q.criterion) + " · " + esc(critOf(p.assignment, q.criterion).name) + (cs ? ' <span class="muted">· ' + esc(cs.score) + "/" + esc(cs.points) + "</span>" : "") + "</td></tr>";
      }
      shown++;
      h += '<tr class="' + (disagree ? "disagree" : "") + '"><td><b>' + esc(q.id) + "</b>" + (q.mandatory ? '<div class="detail-text">' + esc(T("mandatory")) + "</div>" : "") + "</td>" +
        "<td>" + esc(q.text) + "</td>" +
        "<td>" + (s1 ? chip(s1.s) + (s1.finding ? '<div class="detail-text">' + esc(s1.finding) + "</div>" : "") : '<span class="muted">—</span>') + "</td>" +
        "<td>" + (s2 ? chip(s2.s, lbl(s2.s) + (s2.s === "PARTIAL" && s2.credit != null ? " " + s2.credit : "")) + (s2.override ? " " + chip(null, "override", "info") : "") +
          ((s2.reason || s2.na) ? '<div class="detail-text">' + esc(s2.reason || s2.na) + "</div>" : "") : '<span class="muted">—</span>') + "</td>" +
        (expected ? "<td>" + (exp ? exp.map(function (x) { return chip(x); }).join(" ") + (offkey ? '<div class="detail-text" style="color:var(--missing)">' + esc(T("offkey")) + "</div>" : "") : '<span class="muted small">' + esc(T("notAsserted")) + "</span>") + "</td>" : "") +
        "</tr>";
    });
    if (!shown) h += '<tr><td colspan="5" class="empty">' + esc(T("nothing")) + "</td></tr>";
    h += "</tbody></table></div></div>";

    h += '<div class="grid two section">';
    h += '<div class="card"><h3>' + esc(D.agents.reviewer) + " · " + esc(T("actions")) + "</h3>" +
      (r && r.recommendations.length ? '<ul class="plain">' + r.recommendations.map(function (x) {
        return "<li>" + (x.rid ? "<b>" + esc(x.rid) + "</b> " : "") + esc(x.action) + "</li>"; }).join("") + "</ul>" : '<div class="muted">—</div>') + "</div>";
    h += '<div class="card"><h3>' + esc(D.agents.professor) + " · " + esc(T("weaknesses")) + "</h3>";
    if (e) {
      h += e.weaknesses.length ? '<ul class="plain">' + e.weaknesses.slice(0, 6).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : '<div class="muted">—</div>';
      if (e.strengths.length) h += '<h3 style="margin-top:12px">' + esc(T("strengths")) + '</h3><ul class="plain">' + e.strengths.slice(0, 6).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
    } else h += '<div class="muted">—</div>';
    h += "</div></div>";
    if (e && e.warnings.length) h += '<div class="warn section">' + e.warnings.map(esc).join("<br>") + "</div>";

    h += '<div class="card section"><h2>' + esc(T("history")) + '</h2><div class="tbl-wrap"><table><thead><tr><th>' + esc(T("hRun")) + "</th><th>" + esc(T("hType")) + "</th><th>" + esc(T("hResult")) + "</th><th>" + esc(T("hFiles")) + "</th></tr></thead><tbody>";
    p.reviews.forEach(function (x) {
      h += "<tr><td>" + esc(x.id) + "</td><td>" + esc(T("review")) + " (" + esc(D.agents.reviewer) + ")</td><td>" + (x.complete ? chip(x.verdict) : '<span class="muted">' + esc(T("incomplete")) + "</span>") +
        (x.check ? " " + esc(T("key")) + " " + chip(x.check.verdict) : "") + "</td><td>" + [link(x.links["review.md"], T("review")), link(x.links["readiness.md"], "readiness"), link(x.links["expected-check.md"], T("keycheck"))].filter(Boolean).join(" · ") + "</td></tr>";
    });
    p.submissions.forEach(function (s) {
      h += "<tr><td>" + esc(s.id) + "</td><td>" + esc(T("frozen")) + "</td><td>" + chip(null, String(s.frozen_at || "").slice(0, 10) + (s.student ? " · " + s.student : ""), "info") + "</td><td>" + esc(s.file_count) + " " + esc(T("files")) + "</td></tr>";
      s.evaluations.forEach(function (x) {
        h += "<tr><td>" + esc(x.id) + "</td><td>" + esc(T("evaluation")) + " (" + esc(D.agents.professor) + ")</td><td>" + (x.test ? chip(null, "TEST", "na") + ' <span class="muted small">' + esc(T("testRun")) + "</span>" : x.complete ? "<b>" + esc(x.total) + "</b> · " + esc(T("grade")) + " " + esc(x.grade) + " " + chip(x.status) : '<span class="muted">' + esc(T("incomplete")) + "</span>") +
          (x.check ? " " + esc(T("key")) + " " + chip(x.check.verdict) : "") + "</td><td>" + [link(x.links["report.md"], T("report")), link(x.links["discrepancies.md"], T("discrepancies")), link(x.links["expected-check.md"], T("keycheck"))].filter(Boolean).join(" · ") + "</td></tr>";
      });
    });
    h += "</tbody></table></div></div>";

    app.innerHTML = h;
    document.querySelectorAll("#rf button").forEach(function (b) { b.onclick = function () { ui.reqFilter = b.getAttribute("data-v"); projectView(name); }; });
  }

  function rankingView() {
    var aid = currentAid(), R = D.rankings[aid], a = A(aid), S = D.similarity[aid];
    var h = nav("ranking") + warnings(aid) + '<div class="card"><div class="toolbar">' + assignSelect(false) + "</div>";
    if (!R || !R.rows.length) { app.innerHTML = h + '<div class="empty">' + esc(T("noRanking")) + "</div></div>"; bindAssign(); return; }
    h += '<div class="note" style="margin-bottom:10px">' + esc(T("rankNote")) + "</div>";
    h += '<div class="tbl-wrap"><table><thead><tr><th>' + esc(T("hRank")) + "</th><th>" + esc(T("hStudent")) + "</th><th>" + esc(T("hPoints")) + "</th><th>" + esc(T("hGrade")) + "</th>" +
      R.rubric.criteria.map(function (c) { return '<th title="' + esc(c.name) + '">' + esc(c.id) + " /" + esc(c.points) + "</th>"; }).join("") +
      "<th>" + esc(T("hIntegrity")) + "</th><th>" + esc(T("hSimilarity")) + "</th><th>" + esc(T("hStatus")) + "</th></tr></thead><tbody>";
    R.rows.forEach(function (r) {
      var name = studentOfProject(r.project) || r.student;
      var sim = r.similarity_level ? chip(r.similarity_level, lbl(r.similarity_level)) : '<span class="muted">—</span>';
      if (r.similar_to && r.similar_to.length && S) sim += '<div class="detail-text">' + r.similar_to.slice(0, 3).map(function (x) { return esc(simLabel(S, x.with)) + " (" + esc(lbl(x.level)) + ")"; }).join(", ") + "</div>";
      h += '<tr class="click" data-p="' + esc(r.project) + '"><td><b class="num">' + (r.rank == null ? "—" : esc(r.rank)) + "</b></td><td>" +
        (name ? '<span class="student">' + esc(name) + "</span>" : '<span class="muted">' + esc(T("noName")) + "</span>") + '<div class="detail-text">' + esc(r.project) + "</div></td>" +
        (r.graded ? '<td><b class="num">' + esc(r.total) + "</b>/100</td><td>" + gradeHtml(r.grade) + "</td>" +
          R.rubric.criteria.map(function (c) { return '<td class="num">' + esc(r.criteria[c.id]) + "</td>"; }).join("") + "<td>" + chip(r.integrity) + "</td>"
          : '<td colspan="' + (3 + R.rubric.criteria.length) + '" class="muted">' + esc(T("notGraded")) + "</td>") +
        "<td>" + sim + "</td><td>" + (r.status ? chip(r.status) : "") + "</td></tr>";
    });
    h += "</tbody></table></div></div>";
    app.innerHTML = h;
    bindAssign();
    document.querySelectorAll("tr.click").forEach(function (tr) { tr.onclick = function () { location.hash = "#/p/" + encodeURIComponent(tr.getAttribute("data-p")); }; });
  }

  function quoteBlock(file, lines, quote) {
    return '<div><div class="small"><code>' + esc(file) + "</code> " + esc(lines) + '</div><div class="code">' + esc(quote || "") + "</div></div>";
  }

  function similarityView() {
    var aid = currentAid(), S = D.similarity[aid];
    var h = nav("similarity") + '<div class="card"><div class="toolbar">' + assignSelect(false) + "</div>";
    if (!S) { app.innerHTML = h + '<div class="empty">' + esc(T("noSimilarity")) + esc(aid) + "</div></div>"; bindAssign(); return; }
    h += '<div class="note">' + esc(T("simNote")) + "</div>";
    h += '<div class="grid tiles" style="margin-top:12px">' + tile(S.n, T("submissions")) + tile(S.counts.HIGH, lbl("HIGH")) + tile(S.counts.MEDIUM, lbl("MEDIUM")) + tile(S.counts.LOW, lbl("LOW")) + "</div>";
    h += '<div class="muted small">' + esc(T("generatedSim")) + " " + esc(String(S.generated_at).replace("T", " ").slice(0, 16)) + " · " +
      esc(S.ignored_common_fingerprints.code + S.ignored_common_fingerprints.docs) + " " + esc(T("ignoredCommon")) + "</div></div>";
    h += '<div class="card section">';
    if (!S.pairs.length) h += '<div class="empty">' + esc(T("noPairs")) + "</div>";
    S.pairs.forEach(function (x) {
      var g = x.git;
      h += '<div class="pair"><div class="issue-head">' + chip(x.level, lbl(x.level)) + '<span class="issue-title">' + esc(simLabel(S, x.a)) + " ↔ " + esc(simLabel(S, x.b)) + "</span>" +
        '<span class="small muted">' + esc(T("codeShort")) + " " + Math.round(x.code.containment * 100) + "% · " + esc(T("textShort")) + " " + Math.round(x.docs.containment * 100) + "%</span></div>";
      h += '<div class="small"><b>' + esc(T("reasons")) + ":</b> " + esc(x.reasons.join("; ")) + "</div>";
      [["code", T("codeRegions")], ["docs", T("textRegions")]].forEach(function (k) {
        if (!x[k[0]].regions.length) return;
        h += '<h3 style="margin-top:12px">' + esc(k[1]) + "</h3>";
        x[k[0]].regions.slice(0, 4).forEach(function (r) {
          h += '<div class="cmp">' + quoteBlock(r.file_a, r.lines_a, r.quote_a) + quoteBlock(r.file_b, r.lines_b, r.quote_b) + "</div>";
        });
      });
      var gl = [];
      g.identical_files.forEach(function (f) { gl.push("<li><b>" + esc(T("identicalFiles")) + ":</b> <code>" + esc(f.file_a) + "</code> = <code>" + esc(f.file_b) + "</code> · " + esc(T("firstSeen")) + ": " + esc(simLabel(S, x.a)) + " " + esc(String(f.first_seen_a || "?").slice(0, 16)) + ", " + esc(simLabel(S, x.b)) + " " + esc(String(f.first_seen_b || "?").slice(0, 16)) + "</li>"); });
      g.foreign_identity_commits.forEach(function (c) { gl.push("<li><b>" + esc(T("foreignCommits")) + ":</b> " + esc(c.commit) + " (" + esc(String(c.date || "").slice(0, 16)) + ") " + esc(c.identity) + " → " + esc(simLabel(S, c.commit_in)) + ": " + esc(c.subject) + "</li>"); });
      if (g.shared_commit_count) gl.push("<li><b>" + esc(T("sharedCommits")) + ":</b> " + esc(g.shared_commit_count) + " (" + esc(g.shared_commits.slice(0, 5).map(function (z) { return z.slice(0, 7); }).join(", ")) + ")</li>");
      g.shared_commit_messages.forEach(function (m) { gl.push("<li><b>" + esc(T("sharedMessages")) + ":</b> “" + esc(m) + "”</li>"); });
      if (gl.length) h += '<h3 style="margin-top:12px">Git</h3><ul class="plain">' + gl.join("") + "</ul>";
      if (g.provenance) {
        h += '<h3>' + esc(T("timelineTitle")) + '</h3><p class="small">A: ' + esc(simLabel(S, x.a)) + " · B: " + esc(simLabel(S, x.b)) + '</p><p class="small muted">' + esc(T("timelineNote")) + '</p>';
        (g.provenance.files || []).forEach(function (f) {
          var order = {A_EARLIER: "earlierA", B_EARLIER: "earlierB", SAME_RECORDED_TIME: "sameTime", UNKNOWN: "unknownOrder"};
          var side = function (s) {return '<code>' + esc((s.commit || "?").slice(0, 12)) + '</code> · ' + esc(s.committer_date || "?") + '<br><span class="muted small">author: ' + esc(s.author || s.identity || "?") + ' · ' + esc(s.author_date || "?") + (!s.history_complete ? ' · ' + esc(T("limitedHistory")) : '') + '</span>';};
          h += '<div class="section"><b>' + esc(T(order[f.recorded_order] || "unknownOrder")) + '</b> <span class="small muted">' + esc(T(f.kind === "NORMALIZED_CODE_FRAGMENTS" ? "normalizedFragments" : "exactVersion")) + '</span><div class="cmp"><div><code>' + esc(f.file_a) + '</code><br>A: ' + side(f.a) + '</div><div><code>' + esc(f.file_b) + '</code><br>B: ' + side(f.b) + '</div></div></div>';
        });
      }
      h += "</div>";
    });
    h += '<div class="muted small" style="margin-top:8px"><i>' + esc(S.disclaimer) + "</i></div></div>";
    app.innerHTML = h;
    bindAssign();
  }

  function route() {
    chrome();
    var m = location.hash.match(/^#\/p\/(.+)$/);
    if (m) projectView(decodeURIComponent(m[1]));
    else if (location.hash === "#/ranking") rankingView();
    else if (location.hash === "#/similarity") similarityView();
    else listView();
  }
  window.addEventListener("hashchange", function () { route(); window.scrollTo(0, 0); });
  window.addEventListener("dashboard-data", function (event) { D = event.detail; route(); });
  route();
})();
</script>
</body>
</html>
"""
