"""Local controls: explicit scope, safe command arguments, job cancellation and API access."""
import contextlib
import http.client
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from grader import cli, dashboard, dashboard_server as live, runner, dashboard_auth
from grader.common import write_json


class DashboardJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roster = self.root / "projects/roster.json"
        write_json(self.roster, {"assignment": "detyra1", "students": [
            {"repo": "owner/one", "student": "One", "assignment": "detyra1"},
            {"repo": "owner/two", "student": "Two", "assignment": "detyra1"}]})
        for module, name, value in [(live, "ROOT", self.root), (dashboard, "ROSTER_FILE", self.roster),
                                    (live, "SUBMISSIONS", self.root / "submissions"),
                                    (live, "REVIEWS", self.root / "reviews"),
                                    (live, "EVALUATIONS", self.root / "evaluations")]:
            p = patch.object(module, name, value)
            p.start(); self.addCleanup(p.stop)
        self.jobs = live.Jobs()
        self.directory = self.root / "job"

    def test_review_command_uses_only_selected_saved_repos(self):
        commands = self.jobs.commands({"action": "review", "repos": ["owner/one"],
                                       "provider": "chatgpt", "model": "gpt-6.1-sol"}, self.directory)
        command = commands[0]
        self.assertEqual(command[:4], [sys.executable, "-u", "-m", "grader"])
        self.assertIn("review-all", command)
        self.assertIn("gpt-6.1-sol", command)
        saved = json.loads((self.directory / "roster.json").read_text())
        self.assertEqual([s["repo"] for s in saved["students"]], ["owner/one"])
        self.assertEqual(command[command.index("--max-turns") + 1], "3")
        self.assertEqual(saved["students"][0]["ref"], "main")

    def test_saved_branch_reaches_review_and_freeze(self):
        write_json(self.roster, {"students": [{"repo": "owner/one", "student": "One",
                   "assignment": "detyra1", "ref": "feature/grading"}]})
        command = self.jobs.commands({"action": "freeze", "repos": ["owner/one"]}, self.directory)[0]
        self.assertEqual(command[command.index("--ref") + 1], "feature/grading")
        self.jobs.commands({"action": "review", "repos": ["owner/one"], "provider": "chatgpt"}, self.directory)
        saved = json.loads((self.directory / "roster.json").read_text())
        self.assertEqual(saved["students"][0]["ref"], "feature/grading")

    def test_invalid_or_empty_scope_and_command_injection_are_rejected(self):
        base = {"action": "review", "repos": ["owner/one"], "provider": "chatgpt"}
        for override in ({"repos": []}, {"repos": ["owner/foreign"]}, {"model": "x; rm -rf /"},
                         {"provider": "shell"}, {"max_turns": 0}, {"timeout": True}, {"action": "bash"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.jobs.commands({**base, **override}, self.directory)

    def test_freeze_scope_names_and_deadline_are_explicit(self):
        commands = self.jobs.commands({"action": "freeze", "repos": ["owner/two"],
                                       "deadline": "2026-11-01T23:59:00+01:00"}, self.directory)
        self.assertEqual(len(commands), 1)
        self.assertIn("Two", commands[0])
        self.assertIn("--deadline", commands[0])
        self.assertEqual(commands[0][commands[0].index("--ref") + 1], "main")
        with self.assertRaises(SystemExit):
            self.jobs.commands({"action": "freeze", "repos": ["owner/one"], "deadline": "2026-11-01T23:59:00"}, self.directory)

    def test_grade_and_comparison_require_known_frozen_ids(self):
        for sid in ("one", "two"):
            write_json(live.SUBMISSIONS / sid / "submission.json", {"assignment": "detyra1"})
        command = self.jobs.commands({"action": "similarity", "submissions": ["one", "two"]}, self.directory)[0]
        self.assertIn("one,two", command)
        self.assertNotIn("--provider", command)
        for ids in (["one"], ["../secret"], ["unknown"]):
            with self.assertRaises(ValueError):
                self.jobs.commands({"action": "similarity", "submissions": ids}, self.directory)
        write_json(live.SUBMISSIONS / "two" / "submission.json", {"assignment": "ml-project"})
        with self.assertRaisesRegex(ValueError, "same assignment"):
            self.jobs.commands({"action": "similarity", "submissions": ["one", "two"]}, self.directory)

    def wait_for(self, job_id, states, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.jobs.lock:
                job = self.jobs.jobs[job_id]
                if job["status"] in states:
                    return job
            time.sleep(.01)
        self.fail("Job did not reach expected state")

    def test_real_local_process_logs_output_and_completes(self):
        with patch.object(self.jobs, "commands", return_value=[[sys.executable, "-u", "-c", "print('local fixture')"]]):
            job = self.jobs.start({"action": "grade", "repos": ["unrelated"], "submissions": ["one"]})
        result = self.wait_for(job["id"], {"completed", "failed"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["scope"], ["one"])
        self.assertIn("local fixture", result["log"])
        self.assertNotIn("process", self.jobs.public(result))
        self.assertTrue((self.root / "state/dashboard-jobs" / job["id"] / "job.json").exists())

    def test_stop_cancels_running_process_and_blocks_overlapping_jobs(self):
        commands = [[sys.executable, "-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"]]
        with patch.object(self.jobs, "commands", return_value=commands):
            job = self.jobs.start({"action": "review", "repos": ["owner/one"]})
            self.addCleanup(lambda: self.jobs.stop(job["id"]))
            with self.assertRaisesRegex(ValueError, "already running"):
                self.jobs.start({"action": "review", "repos": ["owner/two"]})
            deadline = time.monotonic() + 3
            while not self.jobs.jobs[job["id"]]["process"] and time.monotonic() < deadline:
                time.sleep(.01)
            self.jobs.stop(job["id"])
            result = self.wait_for(job["id"], {"cancelled"})
        self.assertIsNone(result["process"])

    def test_usage_reads_only_runner_directories(self):
        run = live.REVIEWS / "project/run"
        write_json(run / "runner.phase1.json", {"model_calls_attempted": 2,
                   "responses": [{"usage": {"input_tokens": 100, "output_tokens": 20}}]})
        summary = self.jobs.usage(json.dumps({"review_dir": str(run)}))
        self.assertEqual(summary, {"input_tokens": 100, "output_tokens": 20, "calls": 2})
        self.assertIsNone(self.jobs.usage(json.dumps({"review_dir": str(self.root)})))


class DashboardProviderTests(unittest.TestCase):
    def test_missing_cli_returns_setup_instructions_without_inference(self):
        with patch("grader.subscriptions.shutil.which", return_value=None):
            result = live.provider_status({"provider": "claude-code"})
        self.assertFalse(result["ready"])
        self.assertIn("Install claude CLI", result["message"])

    def test_auth_error_is_visible_and_success_does_not_call_model(self):
        with patch.object(runner, "create_provider", side_effect=runner.RunnerError("Run: claude auth login")):
            result = live.provider_status({"provider": "claude-code"})
        self.assertFalse(result["ready"])
        self.assertIn("claude auth login", result["message"])
        with patch.object(runner, "create_provider") as create:
            result = live.provider_status({"provider": "chatgpt", "model": "chosen-model"})
        self.assertTrue(result["ready"])
        self.assertEqual(create.call_args.args[0].model, "chosen-model")
        create.return_value.respond.assert_not_called()

    def test_api_status_checks_configuration_without_network_or_key_disclosure(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "ANTHROPIC_MODEL": ""}):
            self.assertFalse(live.provider_status({"provider": "claude"})["ready"])
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "private-fixture", "ANTHROPIC_MODEL": "fixture-model"}), \
                patch("urllib.request.urlopen") as network:
            result = live.provider_status({"provider": "claude"})
        self.assertTrue(result["ready"])
        self.assertNotIn("private-fixture", json.dumps(result))
        network.assert_not_called()
        with self.assertRaises(ValueError):
            live.provider_status({"provider": "shell"})


class DashboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.roster = Path(self.temp.name) / "roster.json"
        for p in (patch.object(dashboard, "ROSTER_FILE", self.roster),
                  patch.object(dashboard, "collect", return_value={"projects": [], "assignments": {}})):
            p.start(); self.addCleanup(p.stop)
        accounts = Path(self.temp.name) / "professors.json"
        dashboard_auth.set_password("professor", "fixture-password-123", accounts)
        auth = dashboard_auth.Auth(accounts)
        self.cookie = "professor_session=" + auth.login("professor", "fixture-password-123")
        self.server = live.Server(auth=auth, data_dir=Path(self.temp.name) / "tenants")
        self.jobs = self.server.workspace("professor")
        self.roster = self.jobs.roster_file
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, data=None, token=True, extra=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Content-Type": "application/json", "Cookie": self.cookie}
        if token: headers["X-Dashboard-Token"] = self.server.token
        headers.update(extra or {})
        connection.request(method, path, body=json.dumps(data) if data is not None else None, headers=headers)
        response = connection.getresponse()
        content = response.read()
        status = response.status
        connection.close()
        return status, content

    def test_all_data_routes_require_login_even_with_csrf_token(self):
        for path in ("/", "/professors/new", "/controls.js", "/reviews/project/report.md", "/api/state"):
            status, body = self.request("GET", path, extra={"Cookie": ""})
            self.assertEqual(status, 401 if path.startswith("/api/") else 303)
            self.assertNotIn(b"live-config", body)
        with patch.object(self.jobs, "start") as start:
            self.assertEqual(self.request("POST", "/api/jobs", {}, extra={"Cookie": ""})[0], 401)
            start.assert_not_called()
        self.assertEqual(self.request("GET", "/login", extra={"Cookie": ""})[0], 200)

    def test_login_form_cookie_and_logout(self):
        from urllib.parse import urlencode
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        form = {"username": "professor", "password": "fixture-password-123", "csrf": self.server.token}
        connection.request("POST", "/login", urlencode(form), {"Content-Type": "application/x-www-form-urlencoded"})
        response = connection.getresponse()
        self.assertEqual(response.status, 303)
        cookie = response.getheader("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        response.read(); connection.close()
        self.cookie = cookie.split(";", 1)[0]
        self.assertEqual(self.request("GET", "/api/state")[0], 200)
        self.assertEqual(self.request("POST", "/api/logout", {})[0], 200)
        self.assertEqual(self.request("GET", "/api/state")[0], 401)

    def test_invalid_login_and_forged_login_form(self):
        from urllib.parse import urlencode
        for csrf, password, status in [("wrong", "fixture-password-123", 403),
                                       (self.server.token, "wrong", 401)]:
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
            connection.request("POST", "/login", urlencode({"username": "professor", "password": password, "csrf": csrf}))
            response = connection.getresponse()
            self.assertEqual(response.status, status)
            self.assertIsNone(response.getheader("Set-Cookie"))
            response.read(); connection.close()

    def test_first_account_setup_in_browser_closes_after_creation(self):
        from urllib.parse import urlencode
        path = Path(self.temp.name) / "fresh-professors.json"
        self.server.auth = dashboard_auth.Auth(path)
        self.assertEqual(self.request("GET", "/", extra={"Cookie": ""})[0], 303)
        status, body = self.request("GET", "/setup", extra={"Cookie": ""})
        self.assertEqual(status, 200)
        self.assertIn(b"Confirm password", body)
        self.assertEqual(self.request("GET", "/api/state", extra={"Cookie": ""})[0], 401)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        form = {"username": "first", "password": "fixture-password-123", "confirmation": "fixture-password-123",
                "csrf": self.server.token}
        connection.request("POST", "/setup", urlencode(form))
        response = connection.getresponse()
        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/login")
        response.read(); connection.close()
        self.assertFalse(self.server.auth.needs_setup())
        self.assertEqual(self.request("GET", "/setup")[0], 303)
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            self.server.auth.create_account("intruder", "fixture-password-123", "fixture-password-123", first=True)
        self.assertEqual(path.read_bytes(), before)

    def test_only_signed_in_professors_can_add_accounts(self):
        data = {"username": "second", "password": "second-password-123", "confirmation": "second-password-123"}
        self.assertEqual(self.request("POST", "/api/professors", data, extra={"Cookie": ""})[0], 401)
        self.assertEqual(self.request("POST", "/api/professors", data, token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/professors", {**data, "confirmation": "wrong"})[0], 400)
        self.assertEqual(self.request("POST", "/api/professors", data)[0], 201)
        self.assertTrue(self.server.auth.login("second", "second-password-123"))
        self.assertEqual(self.request("POST", "/api/professors", data)[0], 400)

    def second_professor(self):
        dashboard_auth.set_password("second", "second-password-123", self.server.auth.path)
        token = self.server.auth.login("second", "second-password-123")
        return "professor_session=" + token

    def test_professors_have_separate_rosters_results_jobs_and_downloads(self):
        data = {"repo": "owner/private", "student": "Private Student", "assignment": "detyra1"}
        self.assertEqual(self.request("POST", "/api/repos", data)[0], 201)
        write_json(self.jobs.root / "state/registry.json", {"projects": {"private-project": {"state": "DRAFT"}}})
        report = self.jobs.reviews / "private-project/run/review.md"
        report.parent.mkdir(parents=True)
        report.write_text("PRIVATE PROFESSOR REPORT")
        write_json(self.jobs.submissions / "private-id/submission.json", {"student": "Private Student", "assignment": "detyra1"})
        self.jobs.jobs["private-job"] = {"id": "private-job", "status": "running", "log": "PRIVATE JOB"}
        status, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertIn(b"Private Student", body)
        self.assertEqual(self.request("GET", "/reviews/private-project/run/review.md")[1], b"PRIVATE PROFESSOR REPORT")
        original_cookie = self.cookie
        self.cookie = self.second_professor()
        status, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertEqual(state["roster"]["students"], [])
        self.assertEqual(state["data"]["projects"], [])
        self.assertEqual(state["jobs"], [])
        self.assertEqual(self.request("GET", "/reviews/private-project/run/review.md")[0], 404)
        self.assertEqual(self.request("POST", "/api/jobs", {"action": "review", "repos": ["owner/private"], "provider": "chatgpt"})[0], 400)
        self.assertEqual(self.request("POST", "/api/jobs", {"action": "grade", "submissions": ["private-id"], "provider": "chatgpt"})[0], 400)
        self.assertEqual(self.request("POST", "/api/stop", {"id": "private-job"})[0], 400)
        other = self.server.workspace("second")
        target = other.reviews / "leak.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(report)
        self.assertEqual(self.request("GET", "/reviews/leak.md")[0], 404)
        relative = "/../" + self.jobs.root.name + "/reviews/private-project/run/review.md"
        self.assertEqual(self.request("GET", relative)[0], 404)
        self.assertEqual(self.request("POST", "/api/repos", data)[0], 201)
        self.assertNotEqual(other.root, self.jobs.root)
        self.cookie = original_cookie
        self.assertEqual(self.request("GET", "/api/state")[0], 200)
        self.assertEqual(self.jobs.jobs["private-job"]["status"], "running")

    def test_worker_subprocess_uses_professor_data_root(self):
        code = ("from grader import state, github, common; "
                "assert github.MIRRORS == common.DATA_ROOT / 'projects'; "
                "assert common.REVIEWS == common.DATA_ROOT / 'reviews'; "
                "assert common.SUBMISSIONS == common.DATA_ROOT / 'submissions'; "
                "assert common.EVALUATIONS == common.DATA_ROOT / 'evaluations'; "
                "state.set_state('worker-private', 'DRAFT')")
        with patch.object(self.jobs, "commands", return_value=[[sys.executable, "-c", code]]):
            status, body = self.request("POST", "/api/jobs", {"action": "review", "repos": ["fixture"]})
        self.assertEqual(status, 202)
        job_id = json.loads(body)["id"]
        end = time.monotonic() + 5
        while time.monotonic() < end and self.jobs.jobs[job_id]["status"] in {"queued", "running"}:
            time.sleep(.01)
        self.assertEqual(self.jobs.jobs[job_id]["status"], "completed")
        self.assertTrue((self.jobs.root / "state/registry.json").exists())
        self.assertIn(b"worker-private", self.request("GET", "/api/state")[1])
        self.cookie = self.second_professor()
        self.assertNotIn(b"worker-private", self.request("GET", "/api/state")[1])

    def test_hosted_origin_requires_https_existing_account_and_secure_cookie(self):
        with patch.dict("os.environ", {"GRADER_PUBLIC_URL": "http://grader.example.edu"}):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                live.Server(auth=self.server.auth)
        fresh = dashboard_auth.Auth(Path(self.temp.name) / "unconfigured.json")
        with patch.dict("os.environ", {"GRADER_PUBLIC_URL": "https://grader.example.edu"}):
            with self.assertRaisesRegex(ValueError, "first professor"):
                live.Server(auth=fresh)
            hosted = live.Server(auth=self.server.auth, data_dir=Path(self.temp.name) / "hosted")
        threading.Thread(target=hosted.serve_forever, daemon=True).start()
        self.addCleanup(hosted.server_close)
        self.addCleanup(hosted.shutdown)
        self.server = hosted
        headers = {"Host": "grader.example.edu", "Origin": "https://grader.example.edu"}
        self.assertEqual(self.request("GET", "/api/state", extra=headers)[0], 200)
        self.assertEqual(self.request("GET", "/api/state")[0], 403)
        self.assertEqual(self.request("GET", "/api/state", extra={**headers, "Origin": "https://foreign.example"})[0], 403)
        from urllib.parse import urlencode
        connection = http.client.HTTPConnection("127.0.0.1", hosted.server_port)
        connection.request("POST", "/login", urlencode({"username": "professor", "password": "fixture-password-123",
                           "csrf": hosted.token}), headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 303)
        self.assertIn("; Secure", response.getheader("Set-Cookie"))
        response.read(); connection.close()

    def test_state_requires_token_and_rejects_foreign_origins_and_hosts(self):
        self.assertEqual(self.request("GET", "/api/state", token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/state", extra={"Origin": "https://foreign.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", extra={"Host": "foreign.example"})[0], 403)
        status, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["data"]["live"])

    def test_add_repo_and_duplicate_preservation(self):
        entry = {"repo": "owner/new", "student": "Name", "assignment": "detyra1"}
        self.assertEqual(self.request("POST", "/api/repos", entry, token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/repos", entry)[0], 201)
        before = self.roster.read_bytes()
        self.assertEqual(self.request("POST", "/api/repos", entry)[0], 400)
        self.assertEqual(self.roster.read_bytes(), before)

    def test_live_page_loads_controls_but_static_export_stays_read_only(self):
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'live-config', body)
        self.assertIn(b'/controls.js', body)
        self.assertNotIn("live-config", dashboard.render({}))
        self.assertEqual(self.request("GET", "/controls.js")[0], 200)
        self.assertEqual(self.request("GET", "/professors/new")[0], 200)
        self.assertEqual(self.request("GET", "/../grader/cli.py")[0], 404)

    def test_start_and_stop_use_fixed_job_api(self):
        with patch.object(self.jobs, "start", return_value={"id": "test", "status": "queued"}) as start:
            self.assertEqual(self.request("POST", "/api/jobs", {"action": "review"})[0], 202)
            start.assert_called_once_with({"action": "review"})
        self.assertEqual(self.request("POST", "/api/stop", {"id": "unknown"})[0], 400)

    def test_provider_check_requires_token_and_returns_setup_state(self):
        self.assertEqual(self.request("POST", "/api/provider-status", {"provider": "claude-code"}, token=False)[0], 403)
        with patch.object(live, "provider_status", return_value={"ready": False, "message": "Sign in first"}):
            status, body = self.request("POST", "/api/provider-status", {"provider": "claude-code"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ready": False, "message": "Sign in first"})

    def test_cli_selects_live_server_only_with_serve_flag(self):
        with patch.object(live, "serve") as serve, contextlib.redirect_stdout(io.StringIO()):
            cli.main(["dashboard", "--serve", "--no-open", "--port", "8800"])
        serve.assert_called_once_with(8800, open_browser=False)
