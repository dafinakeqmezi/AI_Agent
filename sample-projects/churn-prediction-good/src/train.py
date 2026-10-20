"""Model definitions and training.

Three models are trained on the same training split:
  - majority-class baseline (DummyClassifier): the trivial reference point
  - Logistic Regression: the traditional, interpretable baseline
  - Random Forest: the proposed model

Hyperparameters are fixed (no tuning) and documented in report/report.md, Table 2.
"""
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from preprocess import SEED, build_preprocessor, load_data, split_data


def build_models(seed: int = SEED) -> dict:
    return {
        "majority_baseline": Pipeline([
            ("prep", build_preprocessor()),
            ("clf", DummyClassifier(strategy="most_frequent")),
        ]),
        "logistic_regression": Pipeline([
            ("prep", build_preprocessor()),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)),
        ]),
        "random_forest": Pipeline([
            ("prep", build_preprocessor()),
            ("clf", RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=5,
                                           class_weight="balanced", random_state=seed, n_jobs=1)),
        ]),
    }


def train_models(X_train, y_train, seed: int = SEED) -> dict:
    models = build_models(seed)
    for model in models.values():
        model.fit(X_train, y_train)
    return models


if __name__ == "__main__":
    X_train, X_test, y_train, y_test = split_data(load_data())
    for name, model in train_models(X_train, y_train).items():
        print(f"trained {name}: train accuracy={model.score(X_train, y_train):.3f}")
