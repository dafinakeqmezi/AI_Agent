# AI/ML Project Review & Grading System

Two independent AI agents, backed by a shared, versioned academic and AI/ML knowledge base, run inside Claude Code or directly from the terminal with the [automated API runner](docs/automated-runner.md). Other AI tools with workspace and terminal access can follow [AGENTS.md](AGENTS.md); see [portable workflows and prompts for the three Detyra 1 repositories](docs/ai-tools.md). Claude-specific slash commands, settings, and hooks require adaptation in other tools.

- **Agent 1, AI/ML Project Reviewer** (`ml-reviewer`) acts as a senior AI/ML project supervisor. It reviews a project iteratively against the course requirements, ML methodology, literature, reproducibility, documentation and academic-integrity indicators. For each requirement it reports PASS / PARTIAL / MISSING / NOT_APPLICABLE / BLOCKER, with evidence and recommendations, until the project meets its Definition of Done.
- **Agent 2, Professor / Final Evaluator** (`professor`) independently evaluates the frozen final submission against the fixed rubric. It does not coach. Every score and deduction cites a rubric requirement and concrete evidence. It produces criterion scores, a final grade, strengths, weaknesses, integrity concerns for human review, and a full justification.

Academic-integrity checks identify **risk indicators with evidence**. They never conclude that misconduct occurred, and the professor always has the final word.

```
                 knowledge-base/  (rules · requirements · rubric · DoD · integrity policy · ML guidelines · verified literature)
                         │
        ┌────────────────┴────────────────┐
        │                                 │
  Agent 1  /review                  Agent 2  /grade   (phase 1 independent → phase 2 discrepancy check)
        │                                 │
  reviews/…/review.md               evaluations/…/report.md
  readiness (DoD)                   final.json (scores computed by grader/)
        │                                 │
        └──── /freeze → submissions/<id>/ (read-only, SHA-256 manifest) ────┘
                                          │
                               /override (professor)  ·  /benchmark (evaluate the evaluator)
```

## Requirements

