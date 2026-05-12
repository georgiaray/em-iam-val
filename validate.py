"""
Unified validation runner.

Loads canonical adapted-data CSVs, normalises units, runs all checks,
saves results, optionally generates a report.

Usage:
    python validate.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
        --ground_truth adapted-data/shin_01_ground_truth.csv \\
        --run_id shin_01

    # Run only specific checks:
    python validate.py ... --only bounds_check hard_historical_constraints

    # Skip specific checks:
    python validate.py ... --skip regional_consistency

    # Generate report:
    python validate.py ... --report
"""

import sys
import os
import argparse
import importlib
import inspect
from pathlib import Path
import pandas as pd

# Add checks directory to path
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT / "checks"))

from utils import load_csv, normalize_to_canonical


COMMON_CHECKS = [
    ("common.check_plausibility",          "Growth rate plausibility"),
    ("common.sum_check",                    "Hierarchy sum check"),
    ("common.regional_consistency",         "Regional consistency"),
    ("common.bounds_check",                 "Physical bounds"),
    ("common.hard_historical_constraints",  "Hard historical constraints (WGIII/AR6)"),
    ("common.soft_future_constraints",      "Soft future constraints (WGIII/AR6)"),
    ("common.sci_checks",         "SCI vetting checks"),
    ("common.inter_variable_correlation",   "Inter-variable correlation"),
]

GENERATION_CHECKS: list = [
    # e.g. ("generation.distribution_similarity", "Distribution similarity")
]

RECONSTRUCTION_CHECKS: list = [
    ("reconstruction.error_metrics", "Per-scenario error metrics (nRMSE, RMSE, MAE, R², bias)"),
]


