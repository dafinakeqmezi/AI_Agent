"""Git history analysis for criterion C11 (version control & development process) and integrity indicators.

Produces SIGNALS (leads) plus the metrics/timeline the agents grade from. Commit evidence is cited as
{"file": "(git history)", "location": "commit <sha7>", "quote": "<subject>"}.
Outputs: <out>/history.json and <out>/history.md
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import KB, load_json, now_iso, write_json, write_text
from .github import git, parse_time, push_time_of
from .inventory import classify
from .scan import SECRET_RES
from .scc import find_scc
from .scc import snapshots as scc_snapshots

POLICY_FILE = KB / "policies" / "version-control-policy.json"
FMT = "%x1e%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%cn%x1f%ce%x1f%cI%x1f%s%x1f%b%x1f"
NOREPLY_RE = re.compile(r"^(?:\d+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$", re.I)
REPORT_RE = re.compile(r"(?i)(report|paper|thesis|article|manuscript)|\.(pdf|docx|tex)$")


def load_policy() -> dict:
    return load_json(POLICY_FILE)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def read_log(repo: Path, ref: str) -> list[dict]:
    out = git(["log", "--no-renames", "--numstat", f"--format={FMT}", ref], cwd=repo)
    commits = []
    for rec in out.split("\x1e")[1:]:
        parts = rec.split("\x1f")
        if len(parts) < 10:
            continue
        sha, parents, an, ae, ad, cn, ce, cd, subject, body = parts[:10]
        files = []
        for line in (parts[10] if len(parts) > 10 else "").strip().splitlines():
            bits = line.split("\t")
            if len(bits) != 3:
                continue
            a, d, path = bits
            binary = a == "-"
            files.append({"path": path.strip('"'), "added": 0 if binary else int(a),
                          "deleted": 0 if binary else int(d), "binary": binary})
        commits.append({"sha": sha, "parents": parents.split(), "author_name": an, "author_email": ae.lower(),
                        "author_date": ad, "committer_name": cn, "committer_email": ce.lower(), "committer_date": cd,
                        "subject": subject.strip(), "body": body.strip(), "files": files})
    return commits


def large_blobs(repo: Path, ref: str, min_bytes: int) -> list[dict]:
    objs = git(["rev-list", "--objects", ref], cwd=repo)
    r = subprocess.run(["git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize) %(rest)"],
                       cwd=repo, input=objs, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for line in r.stdout.splitlines():
        bits = line.split(" ", 3)
        if len(bits) >= 3 and bits[0] == "blob" and int(bits[2]) >= min_bytes:
            out.append({"blob": bits[1], "size_mb": round(int(bits[2]) / 1e6, 1), "path": bits[3] if len(bits) > 3 else "?"})
    return sorted(out, key=lambda b: -b["size_mb"])


def secrets_in_history(repo: Path, ref: str, max_bytes: int = 100_000_000) -> list[dict]:
    p = subprocess.Popen(["git", "-c", "core.quotepath=off", "log", "-p", "--no-renames", "--no-ext-diff",
                          "--format=%x1eCOMMIT %H", ref], cwd=repo, stdout=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace")
    found, sha, path, read = [], None, None, 0
    for line in p.stdout:
        read += len(line)
        if read > max_bytes:
            break
        if line.startswith("\x1eCOMMIT "):
            sha = line.split()[1]
        elif line.startswith("+++ "):
            path = line[6:].strip() if line.startswith("+++ b/") else None
        elif line.startswith("+") and path:
            for rx, label in SECRET_RES:
                if rx.search(line):
                    found.append({"sha": sha, "path": path, "kind": label, "line": rx.sub("<REDACTED>", line[1:].strip())[:120]})
                    break
    p.kill()
    p.wait()
    return found


def _identity(c: dict, logins: dict) -> tuple[str, str | None]:
    login = (logins.get(c["sha"]) or {}).get("author")
    if not login:
        m = NOREPLY_RE.match(c["author_email"])
        login = m.group(1) if m else None
    return (login.lower() if login else c["author_email"]), login


def _sig(signals, typ, hint, reqs, location, message, quote=""):
    signals.append({"id": f"HSIG-{len(signals) + 1:03d}", "type": typ, "severity_hint": hint, "requirement_ids": reqs,
                    "file": "(git history)", "location": location, "quote": quote[:200], "message": message})


def analyze(repo_dir: Path, ref: str = "HEAD", deadline=None, team: list[str] | None = None, github: dict | None = None,
            branch_ref: str | None = None, course_start=None, out: Path | None = None) -> dict:
    repo_dir = Path(repo_dir).resolve()
    pol = load_policy()
    th = pol["thresholds"]
    deadline = parse_time(deadline) if isinstance(deadline, str) else deadline
    course_start = parse_time(course_start) if isinstance(course_start, str) else course_start
    signals: list[dict] = []
    if not (repo_dir / ".git").exists():
        _sig(signals, "no_git_history", "high", ["VCS-001", "VCS-002", "VCS-003", "VCS-004", "VCS-005"], "-",
             "The submission has no git history; version-control requirements cannot be evidenced.")
        res = {"available": False, "generated_at": now_iso(), "signals": signals, "commits": []}
        if out:
            write_json(Path(out) / "history.json", res)
            write_text(Path(out) / "history.md", "# Git history\n\nNo git history available.\n")
        return res

    github = github or {}
    logins = github.get("commit_logins", {})
    head = git(["rev-parse", ref + "^{commit}"], cwd=repo_dir).strip()
    raw = read_log(repo_dir, ref)
    excl_kinds = set(pol["effective_lines_exclude"]["kinds"])
    excl_names = set(pol["effective_lines_exclude"]["file_names"])
    generic = [re.compile(p, re.I) for p in pol["generic_message_patterns"]]
    web_upload = [re.compile(p, re.I) for p in pol["web_upload_patterns"]]
    ai_trailer = [re.compile(p, re.I) for p in pol["ai_trailer_patterns"]]
    team_l = [t.lower() for t in (team or [])]

    commits = []
    for c in raw:
        ident, login = _identity(c, logins)
        eff_add = sum(f["added"] for f in c["files"]
                      if classify(Path(f["path"])) not in excl_kinds and Path(f["path"]).name.lower() not in excl_names)
        flags = []
        merge = len(c["parents"]) > 1
        if not merge and any(rx.search(c["subject"]) for rx in generic):
            flags.append("generic_message")
        if not merge and len(c["subject"]) < th["min_message_length"]:
            flags.append("short_message")
        if any(rx.search(c["subject"]) for rx in web_upload):
            flags.append("web_upload")
        if any(rx.search(c["subject"] + "\n" + c["body"]) for rx in ai_trailer):
            flags.append("ai_trailer")
        cd, ad = _dt(c["committer_date"]), _dt(c["author_date"])
        if abs((cd - ad).total_seconds()) > th["author_committer_gap_days"] * 86400:
            flags.append("author_committer_date_gap")
        if deadline and cd > deadline:
            flags.append("after_deadline")
        if course_start and ad < course_start:
            flags.append("before_course_start")
        bot = bool(login and login.endswith("[bot]")) or "[bot]" in c["author_name"]
        commits.append({"sha": c["sha"], "short": c["sha"][:7], "merge": merge, "identity": ident, "login": login,
                        "bot": bot, "author_name": c["author_name"], "author_email": c["author_email"],
                        "author_date": c["author_date"], "committer_date": c["committer_date"],
                        "subject": c["subject"], "body": c["body"][:500],
                        "files_changed": len(c["files"]), "added": sum(f["added"] for f in c["files"]),
                        "deleted": sum(f["deleted"] for f in c["files"]), "effective_added": eff_add,
                        "binary_files": sum(f["binary"] for f in c["files"]),
                        "paths": [f["path"] for f in c["files"]][:200], "flags": flags})
    commits.sort(key=lambda c: _dt(c["committer_date"]))
    work = [c for c in commits if not c["merge"] and not c["bot"]]
    total_eff = sum(c["effective_added"] for c in work) or 1

    # ---- scc code snapshots: real code size per commit (every commit, or the last commit of each week)
    scc_bin = find_scc()
    code = {"tool": "scc" if scc_bin else "git numstat", "final": None}
    if scc_bin and work:
        if len(work) <= th.get("scc_max_snapshots", 300):
            targets = [c["sha"] for c in work]
            code["sampling"] = "every non-merge commit"
        else:
            last_of_week = {}
            for c in work:
                last_of_week[tuple(_dt(c["committer_date"]).isocalendar()[:2])] = c["sha"]
            targets = list(last_of_week.values())
            code["sampling"] = "last commit of each week"
        snaps = scc_snapshots(repo_dir, list(dict.fromkeys(targets + [head])), scc_bin)
        prev = 0
        for c in work:
            s = snaps.get(c["sha"])
            if s:
                c["scc"] = {k: s[k] for k in ("code", "comment", "complexity", "doc_lines")}
                c["code_delta"] = s["code"] - prev
                prev = s["code"]
        code["final"] = snaps[head]
    final_code = (code["final"] or {}).get("code") or 0

    # ---- bulk / oversized (code share via scc when available, else numstat effective lines)
    for c in work:
        if final_code and "code_delta" in c:
            share, what = max(0, c["code_delta"]) / final_code, f"{max(0, c['code_delta'])} of {final_code} final code lines (scc)"
        else:
            share, what = c["effective_added"] / total_eff, f"{c['effective_added']} effective lines added"
        if share >= th["bulk_commit_share"] or c["files_changed"] >= th["bulk_commit_files"]:
            c["flags"].append("bulk")
            _sig(signals, "bulk_commit", "medium", ["VCS-001", "VCS-003"], f"commit {c['short']}",
                 f"One commit accounts for {share:.0%} of the code ({what}; {c['files_changed']} files).",
                 c["subject"])
        elif c["effective_added"] > th["max_commit_effective_lines"]:
            c["flags"].append("oversized")
            _sig(signals, "oversized_commit", "low", ["VCS-003"], f"commit {c['short']}",
                 f"Large commit: {c['effective_added']} effective lines added.", c["subject"])
        if "web_upload" in c["flags"]:
            _sig(signals, "web_upload_commit", "medium", ["VCS-001"], f"commit {c['short']}",
                 "Files uploaded through the GitHub web interface (work done outside version control).", c["subject"])

    # ---- activity over time
    days = sorted({_dt(c["committer_date"]).astimezone(timezone.utc).date() for c in work})
    weekly: dict[str, dict] = defaultdict(lambda: {"commits": 0, "effective_added": 0, "code_at_end": None})
    for c in work:
        y, w, _ = _dt(c["committer_date"]).isocalendar()
        weekly[f"{y}-W{w:02d}"]["commits"] += 1
        weekly[f"{y}-W{w:02d}"]["effective_added"] += c["effective_added"]
        if "scc" in c:
            weekly[f"{y}-W{w:02d}"]["code_at_end"] = c["scc"]["code"]
    if len(work) < th["min_commits"]:
        _sig(signals, "few_commits", "medium", ["VCS-001"], "-", f"Only {len(work)} non-merge commits (expected at least {th['min_commits']}).")
    if len(days) < th["min_active_days"]:
        _sig(signals, "few_active_days", "medium", ["VCS-001"], "-", f"Commits on only {len(days)} distinct day(s) (expected at least {th['min_active_days']}).")

    end = deadline or (_dt(work[-1]["committer_date"]) if work else None)
    lm = {"window_hours": th["last_minute_window_hours"], "window_end": end.isoformat() if end else None}
    if end and work:
        start = end - timedelta(hours=th["last_minute_window_hours"])
        in_win = [c for c in work if start <= _dt(c["committer_date"]) <= end]
        lm.update({"commits": len(in_win), "commit_share": round(len(in_win) / len(work), 2),
                   "effective_lines_share": round(sum(c["effective_added"] for c in in_win) / total_eff, 2)})
        if lm["effective_lines_share"] >= th["last_minute_share"] and len(work) > 1:
            _sig(signals, "last_minute_development", "medium", ["VCS-001"], "-",
                 f"{lm['effective_lines_share']:.0%} of effective lines were committed in the last "
                 f"{th['last_minute_window_hours']} h before {'the deadline' if deadline else 'the last commit'}.")

    # ---- messages
    gen = [c for c in work if "generic_message" in c["flags"] or "short_message" in c["flags"]]
    gen_share = round(len(gen) / len(work), 2) if work else 0
    if work and gen_share >= th["generic_message_share"]:
        _sig(signals, "generic_messages", "low", ["VCS-002"], "-",
             f"{gen_share:.0%} of commit messages are generic or very short (e.g. '{gen[0]['subject']}').")

    # ---- authors / team
    by_id: dict[str, dict] = {}
    for c in work:
        a = by_id.setdefault(c["identity"], {"identity": c["identity"], "login": c["login"], "names": set(),
                                             "commits": 0, "effective_added": 0, "days": set()})
        a["names"].add(c["author_name"])
        a["commits"] += 1
        a["effective_added"] += c["effective_added"]
        a["days"].add(_dt(c["committer_date"]).astimezone(timezone.utc).date())
    authors = sorted(({**a, "names": sorted(a["names"]), "active_days": len(a["days"]), "days": None,
                       "line_share": round(a["effective_added"] / total_eff, 2),
                       "commit_share": round(a["commits"] / len(work), 2) if work else 0,
                       "in_team": (a["identity"] in team_l or (a["login"] or "").lower() in team_l) if team_l else None}
                      for a in by_id.values()), key=lambda a: -a["effective_added"])
    for a in authors:
        a.pop("days")
    if team_l:
        min_share = th["team_min_contribution_share_factor"] / len(team_l)
        present = {a["identity"] for a in authors} | {(a["login"] or "").lower() for a in authors}
        for t in team_l:
            if t not in present:
                _sig(signals, "team_member_without_commits", "high", ["VCS-005"], "-",
                     f"Team member '{t}' has no commits in the analysed history (check PRs/co-author trailers and the report).")
        for a in authors:
            if a["in_team"] and a["line_share"] < min_share and a["commit_share"] < min_share:
                _sig(signals, "unbalanced_contribution", "medium", ["VCS-005"], "-",
                     f"'{a['identity']}' contributed {a['line_share']:.0%} of lines / {a['commit_share']:.0%} of commits "
                     f"(below {min_share:.0%}).")
            if a["in_team"] is False:
                _sig(signals, "author_outside_team", "medium", ["VCS-005"], "-",
                     f"Commits by '{a['identity']}' ({', '.join(a['names'])}), who is not on the team list "
                     f"({a['commits']} commits, {a['line_share']:.0%} of lines). Could be a second account, TA or copied history (INT-014).")

    # ---- other per-commit signals
    for c in work:
        if "after_deadline" in c["flags"]:
            _sig(signals, "commit_after_deadline", "high", ["VCS-001"], f"commit {c['short']}",
                 "Commit dated after the deadline is part of the analysed history.", c["subject"])
        if "author_committer_date_gap" in c["flags"]:
            _sig(signals, "author_committer_date_gap", "low", [], f"commit {c['short']}",
                 f"Author date {c['author_date']} vs commit date {c['committer_date']} (rebase/amend, or edited dates; INT-013).",
                 c["subject"])
        if "before_course_start" in c["flags"]:
            _sig(signals, "commit_before_course_start", "medium", [], f"commit {c['short']}",
                 "Commit authored before the course start (imported history? INT-014).", c["subject"])
    ai = [c for c in commits if "ai_trailer" in c["flags"]]
    if ai:
        _sig(signals, "ai_coauthor_trailer", "info", [], f"commit {ai[0]['short']}",
             f"{len(ai)} commit(s) carry AI-assistant attribution. Check that AI usage is disclosed as the AI-usage policy requires (information, not an indicator).",
             ai[0]["subject"])

    # ---- repository hygiene
    blobs = large_blobs(repo_dir, ref, int(th["large_file_mb"] * 1e6))
    for b in blobs[:10]:
        _sig(signals, "large_file_in_history", "low", ["VCS-003"], "-",
             f"{b['path']} ({b['size_mb']} MB) is stored in the git history.")
    secrets = secrets_in_history(repo_dir, ref)
    for s in secrets[:10]:
        _sig(signals, "secret_in_history", "high", ["VCS-003", "IMPL-003"], f"commit {s['sha'][:7]}",
             f"Possible secret ({s['kind']}) added in {s['path']}. It stays in the history even if deleted later; it must be revoked.",
             s["line"])
    tracked = git(["ls-tree", "-r", "--name-only", ref], cwd=repo_dir).splitlines()
    has_gitignore = any(Path(p).name == ".gitignore" for p in tracked)

    # ---- milestones (first commit touching each kind of artifact)
    milestones = {}
    def mark(key, c):
        milestones.setdefault(key, {"commit": c["short"], "date": c["committer_date"], "subject": c["subject"]})
    for c in work:
        for p in c["paths"]:
            kind = classify(Path(p))
            low = p.lower()
            if kind in ("code", "notebook"):
                mark(kind, c)
            if REPORT_RE.search(low) and kind in ("document",):
                mark("report", c)
            if kind == "data":
                mark("data", c)
            if low.startswith(("results/", "outputs/", "output/", "figures/")):
                mark("results", c)
            if re.search(r"(^|/)tests?/|(^|/)test_[^/]*\.py$", low):
                mark("tests", c)
            if Path(low).name.startswith("readme"):
                mark("readme", c)

    # ---- GitHub-side evidence
    gh = {}
    if github:
        repo_meta = github.get("repo", {})
        activity = github.get("activity") or []
        force = [a for a in activity if a.get("type") == "force_push"]
        gh = {"repo": repo_meta, "pull_requests": len(github.get("pull_requests") or []),
              "pull_requests_merged": len([p for p in github.get("pull_requests") or [] if p.get("merged_at")]),
              "branches": github.get("branches"), "push_events": len(activity), "force_pushes": force,
              "errors": github.get("errors")}
        if repo_meta.get("fork") or repo_meta.get("template"):
            _sig(signals, "fork_or_template", "info", [], "-",
                 f"Repository is a {'fork of ' + str(repo_meta.get('parent')) if repo_meta.get('fork') else 'copy of template ' + str(repo_meta.get('template'))}. "
                 "Separate the student's own commits from upstream/template commits (INT-014).")
        for a in force:
            _sig(signals, "force_push", "medium", [], "-",
                 f"Force-push to {a.get('ref')} at {a.get('timestamp')} by {a.get('actor')} (history rewritten; INT-013, often innocent).")
        if activity:
            pushed, how = push_time_of(head, activity, repo_dir)
            gh["frozen_commit_pushed_at"] = pushed
            gh["frozen_commit_pushed_at_note"] = how
            if pushed and deadline and _dt(pushed) > deadline:
                _sig(signals, "pushed_after_deadline", "high", [], f"commit {head[:7]}",
                     f"The analysed commit was first pushed at {pushed}, after the deadline {deadline.isoformat()}, "
                     "although its commit timestamp is earlier (INT-015).")
        else:
            gh["frozen_commit_pushed_at_note"] = "No push activity available from GitHub."
    if branch_ref:
        after = int(git(["rev-list", "--count", f"{head}..{branch_ref}"], cwd=repo_dir, check=False).strip() or 0)
        gh["commits_after_analysed_ref"] = after
        if after:
            _sig(signals, "commits_after_frozen_ref", "info", [], "-",
                 f"{after} commit(s) on {branch_ref} after the analysed commit are excluded (made after the deadline/selected ref).")

    first = work[0]["committer_date"] if work else None
    last = work[-1]["committer_date"] if work else None
    metrics = {
        "commits": len(work), "merge_commits": len([c for c in commits if c["merge"]]),
        "bot_commits": len([c for c in commits if c["bot"]]),
        "first_commit": first, "last_commit": last,
        "span_days": round((_dt(last) - _dt(first)).total_seconds() / 86400, 1) if work else 0,
        "active_days": len(days), "active_weeks": len(weekly),
        "effective_lines_added": total_eff if work else 0,
        "largest_commit_share": round(max((c["effective_added"] for c in work), default=0) / total_eff, 2),
        "generic_message_share": gen_share,
        "mean_message_length": round(sum(len(c["subject"]) for c in work) / len(work), 1) if work else 0,
        "last_minute": lm, "has_gitignore": has_gitignore, "authors": len(authors),
        "code_measure": code["tool"],
        "final_code_lines": final_code if code["final"] else None,
        "final_complexity": (code["final"] or {}).get("complexity"),
        "comment_ratio": round(code["final"]["comment"] / code["final"]["code"], 2) if code["final"] and code["final"]["code"] else None,
        "languages": (code["final"] or {}).get("languages"),
    }
    res = {"available": True, "generated_at": now_iso(), "repo_dir": str(repo_dir), "ref": ref, "head_sha": head,
           "branch_ref": branch_ref, "deadline": deadline.isoformat() if deadline else None, "team": team or [],
           "thresholds": th, "metrics": metrics, "weekly": dict(sorted(weekly.items())), "authors": authors,
           "milestones": milestones, "github": gh, "large_blobs": blobs[:20], "secrets": secrets[:20],
           "disclaimer": "History signals are leads about the development process, not findings. Commit timestamps are client-controlled.",
           "signals": signals, "commits": commits}
    if out:
        write_json(Path(out) / "history.json", res)
        write_text(Path(out) / "history.md", render(res))
    return res


def render(h: dict) -> str:
    m = h["metrics"]
    L = ["# Git history (C11: version control & development process)", "",
         f"Analysed commit `{h['head_sha'][:12]}` ({h['ref']}); deadline: {h['deadline'] or 'not set'}; team: {', '.join(h['team']) or 'not set'}",
         "", "Cite commits as `{\"file\": \"(git history)\", \"location\": \"commit <sha7>\", \"quote\": \"<subject>\"}`.", "",
         "| Metric | Value |", "|---|---|"]
    for k in ("commits", "merge_commits", "bot_commits", "first_commit", "last_commit", "span_days", "active_days",
              "active_weeks", "effective_lines_added", "largest_commit_share", "generic_message_share",
              "mean_message_length", "has_gitignore", "authors", "code_measure", "final_code_lines",
              "final_complexity", "comment_ratio", "languages"):
        L.append(f"| {k} | {m[k]} |")
    lm = m["last_minute"]
    if "commits" in lm:
        L.append(f"| last {lm['window_hours']} h before {lm['window_end']} | {lm['commits']} commits, {lm['effective_lines_share']:.0%} of lines |")
    g = h.get("github") or {}
    if g:
        L += [f"| GitHub PRs (merged) | {g.get('pull_requests')} ({g.get('pull_requests_merged')}) |",
              f"| push events / force pushes | {g.get('push_events')} / {len(g.get('force_pushes') or [])} |",
              f"| analysed commit first pushed | {g.get('frozen_commit_pushed_at') or g.get('frozen_commit_pushed_at_note', '-')} |"]
        if g.get("commits_after_analysed_ref") is not None:
            L.append(f"| commits after analysed ref (excluded) | {g['commits_after_analysed_ref']} |")
    L += ["", "## Weekly activity", "", "| Week | Commits | Effective lines added | Code lines at end of week (scc) | |",
          "|---|---|---|---|---|"]
    mx = max((w["effective_added"] for w in h["weekly"].values()), default=1) or 1
    for wk, w in h["weekly"].items():
        bar = "#" * max(1, round(20 * w["effective_added"] / mx)) if w["effective_added"] else ""
        code_end = "-" if w.get("code_at_end") is None else w["code_at_end"]
        L.append(f"| {wk} | {w['commits']} | {w['effective_added']} | {code_end} | {bar} |")
    L += ["", "## Authors", "", "| Identity | Names | Commits | Lines share | Active days | In team |", "|---|---|---|---|---|---|"]
    for a in h["authors"]:
        L.append(f"| {a['identity']} | {', '.join(a['names'])} | {a['commits']} | {a['line_share']:.0%} | {a['active_days']} | {a['in_team'] if a['in_team'] is not None else '-'} |")
    L += ["", "## Milestones (first commit touching each artifact type)", ""]
    L += [f"- **{k}**: {v['date']} `{v['commit']}` {v['subject']}" for k, v in h["milestones"].items()] or ["- none"]
    L += ["", "## Signals (leads; confirm before citing)", ""]
    L += [f"- [{s['severity_hint']}] **{s['type']}** {s['location']}: {s['message']}" + (f" (\"{s['quote']}\")" if s["quote"] else "")
          for s in h["signals"]] or ["- none"]
    work = [c for c in h["commits"] if not c["merge"]]
    L += ["", f"## Commits ({len(work)} non-merge; oldest first{', first 300 shown' if len(work) > 300 else ''})", "",
          "| Date | Commit | Author | +eff | Code Δ (scc) | Code total | Files | Flags | Message |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in work[:300]:
        msg = c["subject"].replace("|", "\\|")[:90]
        delta = f"{c['code_delta']:+}" if "code_delta" in c else "-"
        total = c["scc"]["code"] if "scc" in c else "-"
        L.append(f"| {c['committer_date'][:16]} | {c['short']} | {c['login'] or c['author_name']} | {c['effective_added']} | "
                 f"{delta} | {total} | {c['files_changed']} | {', '.join(c['flags'])} | {msg} |")
    L += ["", f"_{h['disclaimer']}_"]
    return "\n".join(L) + "\n"
