"""Check an Agent 1 review or an Agent 2 evaluation against an expected-findings file.

Used with the controlled sample projects in sample-projects/ (answer keys in tests/expected/),
so that "does the agent find the planted problems?" is a pass/fail test instead of a judgement call.

Expected file:
{
  "project": "...",
  "fixture": "sample-projects/...",
  "expected_findings": [
    {"requirement_id": "DATA-004", "label": "target leakage", "status": "BLOCKER",
     "also_acceptable": [], "core": true, "why": "..."}
  ],
  "not_asserted": [{"requirement_id": "VCS-001", "reason": "..."}],
  "review": {"readiness": "NOT_READY", "integrity_risk_level": ["..."], "min_agreement": 0.8},
  "evaluation": {"total_range": [lo, hi], "grade_range": [lo, hi], "integrity_risk_level": ["..."],
                 "min_agreement": 0.8}
}

A run fails if any of these hold:
  - a core finding does not match (status or also_acceptable)
  - an expected BLOCKER is not reported as BLOCKER (review) / MISSING (evaluation)
  - the agent reports PASS where a problem is expected (missed problem)
  - the agent reports MISSING/BLOCKER where PASS is expected (false deduction)
  - the agent reports a BLOCKER that the expected file does not allow (review)
  - agreement over all asserted requirements is below min_agreement
  - readiness verdict, integrity risk level, total or grade fall outside the expectation
"""
from __future__ import annotations

from pathlib import Path

from .common import REQUIREMENTS_FILE, load_json, now_iso, write_json, write_text

PROBLEM = {"PARTIAL", "MISSING", "BLOCKER"}


def _accepted(f: dict, mode: str) -> tuple[set[str], set[str]]:
    """(exact, acceptable) statuses for one expected finding. Evaluations have no BLOCKER: it maps to MISSING."""
    exact = {f["status"]}
    ok = set(f.get("also_acceptable", []))
    if mode == "evaluation":
        exact = {"MISSING" if s == "BLOCKER" else s for s in exact}
        ok = {"MISSING" if s == "BLOCKER" else s for s in ok} - exact
    return exact, ok


def validate_expected(spec: dict, reqs: list[dict]) -> list[str]:
    errors = []
    by_id = {r["id"]: r for r in reqs}
    valid = {"PASS", "PARTIAL", "MISSING", "NOT_APPLICABLE", "BLOCKER"}
    seen = set()
    for f in spec.get("expected_findings", []):
        rid = f.get("requirement_id")
        if rid not in by_id:
            errors.append(f"{rid}: unknown requirement id")
            continue
        if rid in seen:
            errors.append(f"{rid}: listed more than once")
        seen.add(rid)
        for s in [f.get("status"), *f.get("also_acceptable", [])]:
            if s not in valid:
                errors.append(f"{rid}: invalid status {s!r}")
            if s == "NOT_APPLICABLE" and not by_id[rid].get("can_be_na"):
                errors.append(f"{rid}: requirement cannot be NOT_APPLICABLE")
    for n in spec.get("not_asserted", []):
        if n.get("requirement_id") not in by_id:
            errors.append(f"not_asserted {n.get('requirement_id')}: unknown requirement id")
        if n.get("requirement_id") in seen:
            errors.append(f"{n.get('requirement_id')}: both asserted and not_asserted")
        if not n.get("reason"):
            errors.append(f"not_asserted {n.get('requirement_id')}: reason required")
    covered = seen | {n.get("requirement_id") for n in spec.get("not_asserted", [])}
    for rid in by_id:
        if rid not in covered:
            errors.append(f"{rid}: neither asserted nor listed in not_asserted")
    return errors


def compare(actual: dict[str, str], spec: dict, mode: str) -> dict:
    """actual: requirement_id -> status reported by the agent."""
    rows, failures = [], []
    agree = asserted = 0
    expected_ids = set()
    for f in spec["expected_findings"]:
        rid = f["requirement_id"]
        expected_ids.add(rid)
        exact, ok = _accepted(f, mode)
        got = actual.get(rid)
        asserted += 1
        if got is None:
            result = "NOT_ASSESSED"
        elif got in exact:
            result = "MATCH"
        elif got in ok:
            result = "ACCEPTABLE"
        else:
            result = "MISMATCH"
        if result in {"MATCH", "ACCEPTABLE"}:
            agree += 1
        problems = []
        if result in {"MISMATCH", "NOT_ASSESSED"}:
            if f.get("core"):
                problems.append("core finding not matched")
            if f["status"] == "BLOCKER":
                problems.append("missed blocker")
            if got == "PASS" and f["status"] in PROBLEM:
                problems.append("missed problem (agent PASS)")
            if f["status"] == "PASS" and got in {"MISSING", "BLOCKER"}:
                problems.append(f"false deduction (agent {got})")
        for p in problems:
            failures.append(f"{rid} ({f.get('label', '')}): {p}; expected {f['status']}"
                            + (f" (or {', '.join(f.get('also_acceptable', []))})" if f.get("also_acceptable") else "")
                            + f", got {got}")
        rows.append({"requirement_id": rid, "label": f.get("label"), "core": bool(f.get("core")),
                     "expected": f["status"], "also_acceptable": f.get("also_acceptable", []),
                     "actual": got, "result": result, "problems": problems})
    if mode == "review":
        ignored = {n["requirement_id"] for n in spec.get("not_asserted", [])}
        allowed = {f["requirement_id"] for f in spec["expected_findings"]
                   if "BLOCKER" in [f["status"], *f.get("also_acceptable", [])]}
        for rid, st in sorted(actual.items()):
            if st == "BLOCKER" and rid not in allowed and rid not in ignored:
                failures.append(f"{rid}: unexpected BLOCKER (not allowed by the expected file)")
    agreement = round(agree / asserted, 3) if asserted else None
    return {"rows": rows, "failures": failures, "agreement": agreement, "asserted": asserted,
            "counts": {k: sum(1 for r in rows if r["result"] == k)
                       for k in ("MATCH", "ACCEPTABLE", "MISMATCH", "NOT_ASSESSED")}}


