---
description: Professor - override a score, mark a false positive, comment, approve, or request re-evaluation
argument-hint: <evaluation-dir> <what to change, in plain words>
---

The professor wants to change an evaluation: `$ARGUMENTS`

Translate the request into one or more `python -m grader override` calls. Always pass `--by "<professor name>"`. If the name is not known, ask once.

| Request | Command |
|---|---|
| Change a requirement's result | `python -m grader override <dir> --requirement DATA-004 --status PARTIAL --credit 0.5 --reason "..." --by "..."` |
| Mark a finding / integrity indicator as a false positive | `python -m grader override <dir> --false-positive "integrity.indicators[0]" --reason "..." --by "..."` |
| Add a comment | `python -m grader override <dir> --comment "..." --by "..."` |
| Accept the grade | `python -m grader override <dir> --approve --by "..."` |
| Request re-evaluation | `python -m grader override <dir> --request-reevaluation --reason "..." --by "..."` |

Rules:
- A reason is required for every change. Ask for one if it is missing; do not make one up.
- Overrides are append-only. The grade is recomputed after each one, and the report shows the agent's original status next to the professor's.
- Any change after approval returns the evaluation to PROVISIONAL until it is approved again.
- Show the new total, grade and status after the commands run.
