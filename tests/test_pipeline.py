"""Tests for the deterministic toolkit. Run: python -m unittest discover -s tests -v"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grader import benchmark, freeze, readiness, score, state  # noqa: E402
from grader.common import REQUIREMENTS_FILE, RUBRIC_FILE, load_json, write_json  # noqa: E402
from grader.scan import scan  # noqa: E402

EXAMPLE = ROOT / "examples" / "leaky-churn"
REQS = load_json(REQUIREMENTS_FILE)["requirements"]
EV = [{"file": "README.md", "location": "L1", "quote": "Customer churn prediction"}]


def all_pass_assessments():
    return [{"requirement_id": r["id"], "status": "PASS", "evidence": EV} for r in REQS]


def evaluation(assessments, sid):
    return {"meta": {"submission_id": sid, "evaluation_id": "eval-test", "model": "test"},
            "assessments": assessments, "strengths": [], "weaknesses": [], "critical_issues": [],
            "integrity": {"risk_level": "NONE_FOUND", "indicators": [], "disclaimer": "indicators only"},
            "justification": "test"}


class Sandbox(unittest.TestCase):
    """Redirect submissions/, evaluations/, reviews/ and state to a temp dir."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.subs, self.evals = self.tmp / "submissions", self.tmp / "evaluations"
        patches = [
            mock.patch.object(freeze, "SUBMISSIONS", self.subs),
            mock.patch.object(score, "SUBMISSIONS", self.subs),
            mock.patch.object(state, "STATE_FILE", self.tmp / "state" / "registry.json"),
            mock.patch.object(benchmark, "EVALUATIONS", self.evals),
            mock.patch.object(benchmark, "BENCH", self.tmp / "benchmark"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        for p in self.tmp.rglob("*"):
            if p.is_file():
                os.chmod(p, stat.S_IWRITE | stat.S_IREAD)

    def frozen(self):
        return freeze.freeze(EXAMPLE, student="Test Student", submission_id="leaky-churn-test")["submission_id"]

    def score_dir(self, assessments, sid):
        d = self.evals / sid / "eval-test"
        write_json(d / "evaluation.json", evaluation(assessments, sid))
        return d


class TestConfig(unittest.TestCase):
    def test_rubric_and_requirements_consistent(self):
        self.assertEqual(score.check_config(load_json(RUBRIC_FILE), REQS), [])


class TestScan(unittest.TestCase):
    def test_detects_planted_flaws(self):
        with tempfile.TemporaryDirectory() as out:
            types = {s["type"] for s in scan(EXAMPLE, Path(out))["signals"]}
        for expected in ["leakage_fit_before_split", "hardcoded_path", "no_seed_found", "unpinned_dependencies",
                         "possible_prompt_injection", "mentioned_not_implemented", "implausibly_high_metric"]:
            self.assertIn(expected, types)


class TestFreeze(Sandbox):
    def test_freeze_and_tamper_detection(self):
        sid = self.frozen()
        self.assertTrue(freeze.verify(sid)["intact"])
        self.assertEqual(state.get("leaky-churn")["state"], "FINAL_SUBMISSION")
        f = self.subs / sid / "files" / "src" / "train.py"
        os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
        f.write_text("tampered", encoding="utf-8")
        res = freeze.verify(sid)
        self.assertFalse(res["intact"])
        self.assertEqual(res["problems"][0]["problem"], "modified")


class TestScore(Sandbox):
    def test_all_pass_gives_full_marks(self):
        sid = self.frozen()
        res = score.compute(self.score_dir(all_pass_assessments(), sid))
        self.assertEqual(res["total"], 100.0)
        self.assertEqual(res["grade"], 10)
        self.assertEqual(state.get("leaky-churn")["state"], "GRADED")

    def test_partial_and_missing_arithmetic(self):
        sid = self.frozen()
        a = {x["requirement_id"]: x for x in all_pass_assessments()}
        a["DATA-004"] = {"requirement_id": "DATA-004", "status": "PARTIAL", "credit": 0.5, "evidence": EV,
                         "deduction_reason": "leakage"}
        a["METH-001"] = {"requirement_id": "METH-001", "status": "MISSING", "searched": ["src/"],
                         "deduction_reason": "no baseline"}
        res = score.compute(self.score_dir(list(a.values()), sid))
        crit = {c["id"]: c["score"] for c in res["criteria"]}
        self.assertEqual(crit["C3"], 8.5)   # 10 - 3*0.5
        self.assertEqual(crit["C4"], 8.0)   # 12 - 4
        self.assertEqual(res["total"], 94.5)
        self.assertEqual(res["grade"], 10)  # 94.5 rounds half-up to 95
        self.assertIn("DATA-004", res["mandatory_requirements_not_met"])

    def test_not_applicable_rescales_criterion(self):
        sid = self.frozen()
        a = {x["requirement_id"]: x for x in all_pass_assessments()}
        a["EXP-003"] = {"requirement_id": "EXP-003", "status": "NOT_APPLICABLE", "na_reason": "single component"}
        a["EXP-002"] = {"requirement_id": "EXP-002", "status": "MISSING", "searched": ["results/"], "deduction_reason": "x"}
        res = score.compute(self.score_dir(list(a.values()), sid))
        c6 = next(c for c in res["criteria"] if c["id"] == "C6")
        self.assertEqual(c6["score"], 8.56)  # (4+3)/(4+2+3) * 11

    def test_rules_enforced(self):
        sid = self.frozen()
        a = {x["requirement_id"]: x for x in all_pass_assessments()}
        a["PROB-001"] = {"requirement_id": "PROB-001", "status": "PASS", "evidence": []}               # credit w/o evidence
        a["PROB-002"] = {"requirement_id": "PROB-002", "status": "MISSING"}                           # deduction w/o reason
        a["DATA-004"] = {"requirement_id": "DATA-004", "status": "NOT_APPLICABLE", "na_reason": "x"}  # cannot be N/A
        a["LIT-001"] = {"requirement_id": "LIT-001", "status": "PASS",
                        "evidence": [{"file": "does/not/exist.py", "location": "L1"}]}                 # invented file
        a["EVAL-001"] = {"requirement_id": "EVAL-001", "status": "PARTIAL", "credit": 0.6, "evidence": EV,
                         "deduction_reason": "x"}                                                      # bad credit level
        a["EXTRA-1"] = {"requirement_id": "EXTRA-1", "status": "MISSING", "searched": ["x"], "deduction_reason": "x"}
        del a["DOC-003"]                                                                               # not assessed
        with self.assertRaises(score.ScoreError) as cm:
            score.compute(self.score_dir(list(a.values()), sid))
        msg = "\n".join(cm.exception.errors)
        for needle in ["PROB-001", "PROB-002", "cannot be NOT_APPLICABLE", "does/not/exist.py",
                       "PARTIAL credit", "EXTRA-1", "DOC-003: not assessed"]:
            self.assertIn(needle, msg)

    def test_overrides_and_approval(self):
        from grader import override
        sid = self.frozen()
        d = self.score_dir(all_pass_assessments(), sid)
        override.add(d, {"type": "approve", "by": "Prof"})
        self.assertEqual(score.compute(d)["review_status"], "APPROVED")
        override.add(d, {"type": "requirement", "requirement_id": "METH-001", "status": "MISSING",
                         "reason": "baseline is the same model", "by": "Prof"})
        res = score.compute(d)
        self.assertEqual(res["total"], 96.0)
        self.assertEqual(res["review_status"], "PROVISIONAL")  # change after approval needs re-approval
        row = next(q for c in res["criteria"] for q in c["requirements"] if q["requirement_id"] == "METH-001")
        self.assertEqual(row["agent_status"], "PASS")
        self.assertIn("Professor override", (d / "report.md").read_text(encoding="utf-8"))


class TestReadiness(Sandbox):
    def review(self, d, statuses):
        reqs = [{"requirement_id": r["id"], "status": statuses.get(r["id"], "PASS"), "evidence": EV,
                 "finding": "x", "type": "FACT"} for r in REQS]
        write_json(d / "review.json", {"requirements": reqs, "findings": [], "recommendations": [],
                                       "integrity": {"risk_level": "NONE_FOUND", "indicators": [], "disclaimer": "x"}})
        write_json(d / "artifacts" / "inventory.json", {"files": [{"path": "README.md"}]})

    def test_blocker_not_ready(self):
        d = self.tmp / "rev1"
        self.review(d, {"DATA-004": "BLOCKER"})
        res = readiness.evaluate(d)
        self.assertEqual(res["verdict"], "NOT_READY")
        self.assertEqual(res["blockers"], ["DATA-004"])

    def test_all_pass_ready(self):
        d = self.tmp / "rev2"
        self.review(d, {})
        self.assertEqual(readiness.evaluate(d)["verdict"], "READY_FOR_FINAL_REVIEW")


class TestBenchmark(Sandbox):
    def test_compare_with_human(self):
        sid = self.frozen()
        a = {x["requirement_id"]: x for x in all_pass_assessments()}
        a["DATA-004"] = {"requirement_id": "DATA-004", "status": "MISSING", "searched": ["src/"], "deduction_reason": "leak"}
        score.compute(self.score_dir(list(a.values()), sid))
        human = self.tmp / "human.json"
        write_json(human, {"projects": [{"submission_id": sid, "human_total": 90, "human_grade": 9,
                                          "requirements": {"DATA-004": "MISSING", "METH-001": "MISSING"},
                                          "planted_issues": ["DATA-004", "METH-001"],
                                          "integrity_expected": "NEEDS_REVIEW"}]})
        res = benchmark.run(human)
        self.assertEqual(res["projects_compared"], 1)
        self.assertEqual(res["missed_problems"], 1)          # METH-001
        self.assertEqual(res["planted_issue_recall"], 0.5)
        self.assertEqual(res["missed_integrity_concerns"], 1)


class TestHook(unittest.TestCase):
    def run_hook(self, path):
        hook = ROOT / ".claude" / "hooks" / "protect_submissions.py"
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}, "cwd": str(ROOT)})
        return subprocess.run([sys.executable, str(hook)], input=payload, capture_output=True, text=True).returncode

    def test_blocks_submissions(self):
        self.assertEqual(self.run_hook(ROOT / "submissions" / "x" / "files" / "a.py"), 2)
        self.assertEqual(self.run_hook("submissions/x/manifest.json"), 2)

    def test_allows_other_paths(self):
        self.assertEqual(self.run_hook(ROOT / "evaluations" / "x" / "evaluation.json"), 0)


if __name__ == "__main__":
    unittest.main()
