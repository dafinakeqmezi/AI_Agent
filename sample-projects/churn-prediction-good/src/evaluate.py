"""End-to-end evaluation: load -> split -> train -> evaluate on the held-out test set.

Writes results/metrics.json, which is the single source of every number in
report/report.md.

Usage:
    python src/evaluate.py
"""
import json
import platform
from pathlib import Path

import sklearn
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

from preprocess import PROJECT_ROOT, SEED, TEST_SIZE, describe, load_data, split_data
from train import train_models

RESULTS_PATH = PROJECT_ROOT / "results" / "metrics.json"


def classification_metrics(y_true, y_pred) -> dict:
    """Metrics for the positive (churn = 1) class plus the confusion matrix."""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def main(out_path: Path = RESULTS_PATH) -> dict:
    df = load_data()
    X_train, X_test, y_train, y_test = split_data(df)
    models = train_models(X_train, y_train)

    results = {
        "setup": {
            "seed": SEED,
            "test_size": TEST_SIZE,
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "train_churn_rate": round(float(y_train.mean()), 4),
            "test_churn_rate": round(float(y_test.mean()), 4),
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
        },
        "dataset": describe(df),
        "models": {},
    }
    for name, model in models.items():
        results["models"][name] = {
            "train": classification_metrics(y_train, model.predict(X_train)),
            "test": classification_metrics(y_test, model.predict(X_test)),
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


if __name__ == "__main__":
    res = main()
    print(f"{'model':<22}{'acc':>7}{'prec':>7}{'rec':>7}{'f1':>7}")
    for name, m in res["models"].items():
        t = m["test"]
        print(f"{name:<22}{t['accuracy']:>7.3f}{t['precision']:>7.3f}{t['recall']:>7.3f}{t['f1']:>7.3f}")
    print(f"wrote {RESULTS_PATH}")
