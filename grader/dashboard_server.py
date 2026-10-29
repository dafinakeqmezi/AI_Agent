"""Optional loopback dashboard controls. Executes only fixed grader commands."""
from __future__ import annotations

import json
import hashlib
from http.cookies import SimpleCookie, CookieError
import mimetypes
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

from . import cli_logins, dashboard, dashboard_accounts, dashboard_auth, github, roster
from .common import ROOT, REVIEWS, EVALUATIONS, SUBMISSIONS, assignment_files, load_json, now_iso, write_json


def provider_status(data, env=None):
    """Check local configuration/sign-in only; never request an inference.
    `env` is a professor workspace environment: subscription checks then use that professor's own sign-in."""
    from . import runner
    name = data.get("provider")
    if name not in {"chatgpt", "claude-code", "openai", "claude"}:
        raise ValueError("Choose a supported provider")
    model = data.get("model", "")
    if not isinstance(model, str):
        raise ValueError("Model must be text")
    args = SimpleNamespace(provider=name, model=model.strip() or None, timeout=30)
    args.model = runner.model_for(args)
    try:
        runner.create_provider(args, env=env)
    except runner.RunnerError as error:
        message = str(error)
        if env is not None and name in {"chatgpt", "claude-code"} and "Install" not in message:
            message = "Connect your own subscription under Subscriptions in this dashboard."
        return {"ready": False, "message": message}
    message = ("CLI installed and signed in. Model access is checked when you run."
               if name in {"chatgpt", "claude-code"} else
               "API key and model configured. Credentials and model access are checked when you run.")
    return {"ready": True, "message": message}


def integer(data, key, default, minimum, maximum):
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


