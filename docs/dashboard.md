# Live dashboard

Start the dashboard from the repository root:

```sh
python3 -m grader dashboard --serve
```

The command prints a local URL and opens it in your browser. Keep the terminal
running. Press Ctrl+C to stop the server and any active dashboard job. To choose
a fixed port or open the browser yourself:

```sh
python3 -m grader dashboard --serve --port 8765 --no-open
```

## Professor access

Open the printed URL. On the first run, the browser shows **Create professor
account** with username, password and confirmation fields. After creating it,
sign in. Once the first account exists, setup closes and visitors must sign in.
There is no default password or open registration.

While signed in, select **Invite professor** in the dashboard header to create
another account on a dedicated page. Account forms are separate from review controls
and share the dashboard’s colors, typography and saved theme. Each professor has a separate workspace: repositories, students,
reviews, frozen submissions, grades, rankings, similarity reports, logs and jobs.
Professors can register the same GitHub repository independently. One job can run
per professor, so different professors can work concurrently.

For terminal-based account creation or password recovery, you can still use:

```sh
python3 -m grader professor-account another-professor
```

Passwords must contain at least 12 characters. Salted PBKDF2 password hashes are
stored in the ignored `state/professors.json`, with owner-only file permissions.
Each account can access only its own dashboard data and job controls. Password resets
invalidate that account's existing sessions. Sessions expire after eight hours;
**Sign out** in the header immediately revokes the current session. Five sign-in attempts per
minute are allowed across the local server. Restarting the server signs everyone
out; signing out does not stop a running job.

All live pages, report downloads, and APIs require a session. The server binds
to loopback; public hosting requires an HTTPS reverse proxy (see below). A person
with access to the underlying files can still read them. Exported static
`dashboard.html` snapshots contain student data and have no login protection:
keep them private and remove old exports if they are no longer needed.

## Professor storage and hosting

Data lives under `state/professor-data/<account-id>/`, where the ID is derived
from the authenticated username. The server chooses this directory; request
parameters cannot select a different professor. Downloads and job IDs are also
scoped to that account. Back up the entire `state/` tree and protect filesystem
access. Course materials and rubrics are shared, while student data is separate.
Existing root-level results and rosters are preserved and are **not** assigned
or exposed to any professor automatically. Terminal runs without a data-root
setting still use the legacy root-level workspace.

To use the terminal with one professor's workspace, set `GRADER_DATA_ROOT` to its
absolute storage directory before running grader commands. Dashboard workers
set it automatically; it does not change the shared academic rules.

For hosting, create the first account through the local browser first. Then put
an HTTPS reverse proxy in front of the loopback server and configure the exact
public origin:

```sh
export GRADER_PUBLIC_URL=https://grader.example.edu
python3 -m grader dashboard --serve --port 8765 --no-open
```

Configure the proxy to forward to `127.0.0.1:8765`, preserve the original `Host`
header, and terminate HTTPS. The configured origin is checked on requests;
cookies use `Secure` in this mode. Hosted mode refuses to start without an
existing professor account, preventing public first-account registration.
Run a **single server process**: sessions and job tracking are in memory. A restart
requires signing in again. This change prepares account isolation and proxy
configuration; it does not deploy a server, set up TLS, or provide high availability.
Provider credentials and CLI sign-ins remain configured by the server operator;
separate professor model accounts and billing are not implemented.

## Review repositories

Expand **Run reviews and comparisons** to access the controls. The panel starts
collapsed to keep saved results visible. Repository registration and freeze
options expand separately; job status and stop controls remain visible.

