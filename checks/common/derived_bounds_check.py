"""
Derived bounds check.

Derives empirical bounds from the ground truth IAM data and checks that
emulator predictions fall within those bounds. Bounds are computed as
configurable percentiles (default 1st–99th) of the ground truth distribution
per variable, pooled across all regions, scenarios, and timesteps.

This check belongs to the 'Historical and domain knowledge comparison'
validation family: the IAM's own output distribution encodes domain knowledge
about what values are physically and structurally plausible.

Requires ground truth. If not provided the check is skipped.

Contrast with physical_bounds_check.py, which enforces hard mathematical
constraints (e.g. non-negativity) that are independent of the data.

Usage (standalone):
    python checks/common/derived_bounds_check.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
        --ground_truth adapted-data/shin_01_ground_truth.csv \\
        --run_id shin_01
"""

from typing import Optional
import sys
from pathlib import Path
import argparse
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import (
    IDX, load_csv, normalize_to_canonical,
    make_out_dir, save_check_outputs,
)


def derive_bounds(
    gt_long: pd.DataFrame,
    targets: list,
    lower_pct: float = 1.0,
    upper_pct: float = 99.0,
) -> pd.DataFrame:
    """
    Derive empirical lower and upper bounds per variable from ground truth.

    Pools all values across regions, scenarios, and timesteps before computing
    percentiles, giving a global envelope for each variable.

    Returns DataFrame with columns: Variable, Lower_Bound, Upper_Bound.
    """
    rows = []
    for var in targets:
        vals = gt_long[gt_long["Variable"] == var]["Value"].dropna()
        if vals.empty:
            continue
        rows.append({
            "Variable":    var,
            "Lower_Bound": float(np.percentile(vals, lower_pct)),
            "Upper_Bound": float(np.percentile(vals, upper_pct)),
        })
    return pd.DataFrame(rows)


def run_derived_bounds_check(
    pred_long: pd.DataFrame,
    bounds: pd.DataFrame,
) -> pd.DataFrame:
    """
    Check predictions against derived empirical bounds.

    Parameters
    ----------
    pred_long : canonical long DataFrame of predictions
    bounds    : DataFrame with columns Variable, Lower_Bound, Upper_Bound

    Returns a copy of pred_long with added Status and Violation_Type columns.
    """
    results = pred_long.copy()
    results["Status"] = "PASS"
    results["Violation_Type"] = ""

    for _, row in bounds.iterrows():
        var   = row["Variable"]
        lo    = row["Lower_Bound"]
        hi    = row["Upper_Bound"]
        mask  = results["Variable"] == var
        if not mask.any():
            continue

        vals = results.loc[mask, "Value"]

        below = (vals < lo) & vals.notna()
        above = (vals > hi) & vals.notna()

        results.loc[mask & below, "Status"] = "FAIL"
        results.loc[mask & below, "Violation_Type"] = (
            f"Below derived lower bound ({lo:.4g})"
        )
        results.loc[mask & above, "Status"] = "FAIL"
        results.loc[mask & above, "Violation_Type"] = (
            f"Above derived upper bound ({hi:.4g})"
        )

    return results


def scenario_summary(checked: pd.DataFrame) -> pd.DataFrame:
    """Summarise pass/fail by (Model, Scenario, Region)."""
    grp = checked.groupby(IDX)["Status"]
    summary = grp.value_counts().unstack(fill_value=0).reset_index()
    for col in ("PASS", "FAIL"):
        if col not in summary.columns:
            summary[col] = 0
    summary["Total"]     = summary["PASS"] + summary["FAIL"]
    summary["Pass_Rate"] = summary["PASS"] / summary["Total"].replace(0, np.nan)
    return summary.sort_values("Pass_Rate")


def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    percentile: float = 1.0,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Run derived bounds check on pre-loaded, pre-normalised DataFrames.

    Parameters
    ----------
    predictions  : canonical long DataFrame
    ground_truth : canonical long DataFrame (required — skipped if absent)
    percentile   : tail percentile for bounds derivation (default 1.0 → 1st/99th)
    out_dir      : root results directory
    run_id       : run identifier
    """
    check_name = "derived_bounds_check"

    if ground_truth is None:
        print("  [derived_bounds_check] No ground truth provided — skipping.")
        return {
            "check_name":    check_name,
            "passed":        True,
            "results":       pd.DataFrame(),
            "summary":       pd.DataFrame(),
            "unit_warnings": [],
            "skipped":       ["Ground truth required for derived bounds check"],
        }

    targets = predictions["Variable"].unique().tolist()
    bounds  = derive_bounds(ground_truth, targets, percentile, 100.0 - percentile)

    if bounds.empty:
        msg = "No matching variables found between predictions and ground truth."
        print(f"  [derived_bounds_check] WARNING: {msg}")
        return {
            "check_name":    check_name,
            "passed":        True,
            "results":       pd.DataFrame(),
            "summary":       pd.DataFrame(),
            "unit_warnings": [],
            "skipped":       [msg],
        }

    print(f"  [derived_bounds_check] Derived bounds for {len(bounds)} variables "
          f"(percentile range: {percentile:.1f}–{100-percentile:.1f}).")

    results = run_derived_bounds_check(predictions, bounds)
    summary = scenario_summary(results)

    n_fail = (results["Status"] == "FAIL").sum()
    passed = n_fail == 0

    print(f"  [derived_bounds_check] Violations: {n_fail:,} "
          f"({'PASS' if passed else 'FAIL'})")

    out_path = make_out_dir(out_dir, run_id, check_name)
    save_check_outputs(out_path, results, summary)
    bounds.to_csv(out_path / "bounds_used.csv", index=False)

    return {
        "check_name":    check_name,
        "passed":        passed,
        "results":       results,
        "summary":       summary,
        "unit_warnings": [],
        "skipped":       [],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Derived bounds check — checks emulator predictions against "
                    "empirical bounds derived from IAM ground truth percentiles."
    )
    parser.add_argument("--predictions",  required=True,
                        help="Path to predictions CSV (IAMC format)")
    parser.add_argument("--ground_truth", required=True,
                        help="Path to ground truth CSV (IAMC format)")
    parser.add_argument("--run_id",       required=True, help="Run identifier")
    parser.add_argument("--out_dir",      default="results", help="Output directory")
    parser.add_argument("--percentile",   type=float, default=1.0,
                        help="Tail percentile for bounds (default 1.0 → 1st/99th)")

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth))

    result = run(
        predictions=pred,
        ground_truth=gt,
        percentile=args.percentile,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    print(f"\nDerived bounds check: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Results saved to {args.out_dir}/{args.run_id}/derived_bounds_check/")


if __name__ == "__main__":
    main()
