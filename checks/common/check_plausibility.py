"""
Growth rate plausibility check.

Computes period-on-period growth rates and checks they fall within
empirically-derived bounds from the ground truth data.

Usage (standalone):
    python checks/check_plausibility.py --predictions adapted-data/shin_01_predictions.csv \\
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
    make_out_dir, save_check_outputs
)


def compute_growth_rates(long: pd.DataFrame) -> pd.DataFrame:
    """
    Compute period-on-period growth rates for every trajectory.

    Uses sort + shift for vectorised computation.
    Returns DataFrame with columns:
        Model, Scenario, Region, Variable, Year_From, Year_To, Growth_Rate
    """
    group_cols = IDX + ["Variable"]
    df = long.sort_values(group_cols + ["Year"]).copy()

    # Shift value within each trajectory group
    df["prev_value"] = df.groupby(group_cols)["Value"].shift(1)
    df["prev_year"]  = df.groupby(group_cols)["Year"].shift(1)

    # Drop first row of each group (no previous value)
    df = df.dropna(subset=["prev_value", "prev_year"])

    # Compute growth rate.
    # Where |prev_value| < abs_floor the denominator is too small for a meaningful
    # relative rate — set to NaN so the transition is excluded from both bound
    # derivation and violation flagging.  This avoids spurious 10,000x+ growth
    # rates from variables that start near zero (e.g. CCS, Geothermal, Oil in
    # early years).  The == 0 case is a subset of this.
    abs_floor = 1.0
    near_zero = df["prev_value"].abs() < abs_floor
    df["Growth_Rate"] = np.where(
        near_zero,
        np.nan,
        (df["Value"] - df["prev_value"]) / df["prev_value"].abs(),
    )

    return df[IDX + ["Variable", "prev_year", "Year", "Growth_Rate"]].rename(
        columns={"prev_year": "Year_From", "Year": "Year_To"}
    ).reset_index(drop=True)



def derive_empirical_bounds(
    growth_df: pd.DataFrame,
    lower_pct: float = 1.0,
    upper_pct: float = 99.0
) -> pd.DataFrame:
    """
    Derive empirical bounds on growth rates.

    Computes percentiles of growth_rate for each variable.
    """
    bounds_data = []

    for var in growth_df["Variable"].unique():
        var_growth = growth_df[growth_df["Variable"] == var]["Growth_Rate"]
        # Filter out infinities for percentile computation
        var_growth_finite = var_growth[np.isfinite(var_growth)]

        if var_growth_finite.empty:
            continue

        lower = np.percentile(var_growth_finite, lower_pct)
        upper = np.percentile(var_growth_finite, upper_pct)

        bounds_data.append({
            "Variable": var,
            "Lower_Bound": lower,
            "Upper_Bound": upper,
        })

    return pd.DataFrame(bounds_data)


def flag_violations(
    growth_df: pd.DataFrame,
    bounds: pd.DataFrame
) -> pd.DataFrame:
    """
    Flag growth rate violations against bounds.

    Returns growth_df with added Status and Violation_Type columns.
    """
    result = growth_df.copy()
    result["Status"] = "PASS"
    result["Violation_Type"] = ""

    for idx, bounds_row in bounds.iterrows():
        var = bounds_row["Variable"]
        lower = bounds_row["Lower_Bound"]
        upper = bounds_row["Upper_Bound"]

        var_mask = result["Variable"] == var
        gr = result.loc[var_mask, "Growth_Rate"]

        # Exclude infinities from comparison
        below = (gr < lower) & np.isfinite(gr)
        above = (gr > upper) & np.isfinite(gr)
        infinite = ~np.isfinite(gr)

        result.loc[var_mask & below, "Status"] = "FAIL"
        result.loc[var_mask & below, "Violation_Type"] = f"Below lower bound ({lower:.4f})"

        result.loc[var_mask & above, "Status"] = "FAIL"
        result.loc[var_mask & above, "Violation_Type"] = f"Above upper bound ({upper:.4f})"

        result.loc[var_mask & infinite, "Status"] = "FAIL"
        result.loc[var_mask & infinite, "Violation_Type"] = "Infinite growth rate (zero denominator)"

    return result


def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    percentile: float = 1.0,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs
) -> dict:
    """
    Run growth rate plausibility check.

    Args:
        predictions: Path to predictions CSV
        ground_truth: Path to ground truth CSV (optional)
        percentile: Percentile for bounds (default 1.0)
        out_dir: Output directory (default results)
        run_id: Run identifier (default run)

    Returns:
        dict with keys: check_name, passed, results, summary, unit_warnings, skipped
    """
    # Load and normalize
    pred_long = predictions

    # Compute growth rates
    pred_growth = compute_growth_rates(pred_long)

    if pred_growth.empty:
        return {
            "check_name": "check_plausibility",
            "passed": True,
            "results": pd.DataFrame(),
            "summary": pd.DataFrame(),
            "unit_warnings": [],
            "skipped": ["No growth rates computed"],
        }

    # Derive bounds
    if ground_truth is not None:
        gt_long = ground_truth
        gt_growth = compute_growth_rates(gt_long)

        if not gt_growth.empty:
            bounds = derive_empirical_bounds(
                gt_growth,
                percentile,
                100 - percentile
            )
            print(f"Derived empirical bounds from ground truth: {len(bounds)} variables")
        else:
            bounds = derive_empirical_bounds(pred_growth, percentile, 100 - percentile)
            print("Ground truth growth rates empty, using prediction bounds")
    else:
        bounds = derive_empirical_bounds(pred_growth, percentile, 100 - percentile)
        print("No ground truth provided, deriving bounds from predictions")

    # Flag violations
    results = flag_violations(pred_growth, bounds)

    # Generate summary
    pass_count = (results["Status"] == "PASS").sum()
    fail_count = (results["Status"] == "FAIL").sum()
    total = pass_count + fail_count
    summary = pd.DataFrame([{
        "Pass_Count": pass_count,
        "Fail_Count": fail_count,
        "Pass_Rate": pass_count / total if total > 0 else 1.0,
    }])

    # Determine pass
    passed = (results["Status"] == "PASS").all()

    # Save outputs
    out_path = make_out_dir(out_dir, run_id, "check_plausibility")
    save_check_outputs(out_path, results, summary)

    # Also check ground truth if provided
    if ground_truth is not None and not gt_growth.empty:
        gt_results = flag_violations(gt_growth, bounds)
        gt_pass = (gt_results["Status"] == "PASS").sum()
        gt_fail = (gt_results["Status"] == "FAIL").sum()
        gt_total = gt_pass + gt_fail
        gt_summary = pd.DataFrame([{
            "Pass_Count": gt_pass,
            "Fail_Count": gt_fail,
            "Pass_Rate": gt_pass / gt_total if gt_total > 0 else 1.0,
        }])
        gt_out_path = make_out_dir(out_dir, run_id, "check_plausibility_ground_truth")
        save_check_outputs(gt_out_path, gt_results, gt_summary)

    return {
        "check_name": "check_plausibility",
        "passed": passed,
        "results": results,
        "summary": summary,
        "unit_warnings": [],
        "skipped": [],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Growth rate plausibility check for IAM emulation predictions"
    )
    parser.add_argument("--predictions", required=True, help="Path to predictions CSV")
    parser.add_argument("--ground_truth", help="Path to ground truth CSV (optional)")
    parser.add_argument("--run_id", required=True, help="Run identifier")
    parser.add_argument("--out_dir", default="results", help="Output directory")
    parser.add_argument("--percentile", type=float, default=1.0, help="Percentile for bounds")

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth)) if args.ground_truth else None

    result = run(
        predictions=pred,
        ground_truth=gt,
        percentile=args.percentile,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    print(f"\nPlausibility check: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Results saved to {args.out_dir}/{args.run_id}/check_plausibility/")


if __name__ == "__main__":
    main()
