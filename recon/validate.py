"""
Rule-based data validation.

Rules are declared in config (YAML), e.g.

    validation:
      - {column: account_id, rule: not_null}
      - {column: invoice_id, rule: unique}
      - {column: amount, rule: min, value: 0}
      - {column: status, rule: allowed_values, value: [Paid, Open, Overdue, Void]}
      - {column: invoice_id, rule: pattern, value: '^INV-\\d{6}$'}
      - {column: invoice_date, rule: not_in_future}
      - {column: discount_pct, rule: between, value: [0, 50]}
      - {column: notes, rule: max_length, value: 255}
      - {columns: [account_id, invoice_date], rule: unique_together}

Each rule returns the rows that FAIL it, so every issue can be traced to a record.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class RuleResult:
    name: str
    column: str
    rule: str
    failed_rows: pd.DataFrame

    @property
    def failures(self) -> int:
        return len(self.failed_rows)

    @property
    def passed(self) -> bool:
        return self.failures == 0


def _mask(df: pd.DataFrame, column: str, rule: str, value, today: pd.Timestamp) -> pd.Series:
    """Return a boolean mask that is True where the row FAILS the rule."""
    s = df[column]
    if rule == "not_null":
        return s.isna() | (s.astype(str).str.strip() == "")
    if rule == "unique":
        return s.duplicated(keep=False) & s.notna()
    if rule == "min":
        return pd.to_numeric(s, errors="coerce") < value
    if rule == "max":
        return pd.to_numeric(s, errors="coerce") > value
    if rule == "allowed_values":
        return s.notna() & ~s.isin(value)
    if rule == "pattern":
        return s.notna() & ~s.astype(str).str.fullmatch(value)
    if rule == "not_in_future":
        return pd.to_datetime(s, errors="coerce") > today
    if rule == "between":
        lo, hi = value
        num = pd.to_numeric(s, errors="coerce")
        return num.notna() & ((num < lo) | (num > hi))
    if rule == "max_length":
        return s.notna() & (s.astype(str).str.len() > value)
    if rule == "is_date":
        return s.notna() & pd.to_datetime(s, errors="coerce", format=value or None).isna()
    raise ValueError(f"Unknown rule '{rule}'")


def validate(df: pd.DataFrame, rules: list[dict], today: str | None = None) -> list[RuleResult]:
    today_ts = pd.Timestamp(today) if today else pd.Timestamp.today().normalize()
    results = []
    for r in rules:
        rule, value = r["rule"], r.get("value")
        if rule == "unique_together":
            # composite key: the combination of several columns must be unique
            cols = r["columns"]
            missing = [c for c in cols if c not in df.columns]
            if missing:
                raise KeyError(f"Validation rule refers to missing columns {missing}")
            column = "+".join(cols)
            mask = df.duplicated(subset=cols, keep=False)
            results.append(RuleResult(name=r.get("name", f"{'_'.join(cols)}_unique_together"), column=column,
                                      rule=rule, failed_rows=df[mask].copy()))
            continue
        column = r["column"]
        if column not in df.columns:
            raise KeyError(f"Validation rule refers to missing column '{column}'")
        mask = _mask(df, column, rule, value, today_ts)
        results.append(
            RuleResult(
                name=r.get("name", f"{column}_{rule}" + (f"_{value}" if rule in ("min", "max") else "")),
                column=column,
                rule=rule,
                failed_rows=df[mask.fillna(False)].copy(),
            )
        )
    return results


def summarise(results: list[RuleResult], total_rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rule": r.name,
                "column": r.column,
                "check": r.rule,
                "failed_rows": r.failures,
                "pass_rate_pct": round(100 * (1 - r.failures / total_rows), 2) if total_rows else 100.0,
                "status": "PASS" if r.passed else "FAIL",
            }
            for r in results
        ]
    )
