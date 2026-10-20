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

For each model step, Python starts a fresh ephemeral CLI process in an empty
temporary working directory. The CLI receives only the role instructions and
this phase's conversation, returning one structured action. Python executes file
reads through the existing scoped file reader and validates submitted reports.
The native CLI shell, file, browser, connector and plugin capabilities are disabled;
project instructions and memories are not auto-loaded. Neither provider resumes
an old session. Temporary structured outputs are removed after the call.

This replays context through the CLI at each step and can be slower than a direct
API run. Audit files identify `chatgpt` or `claude-code`, record usage reported by
the CLI, and use `cli-default` when no explicit model was requested. That label
does not identify an exact resolved model revision.

No API key is required. API-key and alternative API-authentication environment
variables are removed from child processes without modifying your shell, and
Codex is forced to ChatGPT authentication. Failures and plan limits stop that run;
the runner never switches to the direct API providers. Account-level extra usage
or credit settings are still managed by the provider; review those settings if
you want usage to stop strictly at the included allowance.

`--max-turns` bounds CLI invocations per phase. `--timeout` bounds each invocation;
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
