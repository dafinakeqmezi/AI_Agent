"""Data loading, train/test split and the preprocessing pipeline.

All preprocessing (imputation, scaling, one-hot encoding) is wrapped in a
scikit-learn ColumnTransformer that is placed *inside* each model Pipeline, so
it is fitted on the training split only and never sees the test data.
"""
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 42
TEST_SIZE = 0.2
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "customer_churn.csv"

TARGET = "churn"
ID_COLUMN = "customer_id"
NUMERIC_FEATURES = ["age", "tenure_months", "monthly_charges", "support_calls"]
CATEGORICAL_FEATURES = ["contract_type", "internet_service", "payment_method"]


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load the CSV and run basic integrity checks."""
    df = pd.read_csv(path)
    expected = {ID_COLUMN, TARGET, *NUMERIC_FEATURES, *CATEGORICAL_FEATURES}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        raise ValueError(f"Dataset is missing columns: {sorted(missing_cols)}")
    if df[ID_COLUMN].duplicated().any():
        raise ValueError("Duplicate customer_id values found; each customer must appear once.")
    return df


def split_data(df: pd.DataFrame, test_size: float = TEST_SIZE, seed: int = SEED):
    """Stratified hold-out split. The ID column is dropped (it carries no signal)."""
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]
    return train_test_split(X, y, test_size=test_size, stratify=y, random_state=seed)


def build_preprocessor() -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = OneHotEncoder(handle_unknown="ignore")
    return ColumnTransformer([
        ("num", numeric, NUMERIC_FEATURES),
        ("cat", categorical, CATEGORICAL_FEATURES),
    ])


def describe(df: pd.DataFrame) -> dict:
    """Summary statistics reported in the Data section of the report."""
    return {
        "n_rows": int(len(df)),
        "n_features": len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES),
        "churn_rate": round(float(df[TARGET].mean()), 4),
        "missing_values": {c: int(v) for c, v in df.isna().sum().items() if v > 0},
        "duplicate_ids": int(df[ID_COLUMN].duplicated().sum()),
    }


if __name__ == "__main__":
    data = load_data()
    print(describe(data))
    X_train, X_test, y_train, y_test = split_data(data)
    print(f"train={len(X_train)} test={len(X_test)} "
          f"train churn rate={y_train.mean():.3f} test churn rate={y_test.mean():.3f}")
