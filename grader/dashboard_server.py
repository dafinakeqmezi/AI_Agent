"""Optional loopback dashboard controls. Executes only fixed grader commands."""
from __future__ import annotations

import json
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
from urllib.parse import unquote, urlsplit

from . import dashboard, github, roster
from .common import ROOT, REVIEWS, EVALUATIONS, SUBMISSIONS, assignment_files, load_json, now_iso, write_json


def provider_status(data):
    """Check local configuration/sign-in only; never request an inference."""
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
        runner.create_provider(args)
    except runner.RunnerError as error:
        return {"ready": False, "message": str(error)}
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
    def __init__(self):
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
        saved = roster.read(dashboard.ROSTER_FILE)
        by_repo = {s["repo"]: s for s in saved["students"]}
        if any(name not in by_repo for name in names):
            raise ValueError("Selected repository is not in the saved roster")
        entries = []
        for name in dict.fromkeys(names):
            entry = dict(by_repo[name])
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
            path = SUBMISSIONS / sid / "submission.json"
            if not path.is_file() or not path.resolve().is_relative_to(SUBMISSIONS.resolve()):
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
            directory = ROOT / "state" / "dashboard-jobs" / job_id
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
                        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                                   stderr=subprocess.STDOUT, text=True, bufsize=1,
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

    @staticmethod
    def usage(log):
        directories = set()
        for match in re.finditer(r'"(?:review_dir|evaluation_dir)":\s*("(?:[^"\\]|\\.)*")', log):
            try:
                path = Path(json.loads(match.group(1))).resolve()
                if any(path.is_relative_to(root.resolve()) for root in (REVIEWS, EVALUATIONS)):
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

    def __init__(self, port=0):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.jobs = Jobs()
        self.url = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body, kind="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = (json.dumps(body, ensure_ascii=False) if kind.startswith("application/json") else body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def permitted(self, api=False):
        if self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
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

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if not self.permitted(path.startswith("/api/")):
            return
        try:
            if path == "/":
                page = dashboard.render(dashboard.collect(ROOT))
                config = json.dumps({"token": self.server.token}).replace("<", "\\u003c")
                extra = '<script id="live-config" type="application/json">' + config + '</script><script src="/controls.js"></script>'
                self.respond(200, page.replace("</body>", extra + "</body>"), "text/html; charset=utf-8")
            elif path == "/controls.js":
                self.respond(200, Path(__file__).with_name("dashboard_controls.js").read_bytes(), "text/javascript; charset=utf-8")
            elif path == "/api/state":
                data = dashboard.collect(ROOT)
                data["live"] = True
                saved = roster.read(dashboard.ROSTER_FILE)
                with self.server.jobs.lock:
                    jobs = [self.server.jobs.public(j) for j in self.server.jobs.jobs.values()]
                self.respond(200, {"data": data, "roster": saved, "jobs": jobs})
            else:
                file = (ROOT / path.lstrip("/")).resolve()
                allowed = any(file.is_relative_to(root.resolve()) for root in (REVIEWS, EVALUATIONS))
                if allowed and file.is_file() and file.suffix in {".md", ".json", ".html"}:
                    self.respond(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "text/plain")
                else:
                    self.respond(404, {"error": "Not found"})
        except (ValueError, OSError, SystemExit) as error:
            self.respond(400, {"error": str(error)})

    def do_POST(self):
        if not self.permitted(api=True):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            path = urlsplit(self.path).path
            if path == "/api/provider-status":
                self.respond(200, provider_status(data))
            elif path == "/api/repos":
                with self.server.jobs.lock:
                    if self.server.jobs.active():
                        raise ValueError("Wait for the running job before changing the roster")
                    entry = roster.add(dashboard.ROSTER_FILE, data.get("repo", ""),
                                       data.get("student", ""), data.get("assignment", ""))
                self.respond(201, entry)
            elif path == "/api/jobs":
                self.respond(202, self.server.jobs.start(data))
            elif path == "/api/stop":
                self.respond(200, self.server.jobs.stop(data.get("id")))
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
        for job in list(server.jobs.jobs.values()):
            server.jobs.stop(job["id"])
        server.server_close()
