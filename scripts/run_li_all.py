"""
Full validation runner for the Li et al. (Deep-IAM) dataset.

Mirrors the behaviour of run_all.py for ml-iam: runs validation checks against
both the generated model outputs (predictions) and the AR6 ground truth, then
optionally generates a report.

Checks run against GENERATED outputs:
  plausibility    Growth rate plausibility
  sum_check       Hierarchy sum check
  bounds_check    Physical + empirical bounds

Checks run against GROUND TRUTH (AR6 input data):
  plausibility, sum_check, bounds_check  (same three)

Not run (not applicable):
  regional_consistency  — Li et al. data is World-level only.

⚠ Timestep note
----------------
Li et al. data uses 10-year timesteps (2020–2100 for generated; 2010–2100 for
ground truth). The plausibility check computes 10-year growth rates rather than
the 5-year rates used for ml-iam. Flag this when comparing results.

Usage
-----
    # Validate VAE outputs (primary model per paper)
    python scripts/run_li_all.py --run_id li_vae_01 --model vae

    # Validate CGAN outputs
    python scripts/run_li_all.py --run_id li_cgan_01 --model cgan

    # Validate all three models in sequence
    python scripts/run_li_all.py --run_id li_vae_01  --model vae  --report
    python scripts/run_li_all.py --run_id li_cgan_01 --model cgan --report
    python scripts/run_li_all.py --run_id li_rcgan_01 --model rcgan --report

    # Skip ground truth pass
    python scripts/run_li_all.py --run_id li_vae_01 --model vae --no-groundtruth

Results are written to:
    ml-iam/results/xgb/<run_id>/<check_name>/               (generated outputs)
    ml-iam/results/xgb/<run_id>/<check_name>_ground_truth/  (AR6 ground truth)
    ml-iam/results/xgb/<run_id>/predictions/                (long-format export
                                                             for correlation analysis)

Reports are written to:
    em-iam-val/reports/<run_id>/report.md

Notes:
    After all checks, generated scenarios and AR6 ground truth are exported
    in long (tidy) format to results/xgb/<run_id>/predictions/ for use by
    the inter-variable correlation section of the report (section 5).
"""

import argparse
import importlib
import os
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_ml_iam_root = os.environ.get("ML_IAM_ROOT")
if not _ml_iam_root:
    _ml_iam_root = str(Path(__file__).resolve().parent.parent.parent / "ml-iam")
REPO_ROOT = Path(_ml_iam_root)

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from li_generated_adapter import load_generated_data        # noqa: E402
from li_ground_truth_adapter import load_li_ground_truth    # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (shared with run_li_groundtruth.py)
# ---------------------------------------------------------------------------

class _Tee:
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
    d = REPO_ROOT / "results" / "xgb" / run_id / check_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_check(module_name: str, description: str, argv: list) -> bool:
    """Import and run a check module's main() with the given argv."""
    print(f"\n{'#'*60}")
    print(f"  Running: {description}")
    print(f"{'#'*60}")
    original_argv = sys.argv
    try:
        sys.argv = [module_name] + argv
        mod = importlib.import_module(module_name)
        importlib.reload(mod)
        mod.main()
        return True
    except SystemExit as e:
        if e.code in (0, None):
            return True
        print(f"\n  [ERROR] {description} exited with code {e.code}")
        return False
    except Exception:
        print(f"\n  [ERROR] {description} raised an exception:")
        traceback.print_exc()
        return False
    finally:
        sys.argv = original_argv


# ---------------------------------------------------------------------------
# Per-check runners (predictions pass)
# ---------------------------------------------------------------------------

