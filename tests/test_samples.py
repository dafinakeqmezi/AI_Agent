"""Tests for the controlled sample projects and the expected-findings checker.

Run: python -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grader import expected  # noqa: E402
from grader.common import REQUIREMENTS_FILE, load_json, write_json  # noqa: E402
from grader.scan import SEED_RE, scan  # noqa: E402

SAMPLES = ROOT / "sample-projects"
GOOD = SAMPLES / "churn-prediction-good"
BAD = SAMPLES / "student-performance-bad"
EXP_GOOD = ROOT / "tests" / "expected" / "expected-churn-review.json"
EXP_BAD = ROOT / "tests" / "expected" / "expected-student-review.json"
REQS = load_json(REQUIREMENTS_FILE)["requirements"]
EV = [{"file": "README.md", "location": "L1"}]


def statuses_from(spec, mode="review"):
    """The 'perfect agent': reports exactly the expected status for every asserted requirement."""
    out = {f["requirement_id"]: f["status"] for f in spec["expected_findings"]}
    if mode == "evaluation":
        out = {k: ("MISSING" if v == "BLOCKER" else v) for k, v in out.items()}
    for n in spec["not_asserted"]:
        out[n["requirement_id"]] = "MISSING"
    return out


def signal_types(project):
    with tempfile.TemporaryDirectory() as d:
        return {s["type"] for s in scan(project, Path(d))["signals"]}


class ExpectedFiles(unittest.TestCase):
    def test_expected_files_are_valid(self):
        for f in (EXP_GOOD, EXP_BAD):
            with self.subTest(f=f.name):
                self.assertEqual(expected.validate_expected(load_json(f), REQS), [])

    def test_answer_keys_are_outside_the_fixtures(self):
        # The reviewer reads the whole project folder; an answer key inside it would leak the answers.
        for p in (GOOD, BAD):
            self.assertFalse(list(p.rglob("expected*.json")))

    def test_core_expectations_from_the_brief(self):
        good = {f["requirement_id"]: f for f in load_json(EXP_GOOD)["expected_findings"]}
        bad = {f["requirement_id"]: f for f in load_json(EXP_BAD)["expected_findings"]}
        self.assertFalse([r for r, f in good.items() if f["status"] == "BLOCKER"])
        self.assertEqual(good["LIT-001"]["status"], "PARTIAL")
        self.assertEqual(good["EVAL-002"]["status"], "PARTIAL")
        self.assertEqual(good["EXP-002"]["status"], "MISSING")
        self.assertEqual({r for r, f in bad.items() if f["status"] == "BLOCKER"},
                         {"DATA-004", "IMPL-002", "LIT-003", "EXP-004"})
        self.assertEqual(bad["METH-001"]["status"], "MISSING")


class SampleFixtures(unittest.TestCase):
    def test_good_project_scan_is_clean(self):
        types = signal_types(GOOD)
        for t in ("hardcoded_path", "no_seed_found", "no_dependency_file", "unpinned_dependencies",
                  "readme_no_run_instructions", "leakage_fit_before_split", "leakage_fit_on_test", "no_readme"):
            self.assertNotIn(t, types)

    def test_bad_project_scan_finds_the_mechanical_flaws(self):
        types = signal_types(BAD)
        for t in ("hardcoded_path", "no_seed_found", "no_dependency_file", "readme_no_run_instructions",
                  "mentioned_not_implemented"):
            self.assertIn(t, types)

    def test_good_report_numbers_come_from_metrics_json(self):
        metrics = load_json(GOOD / "results" / "metrics.json")
        report = (GOOD / "report" / "report.md").read_text(encoding="utf-8")
        readme = (GOOD / "README.md").read_text(encoding="utf-8")
        for name, m in metrics["models"].items():
            for k in ("accuracy", "precision", "recall", "f1"):
                v = f"{m['test'][k]:.4f}"
                self.assertIn(v, report, f"{name} test {k}")
                self.assertIn(v, readme, f"{name} test {k}")
        cm = metrics["models"]["logistic_regression"]["test"]["confusion_matrix"]
        self.assertIn(f"| {cm['tn']} | {cm['fp']} |", report)

    def test_bad_project_target_is_derived_from_leaked_feature(self):
        import csv
        with open(BAD / "data.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertTrue(all(int(r["passed"]) == int(float(r["final_exam_score"]) >= 50) for r in rows))
        self.assertIn('X["final_exam_score"] = df["final_exam_score"]', (BAD / "model.py").read_text(encoding="utf-8"))

    def test_seed_regex(self):
        for s in ("random_state=42", "random_state=SEED", "random_state=cfg.seed", "np.random.default_rng(seed)"):
            self.assertTrue(SEED_RE.search(s), s)
        for s in ("random_state=None", "np.random.default_rng()", "test_size=0.2"):
            self.assertFalse(SEED_RE.search(s), s)


class WrappedReferences(unittest.TestCase):
    """Markdown references wrapped over several lines must be verified against the whole entry."""

    TEXT = """# Report

