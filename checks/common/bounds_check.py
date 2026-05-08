"""
Physical bounds check.

Checks predictions against hard physical lower bounds and empirical bounds
derived from ground truth data.

Usage (standalone):
    python checks/bounds_check.py --predictions adapted-data/xgb_04_predictions.csv \\
                                   --ground_truth adapted-data/xgb_04_ground_truth.csv \\
                                   --run_id xgb_04
"""

import sys
from pathlib import Path
from typing import Optional
import argparse
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import (
    CANONICAL_COLUMNS, IDX, load_csv, normalize_to_canonical,
    make_out_dir, save_check_outputs,
)


# Variables with hard physical lower bound of 0.0
# Energy generation and capacity cannot be negative
PHYSICAL_BOUNDS = {
    "Primary Energy|Coal":                    0.0,
    "Primary Energy|Gas":                     0.0,
    "Primary Energy|Nuclear":                 0.0,
    "Primary Energy|Oil":                     0.0,
    "Primary Energy|Solar":                   0.0,
    "Primary Energy|Wind":                    0.0,
    "Secondary Energy|Electricity":           0.0,
    "Secondary Energy|Electricity|Biomass":   0.0,
    "Secondary Energy|Electricity|Coal":      0.0,
    "Secondary Energy|Electricity|Gas":       0.0,
    "Secondary Energy|Electricity|Geothermal":0.0,
    "Secondary Energy|Electricity|Hydro":     0.0,
    "Secondary Energy|Electricity|Nuclear":   0.0,
    "Secondary Energy|Electricity|Oil":       0.0,
    "Secondary Energy|Electricity|Solar":     0.0,
    "Secondary Energy|Electricity|Wind":      0.0,
}


def derive_empirical_bounds(
    gt_long: pd.DataFrame,
    targets: list,
    lower_pct: float = 1.0,
    upper_pct: float = 99.0
) -> pd.DataFrame:
    """
    Derive empirical bounds from ground truth data.

    For each variable, compute lower and upper percentiles across all scenarios/regions/years.
    """
    bounds = []

    for var in targets:
        var_data = gt_long[gt_long["Variable"] == var]["Value"]
        if var_data.empty:
            continue

        lower = np.percentile(var_data.dropna(), lower_pct)
        upper = np.percentile(var_data.dropna(), upper_pct)

        bounds.append({
            "Variable": var,
            "Empirical_Lower": lower,
            "Empirical_Upper": upper,
        })

    return pd.DataFrame(bounds)


def build_bounds_table(
    targets: list,
    use_empirical: bool = True,
    empirical_bounds: pd.DataFrame = None
) -> pd.DataFrame:
    """
    Build bounds table combining physical and empirical bounds.

    Returns DataFrame with columns: Variable, Physical_Lower, Empirical_Lower, Empirical_Upper
    """
    bounds_data = []

    for var in targets:
        entry = {
            "Variable": var,
            "Physical_Lower": PHYSICAL_BOUNDS.get(var, np.nan),
            "Empirical_Lower": np.nan,
            "Empirical_Upper": np.nan,
        }

        if use_empirical and empirical_bounds is not None:
            emp = empirical_bounds[empirical_bounds["Variable"] == var]
            if not emp.empty:
                entry["Empirical_Lower"] = emp.iloc[0]["Empirical_Lower"]
                entry["Empirical_Upper"] = emp.iloc[0]["Empirical_Upper"]

        bounds_data.append(entry)

    return pd.DataFrame(bounds_data)


