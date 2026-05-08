"""
Regional consistency check.

Checks that predicted World values equal the sum of subregion predictions.

Usage (standalone):
    python checks/regional_consistency.py --predictions adapted-data/xgb_04_predictions.csv \\
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
    IDX, load_csv, normalize_to_canonical,
    make_out_dir, save_check_outputs
)


REGION_GROUPINGS = {
    "R5": ["R5ASIA", "R5LAM", "R5MAF", "R5OECD90+EU", "R5REF"],
    "R6": ["R6AFRICA", "R6ASIA", "R6LAM", "R6MIDDLE_EAST", "R6OECD90+EU", "R6REF"],
    "R10": [
        "R10AFRICA", "R10CHINA+", "R10EUROPE", "R10INDIA+", "R10LATIN_AM",
        "R10MIDDLE_EAST", "R10NORTH_AM", "R10PAC_OECD", "R10REF_ECON",
        "R10REST_ASIA"
    ],
}


def check_grouping(
    long: pd.DataFrame,
    grouping_name: str,
    regions: list,
    threshold: float = 0.012,
    abs_floor: float = 1.0
) -> pd.DataFrame:
    """
    Check that World equals the sum of the specified subregions.

    Uses pivot_table for vectorised computation.
    """
    all_regions = ["World"] + regions
    subset = long[long["Region"].isin(all_regions)]
    if subset.empty:
        return pd.DataFrame()

    pivot = subset.pivot_table(
        index=["Model", "Scenario", "Variable", "Year"],
        columns="Region",
        values="Value",
        aggfunc="first",
    ).reset_index()

    if "World" not in pivot.columns:
        return pd.DataFrame()

    present_regions = [r for r in regions if r in pivot.columns]
    if not present_regions:
        return pd.DataFrame()

    # Only check rows where ALL regions in the grouping have data.
    # Partial sums (missing regions treated as 0) produce meaningless relative errors.
    complete = pivot[present_regions].notna().all(axis=1)
    pivot = pivot[complete].copy()
    if pivot.empty:
        return pd.DataFrame()

    pivot["regional_sum"] = pivot[present_regions].sum(axis=1)
    pivot["world_value"]  = pivot["World"]
    pivot["residual"]     = (pivot["world_value"] - pivot["regional_sum"]).abs()
    # Also skip rows where |World| < abs_floor — relative tolerance is meaningless
    # when World crosses zero (e.g. CO2 in near-net-zero scenarios).
    pivot["tolerance"]    = (pivot["world_value"].abs() * threshold).clip(lower=abs_floor)
    pivot["Status"]       = np.where(
        pivot["world_value"].abs() < abs_floor,
        "SKIP",
        np.where(pivot["residual"] <= pivot["tolerance"], "PASS", "FAIL")
    )
    pivot["Grouping"]     = grouping_name
    pivot["Region"]       = "World"

    return pivot[["Model", "Scenario", "Region", "Variable", "Year",
                  "Grouping", "world_value", "regional_sum", "residual", "tolerance", "Status"]].rename(
        columns={"world_value": "World_Value", "regional_sum": "Regional_Sum",
                 "residual": "Residual", "tolerance": "Tolerance"}
    )



def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    threshold: float = 0.012,
    abs_floor: float = 1.0,
    grouping: str = None,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs
) -> dict:
    """
    Run regional consistency check.

    Args:
        predictions: Path to predictions CSV
        ground_truth: Path to ground truth CSV (optional)
        threshold: Relative tolerance (default 0.012)
        abs_floor: Absolute tolerance floor (default 1.0)
        grouping: Specific grouping to check (default all)
        out_dir: Output directory (default results)
        run_id: Run identifier (default run)

    Returns:
        dict with keys: check_name, passed, results, summary, unit_warnings, skipped
    """
    # Load and normalize
    pred_long = predictions

    # Determine which groupings to check
    groupings_to_check = {grouping: REGION_GROUPINGS[grouping]} if grouping else REGION_GROUPINGS

    # Run checks
    all_results = []
    for group_name, regions in groupings_to_check.items():
        # Filter to regions that exist in data
        available_regions = [r for r in regions if r in pred_long["Region"].values]
        if not available_regions:
            print(f"Grouping {group_name}: no regions found in data")
            continue

        group_results = check_grouping(pred_long, group_name, available_regions, threshold, abs_floor)
        if not group_results.empty:
            all_results.append(group_results)

    results = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()

    if results.empty:
        # Save empty files so any stale results from a previous run are overwritten
        out_path = make_out_dir(out_dir, run_id, "regional_consistency")
        pd.DataFrame().to_csv(out_path / "results.csv", index=False)
        pd.DataFrame().to_csv(out_path / "summary.csv", index=False)
        print("  No complete regional groupings found in data — results are empty.")
        return {
            "check_name": "regional_consistency",
            "passed": True,
            "results": pd.DataFrame(),
            "summary": pd.DataFrame(),
            "unit_warnings": [],
            "skipped": ["No complete regional groupings found"],
        }

    # Generate summary
    grp = results.groupby(["Model", "Scenario", "Grouping"])["Status"]
    summary = grp.value_counts().unstack(fill_value=0).reset_index()
    for col in ("PASS", "FAIL"):
        if col not in summary.columns:
            summary[col] = 0
    summary["Total"]     = summary["PASS"] + summary["FAIL"]
    summary["Pass_Rate"] = summary["PASS"] / summary["Total"].replace(0, np.nan)

    # Determine pass
    passed = (results["Status"] == "PASS").all()

    # Save outputs
    out_path = make_out_dir(out_dir, run_id, "regional_consistency")
    save_check_outputs(out_path, results, summary)

    # Also check ground truth if provided
    if ground_truth is not None:
        gt_long = ground_truth

        gt_all_results = []
        for group_name, regions in groupings_to_check.items():
            available_regions = [r for r in regions if r in gt_long["Region"].values]
            if available_regions:
                gt_group_results = check_grouping(gt_long, group_name, available_regions, threshold, abs_floor)
                if not gt_group_results.empty:
                    gt_all_results.append(gt_group_results)

        gt_out_path = make_out_dir(out_dir, run_id, "regional_consistency_ground_truth")
        if gt_all_results:
            gt_results = pd.concat(gt_all_results, ignore_index=True)
            gt_grp = gt_results.groupby(["Model", "Scenario", "Grouping"])["Status"]
            gt_summary = gt_grp.value_counts().unstack(fill_value=0).reset_index()
            for col in ("PASS", "FAIL"):
                if col not in gt_summary.columns:
                    gt_summary[col] = 0
            gt_summary["Pass_Rate"] = gt_summary.get("PASS", 0) / (gt_summary.get("PASS", 0) + gt_summary.get("FAIL", 0)).replace(0, np.nan)
            save_check_outputs(gt_out_path, gt_results, gt_summary)
        else:
            # Overwrite any stale results from a previous run
            pd.DataFrame().to_csv(gt_out_path / "results.csv", index=False)
            pd.DataFrame().to_csv(gt_out_path / "summary.csv", index=False)

    return {
        "check_name": "regional_consistency",
        "passed": passed,
        "results": results,
        "summary": summary,
        "unit_warnings": [],
        "skipped": [],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Regional consistency check for IAM emulation predictions"
    )
    parser.add_argument("--predictions", required=True, help="Path to predictions CSV")
    parser.add_argument("--ground_truth", help="Path to ground truth CSV (optional)")
    parser.add_argument("--run_id", required=True, help="Run identifier")
    parser.add_argument("--out_dir", default="results", help="Output directory")
    parser.add_argument("--threshold", type=float, default=0.012, help="Relative tolerance")
    parser.add_argument("--abs_floor", type=float, default=1.0, help="Absolute tolerance floor")
    parser.add_argument("--grouping", choices=list(REGION_GROUPINGS.keys()), help="Specific grouping to check")

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth)) if args.ground_truth else None

    result = run(
        predictions=pred,
        ground_truth=gt,
        threshold=args.threshold,
        abs_floor=args.abs_floor,
        grouping=args.grouping,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    print(f"\nRegional consistency check: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Results saved to {args.out_dir}/{args.run_id}/regional_consistency/")


if __name__ == "__main__":
    main()
