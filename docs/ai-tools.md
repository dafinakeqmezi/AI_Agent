# Running the agents in other AI tools

For automated runs using ChatGPT Plus or Claude Pro/Max, see
[subscription setup](subscriptions.md): use `--provider chatgpt` or
`--provider claude-code` with the terminal runner after signing in to the official CLI.

For terminal execution without a chat, use the [automated API runner](automated-runner.md):
`python3 -m grader review-all` reviews the saved roster; `python3 -m grader grade-all
--submissions <id1,id2>` grades frozen IDs. Configure `OPENAI_API_KEY` and an API
model first, or use `--provider claude` with `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`.
The rest of this guide describes running through a chat/coding tool.

The review and evaluation instructions can be used by an AI tool that can read
the workspace, execute Python and Git, and write files. The tool must also support
a fresh session or isolated agent context for independent grading. Tools without
these capabilities require manual file transfer and command execution.

Open this repository as the workspace. Codex reads the root `AGENTS.md` as project
guidance. In other tools, explicitly ask the assistant to read it. The Claude Code
slash commands are not installed automatically in another tool. Its model/tool
settings and submission-protection hook do not carry over either.

These prompts are instructions to the AI, not shell commands. They do not require
changing the shared rubric or creating separate copies of the agent definitions.

## Add repositories through terminal input

From the project folder, run:

```sh
python3 -m grader roster add
```

Enter the GitHub URL (or `owner/repo`), student name, and assignment ID when
prompted. Use `detyra1` for Detyra 1. Run the command again for each new repo.
Entries are saved in `projects/roster.json`; existing entries and class metadata
are preserved, and duplicate repos are rejected without overwriting them.
Registration saves input locally and does not fetch or grade a repository.

You can also supply fields directly:

```sh
python3 -m grader roster add https://github.com/dafinakeqmezi/detyra1-arber-hoti --student "Arber Hoti" --assignment detyra1
python3 -m grader roster list
```

Then send the AI tool:

```text
Read AGENTS.md and projects/roster.json. Run Agent 1 reviews for every saved
entry, using its assignment (or the roster assignment if the entry has none).
Validate the reviews and show the report links. Do not freeze or grade yet.
```

For older roster entries without an entry or roster assignment, determine the
correct assignment before reviewing. Batch deadline freezing is available via
`python3 -m grader github freeze-all --roster projects/roster.json --deadline
<actual-ISO-deadline-with-offset>`; it requires a real deadline. For current-version
freezing without a deadline, ask the AI to follow the individual freeze workflow
for each roster entry.

## Review the three repositories

Paste this into the AI tool:

```text
Read AGENTS.md and follow its Agent 1 workflow using the existing ml-reviewer
instructions. Review these repositories separately with assignment detyra1:

- dafinakeqmezi/detyra1-arber-hoti
- dafinakeqmezi/detyra1-blerta-shala
- dafinakeqmezi/detyra1-driton-morina

Prepare each run with the Python CLI, inspect actual evidence, write review.json
and review.md, and run readiness validation. Report each verdict and output paths.
Do not modify student projects. This request is for reviews only.
```

## Freeze the current versions

When ready for grading, paste:

```text
Read AGENTS.md and freeze the current default-branch versions of these repositories
with assignment detyra1:

- dafinakeqmezi/detyra1-arber-hoti: student Arber Hoti
- dafinakeqmezi/detyra1-blerta-shala: student Blerta Shala
- dafinakeqmezi/detyra1-driton-morina: student Driton Morina

Use python -m grader freeze for each. Report the three returned submission IDs,
frozen commits, and warnings. Do not invent a submission deadline.
```

For deadline-based grading, replace the current-version instruction with the real
deadline and timezone offset. Never use an example date as the actual deadline.

## Grade in a fresh session

Replace the three placeholders below with IDs returned by freezing. Open a fresh
session with this workspace before pasting. Do not paste Agent 1's conclusions.

```text
Read AGENTS.md and follow the independent Agent 2 workflow for assignment detyra1.
The only submissions in scope are:
<submission-id-arber>, <submission-id-blerta>, <submission-id-driton>.

Run similarity restricted to these IDs and evaluate each frozen submission using
the professor role. Keep every phase-1 evaluator isolated from Agent 1's reviews
and previous evaluations. If you cannot create isolated contexts, prepare the run
information and a handoff prompt for each fresh evaluation session instead.

Validate scores using the toolkit and preserve the phase-1 JSON snapshots before
consulting Agent 1 for phase 2. Write discrepancy reports, verify the frozen
manifests, and report provisional grades with evidence and output paths.
Do not approve grades or modify submissions.
```

In the chat-driven workflow, the preparation commands do not call a model: the
AI tool supplies the judgments and reports, while Python validates and computes
scores. The separate `review-all` and `grade-all` commands call the API directly.
Different models may judge evidence differently even when they use the same rubric.

For a manual handoff, the orchestrator runs `python -m grader new-evaluation <id>`
and supplies a fresh examiner with `PHASE: 1`, `SUBMISSION_ID`, `SUBMISSION_FILES`,
`EVAL_DIR`, `ASSIGNMENT`, and `ASSIGNMENT_FILES` from that preparation output, plus
the instructions to read `AGENTS.md` and `.claude/agents/professor.md`. Exclude
reviews and prior evaluation results. When the examiner finishes validated phase
1, the orchestrator saves its snapshots and completes phase 2 as documented.
