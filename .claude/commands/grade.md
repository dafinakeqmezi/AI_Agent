---
description: Agent 2 - independent final evaluation of a frozen submission, then discrepancy check against Agent 1
argument-hint: <submission-id> [--offline]
---

Grade the frozen submission: `$ARGUMENTS`

1. **Prepare and verify:** `python -m grader new-evaluation $ARGUMENTS`
   This refuses to continue if the submission's hashes do not match its manifest. Note `evaluation_dir`, `submission_files`, `assignment` and `assignment_files` (the assignment comes from the frozen submission).

2. **Phase 1 (independent):** delegate to the **professor** subagent:
   > PHASE: 1
   > SUBMISSION_ID: <id>
   > SUBMISSION_FILES: <submission_files>
   > EVAL_DIR: <evaluation_dir>
   > ASSIGNMENT: <assignment>
   > ASSIGNMENT_FILES: <assignment_files as JSON>
   > Evaluate criterion by criterion. Do not open reviews/ or other evaluations. Write evaluation.json and run the score command until it validates.

   Do **not** pass Agent 1's review or any of its conclusions in this prompt.

3. **Snapshot phase 1:** copy `<evaluation_dir>/evaluation.json` to `<evaluation_dir>/evaluation.phase1.json`, and `final.json` to `final.phase1.json`.

4. **Phase 2 (discrepancy check):** find Agent 1's latest review with `python -m grader latest-review <project>`. The project key is in `submissions/<id>/submission.json`. Then delegate to the **professor** subagent again:
   > PHASE: 2
   > SUBMISSION_ID / SUBMISSION_FILES / EVAL_DIR / ASSIGNMENT / ASSIGNMENT_FILES: (same as above)
   > AGENT1_REVIEW: <path to review.json, or "none">
   > Run the discrepancy check, write discrepancies.md, and re-score only for corrections backed by evidence you verified yourself.

5. **Verify again:** `python -m grader verify <submission-id>`. It must still be intact.

6. **Present to the user:**
   - total, grade and status (PROVISIONAL until the professor approves)
   - the criterion score table
   - critical issues, strengths, weaknesses
   - the academic integrity section with its disclaimer
   - the discrepancy summary, including any phase 1 → final change
   - any warnings (for example a PLACEHOLDER rubric)
   - links to `report.md`, `discrepancies.md` and `final.json`
   - how to override or approve: `/override <evaluation_dir> ...`
