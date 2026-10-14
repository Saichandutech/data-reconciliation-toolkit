"""Tests: the toolkit must find exactly the issues injected into the sample data."""
import json
from pathlib import Path

import pandas as pd
import pytest

from recon import reconcile, validate
from recon.cli import load_config, run

ROOT = Path(__file__).resolve().parents[1]
KEY = json.loads((ROOT / "sample_data" / "answer_key.json").read_text())


@pytest.fixture(scope="module")
def results():
    cfg = load_config(ROOT / "config" / "billing_vs_warehouse.yaml")
    return run(cfg, today="2026-10-01")


def test_missing_in_target(results):
    *_, recon = results
    assert sorted(recon.missing_in_target["invoice_id"]) == KEY["missing_in_target"]


def test_missing_in_source(results):
    *_, recon = results
    assert sorted(recon.missing_in_source["invoice_id"]) == KEY["missing_in_source"]


def test_duplicates_in_target(results):
    *_, recon = results
    assert sorted(recon.duplicates_target["invoice_id"].unique()) == KEY["duplicates_in_target"]


def test_amount_mismatches_respect_tolerance(results):
    *_, recon = results
    amt = recon.mismatches[recon.mismatches["column"] == "amount"]
    # the 30 injected +0.004 rounding differences must NOT be flagged
    assert sorted(amt["invoice_id"]) == KEY["amount_mismatches"]


def test_status_mismatches(results):
    *_, recon = results
    st = recon.mismatches[recon.mismatches["column"] == "status"]
    assert sorted(st["invoice_id"]) == KEY["status_mismatches"]


def test_text_normalisation_ignores_case_and_spaces(results):
    *_, recon = results
    assert (recon.mismatches["column"] == "region").sum() == 0


def test_validation_counts(results):
    _, _, rules, _ = results
    got = {r.name: r.failures for r in rules if r.failures}
    assert got == KEY["validation"]


def test_identical_frames_fully_reconcile():
    df = pd.DataFrame({"id": [1, 2, 3], "amt": [1.0, 2.0, None], "txt": ["a", None, "c"]})
    r = reconcile(df, df.copy(), key="id", compare=["amt", "txt"])
    assert r.mismatches.empty and r.match_rate_pct == 100.0


def test_null_vs_value_is_a_mismatch():
    a = pd.DataFrame({"id": [1], "txt": [None]})
    b = pd.DataFrame({"id": [1], "txt": ["x"]})
    assert len(reconcile(a, b, key="id", compare=["txt"]).mismatches) == 1


def test_unknown_rule_raises():
    with pytest.raises(ValueError):
        validate(pd.DataFrame({"a": [1]}), [{"column": "a", "rule": "bogus"}])


def test_between_rule():
    df = pd.DataFrame({"pct": [0, 25, 50, 51, -1, None]})
    (r,) = validate(df, [{"column": "pct", "rule": "between", "value": [0, 50]}])
    assert sorted(r.failed_rows["pct"].tolist()) == [-1, 51]


def test_max_length_rule():
    df = pd.DataFrame({"code": ["AB", "ABCDE", None]})
    (r,) = validate(df, [{"column": "code", "rule": "max_length", "value": 3}])
    assert r.failed_rows["code"].tolist() == ["ABCDE"]


def test_unique_together_rule():
    df = pd.DataFrame({"acct": ["A", "A", "A", "B"], "day": ["d1", "d1", "d2", "d1"]})
    (r,) = validate(df, [{"columns": ["acct", "day"], "rule": "unique_together"}])
    assert r.failures == 2 and r.name == "acct_day_unique_together"


def test_customer_master_example_runs():
    cfg = load_config(ROOT / "config" / "crm_vs_billing_customers.yaml")
    _, _, rules, recon = run(cfg)
    assert len(recon.missing_in_target) == 4
    assert (recon.mismatches["column"] == "email").sum() == 3   # CRM nulls; case-only differences ignored
    assert {r.name: r.failures for r in rules if r.failures} == {"email_not_null": 3, "credit_limit_min_0": 2}