def run_validation(
    predictions_path: str,
    ground_truth_path: str = None,
    run_id: str = "run",
    out_dir: str = "results",
    method_type: str = None,
    only_checks: list = None,
    skip_checks: list = None,
    report: bool = False,
    **check_kwargs
) -> dict:
    """
    Run full validation pipeline.

    Args:
        predictions_path: Path to predictions CSV (IAMC wide format)
        ground_truth_path: Path to ground truth CSV (optional, IAMC wide format)
        run_id: Run identifier
        out_dir: Output directory
        method_type: "generation" or "reconstruction" — adds type-specific checks
                     on top of the common checks. If None, only common checks run.
        only_checks: List of check names to run (default: all)
        skip_checks: List of check names to skip
        report: Generate summary report
        **check_kwargs: Additional arguments passed to individual checks

    Returns:
        dict with overall results and check summaries
    """
    print("=" * 70)
    print("EM-IAM-VAL Validation Framework")
    print("=" * 70)

    # Load and normalize data
    print(f"\nLoading predictions from {predictions_path}")
    pred_long = load_csv(predictions_path)
    print(f"  Loaded {len(pred_long)} rows, {pred_long['Variable'].nunique()} variables")

    print("\nNormalizing to canonical units...")
    pred_long = normalize_to_canonical(pred_long)

    gt_long = None
    if ground_truth_path:
        print(f"\nLoading ground truth from {ground_truth_path}")
        gt_long = load_csv(ground_truth_path)
        print(f"  Loaded {len(gt_long)} rows, {gt_long['Variable'].nunique()} variables")

        print("\nNormalizing ground truth to canonical units...")
        gt_long = normalize_to_canonical(gt_long)

    # Build the full check list for this run
    all_checks = list(COMMON_CHECKS)
    if method_type == "generation":
        all_checks += GENERATION_CHECKS
    elif method_type == "reconstruction":
        all_checks += RECONSTRUCTION_CHECKS

    # Apply --only / --skip filters
    checks_to_run = []
    for check_name, check_label in all_checks:
        if only_checks and check_name not in only_checks:
            continue
        if skip_checks and check_name in skip_checks:
            continue
        checks_to_run.append((check_name, check_label))

    if not checks_to_run:
        print("No checks to run.")
        return {"passed": False, "reason": "No checks selected"}

    print(f"\nRunning {len(checks_to_run)} checks:")
    for check_name, check_label in checks_to_run:
        print(f"  - {check_label} ({check_name})")

    # Run each check
    check_results = {}
    overall_passed = True
    summary_rows = []

    for check_name, check_label in checks_to_run:
        print(f"\n{'=' * 70}")
        print(f"Running: {check_label}")
        print("=" * 70)

        try:
            # Import check module
            check_module = importlib.import_module(check_name)

            # Get the run function signature to know what kwargs to pass
            run_func = check_module.run
            sig = inspect.signature(run_func)

            # Filter kwargs to only those accepted by run()
            accepted_kwargs = {}
            for param_name, param in sig.parameters.items():
                if param_name in check_kwargs:
                    accepted_kwargs[param_name] = check_kwargs[param_name]
                elif param_name == "predictions":
                    accepted_kwargs["predictions"] = pred_long   # DataFrame, not path
                elif param_name == "ground_truth":
                    accepted_kwargs["ground_truth"] = gt_long    # DataFrame or None
                elif param_name == "run_id":
                    accepted_kwargs["run_id"] = run_id
                elif param_name == "out_dir":
                    accepted_kwargs["out_dir"] = out_dir

            # Run check
            result = run_func(**accepted_kwargs)

            check_results[check_name] = result
            passed = result.get("passed", False)

            if not passed:
                overall_passed = False

            # Extract summary metric
            summary_df = result.get("summary")
            if summary_df is not None and not summary_df.empty:
                if "Pass_Rate" in summary_df.columns:
                    metric = f"{summary_df['Pass_Rate'].mean():.1%}"
                elif "Passes" in summary_df.columns:
                    metric = f"{(summary_df['Passes'] == True).sum()}/{len(summary_df)}"
                else:
                    metric = "N/A"
            else:
                metric = "N/A"

            status_str = "PASS" if passed else "FAIL"
            print(f"Result: {status_str} (metric: {metric})")

            summary_rows.append({
                "Check": check_label,
                "Status": status_str,
                "Metric": metric,
            })

        except Exception as e:
            print(f"ERROR: Check {check_name} failed: {e}")
            import traceback
            traceback.print_exc()
            overall_passed = False
            summary_rows.append({
                "Check": check_label,
                "Status": "ERROR",
                "Metric": str(e)[:50],
            })

    # Print summary
    print(f"\n{'=' * 70}")
    print("Validation Summary")
    print("=" * 70)

    summary_table = pd.DataFrame(summary_rows)
    print(summary_table.to_string(index=False))

    print(f"\nOverall Result: {'PASSED' if overall_passed else 'FAILED'}")
    print(f"Results saved to {out_dir}/{run_id}/")

    return {
        "passed": overall_passed,
        "run_id": run_id,
        "checks": check_results,
        "summary": summary_table,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Unified em-iam-val validation runner"
    )
    parser.add_argument("--predictions", required=True, help="Path to predictions CSV (IAMC wide format)")
    parser.add_argument("--ground_truth", help="Path to ground truth CSV (optional, IAMC wide format)")
    parser.add_argument("--run_id", required=True, help="Run identifier")
    parser.add_argument("--out_dir", default="results", help="Output directory (default: results/)")
    parser.add_argument("--method_type", choices=["generation", "reconstruction"],
                        help="Emulation method type — adds type-specific checks on top of common checks")
    parser.add_argument("--only", nargs="*", metavar="CHECK",
                        help="Run only these checks (space-separated check names)")
    parser.add_argument("--skip", nargs="*", metavar="CHECK",
                        help="Skip these checks (space-separated check names)")
    parser.add_argument("--report", action="store_true", help="Generate summary report")
    parser.add_argument("--percentile", type=float, default=1.0,
                        help="Percentile for empirical bounds (default: 1.0)")
    parser.add_argument("--threshold", type=float, default=0.012,
                        help="Relative tolerance for sum check (default: 0.012)")
    parser.add_argument("--abs_floor", type=float, default=1.0,
                        help="Absolute tolerance floor (default: 1.0)")
    parser.add_argument("--world_region", default="World",
                        help="World region name (default: World)")
    parser.add_argument("--pass_mode", default="mean", choices=["mean", "all"],
                        help="Pass criterion for sum check (default: mean)")
    parser.add_argument("--grouping", choices=["R5", "R6", "R10"],
                        help="Regional grouping for regional consistency check")

    args = parser.parse_args()

    # Validate check names against the full set for the given method_type
    type_checks = (GENERATION_CHECKS if args.method_type == "generation"
                   else RECONSTRUCTION_CHECKS if args.method_type == "reconstruction"
                   else [])
    valid_checks = [name for name, _ in COMMON_CHECKS + type_checks]
    if args.only:
        for check in args.only:
            if check not in valid_checks:
                print(f"Unknown check: {check}")
                print(f"Valid checks: {', '.join(valid_checks)}")
                sys.exit(1)

    if args.skip:
        for check in args.skip:
            if check not in valid_checks:
                print(f"Unknown check: {check}")
                print(f"Valid checks: {', '.join(valid_checks)}")
                sys.exit(1)

    # Build check kwargs
    check_kwargs = {
        "percentile": args.percentile,
        "threshold": args.threshold,
        "abs_floor": args.abs_floor,
        "world_region": args.world_region,
        "pass_mode": args.pass_mode,
        "grouping": args.grouping,
    }

    result = run_validation(
        predictions_path=args.predictions,
        ground_truth_path=args.ground_truth,
        run_id=args.run_id,
        out_dir=args.out_dir,
        method_type=args.method_type,
        only_checks=args.only,
        skip_checks=args.skip,
        report=args.report,
        **check_kwargs
    )

    if args.report:
        import importlib, sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))
        rpt = importlib.import_module("make_val_report")
        _sys.argv = ["make_val_report", "--run_id", args.run_id, "--out_dir", args.out_dir]
        rpt.main()

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