## References

- Neslin, S. A., Gupta, S., Kamakura, W., Lu, J., & Mason, C. H. (2006).
  Defection Detection: Measuring and Understanding the Predictive Accuracy of
  Customer Churn Models. *Journal of Marketing Research*, 43(2), 204-211.
  https://doi.org/10.1509/jmkr.43.2.204
- Pedregosa, F., et al. (2011). Scikit-learn: Machine Learning in Python.
  *Journal of Machine Learning Research*, 12, 2825-2830.
  https://jmlr.org/papers/v12/pedregosa11a.html
"""

    def test_wrapped_entries_are_not_split(self):
        from grader import cite
        entries = cite._reference_entries(self.TEXT)
        self.assertEqual(len(entries), 2)
        self.assertIn("Journal of Machine Learning Research", entries[1][1])

    def test_wrapped_doi_entry_is_verified(self):
        from unittest import mock
        from grader import cite
        rec = {"title": "Defection Detection: Measuring and Understanding the Predictive Accuracy of Customer Churn Models",
               "authors": ["Neslin"], "year": 2006, "venue": "Journal of Marketing Research"}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "p"
            root.mkdir()
            (root / "report.md").write_text(self.TEXT, encoding="utf-8")
            with mock.patch.object(cite, "crossref_doi", return_value=("FOUND", rec)), \
                    mock.patch.object(cite.time, "sleep"):
                res = cite.verify_project(root, Path(d) / "out")
        self.assertEqual(res["counts"], {"VERIFIED": 1, "NO_IDENTIFIER": 1})


class Checker(unittest.TestCase):
    def test_perfect_review_passes(self):
        for f in (EXP_GOOD, EXP_BAD):
            spec = load_json(f)
            res = expected.compare(statuses_from(spec), spec, "review")
            self.assertEqual(res["failures"], [], f.name)
            self.assertEqual(res["agreement"], 1.0)

    def test_missed_leakage_fails(self):
        spec = load_json(EXP_BAD)
        actual = statuses_from(spec)
        actual["DATA-004"] = "PASS"
        fails = " ".join(expected.compare(actual, spec, "review")["failures"])
        self.assertIn("DATA-004", fails)
        self.assertIn("missed blocker", fails)
        self.assertIn("missed problem", fails)

    def test_acceptable_alternative_is_not_a_failure(self):
        spec = load_json(EXP_BAD)
        actual = statuses_from(spec)
        actual["EXP-004"] = "MISSING"        # also_acceptable
        actual["METH-001"] = "BLOCKER"       # also_acceptable
        res = expected.compare(actual, spec, "review")
        self.assertEqual(res["failures"], [])
        self.assertEqual(res["counts"]["ACCEPTABLE"], 2)

    def test_false_deduction_and_unexpected_blocker_on_good_project(self):
        spec = load_json(EXP_GOOD)
        actual = statuses_from(spec)
        actual["IMPL-002"] = "BLOCKER"       # took the CV-negation bait
        fails = " ".join(expected.compare(actual, spec, "review")["failures"])
        self.assertIn("false deduction", fails)
        self.assertIn("unexpected BLOCKER", fails)

    def test_ignored_requirements_do_not_count(self):
        spec = load_json(EXP_GOOD)
        actual = statuses_from(spec)
        actual["VCS-001"] = "BLOCKER"
        self.assertEqual(expected.compare(actual, spec, "review")["failures"], [])

    def test_check_review_dir_end_to_end(self):
        spec = load_json(EXP_BAD)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            reqs = [{"requirement_id": k, "status": v, "evidence": EV, "finding": "x"}
                    for k, v in statuses_from(spec).items()]
            write_json(d / "review.json", {"requirements": reqs, "integrity": {"risk_level": "HIGH_CONCERN"}})
            write_json(d / "readiness.json", {"verdict": "NOT_READY"})
            res = expected.check(d, EXP_BAD)
            self.assertEqual(res["verdict"], "PASS", res["failures"])
            self.assertTrue((d / "expected-check.md").exists())
            write_json(d / "review.json", {"requirements": reqs, "integrity": {"risk_level": "NONE_FOUND"}})
            self.assertEqual(expected.check(d, EXP_BAD)["verdict"], "FAIL")

    def test_check_evaluation_dir_maps_blocker_to_missing_and_checks_range(self):
        spec = load_json(EXP_BAD)
        st = statuses_from(spec, "evaluation")
        crit = [{"id": "C1", "requirements": [{"requirement_id": k, "status": v} for k, v in st.items()]}]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_json(d / "final.json", {"criteria": crit, "total": 12.5, "grade": 5,
                                          "integrity": {"risk_level": "HIGH_CONCERN"}})
            self.assertEqual(expected.check(d, EXP_BAD)["verdict"], "PASS")
            write_json(d / "final.json", {"criteria": crit, "total": 72.0, "grade": 8,
                                          "integrity": {"risk_level": "HIGH_CONCERN"}})
            fails = " ".join(expected.check(d, EXP_BAD)["failures"])
            self.assertIn("total 72.0 outside", fails)
            self.assertIn("grade 8 outside", fails)


if __name__ == "__main__":
    unittest.main()


class Dashboard(unittest.TestCase):
    def test_render_escapes_script_close(self):
        import re
        from grader import dashboard
        data = dashboard.collect(ROOT)
        data["projects"].append({"name": "x</script><script>alert(1)</script>", "state": "DRAFT", "updated_at": None,
                                 "history": [], "reviews": [], "review": None, "submissions": [], "evaluation": None})
        html = dashboard.render(data)
        m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
        self.assertEqual(json.loads(m.group(1))["projects"][-1]["name"], "x</script><script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)", html)

    def test_build_writes_file_without_network(self):
        from grader import dashboard
        with tempfile.TemporaryDirectory() as d:
            out = dashboard.build(Path(d) / "dash.html", open_browser=False)
            html = out.read_text(encoding="utf-8")
        self.assertIn("Grading Dashboard", html)
        self.assertNotRegex(html, r'(src|href)="https?://')

    def test_students_file_overrides_freeze_name(self):
        from unittest import mock
        from grader import dashboard
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "students.json"
            f.write_text(json.dumps({"students": {"churn-prediction-good": "Test Name"}}), encoding="utf-8")
            with mock.patch.object(dashboard, "STUDENTS_FILE", f):
                data = dashboard.collect(ROOT)
        names = {p["name"]: p["student"] for p in data["projects"]}
        if "churn-prediction-good" in names:
            self.assertEqual(names["churn-prediction-good"], "Test Name")
