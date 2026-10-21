# Subscription runner performance check

Measured on 2026-10-21 using the installed Codex CLI 0.163.0, its existing
ChatGPT subscription sign-in and the same `cli-default` model setting.
The workload was an Agent 1 review of the generated `detyra1-ready-sample`,
prepared locally with `--assignment detyra1 --offline`. The runner used a
four-call ceiling and a 180-second timeout per call. No API fallback was used.

| Metric | Earlier run in this optimization session | Final optimized run |
|---|---:|---:|
| Model calls | 3 | 2 |
| Input tokens reported by CLI | 155,621 | 105,002 |
| Output tokens reported by CLI | 6,074 | 4,683 |
| Cached input tokens reported by CLI | 8,448 | 0 |
| Phase elapsed seconds | 161.67 | 112.05 |
| Assessed requirements | 19 | 19 |
| PASS requirements | 19 | 19 |
| Readiness | READY_FOR_FINAL_REVIEW | READY_FOR_FINAL_REVIEW |
| Integrity risk | NONE_FOUND | NONE_FOUND |

The final run used about 32.5% fewer input tokens, 22.9% fewer output tokens
and 30.7% less elapsed time. Every requirement status was unchanged. All 33
original-file line ranges cited by the final requirement assessments were
within their source files; this range check does not independently establish
that each academic judgment is correct. Student programs were not executed.

Local audit artifacts (git-ignored):

- Earlier: `reviews/deliza-kadriu__detyra1-ready-sample/20261021-153701/runner.phase1.json`
- Final: `reviews/deliza-kadriu__detyra1-ready-sample/20261021-154134/runner.phase1.json`

The earlier run already used compact JSON reads and the first version of the
plain-text subscription transport. Final changes prioritized code/verifiers
and history, replaced repeated per-line labels with source blocks, supplied
exact duplicate contents by reference, and requested compact output without
echoing runner metadata. The final model requested one additional batch for
the execution log and rendered search trees, then submitted its report.

This is one paired trial, not a statistical benchmark or a quality guarantee.
Provider load, model defaults, response length and caching can change timings.
Agent 2's correction-only phase-2 submission is regression-tested but was not
live-benchmarked in this trial. No model or reasoning-effort downgrade was
introduced to obtain these measurements.
