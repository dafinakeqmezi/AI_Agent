# Run with ChatGPT Plus or a Claude subscription

Use the official CLIs to run the terminal workflow with subscription sign-in.
The Python runner does not read, extract, or save their access tokens. Each CLI
keeps its own login. ChatGPT Plus covers eligible OpenAI models; running Claude
requires its own eligible Claude subscription, such as Pro or Max.

## ChatGPT Plus through Codex

Install or update the [official Codex CLI](https://learn.chatgpt.com/docs/codex-cli),
then sign in with ChatGPT:

```sh
codex login
codex login status
```

The status must say `Logged in using ChatGPT`. The runner rejects an API-key-only
login. Then, from the AI_Agent project directory:

```sh
python3 -m grader roster list
python3 -m grader review-all --provider chatgpt --dry-run
python3 -m grader review-all --provider chatgpt
```

The model defaults to the CLI's built-in choice, with user config ignored for
isolation. To choose a model available to your plan, pass `--model MODEL_NAME` or
set `CODEX_MODEL`. API model names are not necessarily available under your plan.
The runner's `OPENAI_MODEL` setting is not used for this provider.

If the CLI's bundled default is retired or rejected by your account, update Codex,
check the signed-in plan, and pass an available model explicitly with `--model`.
A successful login or cached model catalog alone does not establish model access;
the runner reports an unavailable-model error instead of switching billing paths.

## Claude Pro / Max through Claude Code

Install a current [official Claude Code CLI](https://code.claude.com/docs/en/setup)
and sign in to your subscription account, not a Claude Console account:

```sh
claude auth login
claude auth status
```

The status must identify `authMethod` as `claude.ai`. The runner rejects API-key,
API-helper, Console and third-party authentication. Then run:

```sh
python3 -m grader review-all --provider claude-code --dry-run
python3 -m grader review-all --provider claude-code
```

Optionally select a plan-supported model with `--model sonnet` or set
`CLAUDE_CODE_MODEL`. The API setting `ANTHROPIC_MODEL` is not used for this provider.
The runner needs a current Claude Code version supporting `--bare`, JSON schema
output, `auth status`, tool restrictions and no session persistence. Older
versions fail explicitly; update instead of enabling permission bypass flags.

## Grading without chat prompts

First freeze repositories as described in [the runner guide](automated-runner.md).
Copy the actual returned IDs into either command below:

```sh
python3 -m grader grade-all --provider chatgpt --submissions ID1,ID2,ID3
python3 -m grader grade-all --provider claude-code --submissions ID1,ID2,ID3
```

Each submission has an independent phase 1, saved snapshots, then a separate
phase 2 that may inspect Agent 1's review. Python validates reports, calculates
scores and verifies the frozen manifests. Report locations and formats match the
direct API runner. Grades remain provisional until human approval.

## How subscription execution works

Before subscription inference, the runner supplies a bounded evidence packet
(up to 120,000 serialized characters) containing the assignment materials and
relevant project text. Small projects can submit a validated report in one model
step, avoiding a new invocation for each file. Additional evidence can be read in
batches of up to four files. Files omitted by the packet budget remain accessible
through scoped reads; the packet is not treated as the complete repository.

For each model step, Python starts a fresh ephemeral CLI process. One empty
temporary working directory is reused within a phase to keep the prompt prefix
stable; it is deleted at phase end and is never reused by another project or phase.
The CLI receives only the role instructions and
this phase's conversation, returning one structured action. Python executes file
reads through the existing scoped file reader and validates submitted reports.
The native CLI shell, file, browser, connector and plugin capabilities are disabled;
project instructions and memories are not auto-loaded. Neither provider resumes
an old session. Temporary structured outputs are removed after the call.

The named evidence packet includes the shared rules, so the model need not request
them again. Transport JSON is decoded before building the inference prompt, avoiding
a second layer of escaping around file contents. Agent 1 submits assessment JSON
only; Python renders the student-facing Markdown locally without another model
call or a duplicate generated report. Older clients that supply Markdown remain
supported. Findings, evidence, uncertainty, integrity statements and recommendations
are kept in the generated report.

Additional steps still replay context through the CLI and can be slower than a
direct API run. CLI process startup still occurs per inference; cache benefits
depend on the provider and are not guaranteed. Audit files record prefetched paths, packet size and input
characters per step so repeated context can be inspected. `transport.prompt_characters`
records the actual CLI prompt size, and `token_totals`, `elapsed_seconds` and
`model_calls_attempted` summarize a phase. Unreported token counts are null.
They also identify
`chatgpt` or `claude-code`, record usage reported by
the CLI, and use `cli-default` when no explicit model was requested. That label
does not identify an exact resolved model revision.

No API key is required. API-key and alternative API-authentication environment
variables are removed from child processes without modifying your shell, and
Codex is forced to ChatGPT authentication. Failures and plan limits stop that run;
the runner never switches to the direct API providers. Account-level extra usage
or credit settings are still managed by the provider; review those settings if
you want usage to stop strictly at the included allowance.

`--max-turns` bounds CLI invocations per phase; subscription runs default to 8
instead of the direct API's 60. Increase it explicitly for a large project. The
terminal shows the upfront packet size and requested actions, and the audit
records per-step durations and action names. `--timeout` bounds each invocation;
increase it (for example `--timeout 300`) if a model takes longer to produce a
report. `--max-output-tokens` applies only to direct API calls, not CLI inference.
The same context limit and static-review limitations apply: student code is not
executed and the model does not browse for sources. A dry run checks the roster
or frozen IDs but does not require a CLI installation or test login/model access.

The CLI subprocess may need access to its own local runtime database and network.
If launching the runner from another sandboxed coding agent, those permissions
may be restricted; run it in your normal terminal when needed.

Sources: [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode),
[Codex authentication restrictions](https://learn.chatgpt.com/docs/config-file/config-reference),
[Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference), and
[Claude plan usage with noninteractive tools](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan).
