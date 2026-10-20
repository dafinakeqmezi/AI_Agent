"""Subscription adapters use official login, no API fallback, and only scoped JSON actions."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grader import cli, runner, state, subscriptions
from grader.common import assignment_files, load_json, write_json


def completed(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch.object(subscriptions.shutil, "which", side_effect=lambda name: "/tools/" + name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def provider(self, name, model=None):
        status = "Logged in using ChatGPT" if name == "chatgpt" else json.dumps({"authMethod": "claude.ai"})
        with patch.object(subscriptions, "execute", return_value=completed(status)):
            return subscriptions.SubscriptionCLI(name, model=model)

    def test_missing_cli_and_api_only_logins_fail(self):
        with patch.object(subscriptions.shutil, "which", return_value=None):
            with self.assertRaisesRegex(runner.RunnerError, "Install claude"):
                subscriptions.SubscriptionCLI("claude-code")
        for name, output in [("chatgpt", "Logged in using an API key"),
                             ("claude-code", '{"authMethod": "api_key"}'),
                             ("claude-code", '{"authMethod": "api_key_helper"}'),
                             ("claude-code", '{"authMethod": "none"}')]:
            with self.subTest(name=name, output=output):
                with patch.object(subscriptions, "execute", return_value=completed(output)):
                    with self.assertRaises(runner.RunnerError):
                        subscriptions.SubscriptionCLI(name)

    def test_child_env_strips_api_credentials_without_changing_parent(self):
        values = {"OPENAI_API_KEY": "secret1", "ANTHROPIC_API_KEY": "secret2",
                  "ANTHROPIC_AUTH_TOKEN": "secret3", "CLAUDE_CODE_USE_BEDROCK": "1",
                  "CLAUDE_CODE_OAUTH_TOKEN": "secret4", "OPENAI_BASE_URL": "https://custom.example",
                  "CODEX_HOME": "/existing/user/config"}
        with patch.dict(os.environ, values):
            env = subscriptions.child_environment()
            for key in values.keys() - {"CODEX_HOME"}:
                self.assertNotIn(key, env)
                self.assertEqual(os.environ[key], values[key])
            self.assertEqual(env["CODEX_HOME"], values["CODEX_HOME"])

    def test_cli_flags_disable_native_tools_and_persistence(self):
        codex = self.provider("chatgpt", "chosen-model").command(self.root)
        self.assertIn("--ignore-user-config", codex)
        self.assertIn('forced_login_method="chatgpt"', codex)
        self.assertIn("--ephemeral", codex)
        self.assertIn("shell_tool", codex)
        self.assertIn("tools.view_image=false", codex)
        self.assertEqual(codex[-1], "-")
        self.assertIn("chosen-model", codex)
        claude = self.provider("claude-code").command(self.root)
        self.assertEqual(claude[claude.index("--tools") + 1], "")
        self.assertIn("--bare", claude)
        self.assertIn("--no-session-persistence", claude)
        self.assertIn("--strict-mcp-config", claude)
        self.assertNotIn("--model", claude)
        for command in (codex, claude):
            self.assertFalse(any("dangerously" in arg for arg in command))
            self.assertNotIn("--resume", command)
            self.assertNotIn("--continue", command)

    def test_codex_action_roundtrip(self):
        provider = self.provider("chatgpt")

        def execute(command, *, cwd, env, timeout, prompt):
            self.assertIn("role_instructions", prompt)
            Path(cwd, "action.json").write_text(json.dumps({"tool": "read_file", "arguments_json": '{"path":"project/README.md"}'}))
            return completed('\n'.join(json.dumps(e) for e in [
                {"type": "thread.started", "thread_id": "thread-test"},
                {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]))

        with patch.object(subscriptions, "execute", side_effect=execute):
            response = provider.respond("Read evidence", [], runner.tools_for("review", 1), 1000)
        self.assertEqual(response["id"], "thread-test")
        self.assertEqual(response["output"][0]["name"], "read_file")
        self.assertEqual(json.loads(response["output"][0]["arguments"])["path"], "project/README.md")

    def test_prompt_decodes_json_packets_without_mutating_history(self):
        source = {"prefetched_files": [{"path": "project/test.py", "text": 'L1: print("hello")\nL2: value = {"x": 1}'}]}
        history = [{"role": "user", "content": json.dumps(source)},
                   {"type": "function_call", "arguments": '{"paths":["project/test.py"]}'},
                   {"type": "function_call_output", "output": '{"files":[{"text":"data"}]}'}]
        before = json.dumps(history)
        compact = subscriptions.compact_history(history)
        self.assertEqual(compact[0]["content"], source)
        self.assertEqual(compact[1]["arguments"], {"paths": ["project/test.py"]})
        self.assertEqual(json.dumps(history), before)
        self.assertLess(len(json.dumps(compact)), len(before))

    def test_phase_reuses_working_directory_but_never_stale_outputs(self):
        provider = self.provider("chatgpt")
        directories = []

        def execute(command, *, cwd, env, timeout, prompt):
            directories.append(cwd)
            self.assertFalse(Path(cwd, "action.json").exists())
            if len(directories) != 2:
                Path(cwd, "action.json").write_text(json.dumps({"tool": "list_files", "arguments_json": "{}"}))
            return completed(json.dumps({"type": "turn.completed"}))

        with patch.object(subscriptions, "execute", side_effect=execute):
            provider.begin_phase()
            first = provider.respond("rules", [], runner.tools_for("review", 1), 1000)
            self.assertTrue(first["transport"]["stable_phase_directory"])
            with self.assertRaises(runner.RunnerError):
                provider.respond("rules", [], runner.tools_for("review", 1), 1000)
            provider.end_phase()
            self.assertFalse(Path(directories[0]).exists())
            provider.begin_phase()
            provider.respond("rules", [], runner.tools_for("review", 1), 1000)
            provider.end_phase()
        self.assertEqual(directories[0], directories[1])
        self.assertNotEqual(directories[0], directories[2])
        self.assertFalse(Path(directories[2]).exists())

    def test_claude_structured_output_and_text_fallback(self):
        provider = self.provider("claude-code")
        action = {"tool": "list_files", "arguments_json": "{}"}
        for body in ({"structured_output": action}, {"result": json.dumps(action)}):
            body.update({"subtype": "success", "is_error": False, "session_id": "session-test"})
            with patch.object(subscriptions, "execute", return_value=completed(json.dumps(body))):
                response = provider.respond("Read evidence", [], runner.tools_for("review", 1), 1000)
            self.assertEqual(response["output"][0]["name"], "list_files")
            self.assertEqual(response["id"], "session-test")

    def test_incomplete_invalid_native_tool_and_process_errors_are_not_success(self):
        for name in ("chatgpt", "claude-code"):
            provider = self.provider(name)
            for result in [completed(code=1), completed("not-json"), completed('{"subtype":"error_max_turns","is_error":true}')]:
                with patch.object(subscriptions, "execute", return_value=result):
                    with self.assertRaises(runner.RunnerError):
                        provider.respond("rules", [], runner.tools_for("review", 1), 1000)
        provider = self.provider("chatgpt")
        for event in [{"type": "turn.failed"},
                      {"type": "item.completed", "item": {"type": "command_execution"}}]:
            stdout = json.dumps(event) + '\n' + json.dumps({"type": "turn.completed"})
            with patch.object(subscriptions, "execute", return_value=completed(stdout)):
                with self.assertRaises(runner.RunnerError):
                    provider.respond("rules", [], runner.tools_for("review", 1), 1000)

    def test_timeout_is_reported_without_sensitive_output(self):
        with patch.object(subscriptions.subprocess, "run", side_effect=subprocess.TimeoutExpired("secret", 1)):
            with self.assertRaisesRegex(runner.RunnerError, "timed out") as caught:
                subscriptions.execute(["cli"], cwd=self.root, env={}, timeout=1)
        self.assertNotIn("secret", str(caught.exception))

    def test_unsupported_subscription_model_has_actionable_error(self):
        provider = self.provider("chatgpt")
        result = completed("The requested model is not supported when using Codex with a ChatGPT account.", code=1)
        with patch.object(subscriptions, "execute", return_value=result):
            with self.assertRaisesRegex(runner.RunnerError, "choose an available model with --model"):
                provider.respond("rules", [], runner.tools_for("review", 1), 1000)

    def test_subscription_model_env_does_not_use_api_model_ids(self):
        from argparse import Namespace
        with patch.dict(os.environ, {"OPENAI_MODEL": "api1", "ANTHROPIC_MODEL": "api2",
                                     "CODEX_MODEL": "plan1", "CLAUDE_CODE_MODEL": "plan2"}):
            self.assertEqual(runner.model_for(Namespace(provider="chatgpt", model=None)), "plan1")
            self.assertEqual(runner.model_for(Namespace(provider="claude-code", model=None)), "plan2")
        with patch.object(subscriptions, "SubscriptionCLI") as constructor:
            runner.create_provider(Namespace(provider="chatgpt", model=None, timeout=30))
            constructor.assert_called_once_with("chatgpt", None, 30)

    def test_complete_review_with_subscription_transport(self):
        project = self.root / "project"
        project.mkdir()
        (project / "README.md").write_text("Student fixture")
        run = self.root / "run"
        write_json(run / "run.json", {"project": "test", "assignment": "detyra1"})
        write_json(run / "artifacts/inventory.json", {"files": [{"path": "README.md"}]})
        reqs = load_json(assignment_files("detyra1")["requirements"])["requirements"]
        doc = {"requirements": [{"requirement_id": r["id"], "status": "MISSING", "finding": "Missing",
                                 "searched": ["README.md"]} for r in reqs],
               "integrity": {"risk_level": "NONE_FOUND", "indicators": [], "disclaimer": "Indicators only."}}
        actions = iter([{"tool": "submit_report", "arguments_json": json.dumps({"document": doc})}])
        provider = self.provider("claude-code")

        def execute(command, *, cwd, env, timeout, prompt):
            self.assertNotEqual(Path(cwd), project)
            self.assertIn("Student fixture", prompt)
            self.assertIn("knowledge-base/policies/agent-rules.md", prompt)
            self.assertEqual(prompt.count("# Shared agent rules"), 1)
            return completed(json.dumps({"subtype": "success", "structured_output": next(actions)}))

        with patch.object(subscriptions, "execute", side_effect=execute), patch.object(state, "STATE_FILE", self.root / "state.json"):
            with contextlib.redirect_stdout(io.StringIO()):
                result = runner.session(provider, run, project, "detyra1", "review", 3, 1000)
        self.assertEqual(result["validation_errors"], [])
        self.assertEqual(load_json(run / "runner.phase1.json")["provider"], "claude-code")
        self.assertEqual(len(load_json(run / "runner.phase1.json")["responses"]), 1)
        self.assertTrue((run / "review.md").exists())
        self.assertIn("Rishikimi i projektit", (run / "review.md").read_text())
        self.assertIsNone(provider._phase_directory)
        self.assertEqual(load_json(run / "runner.phase1.json")["model_calls_attempted"], 1)

    def test_prefetch_is_bounded_and_cannot_include_unmounted_reviews(self):
        project = self.root / "project"
        project.mkdir()
        (project / "README.md").write_text("Student evidence")
        outside = self.root / "review.json"
        outside.write_text("Private Agent 1 conclusion")
        (project / "linked.txt").symlink_to(outside)
        files = runner.Files()
        files.mount("project", project)
        packet, size = runner.prefetch(files, "detyra1", budget=500)
        self.assertLessEqual(size, 500)
        self.assertIn("Student evidence", json.dumps(packet))
        self.assertNotIn("Private Agent 1", json.dumps(packet))
        self.assertNotIn("project/linked.txt", files.reads)
        self.assertEqual(files.reads, {entry["path"] for entry in packet})

    def test_batched_reads_keep_scope_and_report_each_error(self):
        (self.root / "one.md").write_text("First file")
        (self.root / "two.md").write_text("Second file")
        files = runner.Files()
        files.mount("project", self.root)
        result = files.call("read_files", {"paths": ["project/one.md", "project/two.md", "../secret"]})
        self.assertIn("First file", result["files"][0]["text"])
        self.assertIn("Second file", result["files"][1]["text"])
        self.assertIn("error", result["files"][2])
        with self.assertRaises(ValueError):
            files.call("read_files", {"paths": ["project/one.md"] * 5})

    def test_both_cli_providers_dry_run_without_install_or_login(self):
        path = self.root / "roster.json"
        write_json(path, {"assignment": "detyra1", "students": [{"repo": "owner/repo"}]})
        for name in ("chatgpt", "claude-code"):
            with patch.object(subscriptions.shutil, "which", return_value=None):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    status = cli.main(["review-all", "--provider", name, "--roster", str(path), "--dry-run"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["provider"], name)

    def test_subscription_call_budget_is_lower_and_explicit_override_works(self):
        for provider, override, expected in (("chatgpt", [], 8), ("claude-code", [], 8),
                                              ("openai", [], 60), ("chatgpt", ["--max-turns", "3"], 3)):
            with patch.object(runner, "run_reviews", return_value={}) as reviews:
                with contextlib.redirect_stdout(io.StringIO()):
                    cli.main(["review-all", "--provider", provider, "--dry-run", *override])
            self.assertEqual(reviews.call_args.args[0].max_turns, expected)
