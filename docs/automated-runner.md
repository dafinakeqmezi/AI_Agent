# Run reviews and grading without a chat

To use ChatGPT Plus or a Claude Pro/Max subscription without API keys, see
[subscription-backed runners](subscriptions.md). The direct API options below
remain available separately.

The terminal runner calls the OpenAI Responses API or Anthropic Messages API
directly. No Claude Code or chat session is needed. It uses Python 3.10+ and the
standard library; no provider SDK installation is needed. Choose `--provider
openai` (the default) or `--provider claude`.

## Configure once per terminal session

Set `OPENAI_API_KEY` in your environment using your usual secret manager. Do not
paste it into chat, put it in the roster, or commit it. In the macOS zsh terminal,
this prompts for the key without displaying it or including its value in shell
history:

```sh
read -s 'OPENAI_API_KEY?OpenAI API key: '
export OPENAI_API_KEY
```

Choose an API model available to your OpenAI project that supports Responses
function calling. Replace the placeholder:

```sh
export OPENAI_MODEL="YOUR_API_MODEL_ID"
```

Alternatively pass `--model YOUR_API_MODEL_ID` to each run. The runner deliberately
does not guess a model. Calls use API credentials and incur API usage; a chat app
login does not supply these credentials. Repository content and academic rules
that the model reads are sent to the chosen provider. OpenAI requests use
`store: false`; this OpenAI-specific flag is not sent to Claude.

### Claude setup

For Claude, use an Anthropic API key and an available Claude API model that
supports tool use. In zsh:

```sh
read -s 'ANTHROPIC_API_KEY?Anthropic API key: '
export ANTHROPIC_API_KEY
export ANTHROPIC_MODEL="YOUR_CLAUDE_API_MODEL_ID"
```

Replace the model placeholder, then run:

```sh
python3 -m grader review-all --provider claude --dry-run
python3 -m grader review-all --provider claude
python3 -m grader grade-all --provider claude --submissions ID_ARBER,ID_BLERTA,ID_DRITON
```

Replace the submission IDs with actual frozen IDs before grading. You can use
`--model YOUR_CLAUDE_API_MODEL_ID` instead of `ANTHROPIC_MODEL`. Claude only reads
`ANTHROPIC_MODEL` and `ANTHROPIC_API_KEY`; OpenAI only reads `OPENAI_MODEL` and
`OPENAI_API_KEY`. The validation, report paths, static-analysis limitations, and
phase isolation are the same for both providers. Audit files identify which
provider and model performed each phase.

## Add repositories and review

Run these from the project root:

```sh
python3 -m grader roster add
python3 -m grader roster list
python3 -m grader review-all --dry-run
python3 -m grader review-all --provider openai
```

Run `roster add` once for each repo, supplying a student name and assignment ID
(for example `detyra1`). Use `--roster path/to/roster.json` for a different saved
list. An entry's assignment takes precedence over the command's `--assignment`
fallback, then the roster-level assignment. Missing assignments cause a preflight
error rather than silently using the ML rubric.

The review command fetches each repo, prepares the artifacts, runs Agent 1, writes
`review.json` and `review.md`, and applies readiness validation. The model can
correct invalid JSON assessments through another tool call. `NOT_READY` is a
valid completed review; it is not a runner failure.

Progress and report paths print in the terminal. Each run also writes
`runner.phase1.json` with requested model, API response IDs, returned model IDs,
usage counters, files read, limitations, and completion status. Credentials and
raw model conversations are not written to this audit file.

## Freeze and grade

Freeze each repo using the existing deterministic CLI; for example:

```sh
python3 -m grader freeze dafinakeqmezi/detyra1-arber-hoti --student "Arber Hoti" --assignment detyra1
python3 -m grader freeze dafinakeqmezi/detyra1-blerta-shala --student "Blerta Shala" --assignment detyra1
python3 -m grader freeze dafinakeqmezi/detyra1-driton-morina --student "Driton Morina" --assignment detyra1
```

Without `--ref` or `--deadline`, this captures the current default-branch version.
Use the actual `--deadline` with timezone offset for deadline-based submissions.
For a roster batch at a real deadline use `python3 -m grader github freeze-all
--roster projects/roster.json --deadline <actual-ISO-deadline-with-offset>`.

Copy the returned submission IDs into the following commands (replace the example
IDs with your actual ones):

```sh
python3 -m grader grade-all --submissions ID_ARBER,ID_BLERTA,ID_DRITON --dry-run
python3 -m grader grade-all --submissions ID_ARBER,ID_BLERTA,ID_DRITON --provider openai
```

Grading verifies manifests before starting. Each submission receives an independent
phase-1 API context with no file access to reviews or earlier evaluations. The
runner validates and scores its assessments, preserves `evaluation.phase1.json` and
`final.phase1.json`, and starts a separate phase-2 context with the latest Agent 1
review, if one exists. Phase 2 rechecks evidence, writes `discrepancies.md`, and
rescores. No-review cases are explicit. Each phase has its own audit file.
Manifests are checked before scoring and again after the workflow.

Results are provisional and saved in the evaluation directory. Only the human
course professor approves grades. The command does not implicitly freeze, run
class similarity, rank students, or open a browser. Those remain explicit CLI
operations (`similarity`, `ranking`, `dashboard`).

## Limits and failures

The model has read-only tools scoped to the project, prepared artifacts, and
knowledge base. It can submit reports only to its prepared output directory. It
cannot execute student programs or browse the web. Reports explicitly state that
runtime checks are unverified. Working-code requirements still need independent
execution checks; a static review is not evidence of successful execution.
Unsupported binary files must have extracted text (optional pypdf enables PDF
extraction) or be reported as uninspected. Preparation can verify citations;
`--offline` disables those checks but still needs network for GitHub/API calls.

Default limits are 60 API calls per phase, 12,000 output tokens per call, a
120-second request timeout, and a fixed context-size limit. Change the first
three with `--max-turns`, `--max-output-tokens`, and `--timeout`. These are bounds
on calls/output, not a dollar budget. Grading can use two phases per submission.
Incomplete responses fail clearly instead of being marked successful. There are
no automatic transport retries that might duplicate a charged request.

A failed repository does not stop the rest of a batch. The JSON summary lists
successes, failures and output directories; any failure produces a nonzero exit
code. A phase limit or interruption leaves inspectable artifacts and its audit
file. There is no automatic resume; rerunning starts new runs. Repeated runs use
the toolkit's timestamp-based directories, so wait at least a second between runs
for the same project. Dry runs require neither API credentials nor a model, do
not fetch repos or call the API, and grading dry runs verify the existing manifests.

API implementation references: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
and [Claude tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls).