def run_plausibility_pred(test_data, values, targets, run_id, percentile, by_category):
    from check_plausibility import (
        build_trajectory_df, compute_growth_rates,
        derive_empirical_bounds, flag_violations,
    )
    out_dir = _out_dir(run_id, "plausibility")
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee
    try:
        print("=" * 60)
        print("  PLAUSIBILITY CHECK — Li et al. generated outputs")
        print(f"  Run ID : {run_id}")
        print("  NOTE   : 10-year timesteps (not 5-year as in ml-iam)")
        print("=" * 60)

        pred_long  = build_trajectory_df(test_data, values, targets, "predictions")
        pred_growth = compute_growth_rates(pred_long)
        bounds      = derive_empirical_bounds(pred_growth, percentile, 100.0 - percentile)
        flagged     = flag_violations(pred_growth, bounds)

        n_viol  = flagged["violation"].sum()
        n_total = len(flagged)
        print(f"\n  Violations: {n_viol:,} / {n_total:,}  ({100*n_viol/n_total:.2f}%)")

        if by_category and "Scenario_Category" in flagged.columns:
            print("\n  By category:")
            cat_s = (
                flagged.groupby("Scenario_Category")["violation"]
                .agg(["sum", "count"])
                .rename(columns={"sum": "violations", "count": "total"})
            )
            cat_s["pct"] = 100 * cat_s["violations"] / cat_s["total"]
            print(cat_s.to_string())

        flagged.to_csv(out_dir / "growth_rate_violations.csv", index=False)
        bounds.to_csv(out_dir / "empirical_bounds.csv",        index=False)
        print(f"\n  Saved to: {out_dir}")
        return True
    except Exception:
        traceback.print_exc()
        return False
    finally:
        tee.close()


def run_sum_check_pred(test_data, values, targets, run_id, threshold, abs_floor):
    import pandas as pd
    from sum_check import discover_hierarchy, build_long, run_sum_check as _run, scenario_summary

    out_dir = _out_dir(run_id, "sum_check")
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee
    try:
        print("=" * 60)
        print("  SUM CHECK — Li et al. generated outputs")
        print(f"  Run ID    : {run_id}")
        print(f"  Threshold : {threshold:.1%}")
        print("=" * 60)

        hierarchy = discover_hierarchy(targets)
        if not hierarchy:
            print("\n  No parent-child relationships found in targets — skipping.")
            return True

        print(f"\n  Hierarchy:")
        for parent, children in hierarchy.items():
            print(f"    {parent}")
            for c in children:
                print(f"      └─ {c}")

        long = build_long(test_data, values, targets, "predictions")
        all_tdfs = [_run(long, p, c, threshold, abs_floor) for p, c in hierarchy.items()]
        timestep_df = pd.concat(all_tdfs, ignore_index=True)
        summary     = scenario_summary(timestep_df, threshold, pass_mode="mean")

        n_pass = summary["passed"].sum()
        n_tot  = len(summary)
        print(f"\n  Passing (mean mode): {n_pass} / {n_tot}  ({100*n_pass/n_tot:.1f}%)")

        summary.to_csv(out_dir / "scenario_summary.csv",  index=False)
        timestep_df.to_csv(out_dir / "timestep_errors.csv", index=False)
        print(f"\n  Saved to: {out_dir}")
        return True
    except Exception:
        traceback.print_exc()
        return False
    finally:
        tee.close()


def run_bounds_pred(test_data, values, targets, run_id, percentile, use_empirical):
    from bounds_check import (
        build_long, derive_empirical_bounds, build_bounds_table,
        run_bounds_check, scenario_summary,
    )
    out_dir = _out_dir(run_id, "bounds_check")
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee
    try:
        print("=" * 60)
        print("  BOUNDS CHECK — Li et al. generated outputs")
        print(f"  Run ID          : {run_id}")
        print(f"  Empirical bounds: {'yes' if use_empirical else 'no (physical only)'}")
        print("=" * 60)

        pred_long = build_long(test_data, values, targets, "predictions")
        emp_bounds = (
            derive_empirical_bounds(pred_long, targets, percentile, 100.0 - percentile)
            if use_empirical else None
        )
        bounds_table = build_bounds_table(targets, use_empirical, emp_bounds)
        checked      = run_bounds_check(pred_long, bounds_table)
        summary      = scenario_summary(checked)

        n_viol  = checked["violation"].sum()
        n_total = len(checked)
        print(f"\n  Violations: {n_viol:,} / {n_total:,}  ({100*n_viol/n_total:.2f}%)")

        summary.to_csv(out_dir / "scenario_summary.csv", index=False)
        checked[checked["violation"]].to_csv(out_dir / "violations.csv", index=False)
        bounds_table.to_csv(out_dir / "bounds_used.csv", index=False)
        print(f"\n  Saved to: {out_dir}")
        return True
    except Exception:
        traceback.print_exc()
        return False
    finally:
        tee.close()


# ---------------------------------------------------------------------------
# Historical and domain knowledge constraint checks (shared logic)
# ---------------------------------------------------------------------------

