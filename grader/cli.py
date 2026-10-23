"""Command line entry point: python -m grader <command> ..."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import (benchmark, books, cite, dashboard, expected, freeze, github, history, override, ranking, readiness,
               roster, score, similarity, state)
from .common import (DATA_ROOT, EVALUATIONS, REVIEWS, ROOT, STATES, SUBMISSIONS, assignment_files, list_assignments,
                     load_json, now_iso, project_key, stamp, write_json)
from .inventory import build_inventory
from .scan import scan
from .versions import collect_versions


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def prepare(root: Path, out: Path, offline: bool, deadline: str | None = None, team: list[str] | None = None,
            github_meta: dict | None = None, branch_ref: str | None = None) -> dict:
    inv = build_inventory(root, out)
    sc = scan(root, out)
    ci = cite.verify_project(root, out, offline=offline)
    res = {"artifacts_dir": str(out), "files": inv["file_count"], "by_kind": inv["counts_by_kind"],
           "inventory_notes": inv["notes"], "signals": len(sc["signals"]),
           "signal_types": sorted({s["type"] for s in sc["signals"]}), "citations": ci["counts"]}
    if (root / ".git").exists():
        h = history.analyze(root, ref="HEAD", deadline=deadline, team=team, github=github_meta,
                            branch_ref=branch_ref, out=out)
        res["git_history"] = {"commits": h["metrics"]["commits"], "active_days": h["metrics"]["active_days"],
                              "code_measure": h["metrics"]["code_measure"],
                              "signal_types": sorted({s["type"] for s in h["signals"]})}
    if github_meta:
        write_json(out / "github.json", github_meta)
    return res


def _team(a) -> list[str] | None:
    return [t.strip() for t in a.team.split(",") if t.strip()] if getattr(a, "team", None) else None


def _github_source(spec: str, ref: str | None, deadline: str | None) -> tuple[Path, dict, dict]:
    """Fetch/update the local mirror of a GitHub repo and collect API metadata."""
    try:
        info = github.fetch(spec, ref=ref, deadline=deadline)
        owner, repo = github.parse_repo(spec)
        meta = github.repo_metadata(owner, repo, sha=info["sha"])
    except github.GitHubError as e:
        sys.exit(str(e))
    return Path(info["mirror"]), info, meta


def _assignment_info(af: dict) -> dict:
    """Paths the agents must read for this assignment (passed into their prompts)."""
    out = {"assignment": af["id"], "assignment_files": {k: str(af[k]) for k in ("requirements", "rubric", "dod")}}
    if af["meta"]:
        out["assignment_files"]["assignment"] = str(af["meta"])
        meta = load_json(af["meta"])
        out["assignment_files"]["guidelines"] = [str(ROOT / g) for g in meta.get("guidelines", [])]
    return out


def cmd_new_review(a):
    info, meta = None, None
    if github.is_repo_spec(a.project):
        src, info, meta = _github_source(a.project, a.ref, None)
    else:
        src = Path(a.project).resolve()
    if not src.is_dir():
        sys.exit(f"Not a directory: {src}")
    key = project_key(src)
    d = REVIEWS / key / stamp()
    summary = prepare(src, d / "artifacts", a.offline, deadline=a.deadline, team=_team(a), github_meta=meta,
                      branch_ref=(info or {}).get("branch_ref"))
    af = assignment_files(a.assignment)
    write_json(d / "run.json", {"kind": "review", "project": key, "project_path": str(src), "started_at": now_iso(),
                                "assignment": af["id"], "source": info or {"type": "local", "path": str(src)},
                                "deadline": a.deadline, "team": _team(a) or [], "versions": collect_versions(af["id"])})
    state.set_state(key, "UNDER_REVIEW", ref=str(d.relative_to(REVIEWS.parent)))
    _print({"review_dir": str(d), "project": key, **_assignment_info(af), **summary})


def cmd_readiness(a):
    d = Path(a.review_dir)
    res = readiness.evaluate(d)
    run = load_json(d / "run.json") if (d / "run.json").exists() else {}
    if run.get("project"):
        cur = state.get(run["project"]) or {}
        if cur.get("state") in (None, "DRAFT", "UNDER_REVIEW", "READY_FOR_FINAL_REVIEW"):
            state.set_state(run["project"], res["verdict"] if res["verdict"] == "READY_FOR_FINAL_REVIEW" else "UNDER_REVIEW",
                            ref=str(d), note=res["verdict"])
    _print({k: res[k] for k in ("verdict", "counts", "failed_conditions", "validation_errors")})
    print(f"\nWritten: {d / 'readiness.md'}")
    return 2 if res["validation_errors"] else 0


def _freeze_one(project: str, student=None, sid=None, max_file_mb=200.0, ref=None, deadline=None, team=None,
                assignment=None) -> dict:
    assignment_files(assignment)  # fail fast on an unknown assignment, before cloning anything
    if github.is_repo_spec(project):
        src, info, meta = _github_source(project, ref, deadline)
        return freeze.freeze(src, student=student, submission_id=sid, max_file_mb=max_file_mb, deadline=deadline,
                             team=team, source=info, github_meta=meta, assignment=assignment)
    return freeze.freeze(project, student=student, submission_id=sid, max_file_mb=max_file_mb, deadline=deadline, team=team,
                         assignment=assignment)


FREEZE_KEYS = ("submission_id", "project", "student", "assignment", "source", "git_commit", "deadline", "frozen_at", "file_count",
               "manifest_sha256", "warnings")


def cmd_freeze(a):
    sub = _freeze_one(a.project, a.student, a.id, a.max_file_mb, a.ref, a.deadline, _team(a), a.assignment)
    _print({k: sub.get(k) for k in FREEZE_KEYS})


def cmd_history(a):
    src = Path(a.repo).resolve()
    h = history.analyze(src, ref=a.ref, deadline=a.deadline, team=_team(a), out=Path(a.out))
    _print({"metrics": h.get("metrics"), "signals": [f"{s['type']} {s['location']}" for s in h["signals"]]})
    print(f"\nWritten: {Path(a.out) / 'history.md'}")


def cmd_github_repos(a):
    try:
        repos = github.list_repos(org=a.org, user=a.user, prefix=a.prefix)
    except github.GitHubError as e:
        sys.exit(str(e))
    for r in repos:
        print(f"{r['full_name']:50s} {'private' if r['private'] else 'public ':8s} pushed {r['pushed_at']}")
    if a.write_roster:
        roster = {"course": None, "deadline": a.deadline, "students": [
            {"student": None, "repo": r["full_name"], "team": [], "ref": None} for r in repos]}
        write_json(a.write_roster, roster)
        print(f"\nRoster template written to {a.write_roster}. Fill in student names and GitHub logins (team).")


def cmd_roster_add(a):
    try:
        repo = a.repo if a.repo is not None else input("GitHub URL or owner/repo: ").strip()
        student = a.student if a.student is not None else input("Student name: ").strip()
        assignment = a.assignment
        if assignment is None:
            print("Available assignments: " + ", ".join(list_assignments()))
            assignment = input("Assignment ID: ").strip()
        entry = roster.add(Path(a.roster), repo, student, assignment, getattr(a, "branch", "main"))
    except (EOFError, KeyboardInterrupt):
        sys.exit("Input cancelled; roster was not changed.")
    except (ValueError, OSError) as e:
        sys.exit(str(e))
    _print({"roster": str(Path(a.roster).resolve()), "added": entry})
    print("Saved locally. No repository was fetched, reviewed, frozen, or graded.")


def cmd_roster_list(a):
    if not Path(a.roster).exists():
        sys.exit("Roster not found. Add a repository with: python -m grader roster add")
    try:
        _print(roster.read(Path(a.roster)))
    except (ValueError, OSError) as e:
        sys.exit(str(e))


def cmd_runner(a):
    from . import runner
    if a.max_turns is None:
        a.max_turns = 8 if a.provider in {"chatgpt", "claude-code"} else 60
    try:
        result = runner.run_reviews(a) if a.cmd == "review-all" else runner.run_grades(a)
    except (runner.RunnerError, ValueError, OSError) as e:
        sys.exit(str(e))
    _print(result)
    return 1 if result.get("failed") else 0


def positive_int(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def cmd_github_freeze_all(a):
    roster = load_json(a.roster)
    deadline = a.deadline or roster.get("deadline")
    if not deadline:
        sys.exit("A deadline is required (roster 'deadline' or --deadline), e.g. 2026-12-15T23:59:00+01:00")
    results = []
    for s in roster["students"]:
        try:
            sub = _freeze_one(s["repo"], s.get("student"), s.get("submission_id"), a.max_file_mb, s.get("ref"),
                              s.get("deadline") or deadline, s.get("team") or None,
                              s.get("assignment") or a.assignment or roster.get("assignment"))
            results.append({"repo": s["repo"], "student": s.get("student"), "assignment": sub.get("assignment"),
                            "submission_id": sub["submission_id"],
                            "commit": (sub.get("git_commit") or "")[:12], "files": sub["file_count"], "warnings": sub["warnings"]})
        except SystemExit as e:  # one failing repo must not stop the batch
            results.append({"repo": s["repo"], "student": s.get("student"), "error": str(e)})
    _print(results)
    failed = [r for r in results if "error" in r]
    print(f"\nFrozen {len(results) - len(failed)} / {len(results)} repositories at deadline {deadline}.")
    return 1 if failed else 0


def cmd_kb_add_book(a):
    meta = {"title": a.title, "authors": [x.strip() for x in a.authors.split(";")], "edition": a.edition or "",
            "publisher": a.publisher or "", "year": a.year, "short_cite": a.short_cite or a.key,
            "license_note": "Local reference copy; do not redistribute or commit to git."}
    _print(books.add_book(Path(a.pdf), a.key, meta))
    print("Next: write a TOPICS.md (requirement -> section map) and add the book to knowledge-base/INDEX.md "
          "and literature/references.json; bump knowledge-base/manifest.json.")


def cmd_verify(a):
    res = freeze.verify(a.submission_id)
    _print(res)
    return 0 if res["intact"] else 3


def cmd_new_evaluation(a):
    sub_dir = SUBMISSIONS / a.submission_id
    if not (sub_dir / "submission.json").exists():
        sys.exit(f"Unknown submission {a.submission_id}")
    check = freeze.verify(a.submission_id)
    if not check["intact"]:
        _print(check)
        sys.exit("Submission failed integrity verification; refusing to evaluate.")
    d = EVALUATIONS / a.submission_id / f"eval-{stamp()}"
    summary = prepare(sub_dir / "files", d / "artifacts", a.offline)
    # The git history was analysed at freeze time (the frozen files/ copy has no .git): expose it to Agent 2.
    for name in ("history.json", "history.md", "github.json", "git-log.txt"):
        if (sub_dir / "metadata" / name).exists():
            shutil.copyfile(sub_dir / "metadata" / name, d / "artifacts" / name)
    if (sub_dir / "metadata" / "history.json").exists():
        h = load_json(sub_dir / "metadata" / "history.json")
        summary["git_history"] = {"commits": (h.get("metrics") or {}).get("commits"), "available": h.get("available"),
                                  "signal_types": sorted({s["type"] for s in h.get("signals", [])})}
    af = assignment_files(load_json(sub_dir / "submission.json").get("assignment"))
    write_json(d / "run.json", {"kind": "evaluation", "submission_id": a.submission_id, "started_at": now_iso(),
                                "assignment": af["id"], "versions": collect_versions(af["id"]), "integrity_check": check})
    _print({"evaluation_dir": str(d), "submission_files": str(sub_dir / "files"), **_assignment_info(af), **summary})


def cmd_score(a):
    d = Path(a.eval_dir)
    run = load_json(d / "run.json") if (d / "run.json").exists() else {}
    if run.get("submission_id"):
        check = freeze.verify(run["submission_id"])
        if not check["intact"]:
            _print(check)
            sys.exit("Submission changed during evaluation; refusing to score.")
        run["integrity_check_at_scoring"] = check
        write_json(d / "run.json", run)
    try:
        res = score.compute(d)
    except score.ScoreError as e:
        print("evaluation.json failed validation. Fix these and re-run score:\n")
        for err in e.errors:
            print(f"- {err}")
        return 2
    _print({"total": res["total"], "grade": res["grade"], "status": res["review_status"],
            "criteria": {c["id"]: c["score"] for c in res["criteria"]}, "warnings": res["warnings"]})
    print(f"\nWritten: {d / 'report.md'}")
    return 0


def cmd_override(a):
    d = Path(a.eval_dir)
    if a.requirement:
        if not a.status or not a.reason:
            sys.exit("--requirement needs --status and --reason")
        entry = {"type": "requirement", "requirement_id": a.requirement, "status": a.status, "reason": a.reason}
        if a.credit is not None:
            entry["credit"] = a.credit
    elif a.false_positive:
        if not a.reason:
            sys.exit("--false-positive needs --reason")
        entry = {"type": "false_positive", "target": a.false_positive, "reason": a.reason}
    elif a.comment:
        entry = {"type": "comment", "text": a.comment}
    elif a.approve:
        entry = {"type": "approve"}
    elif a.request_reevaluation:
        if not a.reason:
            sys.exit("--request-reevaluation needs --reason")
        entry = {"type": "request_reevaluation", "reason": a.reason}
    else:
        sys.exit("Nothing to do: use --requirement, --false-positive, --comment, --approve or --request-reevaluation")
    entry["by"] = a.by
    rec = override.add(d, entry)
    print(f"Recorded {rec['id']} ({rec['type']}). Recomputing grade...\n")
    return cmd_score(argparse.Namespace(eval_dir=str(d)))


def cmd_latest_review(a):
    d = REVIEWS / a.project
    runs = sorted([p for p in d.iterdir() if (p / "review.json").exists()]) if d.exists() else []
    if not runs:
        print("none")
        return 1
    print(runs[-1])
    return 0


def cmd_cite(a):
    if a.doi:
        _print(dict(zip(("result", "record"), cite.crossref_doi(a.doi))))
    elif a.arxiv:
        _print(dict(zip(("result", "record"), cite.arxiv_id(a.arxiv))))
    elif a.title:
        _print(cite.crossref_title_search(a.title))
    elif a.project and a.out:
        _print(cite.verify_project(Path(a.project), Path(a.out), offline=a.offline)["counts"])
    else:
        sys.exit("Use --doi, --arxiv, --title, or <project> --out <dir>")


def cmd_state(a):
    if a.set:
        _print(state.set_state(a.project, a.set, note=a.note))
    else:
        _print(state.get(a.project) or {"state": "DRAFT", "note": "not registered yet"})


def cmd_status(a):
    projects = state.all_projects()
    if not projects:
        print("No projects registered yet.")
    for name, p in sorted(projects.items()):
        last = p["history"][-1] if p["history"] else {}
        print(f"{name:40s} {p['state']:24s} {p.get('updated_at', '')}  {last.get('ref', '')}")


def cmd_check_expected(a):
    res = expected.check(Path(a.run_dir), Path(a.expected))
    _print({k: res[k] for k in ("verdict", "mode", "agreement", "counts", "failures")})
    print(f"\nWritten: {Path(a.run_dir) / 'expected-check.md'}")
    return 0 if res["verdict"] == "PASS" else 1


def cmd_similarity(a):
    ids = [x.strip() for x in a.submissions.split(",")] if a.submissions else None
    r = similarity.run(a.assignment, ids=ids, base=Path(a.base) if a.base else None, roster=a.roster)
    _print({"assignment": r["assignment"], "submissions": r["n"], "pairs": len(r["pairs"]), "levels": r["counts"],
            "flagged": [f"{p['level']}: {p['student_a']} ({p['a']}) <-> {p['student_b']} ({p['b']}): {'; '.join(p['reasons'])}"
                        for p in r["pairs"] if p["level"] in ("HIGH", "MEDIUM")]})
    print(f"\nWritten: {Path(r['out_dir']) / 'similarity.md'}")


def cmd_ranking(a):
    r = ranking.run(a.assignment, roster=a.roster)
    print(ranking.render(r))
    print(f"Written: {Path(r['out_dir']) / 'ranking.md'}")


def cmd_dashboard(a):
    if getattr(a, "serve", False):
        from .dashboard_server import serve
        serve(a.port, open_browser=not a.no_open)
        return
    out = dashboard.build(Path(a.out), open_browser=not a.no_open)
    print(f"Dashboard written: {out}")


def main(argv=None) -> int:
    # Windows consoles default to cp1252; titles, names and reports contain other characters.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m grader", description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("versions", help="print rubric/requirements/KB/prompt versions").set_defaults(
        fn=lambda a: _print(collect_versions()))

    p = sp.add_parser("prepare", help="inventory + scan + citations for any folder")
    p.add_argument("project"); p.add_argument("--out", required=True); p.add_argument("--offline", action="store_true")
    p.set_defaults(fn=lambda a: _print(prepare(Path(a.project).resolve(), Path(a.out), a.offline)))

    p = sp.add_parser("new-review", help="Agent 1: start a review run for a project folder or GitHub repo")
    p.add_argument("project", help="folder, owner/repo, or https://github.com/owner/repo")
    p.add_argument("--ref", help="GitHub branch/tag/SHA (default: default branch)")
    p.add_argument("--deadline", help="ISO-8601 with offset; used for last-minute analysis")
    p.add_argument("--team", help="comma-separated GitHub logins/emails of the team")
    p.add_argument("--assignment", help="assignment id (default ml-project); see python -m grader assignments")
    p.add_argument("--offline", action="store_true"); p.set_defaults(fn=cmd_new_review)

    p = sp.add_parser("history", help="analyse the git history of a local repo (C11 metrics + signals)")
    p.add_argument("repo"); p.add_argument("--out", required=True); p.add_argument("--ref", default="HEAD")
    p.add_argument("--deadline"); p.add_argument("--team"); p.set_defaults(fn=cmd_history)

    for name, description in (("review-all", "automated API reviews of the saved roster"),
                              ("grade-all", "automated two-phase API grading of frozen IDs")):
        p = sp.add_parser(name, help=description)
        p.add_argument("--provider", choices=["openai", "claude", "chatgpt", "claude-code"], default="openai")
        p.add_argument("--model", help="model ID or chosen provider's model environment variable; subscription CLIs can use their default")
        p.add_argument("--max-turns", type=positive_int, help="maximum model calls per phase (subscription default: 8; direct API: 60)")
        p.add_argument("--max-output-tokens", type=positive_int, default=12000, help="output cap per direct API call (not subscription CLI calls)")
        p.add_argument("--timeout", type=positive_int, default=120, help="request timeout in seconds")
        p.add_argument("--dry-run", action="store_true", help="check scope without API calls or starting runs")
        p.add_argument("--offline", action="store_true", help="skip preparation's external citation checks; API/GitHub still need network")
        if name == "review-all":
            p.add_argument("--roster", default=str(DATA_ROOT / "projects" / "roster.json"))
            p.add_argument("--assignment", help="fallback when a roster entry has no assignment")
        else:
            p.add_argument("--submissions", required=True, help="comma-separated frozen IDs; does not freeze repos")
        p.set_defaults(fn=cmd_runner)

    rp = sp.add_parser("roster", help="register student repositories locally")
    rsp = rp.add_subparsers(dest="roster_command", required=True)
    p = rsp.add_parser("add", help="add a repo; prompt for missing fields")
    p.add_argument("repo", nargs="?")
    p.add_argument("--student")
    p.add_argument("--assignment")
    p.add_argument("--roster", default=str(DATA_ROOT / "projects" / "roster.json"))
    p.add_argument("--branch", default="main", help="Git branch to fetch (default: main)")
    p.set_defaults(fn=cmd_roster_add)
    p = rsp.add_parser("list", help="show saved repositories")
    p.add_argument("--roster", default=str(DATA_ROOT / "projects" / "roster.json"))
    p.set_defaults(fn=cmd_roster_list)

    gh = sp.add_parser("github", help="GitHub: list student repos, freeze all repos of a roster at the deadline")
    gsp = gh.add_subparsers(dest="gcmd", required=True)
    p = gsp.add_parser("repos", help="list repositories of an org/user (needs GITHUB_TOKEN for private repos)")
    p.add_argument("--org"); p.add_argument("--user"); p.add_argument("--prefix", help="e.g. a GitHub Classroom assignment prefix")
    p.add_argument("--write-roster", metavar="FILE", help="write a roster template, e.g. projects/roster.json")
    p.add_argument("--deadline"); p.set_defaults(fn=cmd_github_repos)
    p = gsp.add_parser("freeze-all", help="freeze every repo in a roster at the deadline commit")
    p.add_argument("--roster", default=str(DATA_ROOT / "projects" / "roster.json")); p.add_argument("--deadline")
    p.add_argument("--assignment", help="assignment id for every repo (else the roster's 'assignment')")
    p.add_argument("--max-file-mb", type=float, default=200.0); p.set_defaults(fn=cmd_github_freeze_all)

    p = sp.add_parser("kb-add-book", help="index a textbook PDF into knowledge-base/literature/books/<key>")
    p.add_argument("pdf"); p.add_argument("--key", required=True); p.add_argument("--title", required=True)
    p.add_argument("--authors", required=True, help='"Last, F.; Last, F."'); p.add_argument("--year", type=int)
    p.add_argument("--edition"); p.add_argument("--publisher"); p.add_argument("--short-cite")
    p.set_defaults(fn=cmd_kb_add_book)

    p = sp.add_parser("readiness", help="Agent 1: validate review.json and apply the Definition of Done")
    p.add_argument("review_dir"); p.set_defaults(fn=cmd_readiness)

    p = sp.add_parser("freeze", help="create an immutable FINAL_SUBMISSION")
    p.add_argument("project", help="folder, owner/repo, or https://github.com/owner/repo")
    p.add_argument("--student"); p.add_argument("--id")
    p.add_argument("--ref", help="GitHub branch/tag/SHA to freeze")
    p.add_argument("--deadline", help="ISO-8601 with offset; GitHub: freeze the last commit at/before it")
    p.add_argument("--team", help="comma-separated GitHub logins/emails of the team")
    p.add_argument("--assignment", help="assignment id (default ml-project); see python -m grader assignments")
    p.add_argument("--max-file-mb", type=float, default=200.0); p.set_defaults(fn=cmd_freeze)

    p = sp.add_parser("verify", help="check a frozen submission against its hash manifest")
    p.add_argument("submission_id"); p.set_defaults(fn=cmd_verify)

    p = sp.add_parser("new-evaluation", help="Agent 2: start an evaluation run for a frozen submission")
    p.add_argument("submission_id"); p.add_argument("--offline", action="store_true"); p.set_defaults(fn=cmd_new_evaluation)

    p = sp.add_parser("score", help="Agent 2: validate evaluation.json and compute the grade")
    p.add_argument("eval_dir"); p.set_defaults(fn=cmd_score)

    p = sp.add_parser("override", help="professor: override a requirement, dismiss a finding, comment, approve")
    p.add_argument("eval_dir")
    p.add_argument("--requirement"); p.add_argument("--status", choices=sorted(score.EVAL_STATUSES))
    p.add_argument("--credit", type=float)
    p.add_argument("--false-positive", metavar="TARGET", help='e.g. "integrity.indicators[0]"')
    p.add_argument("--comment"); p.add_argument("--approve", action="store_true")
    p.add_argument("--request-reevaluation", action="store_true")
    p.add_argument("--reason"); p.add_argument("--by", required=True)
    p.set_defaults(fn=cmd_override)

    p = sp.add_parser("latest-review", help="print the latest completed Agent 1 review dir for a project")
    p.add_argument("project"); p.set_defaults(fn=cmd_latest_review)

    p = sp.add_parser("cite", help="verify citations (project, --doi, --arxiv, or --title)")
    p.add_argument("project", nargs="?"); p.add_argument("--out"); p.add_argument("--offline", action="store_true")
    p.add_argument("--doi"); p.add_argument("--arxiv"); p.add_argument("--title"); p.set_defaults(fn=cmd_cite)

    p = sp.add_parser("state", help="show or set a project's lifecycle state")
    p.add_argument("project"); p.add_argument("--set", choices=STATES)
    p.add_argument("--note"); p.set_defaults(fn=cmd_state)

    sp.add_parser("status", help="list all projects and their states").set_defaults(fn=cmd_status)

    p = sp.add_parser("benchmark", help="compare Agent 2 grades with human grades")
    p.add_argument("--file", default=str(benchmark.BENCH / "human_grades.json"))
    p.set_defaults(fn=lambda a: _print({k: v for k, v in benchmark.run(Path(a.file)).items() if k not in ("rows",)}))

    sp.add_parser("assignments", help="list assignments and their requirement files").set_defaults(
        fn=lambda a: _print({aid: _assignment_info(assignment_files(aid))["assignment_files"] for aid in list_assignments()}))

    p = sp.add_parser("similarity", help="compare all submissions of an assignment (shared code, text, git history)")
    p.add_argument("--assignment", help="assignment id (default ml-project)")
    p.add_argument("--submissions", help="comma-separated submission ids (default: latest per project)")
    p.add_argument("--base", help="folder with the professor's starter/base code to ignore")
    p.add_argument("--roster", help="limit the class to the repos in this roster (e.g. projects/roster.json)")
    p.set_defaults(fn=cmd_similarity)

    p = sp.add_parser("ranking", help="rank all students of an assignment by their latest Agent 2 total")
    p.add_argument("--assignment", help="assignment id (default ml-project)")
    p.add_argument("--roster", help="limit to the repos in this roster (default: the class of the latest similarity run)")
    p.set_defaults(fn=cmd_ranking)

    p = sp.add_parser("professor-account", help="create or reset a local professor dashboard login")
    p.add_argument("username")
    def configure_professor(a):
        from .dashboard_auth import configure
        try:
            configure(a.username)
        except (ValueError, EOFError) as error:
            sys.exit(str(error))
    p.set_defaults(fn=configure_professor)

    p = sp.add_parser("dashboard", help="build the local read-only HTML dashboard (dashboard.html) and open it")
    p.add_argument("--out", default=str(dashboard.DEFAULT_OUT))
    p.add_argument("--no-open", action="store_true", help="do not open the browser")
    p.add_argument("--serve", action="store_true", help="serve local controls for repos, model runs, progress and similarity")
    p.add_argument("--port", type=int, default=0, help="live dashboard port (default: choose a free port)")
    p.set_defaults(fn=cmd_dashboard)

    p = sp.add_parser("check-expected", help="compare a review/evaluation run with an expected-findings file")
    p.add_argument("run_dir", help="reviews/<project>/<ts> (Agent 1) or evaluations/<sub>/eval-<ts> (Agent 2)")
    p.add_argument("expected", help="e.g. tests/expected/expected-student-review.json")
    p.set_defaults(fn=cmd_check_expected)

    a = ap.parse_args(argv)
    return a.fn(a) or 0
