---
description: Agent 1 - review an AI/ML project (iterative feedback + Definition of Done)
argument-hint: <project-folder | owner/repo | GitHub URL> [--assignment <id>] [--ref <branch>] [--deadline <ISO+offset>] [--team login1,login2] [--offline]
---

Run an Agent 1 review of: `$ARGUMENTS`

1. Prepare the run: `python -m grader new-review $ARGUMENTS`
   - A GitHub repo (`owner/repo` or URL) is cloned or updated into `projects/<owner>__<repo>/` through the GitHub API and git. Private repos need `GITHUB_TOKEN` set in the environment. Never ask the user to paste a token into the chat.
   - The git history is analysed into `artifacts/history.md` (scc code size per commit, timeline, authors, signals).
   - `--assignment <id>` selects the assignment (`python -m grader assignments` lists them; default `ml-project`). For a course assignment such as `detyra1`, pass it.
   Note `review_dir`, `project`, `assignment`, `assignment_files` and the project path (`run.json` → `project_path`) from the output. If it fails, stop and report the error.
2. Delegate to the **ml-reviewer** subagent with this prompt (fill in the values):
   > PROJECT: <absolute project path (the local mirror for GitHub repos)>
   > REVIEW_DIR: <review_dir>
   > ASSIGNMENT: <assignment>
   > ASSIGNMENT_FILES: <assignment_files as JSON>
   > Perform the full Agent 1 review (stages A-I), write review.json and review.md into REVIEW_DIR, and run the readiness check until it passes validation.
3. When the subagent returns, show the user:
   - the readiness verdict and counts (from `<review_dir>/readiness.md`)
   - the requirement status table (do not hide MISSING/BLOCKER items)
   - the top prioritized actions
   - the integrity risk level with the disclaimer
   - links to `review.md` and `readiness.md`
4. If the verdict is READY_FOR_FINAL_REVIEW, mention that the next step is `/freeze <project-folder> <student name>`.
