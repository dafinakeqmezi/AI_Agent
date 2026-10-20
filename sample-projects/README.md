# Controlled sample projects

Two small scikit-learn projects with **known, documented quality**. They test
whether Agent 1 (`ml-reviewer`) and Agent 2 (`professor`) find the right
problems, rather than producing generic feedback.

| Project | Intent | Answer key |
|---|---|---|
| `churn-prediction-good/` | Good, mostly complete. Only minor gaps. | `tests/expected/expected-churn-review.json` |
| `student-performance-bad/` | Weak, with planted problems. | `tests/expected/expected-student-review.json` |

> **Do not put answer keys or notes inside these folders.** The reviewer reads
> every file in a project folder. Anything that explains the planted flaws must
> stay in `tests/expected/`. The test suite checks this.

## Expected findings (summary)

**churn-prediction-good**

| | Requirements |
|---|---|
| PASS | problem definition (PROB-001/002), dataset documentation (DATA-001/002), train/test split and no leakage (DATA-004), baseline (METH-001), evaluation metrics (EVAL-001), reproducibility (REPRO-001..004), README (DOC-001) |
| PARTIAL | literature review (LIT-001), error analysis (EVAL-002) |
| MISSING | statistical significance (EXP-002), presentation (PRES-001) |
| BLOCKER | none |

Trap: the scanner raises `mentioned_not_implemented` for "cross-validation"
because the Limitations section says it was **not** run. A good reviewer
recognises the negation and does not turn it into an IMPL-002 finding.

**student-performance-bad**

| | Requirements |
|---|---|
| PASS | basic ML model exists (IMPL-001; PARTIAL also accepted) |
| PARTIAL | problem definition (PROB-001), dataset explanation (DATA-002) |
| MISSING | baseline (METH-001), literature review (LIT-001), reproducibility (REPRO-001/002/003), limitations (PROB-004), only accuracy (EVAL-001), hardcoded path (IMPL-003), poor README (DOC-001) |
| BLOCKER | target leakage (DATA-004), report/code inconsistency (IMPL-002), unverifiable or unsupporting citation (LIT-003), unsupported 97.8% claim (EXP-004) |

The target leakage (`final_exam_score` is a feature and `passed` is
`final_exam_score >= 50`) is **not** detected by the deterministic scanner. Only
a reviewer that actually reads the code and data catches it. The scanner does
catch the hardcoded path, missing seed, missing requirements.txt, missing run
instructions and the 5-fold CV claim.

Each answer key lists **every** requirement: an exact expected status,
`also_acceptable` alternatives where reasonable reviewers could differ, and a
`core` flag for the findings that must be right. The VCS requirements are
`not_asserted`, because the fixtures have no git history of their own.

## Running the check

```bash
# Agent 1
/review sample-projects/student-performance-bad
python -m grader check-expected reviews/student-performance-bad/<ts> tests/expected/expected-student-review.json

# Agent 2
/freeze sample-projects/student-performance-bad "Sample Student"
/grade <submission-id>
python -m grader check-expected evaluations/<submission-id>/eval-<ts> tests/expected/expected-student-review.json
```

The checker writes `expected-check.md` / `.json` into the run directory and
exits 1 on FAIL. A run fails when a core finding or a planted blocker is missed,
when the agent says PASS where a problem is expected (missed problem), when it
says MISSING/BLOCKER where PASS is expected (false deduction), when it raises a
BLOCKER the key does not allow, when overall agreement falls below 0.8, or when
readiness, integrity level, total or grade fall outside the expected range.
For evaluations, BLOCKER maps to MISSING (Agent 2 has no BLOCKER status).

Expected grades (placeholder rubric): churn-prediction-good total 65-90 (grade
7-9; C11 is lost without git history), student-performance-bad total 0-35
(grade 5).

## Regenerating the data

- `churn-prediction-good`: `python src/make_dataset.py && python src/evaluate.py`
  (deterministic, seed 42; `results/metrics.json` must not change).
- `student-performance-bad/data.csv` was generated once (240 rows, 73.8% pass,
  8 rows with missing values). The project deliberately ships no generator and
  no data documentation.
