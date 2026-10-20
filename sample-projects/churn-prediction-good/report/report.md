# Predicting Customer Churn in Telecom: Logistic Regression vs. Random Forest

## Abstract

Customer churn is costly for telecom operators because acquiring a new customer
is more expensive than retaining an existing one. We compare a class-weighted
Logistic Regression baseline with a Random Forest for predicting churn from
seven tabular customer features on a 1,200-customer synthetic dataset (26.4%
churners). On a stratified held-out test set of 240 customers, Logistic
Regression reached an F1 score of 0.5875 on the churn class and the Random
Forest 0.5674; a majority-class baseline scores 0.0 despite 73.75% accuracy.
The Random Forest therefore did not improve on the linear baseline, and it shows
a clear train/test gap. Both models met our pre-defined success threshold
(F1 >= 0.55).

## 1. Introduction

### 1.1 Problem

A telecom operator wants to identify customers who are likely to cancel their
contract so that the retention team can contact them with an offer before they
leave. The retention team can only contact a limited number of customers, so
the model has to find a useful share of the real churners (recall) without
flooding the team with false alarms (precision).

### 1.2 Research question

> **RQ:** On tabular telecom customer data, does a Random Forest achieve a
> higher F1 score on the churn class than a class-weighted Logistic Regression
> baseline, when both are trained and tested on the same stratified split?

### 1.3 Objective and success criterion

- **Primary metric:** F1 score of the positive (churn) class on the held-out
  test set.
- **Success threshold:** F1 >= 0.55, and clearly above the majority-class
  baseline.
- Accuracy, precision and recall are reported as secondary metrics.

### 1.4 Inputs, outputs and why ML

- **Inputs:** age, tenure in months, contract type, internet service, payment
  method, monthly charges and number of support calls (7 features).
- **Output:** a binary prediction (churn / no churn) per customer.
- **Why ML rather than a rule:** churn risk depends on several interacting
  factors (for example, many support calls matter more for month-to-month
  customers). A single hand-written rule such as "month-to-month contract" flags
  54% of all customers and cannot rank them, while a learned model combines all
  features and can be re-trained when customer behaviour changes.

### 1.5 Scope and assumptions

The project covers binary churn prediction from static customer attributes. It
does not model *when* a customer churns (survival analysis) or the cost of
retention offers. We assume that all features are available before the churn
decision is made.

## 2. Related Work

- **Neslin et al. (2006)** ran a churn-modelling tournament with many
  participants and found that the modelling approach has a measurable effect on
  how accurately churners are identified, with logistic regression and tree-based
  methods among the strong approaches.
- **Verbeke et al. (2012)** compared many classifiers for telecom churn and
  proposed a profit-based evaluation measure. They argue that the choice of
  evaluation metric changes which model looks best.
- **Breiman (2001)** introduced Random Forests, ensembles of decorrelated
  decision trees that can capture non-linear effects and interactions.
- **Saito and Rehmsmeier (2015)** show that for imbalanced binary
  classification, precision-recall-based evaluation is more informative than
  ROC-based evaluation.
- **Kapoor and Narayanan (2023)** document how data leakage, for example
  preprocessing fitted on the full dataset, inflates reported results in
  ML-based science.

Our project follows this literature by using a linear baseline and a tree
ensemble and by evaluating with precision, recall and F1 instead of accuracy.

## 3. Data

The dataset (`data/customer_churn.csv`) is synthetic and was generated with
`src/make_dataset.py` (seed 42) under a CC0 license; see `data/README.md` for
the full dataset card. Using synthetic data avoids privacy issues with real
customer records.

| Property | Value |
|---|---|
| Rows | 1,200 |
| Features | 7 (4 numeric, 3 categorical) + `customer_id` (dropped) |
| Target | `churn` (1 = churned) |
| Churn rate | 26.42% (317 churners) |
| Missing values | `monthly_charges`: 24 rows (2.0%) |
| Duplicate IDs | 0 |

