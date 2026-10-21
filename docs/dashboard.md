# Live dashboard

Run from the repository root:

```sh
python3 -m grader dashboard --serve
```

The command prints a local URL and opens it in your browser. Keep the terminal
running. Press Ctrl+C to stop the server and any active dashboard job. To choose
a fixed port or open the browser yourself:

```sh
python3 -m grader dashboard --serve --port 8765 --no-open
```

## Review repositories

Expand **Run reviews and comparisons** to access the controls. The panel starts
collapsed to keep saved results visible. Repository registration and freeze
options expand separately; job status and stop controls remain visible.

1. Enter a GitHub URL (or `owner/repo`), student name and assignment, then click
   **Add repository**. Repeat for each repository. This saves the local roster
   without running a model.
2. Check the saved repositories you want to review.
3. Choose ChatGPT subscription (Codex), Claude subscription (Claude Code),
   OpenAI API or Claude API. Enter a model available to that account, or leave
   it blank to use the configured provider default.
4. Set the maximum calls per phase and seconds per model call, then click
   **Review selected repositories**.

The dashboard defaults to three calls per phase and 300 seconds per call.
This bounds model calls, not total job duration or token consumption. If a review
runs out of calls before producing valid output, its job log reports the failure;
you can raise the limit and start another run.

Sign in to the official CLI before using a subscription provider. For API
providers, set credentials and the model in the server's terminal environment.
See [subscription setup](subscriptions.md) and [API runner setup](automated-runner.md).
The dashboard does not accept API keys. Provider and model choices apply to
new runs; they do not change existing results.

Choosing a provider checks its local setup and displays **Ready** or **Setup
needed** with installation/sign-in instructions. This check makes no model call.
Review and grading buttons stay disabled until setup passes; freezing and
comparison remain available. Sign in from your terminal, then click **Check
provider again**. For API providers the check confirms configuration only;
credentials and model availability are verified during the actual run.

## Freeze, grade and compare

Select saved repositories and click **Freeze selected repositories** to create
immutable submissions. Without a deadline or saved ref, this captures the
current default-branch version. An optional deadline must include a timezone,
for example `2026-11-01T23:59:00+01:00`. Existing roster refs and deadlines are
preserved; a saved deadline takes precedence over the dashboard input.

Select frozen submissions, choose a provider and model, then click **Grade
selected submissions** for the independent two-phase evaluation. Grades remain
provisional until the human professor approves them. Freezing alone does not
start grading.

For cross-repository similarity, select at least two frozen submissions from the
same assignment and click **Compare selected submissions**. This deterministic
comparison uses no AI model. Matches are indicators for human investigation;
they never establish cheating or automatically deduct points. Similarity and
ranking views show saved aggregate results, which may include earlier runs.
For comparisons that must exclude shared starter code, use the terminal's
`similarity --base` option; the dashboard does not expose that option yet.

## Results and progress

Existing terminal-generated reviews and evaluations appear in the dashboard.
The live page refreshes saved results every three seconds. Only one dashboard
job runs at a time; **Stop current job** cancels its process tree on macOS/Linux
and prevents further commands in that job. Completed artifacts remain on disk.
Run terminal jobs separately only when you intend them to run concurrently.

The panel shows the latest job's scope, log, elapsed time, and token totals after
a model run finishes when the provider reports usage. Job logs and summaries are
stored under `state/dashboard-jobs/`; the live job panel lists jobs started in
the current server session. Historical academic results remain in the project
views after restarting the server.

The server listens only on `127.0.0.1`. Use its printed URL. Running
`python3 -m grader dashboard` without `--serve` still exports the original
read-only HTML snapshot; that file has no job controls or automatic refresh.
