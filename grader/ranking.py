"""Class ranking for one assignment: the latest Agent 2 grade of every student's latest submission, ranked by total.

The ranking only orders grades the toolkit already computed (python -m grader score); it computes no new points.
Similarity and integrity indicators are shown next to each student for the professor; they never change the order.
Output: evaluations/_class/<assignment>/ranking-<ts>/ranking.json + ranking.md
"""
from __future__ import annotations

from pathlib import Path

from . import similarity
from .common import EVALUATIONS, ROOT, SUBMISSIONS, assignment_files, load_json, now_iso, stamp, write_json, write_text

STUDENTS_FILE = ROOT / "projects" / "students.json"
LEVEL_ORDER = ["NONE", "LOW", "MEDIUM", "HIGH"]


def _display_names() -> dict[str, str]:
    try:
        return {str(k).lower(): v for k, v in (load_json(STUDENTS_FILE).get("students") or {}).items() if v}
    except (OSError, ValueError):
        return {}


def latest_final(sid: str) -> tuple[Path, dict] | None:
    """Latest scored evaluation of a submission, skipping toolkit smoke tests."""
    runs = sorted((EVALUATIONS / sid).glob("eval-*/final.json")) if (EVALUATIONS / sid).exists() else []
    for f in reversed(runs):
        d = load_json(f)
        meta = d.get("meta") or {}
        if any(w in f"{meta.get('evaluator', '')} {d.get('justification', '')}".lower() for w in ("smoke", "wiring test")):
            continue
        return f.parent, d
    return None


def compute(assignment: str | None = None, ids: list[str] | None = None, roster: str | None = None) -> dict:
    """The class is: explicit ids, else the roster's repos, else the submissions of the latest similarity report
    (the latest class run), else every latest submission of the assignment."""
    aid = assignment_files(assignment)["id"]
    rubric = load_json(assignment_files(aid)["rubric"])
    names = _display_names()
    sim = similarity.latest(aid)
    sim_by_sid: dict[str, list[dict]] = {}
    for p in (sim or {}).get("pairs", []):
        if p["level"] == "NONE":
            continue
        for me, other in ((p["a"], p["b"]), (p["b"], p["a"])):
            sim_by_sid.setdefault(me, []).append({"with": other, "level": p["level"], "reasons": p["reasons"]})

    rows = []
    if not ids and not roster and sim:
        ids = [x for x in sim.get("submissions", []) if (SUBMISSIONS / x / "submission.json").exists()]
    for sid in similarity.class_submissions(aid, ids, roster):
        sub = load_json(SUBMISSIONS / sid / "submission.json")
        fin = latest_final(sid)
        partners = sorted(sim_by_sid.get(sid, []), key=lambda x: -LEVEL_ORDER.index(x["level"]))
        row = {"submission_id": sid, "project": sub.get("project"),
               "student": names.get(str(sub.get("project")).lower()) or sub.get("student"),
               "similarity_level": partners[0]["level"] if partners else ("NONE" if sim else None),
               "similar_to": partners, "graded": bool(fin)}
        if fin:
            d, f = fin
            row.update(total=f["total"], grade=f["grade"], status=f.get("review_status"),
                       criteria={c["id"]: c["score"] for c in f["criteria"]},
                       integrity=(f.get("integrity") or {}).get("risk_level"),
                       mandatory_not_met=f.get("mandatory_requirements_not_met", []),
                       evaluation=str(d.relative_to(ROOT)) if d.is_relative_to(ROOT) else str(d))
        rows.append(row)

    graded = sorted([r for r in rows if r["graded"]], key=lambda r: (-r["total"], str(r["student"] or "")))
    rank, prev = 0, None
    for i, r in enumerate(graded, start=1):
        if r["total"] != prev:
            rank, prev = i, r["total"]
        r["rank"] = rank  # equal totals share a rank (1, 2, 2, 4)
    ungraded = [dict(r, rank=None) for r in rows if not r["graded"]]
    return {"generated_at": now_iso(), "assignment": aid,
            "rubric": {"version": rubric.get("version"), "status": rubric.get("status"),
                       "criteria": [{"id": c["id"], "name": c["name"], "points": c["points"]} for c in rubric["criteria"]]},
            "similarity_report": (sim or {}).get("generated_at"),
            "rows": graded + ungraded,
            "note": "Ranked by the total computed by python -m grader score. Similarity and integrity levels are "
                    "review indicators for the professor and do not change the order or any score."}


def run(assignment: str | None = None, out: Path | None = None, roster: str | None = None) -> dict:
    r = compute(assignment, roster=roster)
    out = Path(out) if out else EVALUATIONS / "_class" / r["assignment"] / f"ranking-{stamp()}"
    write_json(out / "ranking.json", r)
    write_text(out / "ranking.md", render(r))
    r["out_dir"] = str(out)
    return r


def render(r: dict) -> str:
    crit = r["rubric"]["criteria"]
    L = [f"# Class ranking: {r['assignment']}", "", f"Generated {r['generated_at']} · rubric {r['rubric']['version']} "
         f"({r['rubric']['status']}) · similarity report {r['similarity_report'] or 'none (run python -m grader similarity)'}", "",
         f"> {r['note']}", "",
         "| Rank | Student | Total | Grade | " + " | ".join(f"{c['id']} /{c['points']}" for c in crit) + " | Integrity | Similarity | Status |",
         "|---" * (7 + len(crit)) + "|"]
    for x in r["rows"]:
        sim = x["similarity_level"] or "-"
        if x["similar_to"]:
            sim += " (" + ", ".join(f"{s['with']}: {s['level']}" for s in x["similar_to"][:3]) + ")"
        if x["graded"]:
            L.append(f"| {x['rank']} | {x['student'] or '?'} | {x['total']} | {x['grade']} | " +
                     " | ".join(str(x["criteria"].get(c["id"], "")) for c in crit) +
                     f" | {x['integrity'] or '-'} | {sim} | {x['status']} |")
        else:
            L.append(f"| - | {x['student'] or '?'} | not graded | | " + " | ".join("" for _ in crit) + f" | | {sim} | |")
    return "\n".join(L) + "\n"