def run_historical_constraints_pred(test_data, values, targets, run_id, check_module_name, out_subdir, label):
    """
    Run hard_historical_constraints or soft_future_constraints against Li et al. outputs.
    Imports CONSTRAINTS and run_constraint from the named check module and runs them
    directly against the already-loaded data, bypassing load_predictions().
    """
    import importlib
    import pandas as pd
    from sum_check import build_long

    check_mod = importlib.import_module(check_module_name)

    out_dir = _out_dir(run_id, out_subdir)
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee
    try:
        print("=" * 60)
        print(f"  {label.upper()} — Li et al. generated outputs")
        print(f"  Run ID : {run_id}")
        print("=" * 60)

        long = build_long(test_data, values, targets, "predictions")
        available_vars  = set(long["Variable"].unique())
        available_years = set(long["Year"].unique())

        print(f"\n  Available years : {sorted(available_years)}")
        print(f"  Available vars  : {len(available_vars)}")

        skipped         = []
        results         = []
        constraints_run = []

        for constraint in check_mod.CONSTRAINTS:
            result, status, missing = check_mod.run_constraint(
                long, constraint, available_vars, available_years
            )
            if status == "skip":
                print(f"\n  Skipping '{constraint['name']}': missing: {missing}")
                skipped.append((constraint["name"], missing))
            else:
                results.append(result)
                constraints_run.append(constraint)

        if results:
            combined = pd.concat(results, ignore_index=True)
            combined.to_csv(out_dir / "all_results.csv", index=False)
            combined[combined["status"] == "FAIL"].to_csv(out_dir / "failures.csv", index=False)
            if "WARN" in combined["status"].values:
                combined[combined["status"] == "WARN"].to_csv(out_dir / "warnings.csv", index=False)

            # Quick summary to console
            summary = (
                combined.groupby("constraint_name")["status"]
                .value_counts().unstack(fill_value=0).reset_index()
            )
            print(f"\n  Results summary:")
            for _, row in summary.iterrows():
                n_pass = row.get("PASS", 0)
                n_warn = row.get("WARN", 0)
                n_fail = row.get("FAIL", 0)
                total  = n_pass + n_warn + n_fail
                print(
                    f"    {row['constraint_name']:<35}  "
                    f"PASS {100*n_pass/total:5.1f}%  "
                    f"FAIL {100*n_fail/total:5.1f}%"
                )

        if skipped:
            pd.DataFrame(skipped, columns=["constraint_name", "missing_variables"]).to_csv(
                out_dir / "skipped.csv", index=False
            )
            print(f"\n  Skipped: {[s[0] for s in skipped]}")

        print(f"\n  Saved to: {out_dir}")
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
        description="Run full em-iam-val validation suite on Li et al. outputs"
    )
    parser.add_argument("--run_id",  required=True,
                        help="Run identifier, e.g. li_vae_01")
    parser.add_argument("--model",   required=True, choices=["vae", "cgan", "rcgan"],
                        help="Which Li et al. model outputs to validate")
    parser.add_argument("--li_path",     default=None,
                        help="Path to Li et al. ground truth CSV folder (default: auto)")
    parser.add_argument("--data_path",   default=None,
                        help="Path to gen_data_<model>.npy (default: auto)")
    parser.add_argument("--labels_path", default=None,
                        help="Path to gen_labels_<model>.npy (default: auto)")
    parser.add_argument("--percentile",  type=float, default=1.0)
    parser.add_argument("--threshold",   type=float, default=0.012)
    parser.add_argument("--abs_floor",   type=float, default=1.0)
    parser.add_argument("--no_empirical",   action="store_true")
    parser.add_argument("--by_category",    action="store_true")
    parser.add_argument("--no-plausibility",    action="store_true")
    parser.add_argument("--no-sum-check",       action="store_true")
    parser.add_argument("--no-bounds",          action="store_true")
    parser.add_argument("--no-hard-historical", action="store_true")
    parser.add_argument("--no-soft-future",     action="store_true")
    parser.add_argument("--no-groundtruth", action="store_true",
                        help="Skip the ground truth reference pass")
    parser.add_argument("--report",         action="store_true",
                        help="Generate a validation report after checks complete")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  LI ET AL. VALIDATION — {args.model.upper()}")
    print(f"  Run ID : {args.run_id}")
    print(f"{'='*60}")

    # Load generated outputs
    pred_data, pred_values, pred_targets = load_generated_data(
        args.model,
        data_path=args.data_path,
        labels_path=args.labels_path,
    )

    results = {}

    # ── Predictions pass ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PREDICTIONS PASS")
    print(f"{'='*60}")

    if not args.no_plausibility:
        results["plausibility"] = run_plausibility_pred(
            pred_data, pred_values, pred_targets,
            run_id=args.run_id, percentile=args.percentile,
            by_category=args.by_category,
        )

    if not args.no_sum_check:
        results["sum_check"] = run_sum_check_pred(
            pred_data, pred_values, pred_targets,
            run_id=args.run_id, threshold=args.threshold,
            abs_floor=args.abs_floor,
        )

    if not args.no_bounds:
        results["bounds_check"] = run_bounds_pred(
            pred_data, pred_values, pred_targets,
            run_id=args.run_id, percentile=args.percentile,
            use_empirical=not args.no_empirical,
        )

    if not args.no_hard_historical:
        results["hard_historical_constraints"] = run_historical_constraints_pred(
            pred_data, pred_values, pred_targets,
            run_id=args.run_id,
            check_module_name="hard_historical_constraints",
            out_subdir="hard_historical_constraints",
            label="Hard historical constraints (AR6 2020 anchors)",
        )

    if not args.no_soft_future:
        results["soft_future_constraints"] = run_historical_constraints_pred(
            pred_data, pred_values, pred_targets,
            run_id=args.run_id,
            check_module_name="soft_future_constraints",
            out_subdir="soft_future_constraints",
            label="Soft future constraints (AR6 domain plausibility)",
        )

    # ── Ground truth pass ────────────────────────────────────────────────────
    if not args.no_groundtruth:
        print(f"\n{'='*60}")
        print("  GROUND TRUTH PASS")
        print(f"{'='*60}")

        gt_argv = [
            "--run_id",    args.run_id,
            "--threshold", str(args.threshold),
            "--abs_floor", str(args.abs_floor),
            "--percentile", str(args.percentile),
        ]
        if args.no_plausibility:    gt_argv.append("--no-plausibility")
        if args.no_sum_check:       gt_argv.append("--no-sum-check")
        if args.no_bounds:          gt_argv.append("--no-bounds")
        if args.no_hard_historical: gt_argv.append("--no-hard-historical")
        if args.no_soft_future:     gt_argv.append("--no-soft-future")
        if args.no_empirical:       gt_argv.append("--no_empirical")
        if args.by_category:        gt_argv.append("--by_category")
        if args.li_path:            gt_argv += ["--li_path", args.li_path]

        results["ground_truth"] = _run_check(
            "run_li_groundtruth", "Ground truth reference pass", gt_argv
        )

    # ── Export predictions in long format (for correlation analysis) ─────────
    print(f"\n{'#'*60}")
    print("  Exporting generated scenarios in long format")
    print(f"{'#'*60}")
    try:
        from sum_check import build_long
        from li_ground_truth_adapter import load_li_ground_truth

        pred_long = build_long(pred_data, pred_values, pred_targets, "predictions")
        out_dir = REPO_ROOT / "results" / "xgb" / args.run_id / "predictions"
        out_dir.mkdir(parents=True, exist_ok=True)
        pred_long.to_csv(out_dir / "predictions_long.csv", index=False)
        print(f"  Saved predictions_long.csv  ({len(pred_long):,} rows)")

        # Ground truth: load AR6 data filtered to same variables as generated outputs
        gt_data, gt_values, gt_targets = load_li_ground_truth(
            li_path=args.li_path if hasattr(args, "li_path") else None,
            variables=pred_targets,
            verbose=False,
        )
        # Align to same targets as predictions
        import numpy as np
        target_idx = [gt_targets.index(t) for t in pred_targets if t in gt_targets]
        aligned_targets = [gt_targets[i] for i in target_idx]
        gt_long = build_long(gt_data, gt_values[:, target_idx], aligned_targets, "ground_truth")
        gt_long.to_csv(out_dir / "groundtruth_long.csv", index=False)
        print(f"  Saved groundtruth_long.csv  ({len(gt_long):,} rows)")
        results["export_predictions"] = True
    except Exception:
        print("  [WARNING] Could not export long-format predictions:")
        traceback.print_exc()
        results["export_predictions"] = False

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  LI VALIDATION SUMMARY — {args.model.upper()}")
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

    # ── Optional report ───────────────────────────────────────────────────────
    if args.report:
        _run_check(
            "make_val_report", "Validation report generation",
            ["--run_id", args.run_id,
             "--title", f"Li et al. Validation — {args.model.upper()} ({args.run_id})"]
        )

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