1. Enter a GitHub URL (or `owner/repo`), student name, assignment and Git branch (default **main**), then click
   **Add repository**. Repeat for each repository. This saves the local roster
   without running a model. Saved repository labels show the branch. The branch
   is used for both reviews and freezes. A nonexistent branch produces a fetch
   error; the tool does not silently switch to another branch.

   From the terminal, use `python3 -m grader roster add owner/repo --student "Name" --assignment detyra1 --branch develop`.
   To change an already registered repository's branch, update its `ref` in
   `projects/roster.json` inside that professor’s storage directory while no job is running.
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
immutable submissions from the saved branch, defaulting to `main` for roster
entries without a ref. An optional deadline must include a timezone,
for example `2026-11-01T23:59:00+01:00`. Existing roster refs and deadlines are
preserved; a saved deadline takes precedence over the dashboard input.

Select frozen submissions, choose a provider and model, then click **Grade
selected submissions** for the independent two-phase evaluation. Grades remain
provisional until the human professor approves them. Freezing alone does not
start grading.

**Not completed** (Albanian: **E papërfunduar**) means the review finished but
the project's completion checklist is not fully satisfied. Its stored code is
still `NOT_READY` for compatibility with earlier runs. **Run incomplete** means
the review or evaluation itself did not finish, for example after a call limit.
Existing dashboard results use the new label automatically; previously saved
Markdown reports retain the wording used when they were generated.

`NOT_READY` does not prevent freezing or grading. Readiness is Agent 1's
completion checklist, not Agent 2's passing-grade threshold. A project with
partial or missing requirements can still receive partial credit. A step-limit
failure means the review/evaluation is incomplete, rather than a NOT_READY
verdict. If the default three calls are insufficient, select only the affected
repository and increase the limit (for example to 12) before retrying; successful
report submission ends the phase early.

For cross-repository similarity, select at least two frozen submissions from the
same assignment and click **Compare selected submissions**. This deterministic
comparison uses no AI model. Matches are indicators for human investigation;
they never establish cheating or automatically deduct points. Similarity and
ranking views show saved aggregate results, which may include earlier runs.
For comparisons that must exclude shared starter code, use the terminal's
`similarity --base` option; the dashboard does not expose that option yet.

New comparisons also include a **Matching-version commit timeline** for up to
ten non-common identical files and four matching code-file pairs. The tool checks
each frozen file's SHA-256 or the shared normalized code fingerprints against
raw Git blobs from the recorded history and lists the earliest
matching commit by committer date on each side, with author dates and identities.
This distinguishes an old filename from the later arrival of matching content.
The original local repositories/mirrors must still be available. History scans
are bounded to 100 path-touching commits per file, 256 KB blobs and a five-second
budget per submission; incomplete/unavailable history is labeled. Renamed files
and changed identifiers can be compared through normalized fingerprints, marked
separately from exact files. Historical paths are not followed across renames,
and older versions missing some of the selected fingerprints may leave gaps.

An earlier recorded version is an investigation lead, not proof that the later
student copied it. Both Git timestamps can be edited; public push dates are not
verified by this check. Shared sources, forks, authorized collaboration and
disclosed reuse (including the two generated sample repositories) must be
considered by the professor. Re-run **Compare selected submissions** to add the
timeline to older comparison results. Scores remain unchanged.

## Results and progress

Terminal-generated reviews and evaluations appear when created with that
professor’s `GRADER_DATA_ROOT`. Legacy root-level records are not exposed to
professor accounts.
The live page refreshes saved results every three seconds. Only one dashboard
job per professor runs at a time; **Stop current job** cancels its process tree on macOS/Linux
and prevents further commands in that job. Completed artifacts remain on disk.
Run terminal jobs separately only when you intend them to run concurrently.

The panel shows the latest job's scope, log, elapsed time, and token totals after
a model run finishes when the provider reports usage. Job logs and summaries are
stored under each professor’s `state/dashboard-jobs/`; the live job panel lists jobs started in
the current server session. Historical academic results remain in the project
views after restarting the server.

The server listens only on `127.0.0.1`. Use its printed URL. Running
`python3 -m grader dashboard` without `--serve` still exports the original
read-only HTML snapshot; that file has no job controls or automatic refresh.
