"""
Second example: customer master data in the CRM vs the billing system (synthetic).
Shows the toolkit reconciling a different dataset with only a new config file.
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def build(seed: int = 21, n: int = 800) -> None:
    rng = np.random.default_rng(seed)
    crm = pd.DataFrame({
        "account_id": [f"ACC-{i:05d}" for i in range(1, n + 1)],
        "email": [f"user{i}@example.com" for i in range(1, n + 1)],
        "state": rng.choice(["TX", "OK", "LA", "NM", "AR"], n),
        "plan": rng.choice(["Basic", "Plus", "Premium"], n),
        "credit_limit": rng.choice([500, 1000, 2500, 5000], n).astype(float),
        "status": rng.choice(["Active", "Suspended", "Closed"], n, p=[0.85, 0.1, 0.05]),
    })
    billing = crm.copy()
    idx = rng.permutation(n)
    billing.loc[idx[:6], "status"] = "Active"                     # closures not synced to billing
    billing.loc[idx[6:10], "plan"] = "Basic"                      # plan upgrades not synced
    billing.loc[idx[10:20], "email"] = billing.loc[idx[10:20], "email"].str.upper()  # case only: ignored
    billing = billing.drop(index=idx[20:24])                      # never provisioned in billing
    crm.loc[idx[24:27], "email"] = None                           # CRM data-quality gaps
    crm.loc[idx[27:29], "credit_limit"] = -100.0
    crm.to_csv(HERE / "crm_customers.csv", index=False)
    billing.sample(frac=1, random_state=3).to_csv(HERE / "billing_customers.csv", index=False)
    print(f"Wrote crm_customers.csv ({len(crm)}) and billing_customers.csv ({len(billing)})")


if __name__ == "__main__":
    build()
