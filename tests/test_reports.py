"""Local report rendering preserves model assessments without another model call."""
import unittest

from grader.reports import render_review
from grader.runner import tools_for


class ReviewReportTests(unittest.TestCase):
    def test_renderer_keeps_evidence_searches_uncertainty_and_custom_sections(self):
        document = {
            "requirements": [{"requirement_id": "TEST-001", "status": "PARTIAL", "finding": "A gap",
                              "confidence": "low", "severity": "MAJOR",
                              "evidence": [{"file": "solver.py", "location": "L2", "quote": 'return "a|b"'}],
                              "searched": ["results/"], "recommendation": "Verify the result"}],
            "findings": [{"type": "FACT", "finding": "A gap"}],
            "claims_ledger": [{"claim": "It works", "status": "UNSUPPORTED"}],
            "report_vs_code": [{"report_says": "BFS", "code_does": "DFS"}],
            "literature": {"coverage": "INCOMPLETE"},
            "reproducibility": {"score": 2, "max": 10},
            "integrity": {"risk_level": "NEEDS_REVIEW", "indicators": [], "disclaimer": "Not proof of misconduct"},
            "recommendations": [{"priority": 1, "action": "Verify the result"}],
            "limitations": "Code was not executed", "custom_note": "Preserve this note",
        }
        result = render_review(document, {"verdict": "NOT_READY", "counts": {"partial": 1}}, "detyra1")
        for value in ("TEST-001", "PARTIAL", "solver.py", "L2", "results/", "Verify the result", "low",
                      "MAJOR", "UNSUPPORTED", "BFS", "DFS", "INCOMPLETE", "NEEDS_REVIEW",
                      "Not proof of misconduct", "Code was not executed", "Preserve this note"):
            self.assertIn(value, result)
        self.assertIn('return "a\\|b"', result)
        self.assertIn("Rishikimi i projektit", result)
        self.assertIn("automated reviewer", result)

    def test_renderer_escapes_html_in_student_quotes(self):
        result = render_review({"requirements": [], "findings": ["<script>alert(1)</script>"]},
                               {"verdict": "NOT_READY"}, "ml-project")
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_review_tool_requests_assessment_once(self):
        submit = next(t for t in tools_for("review", 1) if t["name"] == "submit_report")
        self.assertEqual(submit["parameters"]["required"], ["document"])
        self.assertNotIn("report_md", submit["parameters"]["properties"])
