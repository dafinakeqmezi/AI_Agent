---
description: Evaluate the evaluator - compare Agent 2 grades with human professor grades
---

1. Check that `benchmark/human_grades.json` lists at least one project with a `submission_id` that has an Agent 2 evaluation (`evaluations/<submission_id>/*/final.json`). If none have been evaluated, list what is missing and stop.
2. Run `python -m grader benchmark`.
3. Present `benchmark/results.md`: total MAE, criterion agreement, requirement-status agreement, false deductions, missed problems, planted-issue recall, and false or missed integrity flags.
4. Point out the patterns in the disagreements, such as a criterion where the agent is systematically harsher, or a planted issue type that is never caught. Suggest concrete changes to `requirements.json` wording or the professor prompt. Do not apply them without approval, because any change to them requires re-running the benchmark.
