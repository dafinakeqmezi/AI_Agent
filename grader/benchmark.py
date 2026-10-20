"""Evaluate the evaluator: compare Agent 2 grades against human professor grades.

benchmark/human_grades.json:
{
  "tolerance_fraction": 0.1,
  "projects": [
    {"submission_id": "...", "human_total": 72, "human_grade": 8,
     "criteria": {"C1": 8, ...},                       # optional
     "requirements": {"DATA-004": "MISSING", ...},     # optional, human statuses
     "planted_issues": ["DATA-004", "LIT-003"],        # requirements deliberately broken
     "integrity_expected": "NONE_FOUND" | "NEEDS_REVIEW" | "HIGH_CONCERN"}
  ]
}
"""
from __future__ import annotations

from pathlib import Path

from .common import EVALUATIONS, ROOT, load_json, now_iso, write_json, write_text

BENCH = ROOT / "benchmark"


def latest_final(submission_id: str) -> dict | None:
    d = EVALUATIONS / submission_id
    if not d.exists():
        return None
    runs = sorted([p for p in d.iterdir() if (p / "final.json").exists()], key=lambda p: p.name)
    return load_json(runs[-1] / "final.json") if runs else None


def run(human_file: Path = BENCH / "human_grades.json") -> dict:
    spec = load_json(human_file)
    tol = spec.get("tolerance_fraction", 0.1)
    rows, missing = [], []
    totals = {"crit_pairs": 0, "crit_agree": 0, "crit_abs": 0.0, "req_pairs": 0, "req_agree": 0,
              "false_deductions": 0, "missed_problems": 0, "planted": 0, "planted_caught": 0,
              "false_integrity": 0, "missed_integrity": 0}
    details = []
    for h in spec["projects"]:
        f = latest_final(h["submission_id"])
        if f is None:
            missing.append(h["submission_id"])
            continue
        crit_scores = {c["id"]: (c["score"], c["points"]) for c in f["criteria"]}
        req_status = {q["requirement_id"]: q["status"] for c in f["criteria"] for q in c["requirements"]}
        row = {"submission_id": h["submission_id"], "human_total": h["human_total"], "agent_total": f["total"],
               "total_diff": None if h.get("human_total") is None else round(f["total"] - h["human_total"], 1),
               "human_grade": h.get("human_grade"), "agent_grade": f["grade"]}
        for cid, hs in (h.get("criteria") or {}).items():
            if cid in crit_scores:
                s, pts = crit_scores[cid]
                totals["crit_pairs"] += 1
                totals["crit_abs"] += abs(s - hs)
                if abs(s - hs) <= tol * pts:
                    totals["crit_agree"] += 1
        for rid, hst in (h.get("requirements") or {}).items():
            ast = req_status.get(rid)
            totals["req_pairs"] += 1
            if ast == hst:
                totals["req_agree"] += 1
            if hst == "PASS" and ast in {"PARTIAL", "MISSING"}:
                totals["false_deductions"] += 1
                details.append(f"{h['submission_id']}: FALSE DEDUCTION on {rid} (human PASS, agent {ast})")
            if hst in {"PARTIAL", "MISSING"} and ast == "PASS":
                totals["missed_problems"] += 1
                details.append(f"{h['submission_id']}: MISSED PROBLEM on {rid} (human {hst}, agent PASS)")
        for rid in h.get("planted_issues", []):
            totals["planted"] += 1
            if req_status.get(rid) in {"PARTIAL", "MISSING"}:
                totals["planted_caught"] += 1
            else:
                details.append(f"{h['submission_id']}: planted issue {rid} NOT caught (agent {req_status.get(rid)})")
        exp = h.get("integrity_expected")
        got = (f.get("integrity") or {}).get("risk_level")
        if exp:
            row["integrity_expected"], row["integrity_agent"] = exp, got
            if exp == "NONE_FOUND" and got in {"NEEDS_REVIEW", "HIGH_CONCERN"}:
                totals["false_integrity"] += 1
                details.append(f"{h['submission_id']}: FALSE INTEGRITY FLAG ({got})")
            if exp != "NONE_FOUND" and got == "NONE_FOUND":
                totals["missed_integrity"] += 1
                details.append(f"{h['submission_id']}: MISSED INTEGRITY CONCERN (expected {exp})")
        rows.append(row)

    n = len(rows)
    totalled = [r for r in rows if r["total_diff"] is not None]
    diffs = [abs(r["total_diff"]) for r in totalled]
    graded = [r for r in rows if r["human_grade"] is not None]
    summary = {
        "generated_at": now_iso(),
        "projects_compared": n,
        "projects_without_agent_evaluation": missing,
        "total_mae": round(sum(diffs) / len(diffs), 2) if diffs else None,
        "total_max_abs_diff": max(diffs) if diffs else None,
        "mean_signed_total_diff": round(sum(r["total_diff"] for r in totalled) / len(totalled), 2) if totalled else None,
        "grade_exact_agreement": round(sum(r["agent_grade"] == r["human_grade"] for r in graded) / len(graded), 2) if graded else None,
        "criterion_mae": round(totals["crit_abs"] / totals["crit_pairs"], 2) if totals["crit_pairs"] else None,
        "criterion_agreement_within_tolerance": round(totals["crit_agree"] / totals["crit_pairs"], 2) if totals["crit_pairs"] else None,
        "requirement_status_agreement": round(totals["req_agree"] / totals["req_pairs"], 2) if totals["req_pairs"] else None,
        "false_deductions": totals["false_deductions"],
        "missed_problems": totals["missed_problems"],
        "planted_issue_recall": round(totals["planted_caught"] / totals["planted"], 2) if totals["planted"] else None,
        "false_integrity_flags": totals["false_integrity"],
        "missed_integrity_concerns": totals["missed_integrity"],
        "rows": rows,
        "details": details,
    }
    write_json(BENCH / "results.json", summary)
    L = ["# Grader benchmark: Agent 2 vs human professor", "", f"Generated {summary['generated_at']}, {n} project(s).", "",
         "| Metric | Value |", "|---|---|"]
    for k in ["total_mae", "total_max_abs_diff", "mean_signed_total_diff", "grade_exact_agreement", "criterion_mae",
              "criterion_agreement_within_tolerance", "requirement_status_agreement", "false_deductions",
              "missed_problems", "planted_issue_recall", "false_integrity_flags", "missed_integrity_concerns"]:
        L.append(f"| {k} | {summary[k]} |")
    L += ["", "| Submission | Human | Agent | Diff | Human grade | Agent grade |", "|---|---|---|---|---|---|"]
    L += [f"| {r['submission_id']} | {r['human_total']} | {r['agent_total']} | {'-' if r['total_diff'] is None else format(r['total_diff'], '+')} | {r['human_grade']} | {r['agent_grade']} |" for r in rows]
    if details:
        L += ["", "## Disagreements"] + [f"- {d}" for d in details]
    if missing:
        L += ["", "## Not yet evaluated by Agent 2"] + [f"- {m}" for m in missing]
    write_text(BENCH / "results.md", "\n".join(L) + "\n")
    return summary
