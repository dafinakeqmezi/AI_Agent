# Data leakage checklist

Relevant requirement: **DATA-004** (also IMPL-002, EXP-004, INT-008).
Key sources: `kapoor2023leakage`, `kaufman2012leakage`, `kapoor2024reforms`, `varma2006cvbias` (see `literature/references.json`).

Leakage is the most common reason a student ML project looks much better than it is. Kapoor & Narayanan (2023) found leakage errors affecting hundreds of papers across many fields. Check every type below. Treat `scan.json` signals as leads, not conclusions: open the code and confirm.

## Leakage types (Kapoor & Narayanan taxonomy, simplified)

| # | Type | What to look for in code |
|---|---|---|
| L1 | No separate test set | Model evaluated on data it was trained on; `model.score(X, y)` on the full set; no hold-out at all |
| L2 | Preprocessing on train+test | `scaler.fit_transform(X)`, `imputer.fit(X)`, `PCA().fit(X)`, `TfidfVectorizer().fit_transform(all_texts)`, target/label encoders fit **before** the split |
| L3 | Feature selection on train+test | `SelectKBest(...).fit(X, y)` or correlation-based filtering on the full dataset before splitting |
| L4 | Resampling before split | `SMOTE().fit_resample(X, y)` / oversampling before `train_test_split` (synthetic copies of test points end up in training) |
| L5 | Duplicates across splits | Duplicate rows or near-duplicate images/texts present in both train and test; augmented copies of the same sample split across sets |
| L6 | Group / subject leakage | Same patient/user/session/device in train and test when the task is generalizing to new ones; needs `GroupKFold` / group split |
| L7 | Temporal leakage | Random split on time-series or forecasting data; features computed using future values (rolling windows centered, `shift(-k)`) |
| L8 | Target leakage (illegitimate features) | Features that are proxies of the label or only known after the outcome (e.g. "account_closed_date" to predict churn) |
| L9 | Tuning on the test set | `GridSearchCV.fit(X_test, ...)`, early stopping on test, picking the best epoch/model by test score, repeated "try and check test" |
| L10 | Non-nested CV for model selection | Reporting the best CV score from a hyperparameter search as the generalization estimate (Varma & Simon 2006) |

## Correct patterns

- `train_test_split` (or group/time-aware split) **first**, then `Pipeline([...preprocessing..., model])` fit on training data only.
- Cross-validation with the whole `Pipeline` passed to `cross_val_score` / `GridSearchCV`, so preprocessing is refit inside each fold.
- Test set used once, at the end.

## Red flags in reported results

- Near-perfect metrics (e.g. > 98-99% accuracy) on a task known to be hard.
- Test score higher than validation/training score without explanation.
- Large gap between the report and a re-run of the supplied code.

When leakage is confirmed, the severity is **CRITICAL** and the status of DATA-004 is **BLOCKER** (Agent 1) / **MISSING or PARTIAL** (Agent 2, depending on extent). Also check whether the claims in the report (EXP-004) depend on the leaked results.
