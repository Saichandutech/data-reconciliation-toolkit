# Configuration Reference

A reconciliation is defined by one YAML file. Paths are relative to the project root.

```yaml
title: "Invoice Reconciliation – Billing System vs Reporting Warehouse"   # report heading
report_name: billing_vs_warehouse    # output file name (without extension)
output_dir: reports                  # where the .xlsx and .html are written

source: {name: Billing system,      path: sample_data/billing_system.csv}
target: {name: Reporting warehouse, path: sample_data/reporting_warehouse.csv}
```

## `reconcile` block

| Key | Required | Default | Meaning |
|---|---|---|---|
| `key` | yes | – | Business key that identifies the same record on both sides (e.g. `invoice_id`) |
| `compare` | yes | – | Columns compared on every matched record |
| `numeric_tolerance` | no | `0.0` | Numeric differences up to this amount are ignored (e.g. `0.01` = one cent) |
| `normalise_text` | no | `true` | Ignore case and leading/trailing spaces when comparing text |
| `sum_columns` | no | `[]` | Measures summed on both sides for the control-totals check |

### How matching works

1. Keys that appear more than once on either side are reported as **duplicates**; the first occurrence is used for comparison.
2. An outer join on `key` splits records into **missing in target**, **missing in source** and **matched**.
3. Each `compare` column is checked on matched records. A column is treated as numeric when every non-null value
   parses as a number; otherwise it is compared as text.
4. A null on one side and a value on the other is always a mismatch; nulls on both sides match.
5. **Fully reconciled %** = (matched records − records with any mismatch) ÷ source rows.

## `validation` block

Rules run against the **source** extract. Every rule reports the exact rows that fail it.

| Rule | Parameters | Fails when |
|---|---|---|
| `not_null` | `column` | value is null or blank |
| `unique` | `column` | value appears more than once |
| `unique_together` | `columns: [a, b]` | the combination of columns appears more than once |
| `min` / `max` | `column`, `value` | numeric value is below / above `value` |
| `between` | `column`, `value: [lo, hi]` | numeric value is outside the inclusive range |
| `max_length` | `column`, `value` | text is longer than `value` characters |
| `allowed_values` | `column`, `value: [..]` | value is not in the list |
| `pattern` | `column`, `value` (regex) | value does not fully match the regular expression |
| `is_date` | `column`, optional `value` (format) | value cannot be parsed as a date |
| `not_in_future` | `column` | date is after today (override with `--today`) |

Give any rule a custom label with `name:`, otherwise one is generated (e.g. `amount_min_0`).

## Command-line options

| Option | Meaning |
|---|---|
| `--config PATH` | YAML file to run (required) |
| `--today YYYY-MM-DD` | Fix "today" for date rules, so runs are reproducible |
| `--fail-on-issues` | Exit with code 1 if anything is found, to stop a scheduled job or CI pipeline |