*Table 1. Dataset summary (from `results/metrics.json`, key `dataset`).*

**Data quality.** `load_data()` checks that all expected columns are present
and that `customer_id` is unique. The only missing values are in
`monthly_charges`. They are imputed with the median of the *training* split.

## 4. Method

### 4.1 Train/test split

We use a single stratified hold-out split: 80% training (960 customers) and 20%
test (240 customers), `random_state=42`. Stratification keeps the churn rate
the same in both splits (26.46% train, 26.25% test). The test set is used once,
for the final evaluation only.

### 4.2 Preprocessing

The pipeline is implemented with scikit-learn (Pedregosa et al., 2011). All
preprocessing is inside a `Pipeline` together with the
classifier, so it is fitted on the training data only (avoiding the leakage
described by Kapoor and Narayanan, 2023):

- numeric features: median imputation, then standardisation;
- categorical features: one-hot encoding (`handle_unknown="ignore"`).

### 4.3 Models

| Model | Role | Hyperparameters |
|---|---|---|
| `DummyClassifier` | trivial baseline | `strategy="most_frequent"` |
| `LogisticRegression` | traditional baseline | `class_weight="balanced"`, `max_iter=1000` |
| `RandomForestClassifier` | proposed model | `n_estimators=300`, `max_depth=8`, `min_samples_leaf=5`, `class_weight="balanced"` |

*Table 2. Models and hyperparameters. All use `random_state=42`.*

Logistic Regression is a strong, interpretable baseline for tabular churn data
(Neslin et al., 2006). The Random Forest was chosen as the proposed model
because it can capture the non-linear and interaction effects (Breiman, 2001)
that we expect between support calls and contract type. Both models use
balanced class weights to counter the 26/74 class imbalance. Hyperparameters
were fixed in advance from common defaults. We did no tuning, so the test set
was never used for model selection.

### 4.4 Why F1 matters here

Only 26% of customers churn. A model that predicts "no churn" for everyone is
73.75% accurate on our test set but finds zero churners, which makes it useless
for the retention team. Accuracy rewards this behaviour because it is dominated
by the majority class. **Precision** measures how many flagged customers really
churn (wasted retention offers), **recall** measures how many real churners we
catch (lost customers). **F1**, the harmonic mean of the two, is high only if
both are reasonable, so we use it as the primary metric (Saito and Rehmsmeier,
2015).

## 5. Results

All numbers are produced by `python src/evaluate.py` and stored in
`results/metrics.json`.

| Model | Accuracy | Precision | Recall | F1 (churn) |
|---|---|---|---|---|
| Majority baseline | 0.7375 | 0.0000 | 0.0000 | 0.0000 |
| Logistic Regression | 0.7250 | 0.4845 | 0.7460 | **0.5875** |
| Random Forest | 0.7458 | 0.5128 | 0.6349 | 0.5674 |

*Table 3. Test-set results (n = 240, 63 churners).*

### 5.1 Confusion matrices (test set)

| | Pred. no churn | Pred. churn |
|---|---|---|
| **Logistic Regression**, actual no churn | 127 | 50 |
| **Logistic Regression**, actual churn | 16 | 47 |
| **Random Forest**, actual no churn | 139 | 38 |
| **Random Forest**, actual churn | 23 | 40 |

*Table 4. Confusion matrices (from `results/metrics.json`, key `confusion_matrix`).*

Logistic Regression catches 47 of the 63 churners but raises 50 false alarms.
The Random Forest is more conservative: 12 fewer false alarms, but it misses
7 more churners.

### 5.2 Training vs. test performance

| Model | Train F1 | Test F1 |
|---|---|---|
| Logistic Regression | 0.6061 | 0.5875 |
| Random Forest | 0.7251 | 0.5674 |

*Table 5. Generalisation gap.*

