---
description: Collect student GitHub repos (org / Classroom prefix) and freeze them all at the deadline
argument-hint: [--org <org> [--prefix <repo-prefix>] | --roster projects/roster.json] --assignment <id> --deadline <ISO+offset>
---

Collect and freeze a class's GitHub repositories: `$ARGUMENTS`

1. Check access: if the repos are private, `GITHUB_TOKEN` must be set in the environment (fine-grained token with read access to Contents and Metadata, or a classic token with `repo`). Check only whether it is set; never print it, and never ask the user to paste it into the chat.
2. **Repos in the students' personal accounts** (no organisation): the roster is written by hand. Create `projects/roster.json` like this, one entry per student, and ask the user to fill it in:
   ```json
   {"course": "AI 2026/27", "assignment": "detyra1", "deadline": "2026-11-01T23:59:00+01:00",
    "students": [{"student": "Emri Mbiemri", "repo": "github-user/repo-name", "team": ["github-user"]}]}
   ```
   Private repos need the professor's account added as collaborator (or a token that can read them). Public repos work without a token (60 API requests/hour; set `GITHUB_TOKEN` for more).
   **Repos in an organisation / GitHub Classroom**: if `projects/roster.json` does not exist, create it from the org:
   `python -m grader github repos --org <org> [--prefix <prefix>] --deadline <deadline> --write-roster projects/roster.json`
   Show the list, and ask the user to fill in each student's name and `team` (GitHub logins) in the roster. Team lists matter for VCS-005 and for spotting outside authors. Stop here until the roster is confirmed.
3. Freeze all: `python -m grader github freeze-all --roster projects/roster.json [--assignment <id>] [--deadline <deadline>]` (the assignment can also be set in the roster)
   Each repo is frozen at its last commit at or before the deadline (a per-student `deadline` or `ref` in the roster overrides this, e.g. for an extension). One failing repo does not stop the batch.
4. Report a table: student, repo, submission_id, frozen commit, files, warnings or errors. Point out repos with history signals worth a look (`pushed_after_deadline`, `force_push`, `bulk_commit`, `no_git_history`). Read them from `submissions/<id>/metadata/history.json` → `signals`.
5. Next step: `/grade-class <assignment>` (similarity across all students, grading of every submission, class ranking), or `/grade <submission_id>` for a single submission.

Tip: to freeze exactly at the deadline (the most robust way to enforce it), schedule step 3 to run at the deadline time.
