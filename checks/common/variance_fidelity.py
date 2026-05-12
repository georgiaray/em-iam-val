"""
Variance fidelity check.

Checks whether the emulator reproduces the marginal variance of each output
variable. Inter-variable correlation checks preserve the shape of variable
relationships but normalise out variance — a model can have perfect
correlations while being systematically over- or under-dispersed. This check
catches that gap.

Two complementary metrics are computed per (Variable, Region):

  Variance ratio  = Var(predictions) / Var(ground truth)
  CV ratio        = CV(predictions)  / CV(ground truth)
                    where CV = std / |mean|  (coefficient of variation)

Variance ratio measures absolute spread fidelity. CV ratio is scale-free and
more interpretable when variable magnitudes differ across regions, but is
unstable when the mean is near zero — both are reported and thresholds are
applied to variance ratio by default.

Status thresholds (applied to variance ratio):
  PASS : 0.5 ≤ ratio ≤ 2.0   (within a factor of 2)
  WARN : 0.25 ≤ ratio < 0.5  or  2.0 < ratio ≤ 4.0
  FAIL : ratio < 0.25         or  ratio > 4.0

Applicable to both reconstruction and generative runs — no 1:1 pairing is
required. For reconstruction runs the variances are computed over the same
held-out scenario set; for generative runs they compare the marginal spread
of the generated ensemble against the reference.

Usage (standalone):
    python checks/common/variance_fidelity.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
        --ground_truth adapted-data/shin_01_ground_truth.csv \\
        --run_id shin_01
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


# Variance ratio thresholds
_PASS_LO  = 0.5
_PASS_HI  = 2.0
_WARN_LO  = 0.25
_WARN_HI  = 4.0

# Minimum ground truth variance below which the check is skipped for that
# pair (avoids division by near-zero for near-constant variables/regions)
_VAR_FLOOR = 1e-8

# Minimum |mean| for CV ratio computation
_MEAN_FLOOR = 1e-6


def _classify(ratio: float) -> str:
    if np.isnan(ratio):
        return "SKIP"
    if _PASS_LO <= ratio <= _PASS_HI:
        return "PASS"
    if _WARN_LO <= ratio <= _WARN_HI:
        return "WARN"
    return "FAIL"


def compute_variance_metrics(
    predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute variance ratio and CV ratio per (Variable, Region).

    Works on unpaired data — only requires that both DataFrames contain the
    same Variable and Region labels. For reconstruction runs the same
    scenario set is used; for generative runs the two distributions are
    compared marginally.

    Returns DataFrame with columns:
        Variable, Region, Units,
        N_pred, N_gt,
        Var_pred, Var_gt, Var_Ratio,
        CV_pred, CV_gt, CV_Ratio,
        Status
    """
    rows = []

    variables = set(predictions["Variable"].unique()) & set(ground_truth["Variable"].unique())

    for var in sorted(variables):
        pred_var = predictions[predictions["Variable"] == var]
        gt_var   = ground_truth[ground_truth["Variable"] == var]
        units    = pred_var["Units"].iloc[0]

        regions = set(pred_var["Region"].unique()) & set(gt_var["Region"].unique())

        for region in sorted(regions):
            p_vals = pred_var[pred_var["Region"] == region]["Value"].dropna().values
            g_vals = gt_var[gt_var["Region"] == region]["Value"].dropna().values

            if len(p_vals) < 2 or len(g_vals) < 2:
                continue

            var_pred = np.var(p_vals, ddof=1)
            var_gt   = np.var(g_vals, ddof=1)

            if var_gt < _VAR_FLOOR:
                # Ground truth is near-constant — ratio undefined, skip
                rows.append({
                    "Variable":  var,
                    "Region":    region,
                    "Units":     units,
                    "N_pred":    len(p_vals),
                    "N_gt":      len(g_vals),
                    "Var_pred":  var_pred,
                    "Var_gt":    var_gt,
                    "Var_Ratio": np.nan,
                    "CV_pred":   np.nan,
                    "CV_gt":     np.nan,
                    "CV_Ratio":  np.nan,
                    "Status":    "SKIP",
                })
                continue

            var_ratio = var_pred / var_gt

            mean_pred = np.mean(np.abs(p_vals))
            mean_gt   = np.mean(np.abs(g_vals))
            cv_pred   = np.sqrt(var_pred) / mean_pred if mean_pred > _MEAN_FLOOR else np.nan
            cv_gt     = np.sqrt(var_gt)   / mean_gt   if mean_gt   > _MEAN_FLOOR else np.nan
            cv_ratio  = cv_pred / cv_gt if (cv_pred is not np.nan and
                                             cv_gt   is not np.nan and
                                             cv_gt   > _MEAN_FLOOR) else np.nan

            rows.append({
                "Variable":  var,
                "Region":    region,
                "Units":     units,
                "N_pred":    len(p_vals),
                "N_gt":      len(g_vals),
                "Var_pred":  var_pred,
                "Var_gt":    var_gt,
                "Var_Ratio": var_ratio,
                "CV_pred":   cv_pred,
                "CV_gt":     cv_gt,
                "CV_Ratio":  cv_ratio,
                "Status":    _classify(var_ratio),
            })

    return pd.DataFrame(rows).sort_values(["Variable", "Region"]).reset_index(drop=True)


