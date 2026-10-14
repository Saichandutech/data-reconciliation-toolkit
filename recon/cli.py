"""
Command-line entry point.

    python -m recon --config config/billing_vs_warehouse.yaml
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from .reconcile import reconcile
from .report import write_excel, write_html
from .validate import summarise, validate


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text())
    base = path.parent.parent  # paths in config are relative to the project root
    for k in ("source", "target"):
        cfg[k]["path"] = (base / cfg[k]["path"]).resolve()
    cfg["output_dir"] = (base / cfg.get("output_dir", "reports")).resolve()
    return cfg


def run(cfg: dict, today: str | None = None):
    read = lambda c: pd.read_csv(c["path"], dtype=str if c.get("all_text") else None)
    source, target = read(cfg["source"]), read(cfg["target"])

    rules = validate(source, cfg.get("validation", []), today=today)
    r = cfg["reconcile"]
    recon = reconcile(
        source,
        target,
        key=r["key"],
        compare=r["compare"],
        numeric_tolerance=r.get("numeric_tolerance", 0.0),
        normalise_text=r.get("normalise_text", True),
        sum_columns=r.get("sum_columns"),
    )
    return source, target, rules, recon


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Reconcile two datasets and validate the source.")
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--today", help="Override today's date for date rules (YYYY-MM-DD)")
    p.add_argument("--fail-on-issues", action="store_true", help="Exit with code 1 if any issue is found (for CI / schedulers)")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    source, _, rules, recon = run(cfg, today=args.today)
    title = cfg.get("title", "Reconciliation Report")
    out = cfg["output_dir"]
    xlsx = write_excel(out / f"{cfg.get('report_name', 'recon_report')}.xlsx", title, recon, rules, len(source))
    htm = write_html(out / f"{cfg.get('report_name', 'recon_report')}.html", title, recon, rules, len(source))

    print(f"\n{title}\n" + "=" * len(title))
    print(recon.summary().to_string(index=False))
    print("\nValidation:")
    print(summarise(rules, len(source)).to_string(index=False))
    print("\nControl totals:")
    print(recon.control_totals.to_string(index=False))
    for n in recon.notes:
        print("Note:", n)
    print(f"\nReports written:\n  {xlsx}\n  {htm}")

    issues = (
        len(recon.missing_in_target) + len(recon.missing_in_source) + len(recon.mismatches)
        + len(recon.duplicates_target) + sum(r.failures for r in rules)
    )
    return 1 if (args.fail_on_issues and issues) else 0
