"""
Ground truth validation runner for the Ling et al. (Deep-IAM) dataset.

Loads the Ling et al. AR6 scenario CSVs via ling_adapter.py, reshapes them
into the em-iam-val canonical format, and runs the applicable validation checks
directly — bypassing the RunStore / ml-iam pipeline used by run_groundtruth.py.

Applicable checks
-----------------
  plausibility    Growth rate plausibility (10-year periods — see note below)
  sum_check       Hierarchy sum check (Secondary Energy|Electricity parent/children)
  bounds_check    Physical + empirical bounds check

Not applicable
--------------
  regional_consistency  Ling data is World-level only; no subregional breakdown.

⚠ Timestep note
----------------
Ling data uses 10-year timesteps (2010, 2020, ..., 2100). The plausibility check
normally computes 5-year period-on-period growth rates (because ml-iam data is
annual). Here it computes 10-year growth rates instead. This is a methodological
difference that should be noted when comparing Ling results against ml-iam results.

Usage
-----
    python scripts/run_ling_groundtruth.py --run_id ling_01
    python scripts/run_ling_groundtruth.py --run_id ling_01 --ling_path /path/to/Ling_emulation/Policy-Generative\ Model
    python scripts/run_ling_groundtruth.py --run_id ling_01 --no-plausibility
    python scripts/run_ling_groundtruth.py --run_id ling_01 --report

Results are written to:
    ml-iam/results/xgb/<run_id>/<check_name>_ground_truth/

The run_id is prefixed with "ling_" by convention (e.g. ling_01) so Ling
results are clearly separated from ml-iam XGBoost runs in the results directory.
The report can then be generated with:
    python scripts/make_val_report.py --run_id ling_01
"""

import argparse
import os
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — mirror the pattern used in all other scripts
# ---------------------------------------------------------------------------

_ml_iam_root = os.environ.get("ML_IAM_ROOT")
if not _ml_iam_root:
    _ml_iam_root = str(Path(__file__).resolve().parent.parent.parent / "ml-iam")
REPO_ROOT = Path(_ml_iam_root)

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ for sibling imports

# ---------------------------------------------------------------------------
# Imports from check modules
# (module-level code in each check just sets REPO_ROOT / sys.path — safe to import)
# ---------------------------------------------------------------------------

from ling_adapter import load_ling_data          # noqa: E402

# Lazy imports inside run_* functions so failures are reported per-check
# rather than aborting everything.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Tee:
    """Write to both stdout and a file simultaneously."""
    def __init__(self, path: Path):
        self._file = open(path, "w")
        self._stdout = sys.stdout

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def close(self):
        sys.stdout = self._stdout
        self._file.close()


def _out_dir(run_id: str, check_name: str) -> Path:
    """Return the output directory for a check, creating it if needed."""
    d = REPO_ROOT / "results" / "xgb" / run_id / check_name
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Per-check runners
# ---------------------------------------------------------------------------

def run_plausibility(test_data, values, targets, run_id, percentile, by_category):
    """Run the growth rate plausibility check against Ling ground truth."""
    from check_plausibility import (
        build_trajectory_df,
        compute_growth_rates,
        derive_empirical_bounds,
        flag_violations,
    )

    out_dir = _out_dir(run_id, "plausibility_ground_truth")
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee

    try:
        print("=" * 60)
        print("  PLAUSIBILITY CHECK — Ling ground truth")
        print(f"  Run ID : {run_id}")
        print("  NOTE   : 10-year timesteps (not 5-year as in ml-iam)")
        print("=" * 60)

        lower_pct = percentile
        upper_pct = 100.0 - percentile

        # For ground truth validation: the data IS the ground truth,
        # so we derive bounds from it and check it against itself.
        gt_long = build_trajectory_df(test_data, values, targets, "ground_truth")

        gt_growth = compute_growth_rates(gt_long)

        n_dropped = len(gt_long) - len(gt_growth) - (
            gt_growth["growth_rate"].isna().sum()
        ) if len(gt_long) > len(gt_growth) else 0
        print(f"\n  Rows after growth-rate computation: {len(gt_growth):,}")

        bounds = derive_empirical_bounds(gt_growth, lower_pct, upper_pct)
        flagged = flag_violations(gt_growth, bounds)

        n_violations = flagged["violation"].sum()
        n_total = len(flagged)
        pct = 100 * n_violations / n_total if n_total else 0.0
        print(f"\n  Violations: {n_violations:,} / {n_total:,}  ({pct:.2f}%)")

        if by_category and "Scenario_Category" in flagged.columns:
            print("\n  By category:")
            cat_summary = (
                flagged.groupby("Scenario_Category")["violation"]
                .agg(["sum", "count"])
                .rename(columns={"sum": "violations", "count": "total"})
            )
            cat_summary["pct"] = 100 * cat_summary["violations"] / cat_summary["total"]
            print(cat_summary.to_string())

        # Save outputs
        viol_path   = out_dir / "growth_rate_violations.csv"
        bounds_path = out_dir / "empirical_bounds.csv"
        flagged.to_csv(viol_path,   index=False)
        bounds.to_csv(bounds_path,  index=False)

        print(f"\n  Saved: {viol_path}")
        print(f"  Saved: {bounds_path}")
        print(f"  Saved: {out_dir / 'report.txt'}")

        return True

    except Exception:
        traceback.print_exc()
        return False
    finally:
        tee.close()


