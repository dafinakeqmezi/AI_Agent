"""Agent 1 Definition of Done: validates review.json and computes READY_FOR_FINAL_REVIEW / NOT_READY."""
from __future__ import annotations

from pathlib import Path

from .common import assignment_files, assignment_of, identity, load_json, now_iso, write_json, write_text
from .validate import check_evidence, commits_from_history

REVIEW_STATUSES = {"PASS", "PARTIAL", "MISSING", "NOT_APPLICABLE", "BLOCKER"}
RISK_LEVELS = {"NONE_FOUND", "NEEDS_REVIEW", "HIGH_CONCERN"}


def verdict_label(verdict, albanian=False):
    if verdict == "NOT_READY":
        return "E papërfunduar" if albanian else "Not completed"
    return verdict


def validate_review(review: dict, reqs: list[dict], known_paths: set[str] | None,
                    known_commits: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    by_id = {r["id"]: r for r in reqs}
    seen = set()
    for i, a in enumerate(review.get("requirements", [])):
        rid = a.get("requirement_id")
        ctx = f"requirements[{i}] ({rid})"
        if rid not in by_id:
            errors.append(f"{ctx}: unknown requirement id")
            continue
        if rid in seen:
            errors.append(f"{ctx}: assessed more than once")
        seen.add(rid)
        st = a.get("status")
        if st not in REVIEW_STATUSES:
            errors.append(f"{ctx}: status {st!r} not in {sorted(REVIEW_STATUSES)}")
            continue
        if st == "PASS" and not a.get("evidence"):
            errors.append(f"{ctx}: PASS requires evidence (no credit without evidence)")
        if st in {"PARTIAL", "MISSING", "BLOCKER"}:
            if not a.get("finding"):
                errors.append(f"{ctx}: {st} requires a 'finding'")
            if not a.get("evidence") and not a.get("searched"):
                errors.append(f"{ctx}: {st} requires 'evidence' or 'searched' (where you looked)")
        if st == "NOT_APPLICABLE":
            if not by_id[rid].get("can_be_na"):
                errors.append(f"{ctx}: requirement cannot be NOT_APPLICABLE")
            if not a.get("na_reason"):
                errors.append(f"{ctx}: NOT_APPLICABLE requires 'na_reason'")
        check_evidence(a.get("evidence", []), known_paths, ctx, errors, known_commits)
    for rid in by_id:
        if rid not in seen:
            errors.append(f"{rid}: no status given (every requirement must have a status)")
    for i, f in enumerate(review.get("findings", [])):
        check_evidence(f.get("evidence", []), known_paths, f"findings[{i}]", errors, known_commits)
        if f.get("type") not in {"FACT", "RECOMMENDATION"}:
            errors.append(f"findings[{i}]: type must be FACT or RECOMMENDATION")
    integ = review.get("integrity") or {}
    if integ.get("risk_level") not in RISK_LEVELS:
        errors.append(f"integrity.risk_level must be one of {sorted(RISK_LEVELS)}")
    if not integ.get("disclaimer"):
        errors.append("integrity.disclaimer is required (risk indicators only; not a misconduct finding)")
    for i, ind in enumerate(integ.get("indicators", [])):
        if not ind.get("evidence"):
            errors.append(f"integrity.indicators[{i}]: every indicator needs evidence")
        check_evidence(ind.get("evidence", []), known_paths, f"integrity.indicators[{i}]", errors, known_commits)
    return errors


def evaluate(review_dir: Path) -> dict:
    review_dir = Path(review_dir)
    review = load_json(review_dir / "review.json")
    af = assignment_files(assignment_of(review_dir))
    reqs = load_json(af["requirements"])["requirements"]
    dod = load_json(af["dod"])
    inv_path = review_dir / "artifacts" / "inventory.json"
    known = {f["path"] for f in load_json(inv_path)["files"]} if inv_path.exists() else None
    hist_path = review_dir / "artifacts" / "history.json"
    commits = commits_from_history(load_json(hist_path)) if hist_path.exists() else None

    errors = validate_review(review, reqs, known, commits)
    status = {a["requirement_id"]: a for a in review.get("requirements", []) if "requirement_id" in a}
    by_id = {r["id"]: r for r in reqs}
    c = dod["conditions"]
    failed = []
    blockers = [rid for rid, a in status.items() if a.get("status") == "BLOCKER"]
    mandatory_not_pass = [r["id"] for r in reqs if r["mandatory"]
                          and status.get(r["id"], {}).get("status") not in {"PASS", "NOT_APPLICABLE"}]
    must_pass_fail = [rid for rid in c.get("must_pass", []) if status.get(rid, {}).get("status") != "PASS"]
    missing = [rid for rid, a in status.items() if a.get("status") == "MISSING"]
    partial = [rid for rid, a in status.items() if a.get("status") == "PARTIAL"]
    risk = (review.get("integrity") or {}).get("risk_level")

    if errors:
        failed.append("review.json failed validation")
    if c.get("no_blockers") and blockers:
        failed.append(f"{len(blockers)} blocker(s)")
    if c.get("all_mandatory_pass") and mandatory_not_pass:
        failed.append(f"{len(mandatory_not_pass)} mandatory requirement(s) not PASS")
    if must_pass_fail:
        failed.append(f"must-pass requirement(s) not PASS: {', '.join(must_pass_fail)}")
    if risk in c.get("integrity_must_not_be", []):
        failed.append(f"integrity risk level {risk} requires human review first")

    verdict = "READY_FOR_FINAL_REVIEW" if not failed else "NOT_READY"
    result = {
        "verdict": verdict,
        "verdict_label": verdict_label(verdict),
        "evaluated_at": now_iso(),
        "failed_conditions": failed,
        "validation_errors": errors,
        "counts": {"blockers": len(blockers), "missing": len(missing), "partial": len(partial),
                   "recommendations": len(review.get("recommendations", []))},
        "blockers": blockers, "mandatory_not_pass": mandatory_not_pass, "missing": missing, "partial": partial,
        "integrity_risk_level": risk,
        "reproducibility": review.get("reproducibility"),
    }
    write_json(review_dir / "readiness.json", result)

    ada = identity("ml-reviewer")
    lines = [f"# Project completion: {verdict_label(verdict)}", "", f"Review by {ada['name']}, {ada['title']} (automated, Agent 1). "
             "Verdict computed by the toolkit from the Definition of Done.", ""]
    if verdict == "NOT_READY":
        lines += ["The review finished, but the project's completion requirements are not all satisfied. "
                  "The project can still be frozen and graded.", ""]
        lines += [f"- {result['counts']['blockers']} blocker(s)", f"- {len(mandatory_not_pass)} mandatory requirement(s) not passing",
                  f"- {len(missing)} missing, {len(partial)} partial requirement(s)",
                  f"- {result['counts']['recommendations']} recommendation(s)", ""]
        lines += ["Failed DoD conditions:"] + [f"- {f}" for f in failed] + [""]
    if errors:
        lines += ["## Validation errors (Agent 1 must fix review.json)", ""] + [f"- {e}" for e in errors] + [""]
    lines += ["## Requirement status", "", "| Requirement | Category | Mandatory | Status |", "|---|---|---|---|"]
    for r in reqs:
        st = status.get(r["id"], {}).get("status", "NO STATUS")
        lines.append(f"| {r['id']} | {r['category']} | {'yes' if r['mandatory'] else 'no'} | {st} |")
    rp = review.get("reproducibility") or {}
    if rp:
        lines += ["", f"Reproducibility score: {rp.get('score')}/{rp.get('max', 10)}"]
        lines += [f"- missing: {m}" for m in rp.get("missing", [])]
    lines += ["", f"Integrity risk level: {risk} (indicators only; not a misconduct finding)"]
    write_text(review_dir / "readiness.md", "\n".join(lines) + "\n")
    return result
