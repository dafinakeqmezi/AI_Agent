"""Render validated review data locally instead of asking the model to repeat it."""
from __future__ import annotations

from html import escape

from .common import identity
from .readiness import verdict_label


def text(value):
    return escape(str(value), quote=False).replace("|", "\\|")


def details(value, depth=0):
    """Keep every supplied field, including evidence and uncertainty, in readable bullets."""
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append("  " * depth + f"- **{text(key)}**:")
                lines.extend(details(item, depth + 1))
            else:
                lines.append("  " * depth + f"- **{text(key)}**: {text(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                # A separate list entry preserves each finding's field grouping.
                lines.append("  " * depth + "-")
                lines.extend(details(item, depth + 1))
            else:
                lines.append("  " * depth + "- " + text(item))
        return lines or ["  " * depth + "- —"]
    return ["  " * depth + text(value)]


def render_review(document, readiness, assignment):
    albanian = assignment == "detyra1"
    headings = ({"title": "Rishikimi i projektit", "summary": "Përmbledhje", "requirements": "Kërkesat",
                 "findings": "Gjetjet", "report_vs_code": "Raporti kundrejt kodit",
                 "claims_ledger": "Pohimet dhe provat", "literature": "Literatura",
                 "reproducibility": "Riprodhueshmëria", "integrity": "Integriteti akademik",
                 "recommendations": "Veprimet e prioritizuara", "limitations": "Kufizimet"}
                if albanian else
                {"title": "Project review", "summary": "Summary", "requirements": "Requirements",
                 "findings": "Findings", "report_vs_code": "Report versus code", "claims_ledger": "Claims ledger",
                 "literature": "Literature", "reproducibility": "Reproducibility", "integrity": "Academic integrity",
                 "recommendations": "Prioritized actions", "limitations": "Limitations"})
    ada = identity("ml-reviewer")
    lines = ["# " + headings["title"], "", ada["greeting"], "", "## " + headings["summary"], "",
             "**" + text(verdict_label(readiness["verdict"], albanian)) + "**", ""]
    lines.extend(details(readiness.get("counts", {})))
    lines += ["", "## " + headings["requirements"], "",
              "| ID | Status |", "|---|---|"]
    for row in document.get("requirements", []):
        lines.append(f"| {text(row['requirement_id'])} | {text(row['status'])} |")
    for row in document.get("requirements", []):
        lines += ["", f"### {text(row['requirement_id'])} · {text(row['status'])}", ""]
        lines.extend(details({k: v for k, v in row.items() if k not in {"requirement_id", "status"}}))
    known = {"meta", "requirements"}
    for key in ("findings", "report_vs_code", "claims_ledger", "literature", "reproducibility", "integrity", "recommendations", "limitations"):
        known.add(key)
        if key in document:
            lines += ["", "## " + headings[key], ""]
            lines.extend(details(document[key]))
    for key, value in document.items():
        if key not in known:
            lines += ["", "## " + text(key), ""]
            lines.extend(details(value))
    lines += ["", ada["signature"], ""]
    return "\n".join(lines)
