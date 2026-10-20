# Customer Churn Prediction

Predicts whether a telecom customer will churn (cancel their contract), using
tabular customer data and two classical classifiers: Logistic Regression
(baseline) and Random Forest (proposed model).

**Research question:** On tabular telecom customer data, does a Random Forest
achieve a higher F1 score on the churn class than a class-weighted Logistic
Regression baseline?

The full write-up is in [report/report.md](report/report.md). All reported numbers
come from [results/metrics.json](results/metrics.json).

## Project structure

```
churn-prediction-good/
├── README.md
├── requirements.txt          pinned dependencies (Python 3.14.2)
├── data/
│   ├── README.md             dataset card: source, license, columns, distribution
│   └── customer_churn.csv    1,200 synthetic customers
├── src/
│   ├── make_dataset.py       regenerates data/customer_churn.csv (seed 42)
│   ├── preprocess.py         loading, checks, stratified split, preprocessing pipeline
│   ├── train.py              majority baseline, Logistic Regression, Random Forest
│   └── evaluate.py           end-to-end run; writes results/metrics.json
├── report/
│   └── report.md
└── results/
    └── metrics.json
```

## How to reproduce

Requires Python 3.14 (tested with 3.14.2).

```bash
# 1. Create an environment and install the pinned dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. (Optional) regenerate the dataset; the committed CSV is identical
python src/make_dataset.py

# 3. Train all models and evaluate on the held-out test set
python src/evaluate.py             # writes results/metrics.json
```

`python src/preprocess.py` prints the dataset summary and split sizes, and
`python src/train.py` trains the models and prints training accuracy.

Every random component uses seed `42` (`SEED` in `src/preprocess.py`), so
re-running produces the same `results/metrics.json`.

## Results (test set, n = 240)

| Model | Accuracy | Precision | Recall | F1 (churn) |
|---|---|---|---|---|
| Majority baseline | 0.7375 | 0.0000 | 0.0000 | 0.0000 |
| Logistic Regression | 0.7250 | 0.4845 | 0.7460 | **0.5875** |
| Random Forest | 0.7458 | 0.5128 | 0.6349 | 0.5674 |

The Random Forest did not improve F1 over the Logistic Regression baseline. See
the report for the discussion and limitations.
