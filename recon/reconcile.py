"""
Record-level reconciliation between a source and a target dataset.

Finds:
  * duplicate keys on either side
  * records missing from the target / missing from the source
  * field-level mismatches on matched records (with a numeric tolerance and
    optional text normalisation, so rounding and casing noise is not flagged)
  * control totals (row counts and summed measures) on both sides
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ReconResult:
    key: str
    source_rows: int
    target_rows: int
    duplicates_source: pd.DataFrame
    duplicates_target: pd.DataFrame
    missing_in_target: pd.DataFrame
    missing_in_source: pd.DataFrame
    mismatches: pd.DataFrame          # long format: key, column, source_value, target_value, difference
    control_totals: pd.DataFrame
    matched_rows: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def mismatched_records(self) -> int:
        return self.mismatches[self.key].nunique() if len(self.mismatches) else 0

    @property
    def match_rate_pct(self) -> float:
        if not self.source_rows:
            return 100.0
        clean = self.matched_rows - self.mismatched_records
        return round(100 * clean / self.source_rows, 2)

    def summary(self) -> pd.DataFrame:
        rows = [
            ("Source rows", self.source_rows),
            ("Target rows", self.target_rows),
            ("Duplicate keys in source", self.duplicates_source[self.key].nunique()),
            ("Duplicate keys in target", self.duplicates_target[self.key].nunique()),
            ("Missing in target", len(self.missing_in_target)),
            ("Missing in source", len(self.missing_in_source)),
            ("Matched records", self.matched_rows),
            ("Records with field mismatches", self.mismatched_records),
            ("Field-level mismatches", len(self.mismatches)),
            ("Fully reconciled (% of source)", self.match_rate_pct),
        ]
        return pd.DataFrame(rows, columns=["metric", "value"], dtype=object)  # keep counts as integers


def _normalise_text(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.casefold()


def reconcile(
    source: pd.DataFrame,
    target: pd.DataFrame,
    key: str,
    compare: list[str],
    numeric_tolerance: float = 0.0,
    normalise_text: bool = True,
    sum_columns: list[str] | None = None,
) -> ReconResult:
    notes = []

    dup_src = source[source[key].duplicated(keep=False)].sort_values(key)
    dup_tgt = target[target[key].duplicated(keep=False)].sort_values(key)
    if len(dup_tgt):
        notes.append(f"{dup_tgt[key].nunique()} keys are duplicated in the target; first occurrence used for comparison.")
    if len(dup_src):
        notes.append(f"{dup_src[key].nunique()} keys are duplicated in the source; first occurrence used for comparison.")

    src = source.drop_duplicates(subset=key, keep="first")
    tgt = target.drop_duplicates(subset=key, keep="first")

    merged = src.merge(tgt, on=key, how="outer", suffixes=("_src", "_tgt"), indicator=True)
    missing_in_target = src[src[key].isin(merged.loc[merged["_merge"] == "left_only", key])]
    missing_in_source = tgt[tgt[key].isin(merged.loc[merged["_merge"] == "right_only", key])]
    both = merged[merged["_merge"] == "both"]

    frames = []
    for col in compare:
        a, b = both[f"{col}_src"], both[f"{col}_tgt"]
        a_num, b_num = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
        is_numeric = a_num.notna().sum() == a.notna().sum() and a.notna().any()

        if is_numeric:
            diff = (b_num - a_num).round(6)
            differs = diff.abs() > numeric_tolerance + 1e-9
            differs |= a_num.isna() ^ b_num.isna()
        else:
            na, nb = (_normalise_text(a), _normalise_text(b)) if normalise_text else (a.astype("string"), b.astype("string"))
            differs = (na != nb).fillna(False) | (na.isna() ^ nb.isna())
            diff = pd.Series(np.nan, index=both.index)

        if differs.any():
            frames.append(
                pd.DataFrame(
                    {
                        key: both.loc[differs, key],
                        "column": col,
                        "source_value": a[differs],
                        "target_value": b[differs],
                        "difference": diff[differs],
                    }
                )
            )
    mismatches = (
        pd.concat(frames, ignore_index=True).sort_values([key, "column"]).reset_index(drop=True)
        if frames
        else pd.DataFrame(columns=[key, "column", "source_value", "target_value", "difference"])
    )

    totals = [{"measure": "row_count", "source": len(source), "target": len(target)}]
    for col in sum_columns or []:
        totals.append(
            {
                "measure": f"sum({col})",
                "source": round(pd.to_numeric(source[col], errors="coerce").sum(), 2),
                "target": round(pd.to_numeric(target[col], errors="coerce").sum(), 2),
            }
        )
    control = pd.DataFrame(totals)
    control["variance"] = (control["target"] - control["source"]).round(2)
    control = control.astype(object)
    control.loc[0, ["source", "target", "variance"]] = [len(source), len(target), len(target) - len(source)]

    return ReconResult(
        key=key,
        source_rows=len(source),
        target_rows=len(target),
        duplicates_source=dup_src,
        duplicates_target=dup_tgt,
        missing_in_target=missing_in_target.reset_index(drop=True),
        missing_in_source=missing_in_source.reset_index(drop=True),
        mismatches=mismatches,
        control_totals=control,
        matched_rows=len(both),
        notes=notes,
    )
