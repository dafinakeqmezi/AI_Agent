---
description: Freeze a project (folder or GitHub repo) into an immutable FINAL_SUBMISSION for grading
argument-hint: <project-folder | owner/repo | GitHub URL> [student name] [--deadline <ISO+offset>] [--ref <branch|tag|sha>] [--team login1,login2]
---

Freeze the final submission. Arguments: `$ARGUMENTS` (first: project folder or GitHub repo; then the student name and options, all optional).

1. Show the user the project's current state: `python -m grader state <project-key>`. The key is the lowercased folder name; for GitHub repos it is `<owner>__<repo>`.
2. Run: `python -m grader freeze <project> --student "<student name>" [--assignment <id>] [--deadline ...] [--ref ...] [--team ...]`
   - `--assignment` records which assignment the submission belongs to (default `ml-project`; e.g. `detyra1`). Grading uses that assignment's requirements and rubric.
   - **GitHub + `--deadline`**: freezes the last commit on the branch made at or before the deadline. Later commits are excluded and reported. GitHub's push log is checked so that a commit dated before the deadline but pushed after it is flagged (INT-015).
   - **GitHub + `--ref`**: freezes that exact branch, tag or commit.
   - The git history is analysed at freeze time and stored, hash-protected, in `submissions/<id>/metadata/` (`history.json`, `history.md`, `github.json`).
   - A deadline must include a timezone offset, e.g. `2026-12-15T23:59:00+01:00`.
3. Report the `submission_id`, `git_commit`, file count, `manifest_sha256`, the number of commits excluded after the deadline, and any warnings (for example a project frozen while not READY_FOR_FINAL_REVIEW).
4. Tell the user that the submission is now immutable (read-only copy plus hash manifest of the files and history) and that the next step is `/grade <submission_id>`.

To freeze a whole class at once, use `/collect`. Never modify files under `submissions/` afterwards.
