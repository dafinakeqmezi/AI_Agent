"""Agent 2 scoring: validates evaluation.json and computes criterion scores, total and grade deterministically.

The LLM judges status + evidence per requirement; arithmetic, rounding and grade mapping happen here.
Rules enforced:
  - every requirement assessed exactly once
  - no credit without evidence (PASS needs evidence)
  - no deduction without a rubric criterion + evidence (PARTIAL/MISSING need deduction_reason + evidence/searched)
  - cited files must exist in the frozen submission
  - professor overrides (overrides.json) win over the agent and are shown side by side
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import state
from .common import (SUBMISSIONS, assignment_files, assignment_of, identity, load_json, now_iso, write_json, write_text)
from .validate import check_evidence, commits_from_history
from .versions import collect_versions

EVAL_STATUSES = {"PASS", "PARTIAL", "MISSING", "NOT_APPLICABLE"}


class ScoreError(Exception):
    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


def check_config(rubric: dict, reqs: list[dict]) -> list[str]:
    errors = []
    crit = {c["id"]: c for c in rubric["criteria"]}
    if sum(c["points"] for c in rubric["criteria"]) != rubric["total_points"]:
        errors.append("rubric: criteria points do not sum to total_points")
    for cid, c in crit.items():
        s = sum(r["points"] for r in reqs if r["criterion_id"] == cid)
        if s != c["points"]:
            errors.append(f"config: requirements of {cid} sum to {s}, criterion is worth {c['points']}")
    for r in reqs:
        if r["criterion_id"] not in crit:
            errors.append(f"config: {r['id']} references unknown criterion {r['criterion_id']}")
    return errors


def apply_overrides(assessments: dict, overrides: list[dict]) -> tuple[dict, dict]:
    """Return (effective assessments, review status info)."""
    eff = {k: dict(v) for k, v in assessments.items()}
    status, approved_by, approved_at = "PROVISIONAL", None, None
    dismissed, comments = [], []
    for o in overrides:
        t = o.get("type")
        if t == "requirement":
            rid = o["requirement_id"]
            base = eff.get(rid, {"requirement_id": rid})
            base.setdefault("agent_status", base.get("status"))
            base.setdefault("agent_credit", base.get("credit"))
            base["status"] = o["status"]
            base["credit"] = o.get("credit")
            base["override"] = {"id": o["id"], "by": o.get("by"), "at": o.get("at"), "reason": o.get("reason")}
            eff[rid] = base
            status = "PROVISIONAL"
        elif t == "false_positive":
            dismissed.append(o)
            status = "PROVISIONAL"
        elif t == "comment":
            comments.append(o)
        elif t == "approve":
            status, approved_by, approved_at = "APPROVED", o.get("by"), o.get("at")
        elif t == "request_reevaluation":
            status = "REEVALUATION_REQUESTED"
    return eff, {"status": status, "approved_by": approved_by, "approved_at": approved_at,
                 "dismissed_findings": dismissed, "comments": comments}


def _round(x: float, q: str) -> float:
    return float(Decimal(str(x)).quantize(Decimal(q), rounding=ROUND_HALF_UP))


def compute(eval_dir: Path) -> dict:
    eval_dir = Path(eval_dir)
    ev = load_json(eval_dir / "evaluation.json")
    af = assignment_files(assignment_of(eval_dir))
    rubric = load_json(af["rubric"])
    req_doc = load_json(af["requirements"])
    reqs = req_doc["requirements"]
    by_id = {r["id"]: r for r in reqs}
    overrides = load_json(eval_dir / "overrides.json")["overrides"] if (eval_dir / "overrides.json").exists() else []
    run = load_json(eval_dir / "run.json") if (eval_dir / "run.json").exists() else {}
    sid = (ev.get("meta") or {}).get("submission_id") or run.get("submission_id")
    manifest_path = SUBMISSIONS / str(sid) / "manifest.json"
    known = {f["path"] for f in load_json(manifest_path)["files"]} if manifest_path.exists() else None
    hist_path = SUBMISSIONS / str(sid) / "metadata" / "history.json"
    commits = commits_from_history(load_json(hist_path)) if hist_path.exists() else None

    errors = check_config(rubric, reqs)
    warnings = []
    if known is None:
        warnings.append(f"Submission manifest for {sid!r} not found; evidence file paths were not checked.")

    # ---- validate agent assessments
    assessments = {}
    for i, a in enumerate(ev.get("assessments", [])):
        rid = a.get("requirement_id")
        ctx = f"assessments[{i}] ({rid})"
        if rid not in by_id:
            errors.append(f"{ctx}: unknown requirement id (no deduction for requirements not in the rubric)")
            continue
        if rid in assessments:
            errors.append(f"{ctx}: assessed more than once")
        assessments[rid] = a
        st = a.get("status")
        if st not in EVAL_STATUSES:
            errors.append(f"{ctx}: status {st!r} not in {sorted(EVAL_STATUSES)}")
            continue
        if st == "PASS" and not a.get("evidence"):
            errors.append(f"{ctx}: PASS without evidence (no credit without evidence)")
        if st in {"PARTIAL", "MISSING"}:
            if not a.get("deduction_reason"):
                errors.append(f"{ctx}: {st} requires deduction_reason (no deduction without justification)")
            if not a.get("evidence") and not a.get("searched"):
                errors.append(f"{ctx}: {st} requires evidence or 'searched' (no deduction without evidence)")
        if st == "PARTIAL" and a.get("credit") not in rubric["scoring"]["partial_credit_levels"]:
            errors.append(f"{ctx}: PARTIAL credit must be one of {rubric['scoring']['partial_credit_levels']}")
        if st == "NOT_APPLICABLE":
            if not by_id[rid].get("can_be_na"):
                errors.append(f"{ctx}: this requirement cannot be NOT_APPLICABLE")
            if not a.get("na_reason"):
                errors.append(f"{ctx}: NOT_APPLICABLE requires na_reason")
        check_evidence(a.get("evidence", []), known, ctx, errors, commits)
    for rid in by_id:
        if rid not in assessments:
            errors.append(f"{rid}: not assessed (every rubric requirement must be assessed)")
    for i, ind in enumerate((ev.get("integrity") or {}).get("indicators", [])):
        if not ind.get("evidence"):
            errors.append(f"integrity.indicators[{i}]: indicator without evidence")
        check_evidence(ind.get("evidence", []), known, f"integrity.indicators[{i}]", errors, commits)
    for o in overrides:
        if o.get("type") == "requirement":
            if o.get("requirement_id") not in by_id:
                errors.append(f"override {o.get('id')}: unknown requirement")
            if o.get("status") not in EVAL_STATUSES:
                errors.append(f"override {o.get('id')}: invalid status")
            if o.get("status") == "PARTIAL" and o.get("credit") not in rubric["scoring"]["partial_credit_levels"]:
                errors.append(f"override {o.get('id')}: PARTIAL credit must be one of {rubric['scoring']['partial_credit_levels']}")
        if o.get("type") in {"requirement", "false_positive", "request_reevaluation"} and not o.get("reason"):
            errors.append(f"override {o.get('id')}: a reason is required")
    if errors:
        raise ScoreError(errors)

    eff, review = apply_overrides(assessments, overrides)

    # ---- arithmetic
    criteria = []
    total = 0.0
    for c in rubric["criteria"]:
        items = [by_id[r["id"]] for r in reqs if r["criterion_id"] == c["id"]]
        applicable = [r for r in items if eff[r["id"]]["status"] != "NOT_APPLICABLE"]
        app_points = sum(r["points"] for r in applicable)
        earned = 0.0
        rows = []
        for r in items:
            a = eff[r["id"]]
            st = a["status"]
            credit = None if st == "NOT_APPLICABLE" else (a.get("credit") if st == "PARTIAL" else rubric["scoring"]["status_credit"][st])
            if credit is not None:
                earned += r["points"] * credit
            rows.append({"requirement_id": r["id"], "requirement": r["requirement"], "mandatory": r["mandatory"],
                         "points": r["points"], "status": st, "credit": credit,
                         "earned": None if credit is None else round(r["points"] * credit, 2),
                         "evidence": a.get("evidence", []), "searched": a.get("searched", []),
                         "deduction_reason": a.get("deduction_reason"), "na_reason": a.get("na_reason"),
                         "agent_status": a.get("agent_status"), "override": a.get("override")})
        if app_points == 0:
            score = float(c["points"])
            warnings.append(f"{c['id']}: all requirements NOT_APPLICABLE; full criterion points awarded. Professor should confirm.")
        else:
            score = earned / app_points * c["points"]
        score = _round(score, "0.01")
        total += score
        criteria.append({"id": c["id"], "name": c["name"], "points": c["points"], "score": score,
                         "comment": (ev.get("criterion_comments") or {}).get(c["id"]), "requirements": rows})
    total = _round(total, "0.1")
    rounded_total = int(Decimal(str(total)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    bands = sorted(rubric["grade_scale"]["bands"], key=lambda b: b["min"], reverse=True)
    grade = next(b["grade"] for b in bands if rounded_total >= b["min"])

    mandatory_failed = [r["requirement_id"] for c in criteria for r in c["requirements"]
                        if r["mandatory"] and r["status"] in {"MISSING", "PARTIAL"}]
    versions_now = collect_versions(af["id"])
    if run.get("versions") and run["versions"]["rubric"]["sha256"] != versions_now["rubric"]["sha256"]:
        warnings.append("The rubric changed after this evaluation started; re-run the evaluation.")
    if run.get("versions") and run["versions"]["requirements"]["sha256"] != versions_now["requirements"]["sha256"]:
        warnings.append("The requirements changed after this evaluation started; re-run the evaluation.")
    if rubric.get("status") == "PLACEHOLDER" or req_doc.get("status") == "PLACEHOLDER":
        warnings.append("PLACEHOLDER rubric/requirements in use; this is not an official grade.")

    result = {
        "submission_id": sid,
        "evaluation_id": (ev.get("meta") or {}).get("evaluation_id") or eval_dir.name,
        "scored_at": now_iso(),
        "review_status": review["status"],
        "approved_by": review["approved_by"],
        "approved_at": review["approved_at"],
        "total": total,
        "total_points": rubric["total_points"],
        "grade": grade,
        "criteria": criteria,
        "mandatory_requirements_not_met": mandatory_failed,
        "critical_issues": ev.get("critical_issues", []),
        "strengths": ev.get("strengths", []),
        "weaknesses": ev.get("weaknesses", []),
        "integrity": ev.get("integrity"),
        "dismissed_findings": review["dismissed_findings"],
        "professor_comments": review["comments"],
        "justification": ev.get("justification"),
        "meta": ev.get("meta"),
        "versions": {"at_evaluation_start": run.get("versions"), "at_scoring": versions_now},
        "integrity_check": run.get("integrity_check"),
        "overrides_applied": len([o for o in overrides if o.get("type") == "requirement"]),
        "warnings": warnings,
    }
    write_json(eval_dir / "final.json", result)
    write_text(eval_dir / "report.md", render(result))
    if sid and (SUBMISSIONS / sid / "submission.json").exists():
        project = load_json(SUBMISSIONS / sid / "submission.json")["project"]
        state.set_state(project, "GRADED", ref=f"{sid}/{eval_dir.name}", note=review["status"])
    return result


def _ev(e: dict) -> str:
    q = f' "{e["quote"]}"' if e.get("quote") else ""
    return f"`{e['file']}` {e.get('location', '')}{q}"


def render(r: dict) -> str:
    meta = r.get("meta") or {}
    sub = {}
    if r.get("submission_id") and (SUBMISSIONS / r["submission_id"] / "submission.json").exists():
        sub = load_json(SUBMISSIONS / r["submission_id"] / "submission.json")
    v = (r.get("versions") or {}).get("at_scoring") or {}
    vale = identity("professor")
    L = ["# FINAL PROJECT EVALUATION", "", f"_{vale.get('greeting', '')}_", ""]
    if r["warnings"]:
        L += ["> **Warnings**"] + [f"> - {w}" for w in r["warnings"]] + [""]
    L += [f"**Status:** {r['review_status']}" + (f" (approved by {r['approved_by']}, {r['approved_at']})" if r["approved_by"] and r["review_status"] == "APPROVED" else
                                                   " (awaiting professor approval)" if r["review_status"] == "PROVISIONAL" else ""), "",
          f"- Project: {sub.get('project', '?')}",
          f"- Student: {sub.get('student') or '?'}",
          f"- Submission: {r['submission_id']} (manifest {str(sub.get('manifest_sha256', ''))[:12]})",
          f"- Evaluation version: {r['evaluation_id']}",
          f"- Date: {r['scored_at']}",
          f"- Examiner: {vale['name']}, {vale['title']} (automated, Agent 2) / model {meta.get('model', '?')}",
          f"- Rubric {v.get('rubric', {}).get('version')} ({v.get('rubric', {}).get('status')}), "
          f"requirements {v.get('requirements', {}).get('version')}, KB {v.get('knowledge_base', {}).get('version')} "
          f"({v.get('knowledge_base', {}).get('content_sha256')}), prompts {v.get('agent_prompts')}",
          f"- Submission integrity check: {'intact' if (r.get('integrity_check') or {}).get('intact') else 'NOT VERIFIED / FAILED'}",
          ""]
    for n, c in enumerate(r["criteria"], start=1):
        L += [f"## {n}. {c['name']} ({c['id']})", f"**Score: {c['score']:g} / {c['points']}**", ""]
        if c.get("comment"):
            L += [c["comment"], ""]
        for q in c["requirements"]:
            badge = q["status"] + (f" ({q['credit']:g})" if q["status"] == "PARTIAL" else "")
            pts = "n/a" if q["earned"] is None else f"{q['earned']:g}/{q['points']}"
            L.append(f"- **{q['requirement_id']}** {badge}, {pts}{' (mandatory)' if q['mandatory'] else ''}")
            if q.get("override"):
                o = q["override"]
                L.append(f"  - Professor override {o['id']} (agent said {q['agent_status']}): {o['reason']} by {o.get('by')}")
            if q["evidence"]:
                L.append("  - Evidence: " + "; ".join(_ev(e) for e in q["evidence"]))
            if q["searched"] and q["status"] != "PASS":
                L.append("  - Searched: " + "; ".join(q["searched"]))
            if q["deduction_reason"] and q["status"] in {"PARTIAL", "MISSING"}:
                L.append(f"  - Reason for deduction: {q['deduction_reason']}")
            if q["na_reason"] and q["status"] == "NOT_APPLICABLE":
                L.append(f"  - Not applicable: {q['na_reason']}")
        L.append("")
    L += ["## TOTAL", f"**{r['total']:g} / {r['total_points']}**", "", "## GRADE", f"**{r['grade']}**", ""]
    L += ["## CRITICAL ISSUES"] + ([f"- {x}" for x in r["critical_issues"]] or ["- none recorded"])
    if r["mandatory_requirements_not_met"]:
        L.append("- Mandatory requirements not fully met: " + ", ".join(r["mandatory_requirements_not_met"]))
    L += ["", "## STRONG AREAS"] + ([f"- {x}" for x in r["strengths"]] or ["- none recorded"])
    L += ["", "## WEAKNESSES"] + ([f"- {x}" for x in r["weaknesses"]] or ["- none recorded"])
    integ = r.get("integrity") or {}
    L += ["", "## ACADEMIC INTEGRITY", f"Risk level: **{integ.get('risk_level', '?')}**"]
    for i, ind in enumerate(integ.get("indicators", [])):
        L.append(f"{i + 1}. [{ind.get('indicator_id')}] {ind.get('description')}: " + "; ".join(_ev(e) for e in ind.get("evidence", [])))
    for d in r["dismissed_findings"]:
        L.append(f"- Marked false positive by {d.get('by')}: {d.get('target')} ({d.get('reason')})")
    L += ["", f"_{integ.get('disclaimer', 'This review identifies risk indicators only. It does NOT establish misconduct. Human review is required.')}_", ""]
    L += ["## FINAL JUSTIFICATION", r.get("justification") or "-", ""]
    L += ["---", f"*{vale['signature']}*", ""]
    if r["professor_comments"]:
        L += ["## PROFESSOR COMMENTS"] + [f"- {c.get('by')} ({c.get('at')}): {c.get('text')}" for c in r["professor_comments"]] + [""]
    return "\n".join(L)
