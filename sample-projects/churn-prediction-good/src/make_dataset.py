"""Generate the synthetic telecom churn dataset used in this project.

The data are synthetic so that they can be shared without privacy or licensing
restrictions. The generating process is documented in data/README.md.

Usage:
    python src/make_dataset.py            # writes data/customer_churn.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_CUSTOMERS = 1200
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "customer_churn.csv"


def generate(n: int = N_CUSTOMERS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    contract = rng.choice(["month-to-month", "one-year", "two-year"], size=n, p=[0.55, 0.25, 0.20])
    internet = rng.choice(["dsl", "fiber", "none"], size=n, p=[0.35, 0.45, 0.20])
    payment = rng.choice(["electronic-check", "credit-card", "bank-transfer", "mailed-check"],
                         size=n, p=[0.35, 0.25, 0.25, 0.15])
    age = rng.integers(18, 80, size=n)

    max_tenure = np.select([contract == "month-to-month", contract == "one-year"], [36, 60], 72)
    tenure = np.floor(rng.uniform(0, 1, size=n) ** 1.3 * max_tenure).astype(int) + 1

    base_charge = np.select([internet == "fiber", internet == "dsl"], [80.0, 55.0], 25.0)
    monthly = np.round(base_charge + rng.normal(0, 12, size=n), 2).clip(18.0, 120.0)

    support_calls = rng.poisson(1.2 + 1.5 * (internet == "fiber"), size=n)

    # Churn log-odds: short tenure, month-to-month contracts, high charges and
    # many support calls raise the risk. The support-call effect has a
    # threshold (>= 4 calls) and interacts with the contract type, so the
    # relationship is not purely linear.
    logit = (
        -1.4
        + 1.3 * (contract == "month-to-month")
        - 0.9 * (contract == "two-year")
        - 0.035 * tenure
        + 0.025 * (monthly - 65)
        + 1.4 * (support_calls >= 4) * (contract == "month-to-month")
        + 0.5 * (support_calls >= 4)
        + 0.4 * (payment == "electronic-check")
        - 0.008 * (age - 45)
    )
    p_churn = 1 / (1 + np.exp(-logit))
    churn = (rng.uniform(size=n) < p_churn).astype(int)

    df = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(1, n + 1)],
        "age": age,
        "tenure_months": tenure,
        "contract_type": contract,
        "internet_service": internet,
        "payment_method": payment,
        "monthly_charges": monthly,
        "support_calls": support_calls,
        "churn": churn,
    })

    # Simulate a realistic data-quality issue: ~2% of monthly_charges missing.
    missing_idx = rng.choice(n, size=int(0.02 * n), replace=False)
    df.loc[missing_idx, "monthly_charges"] = np.nan
    return df


if __name__ == "__main__":
    data = generate()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(data)} rows to {OUT_PATH} (churn rate {data['churn'].mean():.3f})")