def compute_summary(results: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-variable: median variance ratio and median CV ratio across
    regions (median is robust to outlier regions).

    Returns DataFrame with columns:
        Variable, Units, N_Regions, N_Skipped,
        Median_Var_Ratio, Median_CV_Ratio,
        Pass_Rate, Warn_Rate, Fail_Rate
    """
    rows = []
    for var, grp in results.groupby("Variable"):
        active = grp[grp["Status"] != "SKIP"]
        n_skip = (grp["Status"] == "SKIP").sum()

        if active.empty:
            rows.append({
                "Variable":        var,
                "Units":           grp["Units"].iloc[0],
                "N_Regions":       len(grp),
                "N_Skipped":       int(n_skip),
                "Median_Var_Ratio": np.nan,
                "Median_CV_Ratio":  np.nan,
                "Pass_Rate":        np.nan,
                "Warn_Rate":        np.nan,
                "Fail_Rate":        np.nan,
            })
            continue

        total = len(active)
        rows.append({
            "Variable":         var,
            "Units":            grp["Units"].iloc[0],
            "N_Regions":        len(grp),
            "N_Skipped":        int(n_skip),
            "Median_Var_Ratio": active["Var_Ratio"].median(),
            "Median_CV_Ratio":  active["CV_Ratio"].median(),
            "Pass_Rate":        (active["Status"] == "PASS").sum() / total,
            "Warn_Rate":        (active["Status"] == "WARN").sum() / total,
            "Fail_Rate":        (active["Status"] == "FAIL").sum() / total,
        })

    return pd.DataFrame(rows).sort_values("Median_Var_Ratio").reset_index(drop=True)


def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Run variance fidelity check on pre-loaded, pre-normalised DataFrames.

    Parameters
    ----------
    predictions  : canonical long DataFrame (already normalised)
    ground_truth : canonical long DataFrame (required — check is skipped if absent)
    out_dir      : root results directory
    run_id       : run identifier
    """
    check_name = "variance_fidelity"

    if ground_truth is None:
        print("  [variance_fidelity] No ground truth provided — skipping.")
        return {
            "check_name":    check_name,
            "passed":        True,
            "results":       pd.DataFrame(),
            "summary":       pd.DataFrame(),
            "unit_warnings": [],
            "skipped":       ["Ground truth required for variance fidelity check"],
        }

    results = compute_variance_metrics(predictions, ground_truth)

    if results.empty:
        msg = "No matching (Variable, Region) pairs found between predictions and ground truth."
        print(f"  [variance_fidelity] WARNING: {msg}")
        return {
            "check_name":    check_name,
            "passed":        False,
            "results":       pd.DataFrame(),
            "summary":       pd.DataFrame(),
            "unit_warnings": [],
            "skipped":       [msg],
        }

    summary = compute_summary(results)

    active   = results[results["Status"] != "SKIP"]
    n_pass   = (active["Status"] == "PASS").sum()
    n_warn   = (active["Status"] == "WARN").sum()
    n_fail   = (active["Status"] == "FAIL").sum()
    n_skip   = (results["Status"] == "SKIP").sum()
    total    = len(active)
    pass_rate = n_pass / total if total else 1.0
    passed   = n_fail == 0

    print(f"  [variance_fidelity] {total} variable-region pairs evaluated "
          f"({n_skip} skipped — near-constant GT).")
    print(f"  [variance_fidelity] PASS: {n_pass}  WARN: {n_warn}  FAIL: {n_fail}  "
          f"(pass rate: {pass_rate:.1%})")

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
        description="Variance fidelity check — compares marginal variance of "
                    "predictions against ground truth per variable and region."
    )
    parser.add_argument("--predictions",  required=True, help="Path to predictions CSV (IAMC format)")
    parser.add_argument("--ground_truth", required=True, help="Path to ground truth CSV (IAMC format)")
    parser.add_argument("--run_id",       required=True, help="Run identifier")
    parser.add_argument("--out_dir",      default="results", help="Output directory (default: results/)")

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth))

    result = run(
        predictions=pred,
        ground_truth=gt,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    status = "PASSED" if result["passed"] else "FAILED"
    print(f"\nVariance fidelity check: {status}")
    if not result["summary"].empty:
        print("\nPer-variable summary (sorted by median variance ratio):")
        cols = ["Variable", "Median_Var_Ratio", "Median_CV_Ratio", "Pass_Rate", "Fail_Rate"]
        cols = [c for c in cols if c in result["summary"].columns]
        print(result["summary"][cols].to_string(index=False))
    print(f"\nFull results saved to {args.out_dir}/{args.run_id}/variance_fidelity/")


if __name__ == "__main__":
    main()