def _in_range(x, rng) -> bool:
    return rng is None or (x is not None and rng[0] <= x <= rng[1])


def check(run_dir: Path, expected_file: Path) -> dict:
    run_dir, expected_file = Path(run_dir), Path(expected_file)
    spec = load_json(expected_file)
    reqs = load_json(REQUIREMENTS_FILE)["requirements"]
    spec_errors = validate_expected(spec, reqs)
    if spec_errors:
        raise ValueError("Invalid expected file:\n" + "\n".join(spec_errors))

    if (run_dir / "review.json").exists():
        mode = "review"
        review = load_json(run_dir / "review.json")
        actual = {a["requirement_id"]: a.get("status") for a in review.get("requirements", []) if "requirement_id" in a}
        risk = (review.get("integrity") or {}).get("risk_level")
    elif (run_dir / "final.json").exists():
        mode = "evaluation"
        final = load_json(run_dir / "final.json")
        actual = {q["requirement_id"]: q["status"] for c in final["criteria"] for q in c["requirements"]}
        risk = (final.get("integrity") or {}).get("risk_level")
    else:
        raise FileNotFoundError(f"{run_dir}: no review.json (Agent 1) or final.json (Agent 2) found")

    exp = spec.get(mode) or {}
    res = compare(actual, spec, mode)
    failures = res["failures"]
    min_agree = exp.get("min_agreement", 0.8)
    if res["agreement"] is not None and res["agreement"] < min_agree:
        failures.append(f"agreement {res['agreement']} below min_agreement {min_agree}")
    if exp.get("integrity_risk_level") and risk not in exp["integrity_risk_level"]:
        failures.append(f"integrity risk level {risk} not in {exp['integrity_risk_level']}")

    out = {"checked_at": now_iso(), "mode": mode, "run_dir": str(run_dir), "expected_file": str(expected_file),
           "project": spec.get("project"), "integrity_risk_level": risk}
    if mode == "review":
        rd = load_json(run_dir / "readiness.json") if (run_dir / "readiness.json").exists() else {}
        out["readiness"] = rd.get("verdict")
        if exp.get("readiness") and rd and rd.get("verdict") != exp["readiness"]:
            failures.append(f"readiness {rd.get('verdict')} != expected {exp['readiness']}")
        if exp.get("readiness") and not rd:
            failures.append("readiness.json not found; run `python -m grader readiness` first")
    else:
        out["total"], out["grade"] = final.get("total"), final.get("grade")
        if not _in_range(final.get("total"), exp.get("total_range")):
            failures.append(f"total {final.get('total')} outside expected range {exp['total_range']}")
        if not _in_range(final.get("grade"), exp.get("grade_range")):
            failures.append(f"grade {final.get('grade')} outside expected range {exp['grade_range']}")

    out.update({"verdict": "PASS" if not failures else "FAIL", "agreement": res["agreement"],
                "min_agreement": min_agree, "counts": res["counts"], "failures": failures, "rows": res["rows"]})
    write_json(run_dir / "expected-check.json", out)
    write_text(run_dir / "expected-check.md", render(out))
    return out


def render(r: dict) -> str:
    L = [f"# Expected-findings check: {r['verdict']}", "",
         f"- Project: {r['project']} ({r['mode']})",
         f"- Expected file: `{r['expected_file']}`",
         f"- Agreement: {r['agreement']} (minimum {r['min_agreement']}); " +
         ", ".join(f"{k.lower()} {v}" for k, v in r["counts"].items()),
         f"- Integrity risk level: {r['integrity_risk_level']}"]
    if r["mode"] == "review":
        L.append(f"- Readiness: {r.get('readiness')}")
    else:
        L.append(f"- Total: {r.get('total')}, grade: {r.get('grade')}")
    L += ["", "## Failures", ""] + ([f"- {f}" for f in r["failures"]] or ["- none"])
    L += ["", "## Requirements", "", "| Requirement | Label | Core | Expected | Actual | Result |", "|---|---|---|---|---|---|"]
    for x in r["rows"]:
        exp = x["expected"] + (f" (or {', '.join(x['also_acceptable'])})" if x["also_acceptable"] else "")
        L.append(f"| {x['requirement_id']} | {x['label'] or ''} | {'yes' if x['core'] else ''} | {exp} | "
                 f"{x['actual']} | {x['result']} |")
    return "\n".join(L) + "\n"
