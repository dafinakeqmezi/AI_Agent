"""GitHub integration: REST API client + local mirrors of student repositories.

Authentication: set GITHUB_TOKEN (or GH_TOKEN) to a token with read access to the student repos
(fine-grained: Contents + Metadata read; classic: `repo` for private repos). Public repos work without one
(60 API requests/hour). The token is never written to disk or passed on a command line: git receives it
through GIT_CONFIG_* environment variables.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .common import ROOT, load_json, now_iso, write_json

API = "https://api.github.com"
MIRRORS = ROOT / "projects"
MARKER = "grader-mirror.json"  # stored inside .git/, so it never appears in the project files
REPO_RE = re.compile(r"^(?:https?://github\.com/|git@github\.com:)?([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


class GitHubError(Exception):
    pass


def parse_repo(spec: str) -> tuple[str, str] | None:
    """'owner/repo', 'https://github.com/owner/repo(.git)' or 'git@github.com:owner/repo.git' -> (owner, repo)."""
    m = REPO_RE.match(spec.strip())
    return (m.group(1), m.group(2)) if m else None


def is_repo_spec(spec: str) -> bool:
    return parse_repo(spec) is not None and not Path(spec).exists()


def token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def parse_time(s: str | None) -> datetime | None:
    """Parse ISO-8601; a timezone offset is required (deadlines must be unambiguous)."""
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise SystemExit(f"Time {s!r} has no timezone offset; use e.g. 2026-12-15T23:59:00+01:00")
    return dt


# ------------------------------------------------------------------ REST API

def api(path: str, params: dict | None = None, paginate: bool = False, max_pages: int = 10):
    url = path if path.startswith("http") else API + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "aiml-project-grader"}
    if token():
        headers["Authorization"] = f"Bearer {token()}"
    results, pages = [], 0
    while url and pages < max_pages:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read() or b"null")
                link = r.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
                reset = datetime.fromtimestamp(int(e.headers.get("X-RateLimit-Reset", "0")), timezone.utc)
                raise GitHubError(f"GitHub API rate limit exhausted until {reset.isoformat()}. "
                                  f"{'' if token() else 'Set GITHUB_TOKEN for 5000 requests/hour.'}") from None
            if e.code == 404:
                raise GitHubError(f"Not found: {path} (wrong name, or a private repo without a token "
                                  "that can read it; set GITHUB_TOKEN)") from None
            if e.code == 401:
                raise GitHubError("GitHub rejected the token (401). Check GITHUB_TOKEN.") from None
            raise GitHubError(f"GitHub API error {e.code} on {path}: {e.read()[:300]!r}") from None
        except urllib.error.URLError as e:
            raise GitHubError(f"Cannot reach GitHub API: {e.reason}") from None
        if not paginate:
            return data
        results.extend(data if isinstance(data, list) else [data])
        pages += 1
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return results


def repo_metadata(owner: str, repo: str, sha: str | None = None, max_commit_pages: int = 10) -> dict:
    """Repo info, commit -> login mapping, push activity (incl. force pushes), PRs and branches. Best effort."""
    meta: dict = {"full_name": f"{owner}/{repo}", "fetched_at": now_iso(), "errors": {}}
    r = api(f"/repos/{owner}/{repo}")  # without repo access nothing else works: let it raise
    meta["repo"] = {k: r.get(k) for k in ("html_url", "private", "fork", "created_at", "pushed_at",
                                           "default_branch", "size", "language", "visibility")}
    if r.get("fork") and r.get("parent"):
        meta["repo"]["parent"] = r["parent"]["full_name"]
    if r.get("template_repository"):
        meta["repo"]["template"] = r["template_repository"]["full_name"]
    try:
        params = {"per_page": 100}
        if sha:
            params["sha"] = sha
        commits = api(f"/repos/{owner}/{repo}/commits", params, paginate=True, max_pages=max_commit_pages)
        meta["commit_logins"] = {c["sha"]: {"author": (c.get("author") or {}).get("login"),
                                            "committer": (c.get("committer") or {}).get("login"),
                                            "verified": ((c.get("commit") or {}).get("verification") or {}).get("verified")}
                                 for c in commits}
    except GitHubError as e:
        meta["errors"]["commits"] = str(e)
    try:
        acts = api(f"/repos/{owner}/{repo}/activity", {"per_page": 100}, paginate=True, max_pages=5)
        meta["activity"] = [{"timestamp": a.get("timestamp"), "type": a.get("activity_type"), "ref": a.get("ref"),
                             "before": a.get("before"), "after": a.get("after"),
                             "actor": (a.get("actor") or {}).get("login")} for a in acts]
    except GitHubError as e:
        meta["errors"]["activity"] = str(e)
    try:
        pulls = api(f"/repos/{owner}/{repo}/pulls", {"state": "all", "per_page": 100}, paginate=True, max_pages=3)
        meta["pull_requests"] = [{"number": p["number"], "title": p["title"], "user": (p.get("user") or {}).get("login"),
                                  "created_at": p.get("created_at"), "merged_at": p.get("merged_at"),
                                  "state": p.get("state")} for p in pulls]
    except GitHubError as e:
        meta["errors"]["pull_requests"] = str(e)
    try:
        meta["branches"] = [b["name"] for b in api(f"/repos/{owner}/{repo}/branches", {"per_page": 100}, paginate=True, max_pages=2)]
    except GitHubError as e:
        meta["errors"]["branches"] = str(e)
    return meta


def list_repos(org: str | None = None, user: str | None = None, prefix: str | None = None) -> list[dict]:
    if org:
        repos = api(f"/orgs/{org}/repos", {"per_page": 100, "type": "all"}, paginate=True, max_pages=20)
    elif user:
        repos = api(f"/users/{user}/repos", {"per_page": 100}, paginate=True, max_pages=20)
    else:
        repos = api("/user/repos", {"per_page": 100}, paginate=True, max_pages=20)
    out = [{"full_name": r["full_name"], "private": r["private"], "pushed_at": r.get("pushed_at"),
            "default_branch": r.get("default_branch"), "html_url": r["html_url"]} for r in repos]
    if prefix:
        out = [r for r in out if r["full_name"].split("/", 1)[1].startswith(prefix)]
    return sorted(out, key=lambda r: r["full_name"].lower())


# ------------------------------------------------------------------ git mirror

def _git_env() -> dict:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if token():
        basic = base64.b64encode(f"x-access-token:{token()}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"})
    return env


def git(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, env=_git_env(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        if token():
            msg = msg.replace(token(), "***")
        raise GitHubError(f"git {' '.join(args[:2])} failed: {msg[:500]}")
    return r.stdout


def mirror_dir(owner: str, repo: str) -> Path:
    return MIRRORS / f"{owner}__{repo}".lower()


def fetch(spec: str, ref: str | None = None, deadline: str | None = None) -> dict:
    """Clone or update the local mirror and check out the requested commit (detached).

    ref: branch, tag or SHA (default: the repo's default branch).
    deadline: ISO-8601 with offset; selects the last first-parent commit on the branch committed at or before it.
    """
    parsed = parse_repo(spec)
    if not parsed:
        raise GitHubError(f"Not a GitHub repository: {spec!r} (use owner/repo or https://github.com/owner/repo)")
    owner, repo = parsed
    d = mirror_dir(owner, repo)
    url = f"https://github.com/{owner}/{repo}.git"
    if d.exists():
        if not (d / ".git" / MARKER).exists():
            raise GitHubError(f"{d} exists but is not a grader mirror; refusing to overwrite it.")
        git(["fetch", "--prune", "--tags", "--force", "origin", "+refs/heads/*:refs/remotes/origin/*"], cwd=d)
    else:
        d.parent.mkdir(parents=True, exist_ok=True)
        git(["clone", "--no-checkout", url, str(d)])
        write_json(d / ".git" / MARKER, {"repo": f"{owner}/{repo}", "created_at": now_iso()})

    default_branch = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=d, check=False).strip()
    default_branch = default_branch.split("/", 1)[1] if "/" in default_branch else "main"
    target = ref or default_branch
    candidates = [f"origin/{target}", f"refs/tags/{target}", target]
    branch_ref = next((c for c in candidates if git(["rev-parse", "--verify", "--quiet", c + "^{commit}"], cwd=d, check=False).strip()), None)
    if not branch_ref:
        raise GitHubError(f"Ref {target!r} not found in {owner}/{repo}")

    dl = parse_time(deadline)
    if dl:
        sha = None
        for line in git(["rev-list", "--first-parent", "--format=%H %cI", "--no-commit-header", branch_ref], cwd=d).splitlines():
            h, ts = line.split(" ", 1)
            if datetime.fromisoformat(ts) <= dl:
                sha = h
                break
        if not sha:
            raise GitHubError(f"No commit on {branch_ref} at or before the deadline {deadline}")
    else:
        sha = git(["rev-parse", branch_ref + "^{commit}"], cwd=d).strip()

    git(["checkout", "--quiet", "--force", "--detach", sha], cwd=d)
    git(["clean", "-fdxq"], cwd=d)
    after = int(git(["rev-list", "--count", f"{sha}..{branch_ref}"], cwd=d).strip() or 0)
    info = {"type": "github", "repo": f"{owner}/{repo}", "url": f"https://github.com/{owner}/{repo}",
            "branch_ref": branch_ref, "sha": sha, "deadline": deadline, "commits_after_selected": after,
            "mirror": str(d), "fetched_at": now_iso()}
    write_json(d / ".git" / MARKER, {**load_json(d / ".git" / MARKER), "last_fetch": info})
    return info


def _contains(repo_dir: Path, sha: str, tip: str | None) -> bool:
    if not tip or set(tip) == {"0"}:
        return False
    if tip == sha:
        return True
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, tip], cwd=repo_dir, capture_output=True).returncode == 0


def push_time_of(sha: str, activity: list[dict], repo_dir: Path) -> tuple[str | None, str]:
    """When `sha` first reached GitHub, per the activity log: (timestamp, explanation).

    Only a push whose `before` did NOT contain the commit and whose `after` does proves when it arrived.
    If the oldest logged state already contains it, it was pushed before the log begins (time unknown)."""
    pushes = sorted((a for a in activity or [] if a.get("after") and a.get("type") in
                     ("push", "force_push", "pr_merge", "merge_queue_merge", "branch_creation")),
                    key=lambda x: x.get("timestamp") or "")
    for a in pushes:
        if not _contains(repo_dir, sha, a["after"]):
            continue
        if _contains(repo_dir, sha, a.get("before")):
            return None, "already on GitHub before the oldest push in the activity log (push time unknown, not late)"
        return a["timestamp"], f"introduced by the {a.get('type')} at {a['timestamp']}"
    return None, "not found in the activity log"
