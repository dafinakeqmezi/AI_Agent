# Knowledge base index

Shared by Agent 1 (Reviewer) and Agent 2 (Professor). Retrieval is by topic: open only the files relevant to the requirement you are assessing, and do not load everything up front.

| Need | File |
|---|---|
| **Rules both agents must follow** (always read first) | `policies/agent-rules.md` |
| Agent names, personas, greetings and signatures (Ada = Agent 1, Prof. Vale = Agent 2) | `identities.json` |
| **Which assignment am I assessing?** The run's `run.json` → `assignment` (default `ml-project`). List: `python -m grader assignments` | `assignments/<id>/assignment.json` |
| Detyra 1 (AI 2026/27, uninformed search): requirements, rubric, DoD, guidelines | `assignments/detyra1/` (`requirements.json`, `rubric.json`, `dod.json`, `guidelines.md`); course text in `course/ai-2026-27/` |
| ML project requirements (IDs, points, mandatory flags, checks) | `requirements/requirements.json` |
| ML project Definition of Done (Agent 1 readiness) | `requirements/dod.json` |
| ML project grading rubric, weights, grade scale (Agent 2) | `rubric/rubric.json` |
| Academic-integrity indicators, risk levels, AI-usage policy | `policies/integrity-policy.json` |
| Course / professor documents (highest authority) | `course/` |
| Data leakage (DATA-004) | `ml-guidelines/data-leakage.md` |
| Metric choice (EVAL-001, PROB-002) | `ml-guidelines/metric-selection.md` |
| Baselines, experiments, significance, claims ledger (METH-*, EXP-*) | `ml-guidelines/experimental-design.md` |
| Reproducibility (REPRO-*) | `ml-guidelines/reproducibility.md` |
| Code quality, report-vs-code consistency (IMPL-*) | `ml-guidelines/code-quality.md` |
| Literature review, source credibility, citation verification (LIT-*) | `ml-guidelines/literature-review.md` |
| Ethics / responsible AI (DOC-003, DATA-005) | `ml-guidelines/responsible-ai.md` |
| Verified references the agents may cite or recommend | `literature/references.json` |
| Git-history grading (C11) thresholds, guidance and fairness principles | `policies/version-control-policy.json` |
| **Textbook: Russell & Norvig, AIMA 4th ed.** (ML foundations, model selection, overfitting, deep learning, NLP, RL, AI ethics) | `literature/books/aima4/TOPICS.md` (requirement → section map) → `INDEX.md` (all sections + pdf pages) → Grep `text/` → Read `aima4.pdf` pages |

Requirement-to-guideline mapping: each requirement's `review_checks` points at the relevant guideline file. The `ml-guidelines/` files apply to the ML project; other assignments list their own guidelines in `assignment.json` → `guidelines`.

Cross-student comparison (copying between students) for a whole class: `python -m grader similarity --assignment <id>` (indicators only; see `policies/integrity-policy.json`).

Version: see `manifest.json`. Run `python -m grader versions` to print the exact versions and content hashes in effect.
