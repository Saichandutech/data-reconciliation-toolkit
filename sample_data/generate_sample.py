"""
Create two synthetic invoice extracts that *should* match but don't:

  billing_system.csv       - the source of truth (billing platform)
  reporting_warehouse.csv  - the copy loaded into the reporting warehouse

Known issues are injected on purpose so the toolkit's output can be checked
against an answer key (sample_data/answer_key.json). All data is synthetic.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
N = 5_000
STATUSES = ["Paid", "Open", "Overdue", "Void"]
REGIONS = ["North", "South", "East", "West", "Central"]


def build(seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    src = pd.DataFrame(
        {
            "invoice_id": [f"INV-{i:06d}" for i in range(100001, 100001 + N)],
            "account_id": [f"ACC-{a:05d}" for a in rng.integers(1, 1800, N)],
            "invoice_date": (
                pd.Timestamp("2026-01-01") + pd.to_timedelta(rng.integers(0, 270, N), unit="D")
            ).strftime("%Y-%m-%d"),
            "amount": np.round(rng.gamma(4, 30, N) + 20, 2),
            "status": rng.choice(STATUSES, N, p=[0.70, 0.18, 0.10, 0.02]),
            "region": rng.choice(REGIONS, N),
        }
    )
    pool = list(rng.permutation(N))  # draw disjoint row positions for each issue

    def take(k):
        return [pool.pop() for _ in range(k)]

    key = {}

    # 0. Data-quality problems in the SOURCE (they flow downstream to the warehouse
    #    too, so reconciliation can't see them - validation rules must catch them)
    nulls = take(6)
    src.loc[nulls, "account_id"] = np.nan
    neg = take(4)
    src.loc[neg, "amount"] = -src.loc[neg, "amount"]
    bad = take(3)
    src.loc[bad, "status"] = "Pending??"
    fut = take(2)
    src.loc[fut, "invoice_date"] = "2027-03-15"
    key["validation"] = {
        "account_id_not_null": 6,
        "amount_min_0": 4,
        "status_allowed_values": 3,
        "invoice_date_not_in_future": 2,
    }

    tgt = src.copy()

    # 1. Rows that never made it to the warehouse
    drop = take(12)
    key["missing_in_target"] = sorted(src.loc[drop, "invoice_id"])
    tgt = tgt.drop(index=drop)

    # 2. Amount mismatches (real differences)
    amt = take(20)
    tgt.loc[amt, "amount"] = (tgt.loc[amt, "amount"] * rng.uniform(0.80, 1.20, 20)).round(2)
    key["amount_mismatches"] = sorted(src.loc[amt, "invoice_id"])

    # 3. Tiny rounding differences that should be IGNORED (within 0.01 tolerance)
    rnd = take(30)
    tgt.loc[rnd, "amount"] = tgt.loc[rnd, "amount"] + 0.004

    # 4. Status not updated in the warehouse
    st = take(8)
    tgt.loc[st, "status"] = np.where(src.loc[st, "status"] == "Paid", "Open", "Paid")
    key["status_mismatches"] = sorted(src.loc[st, "invoice_id"])

    # 5. Case / whitespace noise that should be IGNORED after normalisation
    ws = take(15)
    tgt.loc[ws, "region"] = " " + tgt.loc[ws, "region"].str.upper() + " "

    # 6. Duplicate loads in the warehouse
    dup = take(3)
    key["duplicates_in_target"] = sorted(src.loc[dup, "invoice_id"])
    tgt = pd.concat([tgt, tgt.loc[dup]], ignore_index=True)

    # 7. Rows in the warehouse that don't exist in billing
    extra = pd.DataFrame(
        {
            "invoice_id": [f"INV-{i:06d}" for i in range(900001, 900006)],
            "account_id": "ACC-99999",
            "invoice_date": "2026-09-30",
            "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
            "status": "Open",
            "region": "West",
        }
    )
    key["missing_in_source"] = sorted(extra["invoice_id"])
    tgt = pd.concat([tgt, extra], ignore_index=True)

    src.to_csv(HERE / "billing_system.csv", index=False)
    tgt.sample(frac=1, random_state=1).to_csv(HERE / "reporting_warehouse.csv", index=False)
    (HERE / "answer_key.json").write_text(json.dumps(key, indent=2))
    return key


if __name__ == "__main__":
    k = build()
    print("Wrote billing_system.csv, reporting_warehouse.csv, answer_key.json")
    print({name: (len(v) if isinstance(v, list) else v) for name, v in k.items()})