def run_sum_check(test_data, values, targets, run_id, threshold, abs_floor):
    """Run the hierarchy sum check against Ling ground truth."""
    from sum_check import discover_hierarchy, build_long, run_sum_check as _run, scenario_summary

    out_dir = _out_dir(run_id, "sum_check_ground_truth")
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee

    try:
        print("=" * 60)
        print("  SUM CHECK — Ling ground truth")
        print(f"  Run ID    : {run_id}")
        print(f"  Threshold : {threshold:.1%}")
        print("=" * 60)

        hierarchy = discover_hierarchy(targets)

        if not hierarchy:
            print("\n  No parent-child variable relationships found in Ling targets.")
            print("  This check requires at least one parent and one child variable")
            print("  (e.g. Secondary Energy|Electricity + Secondary Energy|Electricity|Solar).")
            return True

        print(f"\n  Hierarchy discovered:")
        for parent, children in hierarchy.items():
            print(f"    {parent}")
            for c in children:
                print(f"      └─ {c}")

        long = build_long(test_data, values, targets, "ground_truth")

        import pandas as pd
        all_timestep_dfs = []
        for parent, children in hierarchy.items():
            tdf = _run(long, parent, children, threshold, abs_floor)
            all_timestep_dfs.append(tdf)

        timestep_df = pd.concat(all_timestep_dfs, ignore_index=True)
        summary = scenario_summary(timestep_df, threshold, pass_mode="mean")

        n_pass = summary["passed"].sum()
        n_total = len(summary)
        print(f"\n  Scenarios passing (mean mode): {n_pass} / {n_total}  ({100*n_pass/n_total:.1f}%)")

        summary_path  = out_dir / "scenario_summary.csv"
        timestep_path = out_dir / "timestep_errors.csv"
        summary.to_csv(summary_path,    index=False)
        timestep_df.to_csv(timestep_path, index=False)

        print(f"\n  Saved: {summary_path}")
        print(f"  Saved: {timestep_path}")
        print(f"  Saved: {out_dir / 'report.txt'}")

        return True

    except Exception:
        traceback.print_exc()
        return False
    finally:
        tee.close()