def run_bounds_check(pred_long: pd.DataFrame, bounds_table: pd.DataFrame) -> pd.DataFrame:
    """
    Run bounds check on predictions.

    Returns DataFrame with columns: Model, Scenario, Region, Year,
    Variable, Value, Units, Status, Violation_Type
    """
    results = pred_long.copy()
    results["Status"] = "PASS"
    results["Violation_Type"] = ""

    for idx, row in bounds_table.iterrows():
        var = row["Variable"]
        var_mask = results["Variable"] == var

        # Check physical lower bound
        if not pd.isna(row["Physical_Lower"]):
            phys_lower = row["Physical_Lower"]
            violates = (results.loc[var_mask, "Value"] < phys_lower) & (results.loc[var_mask, "Value"].notna())
            results.loc[var_mask & violates, "Status"] = "FAIL"
            results.loc[var_mask & violates, "Violation_Type"] = f"Below physical lower bound ({phys_lower})"

        # Check empirical bounds
        if not pd.isna(row["Empirical_Lower"]):
            emp_lower = row["Empirical_Lower"]
            violates = (results.loc[var_mask, "Value"] < emp_lower) & (results.loc[var_mask, "Value"].notna())
            results.loc[var_mask & violates, "Status"] = "FAIL"
            results.loc[var_mask & violates, "Violation_Type"] = f"Below empirical lower bound ({emp_lower:.2f})"

        if not pd.isna(row["Empirical_Upper"]):
            emp_upper = row["Empirical_Upper"]
            violates = (results.loc[var_mask, "Value"] > emp_upper) & (results.loc[var_mask, "Value"].notna())
            results.loc[var_mask & violates, "Status"] = "FAIL"
            results.loc[var_mask & violates, "Violation_Type"] = f"Above empirical upper bound ({emp_upper:.2f})"

    return results


def scenario_summary(checked: pd.DataFrame) -> pd.DataFrame:
    """Summarize pass/fail by (Model, Scenario, Region)."""
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
    use_empirical: bool = True,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Run bounds check on pre-loaded, pre-normalised DataFrames.

    Parameters
    ----------
    predictions  : canonical long DataFrame (already normalised)
    ground_truth : canonical long DataFrame (optional, already normalised)
    percentile   : tail percentile for empirical bounds (default 1.0)
    use_empirical: derive empirical bounds from ground_truth (default True)
    out_dir      : root results directory
    run_id       : run identifier
    """
    pred_long = predictions
    gt_long   = ground_truth
    targets   = pred_long["Variable"].unique().tolist()

    # Derive empirical bounds if ground truth provided
    empirical_bounds = None
    if gt_long is not None and use_empirical:
        empirical_bounds = derive_empirical_bounds(gt_long, targets, percentile, 100 - percentile)
        print(f"  Derived empirical bounds from ground truth: {len(empirical_bounds)} variables")
    elif gt_long is None:
        use_empirical = False
        print("  No ground truth provided — using physical bounds only")

    # Build bounds table and run check
    bounds_table = build_bounds_table(targets, use_empirical, empirical_bounds)
    results = run_bounds_check(pred_long, bounds_table)

    # Generate summary
    summary = scenario_summary(results)

    # Check pass/fail
    passed = (results["Status"] == "PASS").all()

    # Save outputs
    out_path = make_out_dir(out_dir, run_id, "bounds_check")
    save_check_outputs(out_path, results, summary)

    # Also run on ground truth if provided
    if gt_long is not None:
        gt_results = run_bounds_check(gt_long, bounds_table)
        gt_summary = scenario_summary(gt_results)
        gt_out_path = make_out_dir(out_dir, run_id, "bounds_check_ground_truth")
        save_check_outputs(gt_out_path, gt_results, gt_summary)

    return {
        "check_name": "bounds_check",
        "passed": passed,
        "results": results,
        "summary": summary,
        "unit_warnings": [],
        "skipped": [],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Physical bounds check for IAM emulation predictions"
    )
    parser.add_argument("--predictions", required=True, help="Path to predictions CSV")
    parser.add_argument("--ground_truth", help="Path to ground truth CSV (optional)")
    parser.add_argument("--run_id", required=True, help="Run identifier")
    parser.add_argument("--out_dir", default="results", help="Output directory")
    parser.add_argument("--percentile", type=float, default=1.0, help="Percentile for bounds (default 1.0)")
    parser.add_argument("--no_empirical", action="store_true", help="Disable empirical bounds")

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth)) if args.ground_truth else None

    result = run(
        predictions=pred,
        ground_truth=gt,
        percentile=args.percentile,
        use_empirical=not args.no_empirical,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    print(f"\nBounds check: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Results saved to {args.out_dir}/{args.run_id}/bounds_check/")


if __name__ == "__main__":
    main()
