"""
Physical bounds check.

Checks predictions against hard physical lower bounds — constraints that
must hold by definition regardless of scenario (e.g. energy generation
cannot be negative). No ground truth is required.

This is a structural/mathematical constraint check, not a comparison against
observational data. It belongs to the same validation family as sum_check
and regional_consistency.

Usage (standalone):
    python checks/common/physical_bounds_check.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
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


# Variables with hard physical lower bound of 0.0.
# Energy generation and capacity cannot be negative.
PHYSICAL_BOUNDS: dict[str, float] = {
    "Primary Energy|Coal":                     0.0,
    "Primary Energy|Gas":                      0.0,
    "Primary Energy|Nuclear":                  0.0,
    "Primary Energy|Oil":                      0.0,
    "Primary Energy|Solar":                    0.0,
    "Primary Energy|Wind":                     0.0,
    "Secondary Energy|Electricity":            0.0,
    "Secondary Energy|Electricity|Biomass":    0.0,
    "Secondary Energy|Electricity|Coal":       0.0,
    "Secondary Energy|Electricity|Gas":        0.0,
    "Secondary Energy|Electricity|Geothermal": 0.0,
    "Secondary Energy|Electricity|Hydro":      0.0,
    "Secondary Energy|Electricity|Nuclear":    0.0,
    "Secondary Energy|Electricity|Oil":        0.0,
    "Secondary Energy|Electricity|Solar":      0.0,
    "Secondary Energy|Electricity|Wind":       0.0,
}


def run_physical_bounds_check(pred_long: pd.DataFrame) -> pd.DataFrame:
    """
    Check predictions against PHYSICAL_BOUNDS.

    Returns a copy of pred_long with added Status and Violation_Type columns.
    Only rows whose Variable appears in PHYSICAL_BOUNDS are checked;
    all other rows receive Status = 'PASS'.
    """
    results = pred_long.copy()
    results["Status"] = "PASS"
    results["Violation_Type"] = ""

    for var, lower_bound in PHYSICAL_BOUNDS.items():
        mask = results["Variable"] == var
        if not mask.any():
            continue
        violates = (
            (results.loc[mask, "Value"] < lower_bound) &
            results.loc[mask, "Value"].notna()
        )
        results.loc[mask & violates, "Status"] = "FAIL"
        results.loc[mask & violates, "Violation_Type"] = (
            f"Below physical lower bound ({lower_bound})"
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
    ground_truth: Optional[pd.DataFrame] = None,   # accepted but unused
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Run physical bounds check on pre-loaded, pre-normalised predictions.

    Ground truth is not used — physical bounds are fixed constants.

    Parameters
    ----------
    predictions  : canonical long DataFrame
    ground_truth : ignored (accepted for interface consistency)
    out_dir      : root results directory
    run_id       : run identifier
    """
    check_name = "physical_bounds_check"

    results = run_physical_bounds_check(predictions)
    summary = scenario_summary(results)

    n_checked = (results["Variable"].isin(PHYSICAL_BOUNDS)).sum()
    n_fail    = (results["Status"] == "FAIL").sum()
    passed    = n_fail == 0

    print(f"  [physical_bounds_check] {n_checked:,} rows checked against "
          f"{len(PHYSICAL_BOUNDS)} bound variables.")
    print(f"  [physical_bounds_check] Violations: {n_fail:,} "
          f"({'PASS' if passed else 'FAIL'})")

    out_path = make_out_dir(out_dir, run_id, check_name)
    save_check_outputs(out_path, results, summary)

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
        description="Physical bounds check — verifies non-negativity and other "
                    "hard physical constraints on IAM emulation predictions."
    )
    parser.add_argument("--predictions", required=True,
                        help="Path to predictions CSV (IAMC format)")
    parser.add_argument("--run_id",      required=True, help="Run identifier")
    parser.add_argument("--out_dir",     default="results", help="Output directory")

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))

    result = run(predictions=pred, out_dir=args.out_dir, run_id=args.run_id)

    print(f"\nPhysical bounds check: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Results saved to {args.out_dir}/{args.run_id}/physical_bounds_check/")


if __name__ == "__main__":
    main()