- Claude Code opened in this folder, another capable AI coding tool, the [subscription CLI runner](docs/subscriptions.md), or the terminal API runner with OpenAI (`OPENAI_API_KEY`, `OPENAI_MODEL`) or Claude (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`). A model can also be supplied via `--model`.
- Python 3.10+ (stdlib only). Optional: `pip install pypdf` to extract PDF text. Without it, the agents read PDFs directly. pypdf is required for `kb-add-book`.
- git. Optional but recommended: [scc](https://github.com/boyter/scc) (`winget install BenBoyter.scc`) to measure real code lines and complexity per commit. Without it, history analysis falls back to `git numstat`.
- Internet access for citation verification (Crossref/arXiv) and GitHub. Use `--offline` to skip citation checks.
- **GitHub:** public repos work without a token (60 API requests/hour). For private or Classroom repos, set `GITHUB_TOKEN`: a fine-grained token with read-only *Contents* and *Metadata* on the student repos, or a classic token with `repo`. The token is passed to git only through environment variables and never written to disk.

## Workflow

| Step | Who | Command | Result |
|---|---|---|---|
| 1 | Professor | Drop course documents into `knowledge-base/course/`, then run `/import-course` | Official `requirements.json`, `rubric.json`, `dod.json` |
| 2 | Student / supervisor | `/review projects/<name>` or `/review owner/repo` (repeat after each change) | `reviews/<name>/<ts>/review.md` + readiness verdict (incl. git history, C11) |
| 3 | Professor | `/freeze owner/repo <student> --deadline 2026-12-15T23:59:00+01:00 --team login1,login2` (or a folder), or `/collect --org <org> --prefix <assignment> --deadline …` for the whole class | Immutable `submissions/<id>/` frozen at the deadline commit, with the analysed history |
| 4 | Professor | `/grade <submission-id>` | `evaluations/<id>/eval-<ts>/report.md`, `discrepancies.md` |
| 5 | Professor | `/override <eval-dir> …` (change a score, mark a false positive, comment, `--approve`) | Grade recomputed; status APPROVED |
| 6 | Maintainer | `/benchmark` | Agreement of Agent 2 with human grades |

States: `DRAFT → UNDER_REVIEW → READY_FOR_FINAL_REVIEW → FINAL_SUBMISSION → GRADED`. Show them with `python -m grader status`.

## How the spec maps to the implementation

| Spec component | Implementation |
|---|---|
| Shared knowledge base, authority hierarchy, 12 behaviour rules | `knowledge-base/` (`INDEX.md` gives topic retrieval); `policies/agent-rules.md` |
| Requirements engine | `knowledge-base/requirements/requirements.json`: 42 requirements (incl. VCS-001..005 for git history) with IDs, criterion, points, mandatory flag, checks |
| Deterministic rubric | `rubric/rubric.json`. The LLM only assigns status + evidence per requirement; `grader/score.py` does the arithmetic (PARTIAL ∈ {0.25, 0.5, 0.75}, N/A rescales) and the grade mapping |
| "No deduction without criterion + evidence", "no credit without evidence" | Enforced by `score.py` / `readiness.py` validation. Cited files must exist in the submission manifest |
| Evidence system | Every finding has requirement, finding, evidence (file + line/cell/page + quote), severity, recommendation |
| Agent 1 review areas A-I, claims ledger, report-vs-code check, reproducibility score | `.claude/agents/ml-reviewer.md`, supported by `grader/scan.py` signals |
| Citation verification ("never invent papers") | `grader/cite.py` (Crossref + arXiv); `literature/references.json` holds 20 references verified on 2026-10-01 |
| Integrity as risk indicators + human review | `policies/integrity-policy.json` (12 indicators, 3 risk levels, mandatory disclaimer). Indicators never change scores |
| Definition of Done | `requirements/dod.json` + `python -m grader readiness` |
| Submission states / immutability | `grader/freeze.py` (read-only copy, SHA-256 manifest, verified before and after grading) + `.claude/hooks/protect_submissions.py` |
| Agent independence | `/grade` phase 1 never sees Agent 1's output. Phase 2 compares, and changes a score only with evidence Agent 2 verified itself. Both phases are kept (`evaluation.phase1.json`) |
| Versioning | Every run records the rubric, requirements, DoD, policy and KB versions + content hashes, agent prompt hashes, the model, and the submission manifest hash (`python -m grader versions`) |
| Human override | `/override`: append-only `overrides.json`. Agent vs professor status is shown side by side; re-approval is required after changes |
| Evaluator of the agents | `benchmark/human_grades.json` + `python -m grader benchmark`: MAE, criterion agreement, false deductions, missed problems, planted-issue recall, false integrity flags |

## GitHub and commit-history grading (criterion C11)

- **Fetch:** `owner/repo` or a GitHub URL is cloned into a local mirror `projects/<owner>__<repo>/`. The REST API supplies the commit→login mapping, pull requests, branches and the **push activity log**, which includes force-pushes.
- **Freeze at the deadline:** `--deadline` freezes the last commit made at or before the deadline. Commit dates are client-controlled, so the push log is also checked: a commit dated before the deadline but pushed after it is flagged (INT-015). The most robust option is to run `/collect` at the deadline.
- **Analysis** (`grader/history.py`, `artifacts/history.md`): commits, active days and weeks, a weekly timeline, **scc code lines and complexity per commit**, authors and team balance, milestones (when code, report, tests and results first appear), and signals. Signals cover bulk uploads, last-minute work, generic messages, oversized commits, secrets or large files ever committed, outside authors, forks/templates, force-pushes, commits after the deadline, and AI co-author trailers (checked against AI-usage disclosure).
- **Grading (`ml-project` only):** C11 *Version control & development process* (10 pts placeholder) has VCS-001 incremental development, VCS-002 commit messages, VCS-003 focused commits and clean history, VCS-004 history consistent with the report, and VCS-005 team contribution (N/A for individual projects). Guidance and thresholds are in `knowledge-base/policies/version-control-policy.json`. Detyra 1 has no separate VCS scoring criterion. History signals alone never establish misconduct.
- **Evidence:** commits are cited as `{"file": "(git history)", "location": "commit <sha7>"}`. The scorer rejects SHAs that are not in the frozen history.

## Textbook knowledge base

`python -m grader kb-add-book <pdf> --key … --title … --authors …` indexes a textbook into `knowledge-base/literature/books/<key>/`: the outline with pdf pages (`INDEX.md`), per-chapter text with page markers (`text/`, ligatures normalized for Grep), and metadata. Russell & Norvig, *AIMA* 4th ed. is installed as `aima4`, with a hand-made `TOPICS.md` mapping requirements to sections (e.g. DATA-004 → §19.4/19.4.1, EVAL-003 → §21.5, DOC-003 → §27.3). Agents cite it by section and use it for explanations and recommendations, never as a reason to deduct. The PDF and extracted text are copyrighted and git-ignored.

## Toolkit CLI (`python -m grader …`)

Open the interactive local dashboard with `python3 -m grader dashboard --serve`.
Add repositories, select a provider and model, run reviews, freeze and grade
submissions, and compare frozen submissions for similarity. Saved results refresh
automatically. See the [dashboard guide](docs/dashboard.md) for setup and controls.
The [measured performance check](docs/runner-performance.md) documents subscription
runner token use, elapsed time and the limits of the comparison.

In the dashboard:

1. Expand **Run reviews and comparisons**, add repositories and select the ones
   to process. Choose their assignment, provider and model.
2. Check the provider's **Ready / Setup needed** message. Install and sign in to
   the official CLI from your terminal when needed, then click **Check provider
   again**. This setup check makes no model call; it does not verify model access.
3. Click **Review selected repositories** for Agent 1's feedback and readiness
   verdict. The default three calls per phase may be insufficient for a larger
   project. Increase **Maximum calls per phase**, for example to 12, if the run
   reaches its limit. The runner stops early after a valid report is submitted.
4. To obtain a grade, expand **Freeze repositories for grading**, freeze the
   selected repositories, then select their entries under **Frozen submissions**
   and click **Grade selected submissions**. This starts Agent 2's independent
   assessment and subsequent discrepancy check.
5. Select at least two frozen submissions of the same assignment and click
   **Compare selected submissions** for similarity and commit-history evidence.

**Readiness is not a grade or a grading gate.** Agent 1 uses the assignment's
Definition of Done; Detyra 1 currently requires every mandatory requirement to
pass. A `NOT_READY` project can still be frozen and graded, earning partial
credit from Agent 2. A step-limit failure is an incomplete run, not a readiness
verdict. All grades remain provisional until the human professor approves them;
the current Detyra 1 weights and grade scale are marked `PLACEHOLDER`.

Detyra 1 has [19 requirements](knowledge-base/assignments/detyra1/requirements.json)
derived from the [course assignment](knowledge-base/course/ai-2026-27/Detyra1.md):
Social Golfers, Sudoku, Latin Square and three search trees. Both agents check
the same academic requirements. The automated runner performs static analysis;
it does not execute student code or independently confirm runtime success.

The Similarity view includes historical matching file versions and normalized
code fragments, commit IDs, author/committer dates, and their recorded order.
An earlier commit is a lead for human investigation, not proof of authorship or
who copied whom. Shared sources, templates, forks and disclosed reuse must be
considered; similarity never changes scores automatically. See the
[comparison limits](docs/dashboard.md#freeze-grade-and-compare).

Add repositories through interactive input with `python3 -m grader roster add`.
Enter the repository URL, student name, and assignment ID; repeat for each repo.
Use `python3 -m grader roster list` to view the saved roster. See the
[AI tools guide](docs/ai-tools.md) for reviewing these saved entries.

To run without chat prompts, configure `OPENAI_API_KEY` and `OPENAI_MODEL`, then
use `python3 -m grader review-all --provider openai`. Grade already frozen IDs
with `python3 -m grader grade-all --submissions <id1,id2> --provider openai`.
Both support `--dry-run` without credentials. See the [runner guide](docs/automated-runner.md)
for setup, limits, and static-analysis limitations.

For Claude, set `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` and use `--provider claude`
with either command. Each provider uses its own credentials and model setting.

To use subscriptions instead of API keys, sign in with the official CLI and use
`python3 -m grader review-all --provider chatgpt` (ChatGPT Plus via Codex) or
`python3 -m grader review-all --provider claude-code` (Claude Pro/Max via Claude Code).
The same providers work with `grade-all --submissions <id1,id2>`.
See [subscription setup](docs/subscriptions.md). They do not fall back to API billing.

`versions` · `prepare <dir> --out <dir>` · `new-review <project|owner/repo> [--ref --deadline --team]` · `history <repo> --out <dir>` · `github repos --org … [--prefix … --write-roster projects/roster.json]` · `github freeze-all --roster projects/roster.json` · `kb-add-book <pdf> …` · `readiness <review-dir>` · `freeze <project> --student …` · `verify <submission-id>` · `new-evaluation <submission-id>` · `score <eval-dir>` · `override <eval-dir> …` · `latest-review <project>` · `cite --doi … | --arxiv … | --title "…"` · `state <project>` · `status` · `benchmark` · `check-expected <run-dir> <expected.json>` · `assignments` · `similarity --assignment <id>` · `ranking --assignment <id>` · `dashboard` (local HTML overview of all projects, reviews and grades)

Tests: `python -m unittest discover -s tests -v`

## Before real use

1. **Replace the placeholders.** `requirements.json`, `rubric.json`, `dod.json`, the grade scale and the AI-usage policy are sensible defaults marked `PLACEHOLDER`, and every grade report warns about this. Use `/import-course` with the professor's documents.
2. **Build the benchmark.** Collect 10-30 projects, including some with deliberately planted flaws (`examples/leaky-churn` and the two controlled samples in `sample-projects/` are the first), have them graded by hand, and run `/benchmark` before trusting Agent 2's grades.
3. **Temperature.** Claude Code does not expose a temperature setting for subagents. Consistency comes instead from requirement-level judgments, fixed credit levels, deterministic scoring, and the benchmark.
4. **Data protection.** `projects/`, `submissions/`, `reviews/` and `evaluations/` hold student data and are git-ignored. Back them up separately, because they are the audit trail.
