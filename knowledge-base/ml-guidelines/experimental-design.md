# Experimental design

Relevant requirements: **METH-001, METH-004, EXP-001 to EXP-004, EVAL-003**.
Key sources: `dodge2019showyourwork`, `demsar2006comparisons`, `dietterich1998tests`, `varma2006cvbias`, `lipton2019troubling`.

## Baselines (METH-001)

Recommended minimum for a student project:

1. **Trivial baseline**: majority class / mean predictor / random.
2. **Simple, traditional baseline**: logistic/linear regression, a decision tree, or the standard method from the related work.
3. **Proposed approach.**

A single model with no comparison cannot support a claim of being "good".

## Controlled comparison (EXP-001)

- All models are evaluated on the same splits, preprocessing and metrics.
- Hyperparameter tuning effort is comparable across models (Dodge et al. 2019): do not tune the proposed model extensively while leaving the baseline at defaults without saying so.

## Variability and significance (EXP-002)

- Report mean ± std over several seeds or CV folds.
- When differences are small, use an appropriate test: McNemar's test or 5x2cv paired test for two classifiers on one dataset (Dietterich 1998), Wilcoxon signed-rank / Friedman with post-hoc tests across multiple datasets (Demšar 2006).
- Not appropriate everywhere (e.g. a single large held-out set with large effects): mark NOT_APPLICABLE only with a reason.

## Ablation (EXP-003)

Needed when the approach has several components (e.g. feature-engineering steps, attention module, data augmentation) and the report claims they help. Remove or replace one component at a time.

## Claims ledger (EXP-004)

For every quantitative or comparative claim in the report, record:

```
CLAIM:    "Our model outperforms existing approaches."
LOCATION: report.pdf p. 7
EVIDENCE: (results file / notebook cell / table) or "none found"
STATUS:   SUPPORTED | UNSUPPORTED | CONTRADICTED
```

Lipton & Steinhardt (2019) list common problems to flag: failing to separate explanation from speculation, failing to identify the source of gains (missing ablations), "mathiness", and misuse of language (e.g. "significant" without a test).

## Generalization (EVAL-003)

Compare training, validation and test performance. A large train-test gap means overfitting; a test score above validation/training needs explanation (possible leakage).
