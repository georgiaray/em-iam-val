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

Reports are written to:
    em-iam-val/reports/<run_id>/report.md
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

from li_generated_adapter import load_generated_data   # noqa: E402
from ling_adapter import load_ling_data                # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (shared with run_ling_groundtruth.py)
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
    parser.add_argument("--ling_path",   default=None,
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
    parser.add_argument("--no-plausibility",action="store_true")
    parser.add_argument("--no-sum-check",   action="store_true")
    parser.add_argument("--no-bounds",      action="store_true")
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
        if args.no_plausibility: gt_argv.append("--no-plausibility")
        if args.no_sum_check:    gt_argv.append("--no-sum-check")
        if args.no_bounds:       gt_argv.append("--no-bounds")
        if args.no_empirical:    gt_argv.append("--no_empirical")
        if args.by_category:     gt_argv.append("--by_category")
        if args.ling_path:       gt_argv += ["--ling_path", args.ling_path]

        results["ground_truth"] = _run_check(
            "run_ling_groundtruth", "Ground truth reference pass", gt_argv
        )

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
