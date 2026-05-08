"""
Hierarchy sum check.

Verifies that each parent variable equals the sum of its direct children
at every timestep, using the | separator convention.

Usage (standalone):
    python checks/sum_check.py --predictions adapted-data/xgb_04_predictions.csv \\
                                --run_id xgb_04
"""

from typing import Optional
import sys
from pathlib import Path
import argparse
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    CANONICAL_COLUMNS, IDX, load_csv, normalize_to_canonical,
    make_out_dir, save_check_outputs
)


def discover_hierarchy(variables: list) -> dict:
    """
    Discover parent-child relationships using | separator.

    Returns dict mapping parent variable to list of direct children.
    """
    hierarchy = {}

    for var in variables:
        parts = var.split("|")
        if len(parts) > 1:
            parent = "|".join(parts[:-1])
            if parent not in hierarchy:
                hierarchy[parent] = []
            # Only add if this is a direct child (parent exists in variables)
            if parent in variables:
                if var not in hierarchy[parent]:
                    hierarchy[parent].append(var)

    return hierarchy


def run_sum_check(
    long: pd.DataFrame,
    parent: str,
    children: list,
    threshold: float = 0.012,
    abs_floor: float = 1.0
) -> pd.DataFrame:
    """
    Check that parent equals sum of children within tolerance.

    Uses pivot_table for efficient vectorised computation across all
    scenarios and timesteps simultaneously.
    """
    all_vars = [parent] + children
    subset   = long[long["Variable"].isin(all_vars)]
    if subset.empty:
        return pd.DataFrame()

    pivot = subset.pivot_table(
        index=IDX + ["Year"],
        columns="Variable",
        values="Value",
        aggfunc="first",
    ).reset_index()

    if parent not in pivot.columns:
        return pd.DataFrame()

    present_children = [c for c in children if c in pivot.columns]
    if not present_children:
        return pd.DataFrame()

    pivot["children_sum"] = pivot[present_children].sum(axis=1)
    pivot["parent_value"] = pivot[parent]
    pivot["residual"]     = (pivot["parent_value"] - pivot["children_sum"]).abs()
    pivot["tolerance"]    = (pivot["parent_value"].abs() * threshold).clip(lower=abs_floor)
    pivot["Status"]       = np.where(pivot["residual"] <= pivot["tolerance"], "PASS", "FAIL")
    pivot["Parent"]       = parent

    # Include individual child columns so the report can show per-child breakdown
    child_cols = [c for c in present_children]
    return pivot[IDX + ["Year", "Parent", "parent_value", "children_sum",
                         "residual", "tolerance", "Status"] + child_cols].rename(
        columns={"parent_value": "Parent_Value", "children_sum": "Children_Sum",
                 "residual": "Residual", "tolerance": "Tolerance"}
    )


def scenario_summary(
    timestep_df: pd.DataFrame,
    threshold: float = 0.012,
    pass_mode: str = "mean"
) -> pd.DataFrame:
    """
    Summarize pass/fail by scenario.

    Args:
        timestep_df: Results from run_sum_check
        threshold: Relative tolerance (for documentation)
        pass_mode: How to determine pass (mean, all)

    Returns:
        DataFrame with summary by scenario
    """
    if timestep_df.empty:
        return pd.DataFrame()

    summary_data = []

    for scenario_key, scenario_group in timestep_df.groupby(IDX):
        pass_count = (scenario_group["Status"] == "PASS").sum()
        fail_count = (scenario_group["Status"] == "FAIL").sum()
        total = pass_count + fail_count

        if pass_mode == "all":
            passes = fail_count == 0
        else:  # mean
            passes = pass_count > fail_count

        summary_data.append({
            "Model": scenario_key[0],
            "Scenario": scenario_key[1],
            "Region": scenario_key[2],
            "Pass_Count": pass_count,
            "Fail_Count": fail_count,
            "Pass_Rate": pass_count / total if total > 0 else 1.0,
            "Passes": passes,
        })

    return pd.DataFrame(summary_data)