Logistic Regression generalises well (gap 0.019). The Random Forest shows a gap
of 0.158, which indicates overfitting even with `max_depth=8` and
`min_samples_leaf=5`.

## 6. Discussion

**Answer to the RQ:** no. On this dataset the Random Forest did not achieve a
higher F1 than the Logistic Regression baseline (0.5674 vs. 0.5875). It reached
higher accuracy and precision but lower recall. Both models clearly beat the
majority baseline and both meet the F1 >= 0.55 threshold.

A likely reason is that most of the signal in the data is approximately linear
in the log-odds (tenure, contract type, charges), which suits Logistic
Regression. The interaction between support calls and contract type that
motivated the Random Forest affects only a small group of customers. Combined
with the overfitting in Table 5, this suggests that the extra flexibility of the
forest is not worth it at this dataset size.

For the retention use case, the higher recall of Logistic Regression is
probably preferable if a retention offer is cheap compared with losing a
customer; if offers are expensive, the Random Forest's higher precision may be
preferred. A profit-based evaluation (Verbeke et al., 2012) would make this
trade-off explicit.

## 7. Limitations

- **Single train/test split.** The test set has only 63 churners, so the F1
  difference of 0.02 between the two models may well be due to chance. We did
  not run cross-validation or repeated splits and did not test the difference
  for statistical significance.
- **Synthetic data.** The data were generated from a known logistic model, which
  probably favours Logistic Regression. Results may not transfer to real
  telecom data.
- **No hyperparameter tuning.** The Random Forest might perform better with
  tuned hyperparameters (selected by cross-validation on the training set).
- **Fixed decision threshold.** We used the default 0.5 threshold. Tuning the
  threshold on validation data could trade precision against recall.
- **Limited error analysis.** We report confusion matrices but did not analyse
  which customer segments are misclassified.

## 8. Ethical considerations

Because the data are synthetic, no personal data are processed. In a real
deployment, a churn model could treat customer groups differently (for
example, by age). Before deployment, performance and offer rates should be
checked per age group, and customers should not be disadvantaged by a churn
score.

## 9. Conclusion

We built a reproducible churn-prediction pipeline with a trivial baseline, a
Logistic Regression baseline and a Random Forest. Evaluated by F1 on the churn
class, Logistic Regression (0.5875) performed slightly better than the Random
Forest (0.5674), and both far exceeded the majority baseline. Future work:
repeated cross-validation with a significance test, hyperparameter tuning on
validation folds, threshold optimisation and a per-segment error analysis.

## References

- Breiman, L. (2001). Random Forests. *Machine Learning*, 45(1), 5-32.
  https://doi.org/10.1023/A:1010933404324
- Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in
  machine-learning-based science. *Patterns*, 4(9), 100804.
  https://doi.org/10.1016/j.patter.2023.100804
- Neslin, S. A., Gupta, S., Kamakura, W., Lu, J., & Mason, C. H. (2006).
  Defection Detection: Measuring and Understanding the Predictive Accuracy of
  Customer Churn Models. *Journal of Marketing Research*, 43(2), 204-211.
  https://doi.org/10.1509/jmkr.43.2.204
- Pedregosa, F., et al. (2011). Scikit-learn: Machine Learning in Python.
  *Journal of Machine Learning Research*, 12, 2825-2830.
  https://jmlr.org/papers/v12/pedregosa11a.html
- Saito, T., & Rehmsmeier, M. (2015). The Precision-Recall Plot Is More
  Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced
  Datasets. *PLOS ONE*, 10(3), e0118432.
  https://doi.org/10.1371/journal.pone.0118432
- Verbeke, W., Dejaeger, K., Martens, D., Hur, J., & Baesens, B. (2012). New
  insights into churn prediction in the telecommunication sector: A profit
  driven data mining approach. *European Journal of Operational Research*,
  218(1), 211-229. https://doi.org/10.1016/j.ejor.2011.09.031