def run_bounds(test_data, values, targets, run_id, percentile, use_empirical):
    """Run the physical + empirical bounds check against Ling ground truth."""
    from bounds_check import (
        build_long,
        derive_empirical_bounds,
        build_bounds_table,
        run_bounds_check,
        scenario_summary,
    )

    out_dir = _out_dir(run_id, "bounds_check_ground_truth")
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee

    try:
        print("=" * 60)
        print("  BOUNDS CHECK — Ling ground truth")
        print(f"  Run ID          : {run_id}")
        print(f"  Empirical bounds: {'yes' if use_empirical else 'no (physical only)'}")
        print("=" * 60)

        lower_pct = percentile
        upper_pct = 100.0 - percentile

        gt_long = build_long(test_data, values, targets, "ground_truth")

        empirical_bounds = None
        if use_empirical:
            empirical_bounds = derive_empirical_bounds(gt_long, targets, lower_pct, upper_pct)

        bounds_table = build_bounds_table(targets, use_empirical, empirical_bounds)
        checked = run_bounds_check(gt_long, bounds_table)
        summary = scenario_summary(checked)

        n_violations = checked["violation"].sum()
        n_total = len(checked)
        pct = 100 * n_violations / n_total if n_total else 0.0
        print(f"\n  Violations: {n_violations:,} / {n_total:,}  ({pct:.2f}%)")

        summary_path    = out_dir / "scenario_summary.csv"
        violations_path = out_dir / "violations.csv"
        bounds_path     = out_dir / "bounds_used.csv"

        summary.to_csv(summary_path, index=False)
        checked[checked["violation"]].to_csv(violations_path, index=False)
        bounds_table.to_csv(bounds_path, index=False)

        print(f"\n  Saved: {summary_path}")
        print(f"  Saved: {violations_path}")
        print(f"  Saved: {bounds_path}")
        print(f"  Saved: {out_dir / 'report.txt'}")

        return True

    except Exception:
        traceback.print_exc()
        return False
    finally:
        tee.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run em-iam-val ground truth checks on the Ling et al. dataset"
    )
    parser.add_argument(
        "--run_id", required=True,
        help="Run identifier for output paths, e.g. ling_01"
    )
    parser.add_argument(
        "--ling_path", default=None,
        help=(
            "Path to the Ling CSV folder "
            "(default: coding/Ling_emulation/Policy-Generative Model)"
        )
    )
    parser.add_argument(
        "--percentile", type=float, default=1.0,
        help="Tail percentile for plausibility and empirical bounds (default: 1.0)"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.012,
        help="Max relative error for sum check (default: 0.012 = 1.2%%)"
    )
    parser.add_argument(
        "--abs_floor", type=float, default=1.0,
        help="Min absolute value for relative error computation (default: 1.0)"
    )
    parser.add_argument(
        "--no_empirical", action="store_true",
        help="Disable empirical bounds in the bounds check (physical bounds only)"
    )
    parser.add_argument(
        "--by_category", action="store_true",
        help="Break down plausibility violations by scenario category"
    )
    parser.add_argument(
        "--drop_failed_vetting", action="store_true", default=True,
        help="Exclude failed-vetting / no-climate-assessment scenarios (default: True)"
    )
    parser.add_argument(
        "--no-plausibility", action="store_true", help="Skip plausibility check"
    )
    parser.add_argument(
        "--no-sum-check",    action="store_true", help="Skip hierarchy sum check"
    )
    parser.add_argument(
        "--no-bounds",       action="store_true", help="Skip bounds check"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Generate a validation report after checks complete"
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  LING GROUND TRUTH VALIDATION")
    print(f"  Run ID : {args.run_id}")
    print(f"{'='*60}")

    # Load data once, reuse across checks
    test_data, values, targets = load_ling_data(
        ling_path=args.ling_path,
        drop_failed_vetting=args.drop_failed_vetting,
    )

    results = {}

    if not args.no_plausibility:
        print(f"\n{'#'*60}")
        print("  Running: Growth rate plausibility check")
        print(f"{'#'*60}")
        results["plausibility (GT)"] = run_plausibility(
            test_data, values, targets,
            run_id=args.run_id,
            percentile=args.percentile,
            by_category=args.by_category,
        )

    if not args.no_sum_check:
        print(f"\n{'#'*60}")
        print("  Running: Hierarchy sum check")
        print(f"{'#'*60}")
        results["sum_check (GT)"] = run_sum_check(
            test_data, values, targets,
            run_id=args.run_id,
            threshold=args.threshold,
            abs_floor=args.abs_floor,
        )

    if not args.no_bounds:
        print(f"\n{'#'*60}")
        print("  Running: Physical bounds check")
        print(f"{'#'*60}")
        results["bounds_check (GT)"] = run_bounds(
            test_data, values, targets,
            run_id=args.run_id,
            percentile=args.percentile,
            use_empirical=not args.no_empirical,
        )

    # Summary
    print(f"\n{'='*60}")
    print("  LING VALIDATION SUMMARY")
    print(f"{'='*60}")
    all_passed = True
    for name, passed in results.items():
        status = "OK" if passed else "ERROR"
        print(f"  [{status:>5}]  {name}")
        if not passed:
            all_passed = False

    if not results:
        print("  No checks were run.")

    print(f"{'='*60}\n")

    # Optional report
    if args.report:
        print("  Generating report...")
        try:
            import importlib
            import make_val_report
            importlib.reload(make_val_report)
            original_argv = sys.argv
            sys.argv = ["make_val_report", "--run_id", args.run_id]
            make_val_report.main()
            sys.argv = original_argv
        except Exception:
            print("  [ERROR] Report generation failed:")
            traceback.print_exc()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