class Jobs:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else ROOT
        self.roster_file = self.root / "projects" / "roster.json" if root is not None else dashboard.ROSTER_FILE
        self.submissions = self.root / "submissions" if root is not None else SUBMISSIONS
        self.reviews = self.root / "reviews" if root is not None else REVIEWS
        self.evaluations = self.root / "evaluations" if root is not None else EVALUATIONS
        self.env = dict(os.environ, GRADER_DATA_ROOT=str(self.root))
        # A professor workspace signs in to Claude Code / Codex with its own CLI homes.
        self.logins = None
        if root is not None:
            self.env.update(cli_logins.environment(self.root))
            self.logins = cli_logins.Logins(self.env)
        self.lock = threading.RLock()
        self.jobs = {}

    def active(self):
        return any(j["status"] in {"queued", "running", "stopping"} for j in self.jobs.values())

    def public(self, job):
        return {k: v for k, v in job.items() if k not in {"process", "cancel", "commands"}}

    def selected_repos(self, data):
        names = data.get("repos")
        if not isinstance(names, list) or not names or not all(isinstance(s, str) for s in names):
            raise ValueError("Select at least one saved repository")
        saved = roster.read(self.roster_file)
        by_repo = {s["repo"]: s for s in saved["students"]}
        if any(name not in by_repo for name in names):
            raise ValueError("Selected repository is not in the saved roster")
        entries = []
        for name in dict.fromkeys(names):
            entry = dict(by_repo[name])
            entry["ref"] = entry.get("ref") or "main"
            entry["assignment"] = entry.get("assignment") or saved.get("assignment")
            if not entry["assignment"]:
                raise ValueError(f"Set an assignment for {name} before running")
            assignment_files(entry["assignment"])
            entries.append(entry)
        return entries

    def selected_submissions(self, data):
        ids = data.get("submissions")
        if not isinstance(ids, list) or not ids or not all(isinstance(s, str) for s in ids):
            raise ValueError("Select frozen submission IDs")
        metadata = []
        for sid in dict.fromkeys(ids):
            if Path(sid).name != sid or sid in {".", ".."} or "\\" in sid:
                raise ValueError("Invalid submission ID")
            path = self.submissions / sid / "submission.json"
            if not path.is_file() or not path.resolve().is_relative_to(self.submissions.resolve()):
                raise ValueError(f"Unknown frozen submission: {sid}")
            metadata.append({**load_json(path), "submission_id": sid})
        return metadata

    def commands(self, data, directory):
        action = data.get("action")
        prefix = [sys.executable, "-u", "-m", "grader"]
        if action in {"review", "freeze"}:
            entries = self.selected_repos(data)
            if action == "freeze":
                deadline = data.get("deadline", "").strip()
                if deadline:
                    github.parse_time(deadline)
                commands = []
                for entry in entries:
                    command = prefix + ["freeze", entry["repo"], "--assignment", entry["assignment"]]
                    if entry.get("student"):
                        command += ["--student", entry["student"]]
                    if entry.get("ref"):
                        command += ["--ref", entry["ref"]]
                    if entry.get("team"):
                        command += ["--team", ",".join(entry["team"])]
                    if entry.get("deadline") or deadline:
                        command += ["--deadline", entry.get("deadline") or deadline]
                    commands.append(command)
                return commands
            roster_path = directory / "roster.json"
            write_json(roster_path, {"students": entries})
            command = prefix + ["review-all", "--roster", str(roster_path)]
        elif action in {"grade", "similarity"}:
            subs = self.selected_submissions(data)
            ids = ",".join(s["submission_id"] for s in subs)
            if action == "similarity":
                if len(subs) < 2:
                    raise ValueError("Select at least two frozen submissions to compare")
                assignments = {s.get("assignment") or "ml-project" for s in subs}
                if len(assignments) != 1:
                    raise ValueError("Similarity comparison requires submissions from the same assignment")
                return [prefix + ["similarity", "--assignment", assignments.pop(), "--submissions", ids]]
            command = prefix + ["grade-all", "--submissions", ids]
        else:
            raise ValueError("Choose review, freeze, grade or similarity")
        provider = data.get("provider")
        if provider not in {"openai", "claude", "chatgpt", "claude-code"}:
            raise ValueError("Choose a supported provider")
        model = data.get("model", "").strip()
        if model and not re.fullmatch(r"[A-Za-z0-9._:/-]{1,100}", model):
            raise ValueError("Enter a model name, not a command or API key")
        command += ["--provider", provider, "--max-turns", str(integer(data, "max_turns", 3, 1, 60)),
                    "--timeout", str(integer(data, "timeout", 300, 10, 1800))]
        if model:
            command += ["--model", model]
        return [command]

    def start(self, data):
        with self.lock:
            if self.active():
                raise ValueError("A job is already running. Wait or stop it before starting another.")
            job_id = uuid.uuid4().hex
            directory = self.root / "state" / "dashboard-jobs" / job_id
            commands = self.commands(data, directory)
            directory.mkdir(parents=True, exist_ok=True)
            job = {"id": job_id, "action": data["action"], "status": "queued", "created_at": now_iso(),
                   "elapsed_seconds": 0, "log": "", "exit_code": None, "usage": None,
                   "scope": list(dict.fromkeys(data.get("repos") if data["action"] in {"review", "freeze"} else data.get("submissions"))),
                   "commands": commands, "cancel": threading.Event(), "process": None}
            self.jobs[job_id] = job
            threading.Thread(target=self.worker, args=(job, directory), daemon=True).start()
            return self.public(job)

    def worker(self, job, directory):
        started = time.monotonic()
        failures = 0
        job["status"] = "running"
        try:
            with (directory / "output.log").open("w", encoding="utf-8") as log:
                for command in job["commands"]:
                    with self.lock:
                        if job["cancel"].is_set():
                            break
                        process = subprocess.Popen(command, cwd=ROOT, env={**self.env, "PYTHONIOENCODING": "utf-8"},
                                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                                   encoding="utf-8", errors="replace",
                                                   start_new_session=os.name != "nt")
                        job["process"] = process
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        with self.lock:
                            job["log"] = (job["log"] + line)[-64000:]
                            job["elapsed_seconds"] = round(time.monotonic() - started, 1)
                    process.stdout.close()
                    failures += process.wait() != 0
                    with self.lock:
                        job["process"] = None
                job["exit_code"] = 1 if failures else 0
        except OSError as error:
            job["log"] += f"\nJob could not run: {error}\n"
            job["exit_code"] = 1
        finally:
            with self.lock:
                job["process"] = None
                job["elapsed_seconds"] = round(time.monotonic() - started, 1)
                job["status"] = "cancelled" if job["cancel"].is_set() else "failed" if job["exit_code"] else "completed"
                job["finished_at"] = now_iso()
                job["usage"] = self.usage(job["log"])
                write_json(directory / "job.json", self.public(job))

    def usage(self, log):
        directories = set()
        for match in re.finditer(r'"(?:review_dir|evaluation_dir)":\s*("(?:[^"\\]|\\.)*")', log):
            try:
                path = Path(json.loads(match.group(1))).resolve()
                if any(path.is_relative_to(root.resolve()) for root in (self.reviews, self.evaluations)):
                    directories.add(path)
            except (ValueError, OSError):
                pass
        totals = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
        known = False
        for directory in directories:
            for path in directory.glob("runner.phase*.json"):
                try:
                    audit = load_json(path)
                except (ValueError, OSError):
                    continue
                totals["calls"] += audit.get("model_calls_attempted", len(audit.get("responses", [])))
                for row in audit.get("responses", []):
                    for key in ("input_tokens", "output_tokens"):
                        value = (row.get("usage") or {}).get(key)
                        if isinstance(value, int):
                            totals[key] += value
                            known = True
        return totals if known else None

    def stop(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError("Job not found")
            if job["status"] not in {"queued", "running", "stopping"}:
                return self.public(job)
            job["cancel"].set()
            job["status"] = "stopping"
            process = job["process"]
            if process is not None and process.poll() is None:
                self.signal_process(process, signal.SIGTERM)
                threading.Thread(target=self.finish_stop, args=(process,), daemon=True).start()
            return self.public(job)

    @staticmethod
    def signal_process(process, sig):
        try:
            if os.name == "nt":
                process.terminate() if sig == signal.SIGTERM else process.kill()
            else:
                os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    def finish_stop(self, process):
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.signal_process(process, signal.SIGKILL)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=0, auth=None, data_dir=None):
        self.auth = auth if auth is not None else dashboard_auth.prepare()
        public_url = os.environ.get("GRADER_PUBLIC_URL", "").rstrip("/")
        public = urlsplit(public_url)
        if public_url and (public.scheme != "https" or not public.hostname or public.username or public.password
                           or public.path or public.query or public.fragment):
            raise ValueError("GRADER_PUBLIC_URL must be an HTTPS origin, such as https://grader.example.edu")
        if public_url and self.auth.needs_setup():
            raise ValueError("Create the first professor account locally before enabling GRADER_PUBLIC_URL")
        self.public_url = public_url
        self.public_host = public.netloc
        self.cookie_security = "; Secure" if public_url else ""
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.data_dir = Path(data_dir) if data_dir is not None else ROOT / "state" / "professor-data"
        self.workspaces = {}
        self.workspace_lock = threading.RLock()
        self.url = public_url or f"http://127.0.0.1:{self.server_port}"

    def workspace(self, username):
        # The identity comes exclusively from a validated server-side session.
        key = hashlib.sha256(username.encode()).hexdigest()
        with self.workspace_lock:
            if key not in self.workspaces:
                root = self.data_dir / key
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.workspaces[key] = Jobs(root)
            return self.workspaces[key]

    def collect(self, workspace):
        result = subprocess.run([sys.executable, "-m", "grader.dashboard_snapshot"], cwd=ROOT,
                                env=workspace.env, capture_output=True, text=True, timeout=30, check=True)
        return json.loads(result.stdout)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body, kind="application/json; charset=utf-8", headers=None):
        if not isinstance(body, bytes):
            body = (json.dumps(body, ensure_ascii=False) if kind.startswith("application/json") else body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def permitted(self, api=False):
        hosts = {self.server.public_host} if self.server.public_url else {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in hosts:
            self.respond(403, {"error": "Invalid host"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self.server.url:
            self.respond(403, {"error": "Invalid origin"})
            return False
        if api and not secrets.compare_digest(self.headers.get("X-Dashboard-Token", ""), self.server.token):
            self.respond(403, {"error": "Dashboard token required"})
            return False
        return True

    def session(self):
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            return cookies["professor_session"].value if "professor_session" in cookies else ""
        except CookieError:
            return ""

    def authenticated(self, path):
        try:
            username = self.server.auth.identity(self.session())
            valid = username is not None
        except (OSError, ValueError, KeyError, TypeError):
            valid = False
        if valid:
            self.workspace = self.server.workspace(username)
            return True
        if path.startswith("/api/") or self.command != "GET":
            self.respond(401, {"error": "Professor sign-in required"})
        else:
            self.respond(303, "", "text/plain", {"Location": "/setup" if self.server.auth.needs_setup() else "/login"})
        return False

    def login_page(self, error="", status=200, setup=False):
        self.respond(status, dashboard_accounts.render(self.server.token,
                     mode="setup" if setup else "login", error=error), "text/html; charset=utf-8")

    def login(self, setup=False):
        if self.server.auth.needs_setup() != setup:
            self.respond(303, "", "text/plain", {"Location": "/setup" if self.server.auth.needs_setup() else "/login"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("Invalid sign-in request")
            fields = parse_qs(self.rfile.read(length).decode())
            if not secrets.compare_digest(fields.get("csrf", [""])[0], self.server.token):
                self.respond(403, {"error": "Invalid sign-in form; reload the page"})
                return
            if setup:
                self.server.auth.create_account(fields.get("username", [""])[0], fields.get("password", [""])[0],
                                                fields.get("confirmation", [""])[0], first=True)
                self.respond(303, "", "text/plain", {"Location": "/login"})
                return
            token = self.server.auth.login(fields.get("username", [""])[0], fields.get("password", [""])[0])
            if not token:
                self.login_page("Invalid username or password", 401)
                return
            self.respond(303, "", "text/plain", {"Location": "/", "Set-Cookie":
                f"professor_session={token}; HttpOnly; SameSite=Strict; Path=/" + self.server.cookie_security})
        except ValueError as error:
            self.login_page(str(error), 400, setup=setup)
        except (OSError, KeyError, TypeError):
            self.login_page("Sign-in unavailable. Check the local account configuration.", 503, setup=setup)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if not self.permitted():
            return
        if path in {"/login", "/setup"}:
            setup = self.server.auth.needs_setup()
            if setup != (path == "/setup"):
                self.respond(303, "", "text/plain", {"Location": "/setup" if setup else "/login"})
            else:
                self.login_page(setup=setup)
            return
        if not self.authenticated(path) or not self.permitted(path.startswith("/api/")):
            return
        try:
            if path == "/":
                page = dashboard.render(self.server.collect(self.workspace))
                config = json.dumps({"token": self.server.token}).replace("<", "\\u003c")
                extra = '<script id="live-config" type="application/json">' + config + '</script><script src="/controls.js"></script>'
                self.respond(200, page.replace("</body>", extra + "</body>"), "text/html; charset=utf-8")
            elif path == "/professors/new":
                self.respond(200, dashboard_accounts.render(self.server.token, mode="invite"), "text/html; charset=utf-8")
            elif path == "/controls.js":
                self.respond(200, Path(__file__).with_name("dashboard_controls.js").read_bytes(), "text/javascript; charset=utf-8")
            elif path == "/api/subscriptions":
                if not self.workspace.logins:
                    raise ValueError("Subscriptions are managed per professor workspace")
                check = parse_qs(urlsplit(self.path).query).get("check", ["1"])[0] != "0"
                self.respond(200, self.workspace.logins.status(check=check))
            elif path == "/api/state":
                data = self.server.collect(self.workspace)
                data["live"] = True
                saved = roster.read(self.workspace.roster_file)
                with self.workspace.lock:
                    jobs = [self.workspace.public(j) for j in self.workspace.jobs.values()]
                self.respond(200, {"data": data, "roster": saved, "jobs": jobs})
            else:
                file = (self.workspace.root / path.lstrip("/")).resolve()
                allowed = any(file.is_relative_to(root.resolve()) for root in (self.workspace.reviews, self.workspace.evaluations))
                if allowed and file.is_file() and file.suffix in {".md", ".json", ".html"}:
                    self.respond(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "text/plain")
                else:
                    self.respond(404, {"error": "Not found"})
        except (ValueError, OSError, SystemExit, subprocess.SubprocessError) as error:
            self.respond(400, {"error": str(error)})

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self.permitted():
            return
        if path in {"/login", "/setup"}:
            self.login(setup=path == "/setup")
            return
        if not self.authenticated(path) or not self.permitted(api=True):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            path = urlsplit(self.path).path
            if path == "/api/logout":
                self.server.auth.logout(self.session())
                self.respond(200, {"ok": True}, headers={"Set-Cookie":
                    "professor_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" + self.server.cookie_security})
            elif path == "/api/professors":
                self.server.auth.create_account(data.get("username", ""), data.get("password", ""),
                                                data.get("confirmation", ""))
                self.respond(201, {"ok": True})
            elif path == "/api/provider-status":
                self.respond(200, provider_status(data, self.workspace.env))
            elif path.startswith("/api/subscriptions/"):
                logins = self.workspace.logins
                if not logins:
                    raise ValueError("Subscriptions are managed per professor workspace")
                action, tool = path.rsplit("/", 1)[1], data.get("tool")
                if action in {"login", "logout"} and self.workspace.active():
                    raise ValueError("Wait for the running job before changing a subscription")
                if action == "login":
                    self.respond(200, logins.start(tool))
                elif action == "code":
                    self.respond(200, logins.submit_code(tool, data.get("code")))
                elif action == "cancel":
                    self.respond(200, logins.cancel(tool))
                elif action == "logout":
                    self.respond(200, logins.logout(tool))
                else:
                    self.respond(404, {"error": "Not found"})
            elif path == "/api/repos":
                with self.workspace.lock:
                    if self.workspace.active():
                        raise ValueError("Wait for the running job before changing the roster")
                    entry = roster.add(self.workspace.roster_file, data.get("repo", ""),
                                       data.get("student", ""), data.get("assignment", ""), data.get("branch", "main"))
                self.respond(201, entry)
            elif path == "/api/jobs":
                self.respond(202, self.workspace.start(data))
            elif path == "/api/stop":
                self.respond(200, self.workspace.stop(data.get("id")))
            else:
                self.respond(404, {"error": "Not found"})
        except (ValueError, TypeError, AttributeError, OSError, SystemExit) as error:
            self.respond(400, {"error": str(error)})


def serve(port=0, open_browser=True):
    server = Server(port)
    print(f"Live dashboard: {server.url} (Ctrl+C stops the server and active jobs)", flush=True)
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for workspace in list(server.workspaces.values()):
            for job in list(workspace.jobs.values()):
                workspace.stop(job["id"])
            if workspace.logins:
                workspace.logins.close()
        server.server_close()
