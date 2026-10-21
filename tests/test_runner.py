"""Automated runner: offline API simulation, validation repair, isolation and failure handling."""
import copy
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from grader import cli, common, freeze, runner, score, state
from grader.common import assignment_files, load_json, write_json


def call(name, **arguments):
    return {"type": "function_call", "call_id": "call-test", "name": name,
            "arguments": json.dumps(arguments)}


class FakeProvider:
    model = "test-model"

    def __init__(self, steps):
        self.steps = iter(steps)
        self.requests = []

    def respond(self, instructions, messages, tools, max_output_tokens):
        self.requests.append(copy.deepcopy(messages))
        return {"status": "completed", "model": self.model, "output": next(self.steps), "usage": {"total_tokens": 10}}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "README.md").write_text("# Student project\n")
        self.run = self.root / "run"
        write_json(self.run / "run.json", {"project": "student", "assignment": "detyra1"})
        write_json(self.run / "artifacts/inventory.json", {"files": [{"path": "README.md"}]})
        for module, name, value in [(state, "STATE_FILE", self.root / "state.json"),
                                    (freeze, "SUBMISSIONS", self.root / "submissions"),
                                    (runner, "SUBMISSIONS", self.root / "submissions"),
                                    (score, "SUBMISSIONS", self.root / "submissions"),
                                    (common, "SUBMISSIONS", self.root / "submissions"),
                                    (cli, "SUBMISSIONS", self.root / "submissions"),
                                    (cli, "EVALUATIONS", self.root / "evaluations"),
                                    (runner, "REVIEWS", self.root / "reviews")]:
            p = patch.object(module, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.make_writable)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def make_writable(self):
        for path in self.root.rglob("*"):
            if path.is_file():
                path.chmod(0o600)

    def review(self):
        requirements = load_json(assignment_files("detyra1")["requirements"])["requirements"]
        return {"requirements": [{"requirement_id": r["id"], "status": "MISSING",
                                   "finding": "Not found in this test fixture.", "searched": ["README.md"]}
                                  for r in requirements],
                "integrity": {"risk_level": "NONE_FOUND", "indicators": [], "disclaimer": "Risk indicators only."}}

    def test_review_repairs_invalid_submission_and_reports_not_ready_as_success(self):
        good = self.review()
        bad = copy.deepcopy(good)
        bad["requirements"].pop()
        provider = FakeProvider([[call("read_file", path="project/README.md")],
                                 [call("submit_report", document=bad, report_md="# Review")],
                                 [call("submit_report", document=good, report_md="# Review")]])
        result = runner.session(provider, self.run, self.project, "detyra1", "review", 4, 1000)
        self.assertEqual(result["validation_errors"], [])
        self.assertEqual(result["verdict"], "NOT_READY")
        audit = load_json(self.run / "runner.phase1.json")
        self.assertTrue(audit["completed"])
        self.assertEqual(len(audit["responses"]), 3)
        self.assertIn("validation_errors", provider.requests[2][-1]["output"])
        self.assertIn("not executed", (self.run / "review.md").read_text())
        self.assertFalse(load_json(self.run / "review.json")["meta"]["code_executed"])

    def test_no_reads_cannot_produce_success(self):
        provider = FakeProvider([[call("submit_report", document=self.review(), report_md="# Review")]])
        with self.assertRaisesRegex(runner.RunnerError, "step limit"):
            runner.session(provider, self.run, self.project, "detyra1", "review", 1, 1000)
        self.assertFalse(load_json(self.run / "runner.phase1.json")["completed"])
        self.assertFalse((self.run / "review.json").exists())

    def test_scoped_files_block_traversal_symlinks_and_allow_pagination(self):
        secret = self.root / "secret.txt"
        secret.write_text("not mounted")
        (self.project / "link.txt").symlink_to(secret)
        files = runner.Files()
        files.mount("project", self.project)
        self.assertNotIn("project/link.txt", files.paths)
        with self.assertRaises(ValueError):
            files.call("read_file", {"path": "project/../secret.txt"})
        (self.project / "README.md").write_text("one\ntwo\nthree\n")
        data = files.call("read_file", {"path": "project/README.md", "start_line": 2, "lines": 1})
        self.assertEqual(data["text"], "L2: two")
        self.assertEqual(data["next_line"], 3)
        # A file replaced with an external symlink after mounting is rejected too.
        (self.project / "README.md").unlink()
        (self.project / "README.md").symlink_to(secret)
        with self.assertRaises(ValueError):
            files.call("read_file", {"path": "project/README.md"})

    def test_unread_file_evidence_is_rejected(self):
        files = runner.Files()
        files.reads.add("project/README.md")
        with self.assertRaisesRegex(ValueError, "not been read"):
            runner.check_inspection({"evidence": [{"file": "src/fake.py"}]}, files)

    def test_complete_json_read_avoids_pagination_and_retains_source_locations(self):
        value = {"results": list(range(1500)), "note": "Të dhëna: {not instructions}"}
        path = self.project / "results.json"
        write_json(path, value)
        files = runner.Files()
        files.mount("project", self.project)
        result = files.call("read_file", {"path": "project/results.json"})
        self.assertEqual(result["content"], value)
        self.assertIsNone(result["next_line"])
        self.assertEqual(result["format"], "complete_json")
        self.assertTrue(result["source_locations"]['$["results"]'].startswith("L2-"))
        self.assertIn("project/results.json", files.reads)
        # Explicit line requests still provide exact original lines.
        page = files.call("read_file", {"path": "project/results.json", "start_line": 2, "lines": 1})
        self.assertIn('L2:   "results": [', page["text"])
        self.assertIsNotNone(page["next_line"])
        self.assertLess(len(json.dumps(result)), len(path.read_text()))

    def test_json_compaction_rejects_invalid_or_oversized_data(self):
        self.assertIsNone(runner.compact_json_file("project/a.json", b'{"bad":'))
        self.assertIsNone(runner.compact_json_file("project/a.json", b'{"x":"' + b'x' * 65000 + b'"}'))
        self.assertIsNone(runner.compact_json_file("project/a.txt", b'{}'))
        self.assertEqual(runner.compact_json_file("project/a.json", b'{}')["content"], {})

    def test_phase2_corrections_preserve_untouched_requirements_and_reject_unknown_ids(self):
        baseline = {"assessments": [{"requirement_id": "A", "status": "PASS", "evidence": [{"file": "a.py"}]},
                                    {"requirement_id": "B", "status": "MISSING"}], "justification": "Initial"}
        original = copy.deepcopy(baseline)
        unchanged = runner.phase2_document({"assessment_updates": []}, copy.deepcopy(baseline))
        self.assertEqual(unchanged, original)
        correction = {"requirement_id": "B", "status": "PARTIAL", "credit": .5, "deduction_reason": "Verified gap"}
        changed = runner.phase2_document({"assessment_updates": [correction], "justification": "Rechecked"}, baseline)
        self.assertEqual(changed["assessments"][0], original["assessments"][0])
        self.assertEqual(changed["assessments"][1], correction)
        self.assertEqual(changed["justification"], "Rechecked")
        for updates in ([{"requirement_id": "UNKNOWN"}], [correction, correction], None):
            with self.assertRaises(ValueError):
                runner.phase2_document({"assessment_updates": updates}, copy.deepcopy(original))

    def test_dry_run_and_missing_key_do_not_fetch_repositories(self):
        path = self.root / "roster.json"
        write_json(path, {"students": [{"repo": "owner/repo", "assignment": "detyra1"}]})
        args = Namespace(roster=str(path), assignment=None, dry_run=True, provider="openai", model=None)
        with patch.object(cli, "cmd_new_review") as prepare:
            result = runner.run_reviews(args)
            self.assertTrue(result["dry_run"])
            args.dry_run, args.timeout = False, 10
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                with self.assertRaisesRegex(runner.RunnerError, "OPENAI_API_KEY"):
                    runner.run_reviews(args)
            prepare.assert_not_called()

    def test_empty_missing_assignment_and_duplicate_rosters_fail_preflight(self):
        path = self.root / "roster.json"
        for students in ([], [{"repo": "owner/repo"}],
                         [{"repo": "owner/repo", "assignment": "detyra1"},
                          {"repo": "OWNER/REPO", "assignment": "detyra1"}]):
            write_json(path, {"students": students})
            with self.assertRaises(runner.RunnerError):
                runner.plan_reviews(path, None)

    def test_api_payload_no_storage_auth_and_encrypted_reasoning(self):
        response = io.BytesIO(json.dumps({"status": "completed", "output": []}).encode())
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}):
            with patch("urllib.request.urlopen", return_value=response) as request:
                runner.OpenAI("test-model").respond("rules", [], [], 1000)
        req = request.call_args.args[0]
        payload = json.loads(req.data)
        self.assertEqual(req.full_url, "https://api.openai.com/v1/responses")
        self.assertFalse(payload["store"])
        self.assertIn("reasoning.encrypted_content", payload["include"])
        self.assertEqual(req.get_header("Authorization"), "Bearer test-secret")
        self.assertNotIn("test-secret", req.data.decode())

    def test_api_errors_do_not_echo_secrets_or_claim_completion(self):
        for outcome in [urllib.error.HTTPError("https://api.openai.com", 401, "secret", {}, io.BytesIO(b"test-secret")),
                        io.BytesIO(json.dumps({"status": "incomplete"}).encode())]:
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}):
                with patch("urllib.request.urlopen", **({"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome})):
                    with self.assertRaises(runner.RunnerError) as error:
                        runner.OpenAI("test-model").respond("rules", [], [], 1000)
                    self.assertNotIn("test-secret", str(error.exception))

    def test_two_phase_grading_keeps_review_out_of_phase1_and_preserves_snapshot(self):
        sub = freeze.freeze(self.project, student="Test", submission_id="student-test", assignment="detyra1")
        review_path = self.root / "reviews" / sub["project"] / "latest" / "review.json"
        write_json(review_path, {"agent1_secret": "DO NOT LEAK INTO PHASE 1"})
        reqs = load_json(assignment_files("detyra1")["requirements"])["requirements"]
        doc = {"assessments": [{"requirement_id": r["id"], "status": "MISSING",
                                 "searched": ["README.md"], "deduction_reason": "Missing from fixture."}
                                for r in reqs], "integrity": {"risk_level": "NONE_FOUND", "indicators": [],
                                                                            "disclaimer": "Risk indicators only."}}
        provider = FakeProvider([
            [call("list_files")], [call("read_file", path="agent1/review.json")],
            [call("read_file", path="project/README.md")], [call("submit_report", document=doc)],
            [call("list_files")], [call("read_file", path="agent1/review.json")],
            [call("read_file", path="project/README.md")],
            [call("read_file", path="evaluation.phase1.json")],
            [call("submit_report", assessment_updates=[], discrepancies_md="# Discrepancies\nNo score change.")]])
        args = Namespace(submissions="student-test", dry_run=False, model="test-model", timeout=10,
                         offline=True, provider="openai", max_turns=10, max_output_tokens=1000)
        with patch.object(runner, "OpenAI", return_value=provider):
            result = runner.run_grades(args)
        self.assertEqual(result["failed"], 0, result)
        run_dir = Path(result["results"][0]["evaluation_dir"])
        phase1 = load_json(run_dir / "evaluation.phase1.json")
        self.assertFalse(phase1["meta"]["agent1_report_consulted"])
        self.assertTrue(load_json(run_dir / "evaluation.json")["meta"]["agent1_report_consulted"])
        self.assertEqual(load_json(run_dir / "evaluation.json")["assessments"], phase1["assessments"])
        self.assertEqual(load_json(run_dir / "final.json")["total"], load_json(run_dir / "final.phase1.json")["total"])
        self.assertEqual(result["results"][0]["status"], "PROVISIONAL")
        self.assertNotIn("DO NOT LEAK", json.dumps(provider.requests[3]))
        self.assertIn("outside this phase", json.dumps(provider.requests[2]))
        self.assertIn("DO NOT LEAK", json.dumps(provider.requests[6]))
        self.assertNotIn("DO NOT LEAK", json.dumps(provider.requests[4]))
        self.assertTrue(freeze.verify("student-test")["intact"])
        self.assertTrue((run_dir / "discrepancies.md").exists())

    def test_batch_continues_after_preparation_failure(self):
        path = self.root / "roster.json"
        write_json(path, {"assignment": "detyra1", "students": [{"repo": "owner/one"}, {"repo": "owner/two"}]})
        args = Namespace(roster=str(path), assignment=None, dry_run=False, model="test-model", timeout=10,
                         offline=True, provider="openai", max_turns=1, max_output_tokens=1000)
        with patch.object(runner, "OpenAI"), patch.object(cli, "cmd_new_review", side_effect=SystemExit("No access")) as prep:
            result = runner.run_reviews(args)
        self.assertEqual(prep.call_count, 2)
        self.assertEqual(result["failed"], 2)

    def test_bad_submission_ids_fail_before_api_calls(self):
        for sid in ("../outside", "..", "missing", ""):
            with self.assertRaises(runner.RunnerError):
                runner.plan_grades(sid)

    def test_command_rejects_zero_step_budget(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                cli.main(["review-all", "--max-turns", "0"])

    def test_claude_tool_loop_uses_native_api_and_saves_validated_review(self):
        responses = [
            {"id": "msg_read", "model": "claude-test", "stop_reason": "tool_use",
             "usage": {"input_tokens": 10, "output_tokens": 5},
             "content": [{"type": "text", "text": "Inspecting the file."},
                         {"type": "tool_use", "id": "read1", "name": "read_file",
                          "input": {"path": "project/README.md"}}]},
            {"id": "msg_submit", "model": "claude-test", "stop_reason": "tool_use",
             "content": [{"type": "tool_use", "id": "submit1", "name": "submit_report",
                          "input": {"document": self.review(), "report_md": "# Review"}}]}]
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-anthropic-secret"}):
            with patch("urllib.request.urlopen", side_effect=[io.BytesIO(json.dumps(r).encode()) for r in responses]) as request:
                result = runner.session(runner.Claude("claude-test"), self.run, self.project,
                                        "detyra1", "review", 3, 1000)
        self.assertEqual(result["validation_errors"], [])
        req = request.call_args_list[1].args[0]
        payload = json.loads(req.data)
        self.assertEqual(req.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(req.get_header("X-api-key"), "test-anthropic-secret")
        self.assertEqual(req.get_header("Anthropic-version"), "2023-06-01")
        self.assertEqual(payload["max_tokens"], 1000)
        self.assertIn("input_schema", payload["tools"][0])
        self.assertNotIn("parameters", payload["tools"][0])
        self.assertEqual([m["role"] for m in payload["messages"]], ["user", "assistant", "user"])
        self.assertEqual(payload["messages"][1]["content"], responses[0]["content"])
        tool_result = payload["messages"][2]["content"][0]
        self.assertEqual(tool_result["type"], "tool_result")
        self.assertEqual(tool_result["tool_use_id"], "read1")
        self.assertIn("Student project", tool_result["content"])
        self.assertNotIn("test-anthropic-secret", req.data.decode())
        audit = load_json(self.run / "runner.phase1.json")
        self.assertTrue(audit["completed"])
        self.assertEqual(audit["provider"], "claude")
        self.assertEqual(audit["responses"][0]["id"], "msg_read")

    def test_claude_groups_tool_results_and_preserves_signed_blocks(self):
        blocks = [{"type": "thinking", "thinking": "internal", "signature": "signed"},
                  {"type": "tool_use", "id": "one", "name": "read_file", "input": {}},
                  {"type": "tool_use", "id": "two", "name": "read_file", "input": {}}]
        messages = runner.Claude.messages([
            {"role": "user", "content": "Start"}, {"type": "claude_message", "content": blocks},
            call("read_file", path="project/one"), call("read_file", path="project/two"),
            {"type": "function_call_output", "call_id": "one", "output": '{"error": "missing"}'},
            {"type": "function_call_output", "call_id": "two", "output": '{"text": "ok"}'}])
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1]["content"], blocks)
        self.assertEqual([b["tool_use_id"] for b in messages[2]["content"]], ["one", "two"])
        self.assertTrue(messages[2]["content"][0]["is_error"])
        self.assertNotIn("is_error", messages[2]["content"][1])

    def test_claude_failures_and_missing_configuration(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            with self.assertRaisesRegex(runner.RunnerError, "ANTHROPIC_API_KEY"):
                runner.Claude("claude-test")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}):
            with self.assertRaisesRegex(runner.RunnerError, "ANTHROPIC_MODEL"):
                runner.Claude(None)
            for reason in ("max_tokens", "refusal", "pause_turn"):
                response = io.BytesIO(json.dumps({"stop_reason": reason, "content": []}).encode())
                with patch("urllib.request.urlopen", return_value=response):
                    with self.assertRaises(runner.RunnerError):
                        runner.Claude("claude-test").respond("rules", [], [], 1000)
            error = urllib.error.HTTPError("https://api.anthropic.com", 401, "test-secret", {}, io.BytesIO(b"test-secret"))
            with patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.Claude("claude-test").respond("rules", [], [], 1000)
                self.assertNotIn("test-secret", str(caught.exception))

    def test_provider_model_environment_is_not_shared(self):
        with patch.dict(os.environ, {"OPENAI_MODEL": "openai-test", "ANTHROPIC_MODEL": "claude-test"}):
            self.assertEqual(runner.model_for(Namespace(provider="claude", model=None)), "claude-test")
            self.assertEqual(runner.model_for(Namespace(provider="openai", model=None)), "openai-test")
            self.assertEqual(runner.model_for(Namespace(provider="claude", model="explicit")), "explicit")
        with patch.object(runner, "Claude") as claude, patch.object(runner, "OpenAI") as openai:
            runner.create_provider(Namespace(provider="claude", model="explicit", timeout=10))
            claude.assert_called_once_with("explicit", 10)
            openai.assert_not_called()

    def test_claude_cli_dry_run_needs_no_keys(self):
        path = self.root / "roster.json"
        write_json(path, {"assignment": "detyra1", "students": [{"repo": "owner/repo"}]})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "ANTHROPIC_MODEL": "claude-test"}):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                status = cli.main(["review-all", "--provider", "claude", "--roster", str(path), "--dry-run"])
        result = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(result["provider"], "claude")
        self.assertEqual(result["model"], "claude-test")
