"""Per-professor subscription sign-ins: separate CLI homes, the CLI's own login flow, no shared accounts."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grader import cli_logins, dashboard_server as live, subscriptions

# Stand-ins for `claude auth login` / `codex login --device-auth`: print what the real CLIs print.
FAKE_CLAUDE = ("import sys; print('Opening browser to sign in'); "
               "print('If the browser did not open, visit: https://claude.com/cai/oauth/authorize?code=true&state=x'); "
               "print('Paste code here if prompted > ', end='', flush=True); "
               "code = sys.stdin.readline().strip(); print(); sys.exit(0 if code == 'abc123#def456' else 1)")
FAKE_CODEX = ("import time; print('1. Open this link in your browser\\n   \\x1b[94mhttps://auth.openai.com/codex/device\\x1b[0m'); "
              "print('2. Enter this one-time code\\n   \\x1b[94mO0MH-8W0WJ\\x1b[0m', flush=True); time.sleep(30)")


def completed(stdout, code=0):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="")


class CliLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fake(self, logins, script):
        return patch.object(logins, "command", return_value=[sys.executable, "-c", script])

    def test_each_workspace_has_its_own_cli_homes(self):
        a, b = live.Jobs(self.root / "a"), live.Jobs(self.root / "b")
        for key in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
            self.assertNotEqual(a.env[key], b.env[key])
            self.assertTrue(Path(a.env[key]).is_dir())
            self.assertTrue(Path(a.env[key]).is_relative_to(self.root / "a"))
        self.assertIsNone(live.Jobs().logins)  # the legacy workspace never touches the operator's sign-in

    def test_subscription_checks_and_runs_use_the_workspace_homes(self):
        jobs = live.Jobs(self.root / "a")
        with patch("grader.subscriptions.shutil.which", return_value="claude"), \
                patch.object(subscriptions, "execute", return_value=completed('{"authMethod": "claude.ai"}')) as run:
            result = live.provider_status({"provider": "claude-code"}, jobs.env)
        self.assertTrue(result["ready"])
        self.assertEqual(run.call_args.kwargs["env"]["CLAUDE_CONFIG_DIR"], jobs.env["CLAUDE_CONFIG_DIR"])
        with patch("grader.subscriptions.shutil.which", return_value="claude"), \
                patch.object(subscriptions, "execute", return_value=completed('{"authMethod": "none"}')):
            result = live.provider_status({"provider": "claude-code"}, jobs.env)
        self.assertFalse(result["ready"])
        self.assertIn("Subscriptions", result["message"])

    def test_child_env_keeps_homes_and_strips_api_keys(self):
        env = subscriptions.child_environment({"CLAUDE_CONFIG_DIR": "/p/claude", "CODEX_HOME": "/p/codex",
                                               "ANTHROPIC_API_KEY": "secret", "OPENAI_API_KEY": "secret"})
        self.assertEqual(env, {"CLAUDE_CONFIG_DIR": "/p/claude", "CODEX_HOME": "/p/codex"})

    def test_only_vendor_sign_in_links_are_shown(self):
        self.assertEqual(cli_logins.login_url("visit: https://claude.com/cai/oauth/authorize?x=1", "claude"),
                         "https://claude.com/cai/oauth/authorize?x=1")
        self.assertEqual(cli_logins.login_url("open https://auth.openai.com/codex/device", "codex"),
                         "https://auth.openai.com/codex/device")
        for text in ("https://evil.example/oauth/authorize", "https://claude.com.evil.example/oauth", "http://claude.com/oauth"):
            self.assertIsNone(cli_logins.login_url(text, "claude"))

    def test_claude_sign_in_shows_link_and_accepts_the_pasted_code(self):
        logins = live.Jobs(self.root / "a").logins
        self.addCleanup(logins.close)
        with self.fake(logins, FAKE_CLAUDE):
            view = logins.start("claude")
        self.assertEqual(view["state"], "waiting")
        self.assertTrue(view["url"].startswith("https://claude.com/cai/oauth/authorize"))
        for bad in ("", "abc\nrm -rf /", "a b c d e f g h", "x" * 600):
            with self.assertRaises(ValueError):
                logins.submit_code("claude", bad)
        self.assertEqual(logins.submit_code("claude", " abc123#def456 ")["state"], "done")

    def test_codex_device_code_is_shown_and_cancel_stops_the_process(self):
        logins = live.Jobs(self.root / "a").logins
        self.addCleanup(logins.close)
        with self.fake(logins, FAKE_CODEX):
            view = logins.start("codex")
        self.assertEqual((view["state"], view["url"], view["code"]),
                         ("waiting", "https://auth.openai.com/codex/device", "O0MH-8W0WJ"))
        process = logins.active["codex"]["process"]
        self.assertEqual(logins.cancel("codex")["state"], "idle")
        self.assertIsNotNone(process.wait(timeout=10))
        with self.assertRaises(ValueError):
            logins.start("bash")

    def test_failed_sign_in_reports_the_last_line(self):
        logins = live.Jobs(self.root / "a").logins
        self.addCleanup(logins.close)
        with self.fake(logins, "import sys; print('Login failed: denied'); sys.exit(2)"):
            logins.start("codex", wait=0)
        logins.active["codex"]["process"].wait(timeout=10)
        for _ in range(50):
            if logins.view("codex")["message"]:
                break
            import time; time.sleep(0.1)
        self.assertEqual(logins.view("codex"), {"state": "failed", "url": None, "code": None,
                                                "message": "Login failed: denied"})


class CliLoginHTTPTests(unittest.TestCase):
    def setUp(self):
        from grader import dashboard, dashboard_auth
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = patch.object(dashboard, "collect", return_value={"projects": [], "assignments": {}})
        p.start(); self.addCleanup(p.stop)
        accounts = Path(self.temp.name) / "professors.json"
        dashboard_auth.set_password("professor", "fixture-password-123", accounts)
        dashboard_auth.set_password("second", "second-password-123", accounts)
        self.auth = dashboard_auth.Auth(accounts)
        self.server = live.Server(auth=self.auth, data_dir=Path(self.temp.name) / "tenants")
        import threading
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, user, password, method, path, data=None):
        import http.client
        cookie = "professor_session=" + self.auth.login(user, password)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, body=json.dumps(data) if data is not None else None,
                           headers={"Content-Type": "application/json", "Cookie": cookie,
                                    "X-Dashboard-Token": self.server.token})
        response = connection.getresponse()
        body = json.loads(response.read() or b"{}")
        connection.close()
        return response.status, body

    def test_sign_in_belongs_to_the_professor_who_started_it(self):
        first = self.server.workspace("professor").logins
        self.addCleanup(first.close)
        with patch.object(first, "command", return_value=[sys.executable, "-c", FAKE_CODEX]):
            status, view = self.request("professor", "fixture-password-123", "POST", "/api/subscriptions/login", {"tool": "codex"})
        self.assertEqual((status, view["code"]), (200, "O0MH-8W0WJ"))
        status, other = self.request("second", "second-password-123", "GET", "/api/subscriptions?check=0")
        self.assertEqual(status, 200)
        self.assertEqual(other["codex"]["login"]["state"], "idle")
        self.assertNotIn("O0MH-8W0WJ", json.dumps(other))
        status, mine = self.request("professor", "fixture-password-123", "GET", "/api/subscriptions?check=0")
        self.assertEqual(mine["codex"]["login"]["code"], "O0MH-8W0WJ")
        self.assertEqual(self.request("professor", "fixture-password-123", "POST", "/api/subscriptions/login", {"tool": "sh"})[0], 400)
        self.assertEqual(self.request("professor", "fixture-password-123", "POST", "/api/subscriptions/run", {"tool": "codex"})[0], 404)


if __name__ == "__main__":
    unittest.main()
