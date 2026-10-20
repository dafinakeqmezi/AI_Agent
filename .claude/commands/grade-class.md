---
description: Grade a whole class for one assignment - cross-student similarity, Agent 2 evaluation of every submission, class ranking
argument-hint: <assignment-id> [--submissions id1,id2,...] [--base <starter-code-folder>]
---

Grade every frozen submission of the assignment: `$ARGUMENTS`

The submissions must already be frozen (`/collect` for GitHub repos, or `/freeze <project> "<student>" --assignment <id>`).

1. **List the class.** Run `python -m grader assignments` to confirm the assignment exists, then list its latest submission per student:
   `python -c "from grader.similarity import class_submissions; print(class_submissions('<assignment>'))"` (or use `--submissions`).
   Show the user the list (student, submission id, frozen commit). If it is empty, stop and point to `/collect` or `/freeze`.

2. **Similarity between students:** `python -m grader similarity --assignment <assignment> [--submissions ...] [--base <starter-code-folder>]`
   Pass `--base` when the professor gave starter code, so that it is not counted as copying. Report the counts of HIGH / MEDIUM / LOW pairs and list the HIGH and MEDIUM pairs with their reasons. These are review priorities, not findings.

3. **Grade each submission** with the `/grade` procedure (phase 1 independent, snapshot, phase 2 discrepancy check, verify), one submission at a time or several in parallel (independent subagents; at most 4 at once).
   - For each: `python -m grader new-evaluation <id>`, then delegate to the **professor** subagent with PHASE 1, SUBMISSION_ID, SUBMISSION_FILES, EVAL_DIR, ASSIGNMENT and ASSIGNMENT_FILES from that output.
   - Add to the phase-1 prompt: "The class similarity report is <path to similarity.md>; read only the pairs that involve this submission and report them as INT-016/INT-017 indicators."
   - Never pass Agent 1's review or another student's evaluation in phase 1. Phase 2 uses `python -m grader latest-review <project>` as in `/grade` (or `none`).

4. **Ranking:** `python -m grader ranking --assignment <assignment>`. It ranks by the totals the toolkit computed; it computes no new points.

5. **Dashboard:** `python -m grader dashboard` (tabs: Projects, Ranking, Similarity).

6. **Present to the user:**
   - the ranking table (rank, student, total, grade, criterion scores, integrity, similarity), all PROVISIONAL
   - the HIGH/MEDIUM similarity pairs with the strongest evidence (matched regions, identical files, foreign-identity commits, who had the code first)
   - submissions with critical issues or HIGH_CONCERN integrity
   - the reminder that similarity and integrity indicators are not proof of copying and never change scores; the professor reviews them and decides
   - how to approve or override: `/override <evaluation_dir> ...`