def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    threshold: float = 0.012,
    abs_floor: float = 1.0,
    pass_mode: str = "mean",
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs
) -> dict:
    """
    Run hierarchy sum check.

    Args:
        predictions: Path to predictions CSV
        ground_truth: Path to ground truth CSV (optional)
        threshold: Relative tolerance (default 0.012)
        abs_floor: Absolute tolerance floor (default 1.0)
        pass_mode: Pass criterion (mean or all) (default mean)
        out_dir: Output directory (default results)
        run_id: Run identifier (default run)

    Returns:
        dict with keys: check_name, passed, results, summary, unit_warnings, skipped
    """
    # Load and normalize
    pred_long = predictions

    # Discover hierarchy
    variables = pred_long["Variable"].unique().tolist()
    hierarchy = discover_hierarchy(variables)

    if not hierarchy:
        print("No parent-child hierarchy found in variables.")
        return {
            "check_name": "sum_check",
            "passed": True,
            "results": pd.DataFrame(),
            "summary": pd.DataFrame(),
            "unit_warnings": [],
            "skipped": ["No hierarchy found"],
        }

    # Run check on all parent-child pairs
    all_results = []
    for parent, children in hierarchy.items():
        pair_results = run_sum_check(pred_long, parent, children, threshold, abs_floor)
        if not pair_results.empty:
            all_results.append(pair_results)

    results = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()

    if results.empty:
        return {
            "check_name": "sum_check",
            "passed": True,
            "results": pd.DataFrame(),
            "summary": pd.DataFrame(),
            "unit_warnings": [],
            "skipped": ["No valid parent-child pairs found"],
        }

    # Generate summary
    summary = scenario_summary(results, threshold, pass_mode)

    # Determine overall pass
    passed = (results["Status"] == "PASS").all()

    # Save outputs
    out_path = make_out_dir(out_dir, run_id, "sum_check")
    save_check_outputs(out_path, results, summary)

    # Also run on ground truth if provided
    if ground_truth is not None:
        gt_long = ground_truth

        gt_results_list = []
        for parent, children in hierarchy.items():
            gt_pair_results = run_sum_check(gt_long, parent, children, threshold, abs_floor)
            if not gt_pair_results.empty:
                gt_results_list.append(gt_pair_results)

        if gt_results_list:
            gt_results = pd.concat(gt_results_list, ignore_index=True)
            gt_summary = scenario_summary(gt_results, threshold, pass_mode)
            gt_out_path = make_out_dir(out_dir, run_id, "sum_check_ground_truth")
            save_check_outputs(gt_out_path, gt_results, gt_summary)

    return {
        "check_name": "sum_check",
        "passed": passed,
        "results": results,
        "summary": summary,
        "unit_warnings": [],
        "skipped": [],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Hierarchy sum check for IAM emulation predictions"
    )
    parser.add_argument("--predictions", required=True, help="Path to predictions CSV")
    parser.add_argument("--ground_truth", help="Path to ground truth CSV (optional)")
    parser.add_argument("--run_id", required=True, help="Run identifier")
    parser.add_argument("--out_dir", default="results", help="Output directory")
    parser.add_argument("--threshold", type=float, default=0.012, help="Relative tolerance")
    parser.add_argument("--abs_floor", type=float, default=1.0, help="Absolute tolerance floor")
    parser.add_argument("--pass_mode", default="mean", choices=["mean", "all"])

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth)) if args.ground_truth else None

    result = run(
        predictions=pred,
        ground_truth=gt,
        threshold=args.threshold,
        abs_floor=args.abs_floor,
        pass_mode=args.pass_mode,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    print(f"\nSum check: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Results saved to {args.out_dir}/{args.run_id}/sum_check/")


if __name__ == "__main__":
    main()
