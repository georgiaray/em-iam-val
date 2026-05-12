"""
Reconstruction error metrics check.

For emulators with a 1:1 correspondence between predicted and ground truth
scenarios, computes per-variable normalised RMSE (nRMSE), RMSE in canonical
units, MAE, R², and bias. Results are broken down by variable, region, and
year to support portrait-plot visualisation.

Normalisation: nRMSE = RMSE / mean(|ground_truth|) per variable-region pair,
making metrics dimensionless and comparable across variables with different
units and scales.

Requires ground truth. If ground truth is not provided the check is skipped.

Usage (standalone):
    python checks/reconstruction/error_metrics.py \\
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


# nRMSE normalisation is suppressed when a region's mean |ground truth| is
# below this value, preventing division by near-zero for variables whose
# regional values are negligibly small.
_NORM_FLOOR = 0.1


def _align(predictions: pd.DataFrame, ground_truth: pd.DataFrame) -> pd.DataFrame:
    """
    Inner-join predictions and ground truth on (Model, Scenario, Region,
    Year, Variable) so every row has a matched pred/gt pair.

    Returns a DataFrame with columns:
        Model, Scenario, Region, Year, Variable, Units,
        Value_pred, Value_gt
    """
    merge_keys = ["Model", "Scenario", "Region", "Year", "Variable"]

    pred = predictions[merge_keys + ["Value", "Units"]].rename(
        columns={"Value": "Value_pred"}
    )
    gt = ground_truth[merge_keys + ["Value"]].rename(
        columns={"Value": "Value_gt"}
    )

    dup_pred = pred.duplicated(subset=merge_keys).sum()
    dup_gt   = gt.duplicated(subset=merge_keys).sum()
    if dup_pred:
        print(f"  [error_metrics] WARNING: {dup_pred} duplicate key rows in predictions — keeping first.")
        pred = pred.drop_duplicates(subset=merge_keys)
    if dup_gt:
        print(f"  [error_metrics] WARNING: {dup_gt} duplicate key rows in ground truth — keeping first.")
        gt = gt.drop_duplicates(subset=merge_keys)

    merged = pred.merge(gt, on=merge_keys, how="inner")
    return merged


def compute_by_variable_region(aligned: pd.DataFrame) -> pd.DataFrame:
    """
    Compute error metrics aggregated over all years for each
    (Variable, Region) pair.

    Returns DataFrame with columns:
        Variable, Region, Units, N, RMSE, nRMSE, MAE, R2, Bias, GT_Mean
    """
    rows = []

    for (var, region), grp in aligned.groupby(["Variable", "Region"]):
        pred_vals = grp["Value_pred"].values
        gt_vals   = grp["Value_gt"].values
        units     = grp["Units"].iloc[0]

        mask = ~(np.isnan(pred_vals) | np.isnan(gt_vals))
        if mask.sum() < 2:
            continue

        p = pred_vals[mask]
        g = gt_vals[mask]

        residuals = p - g
        rmse      = np.sqrt(np.mean(residuals ** 2))
        mae       = np.mean(np.abs(residuals))
        bias      = np.mean(residuals)
        gt_mean   = np.mean(np.abs(g))

        nrmse = rmse / gt_mean if gt_mean > _NORM_FLOOR else np.nan
        nmae  = mae  / gt_mean if gt_mean > _NORM_FLOOR else np.nan
        nbias = bias / gt_mean if gt_mean > _NORM_FLOOR else np.nan

        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((g - np.mean(g)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

        rows.append({
            "Variable": var,
            "Region":   region,
            "Units":    units,
            "N":        int(mask.sum()),
            "RMSE":     rmse,
            "nRMSE":    nrmse,
            "MAE":      mae,
            "nMAE":     nmae,
            "R2":       r2,
            "Bias":     bias,
            "nBias":    nbias,
            "GT_Mean":  gt_mean,
        })

    return pd.DataFrame(rows).sort_values(["Variable", "Region"]).reset_index(drop=True)


def compute_by_variable_year(aligned: pd.DataFrame) -> pd.DataFrame:
    """
    Compute error metrics aggregated over all regions and scenarios for each
    (Variable, Year) pair — useful for diagnosing whether errors accumulate
    over the projection horizon (autoregressive drift).

    Returns DataFrame with columns:
        Variable, Year, Units, N, RMSE, nRMSE, MAE, R2, Bias, GT_Mean
    """
    rows = []

    for (var, year), grp in aligned.groupby(["Variable", "Year"]):
        pred_vals = grp["Value_pred"].values
        gt_vals   = grp["Value_gt"].values
        units     = grp["Units"].iloc[0]

        mask = ~(np.isnan(pred_vals) | np.isnan(gt_vals))
        if mask.sum() < 2:
            continue

        p = pred_vals[mask]
        g = gt_vals[mask]

        residuals = p - g
        rmse      = np.sqrt(np.mean(residuals ** 2))
        mae       = np.mean(np.abs(residuals))
        bias      = np.mean(residuals)
        gt_mean   = np.mean(np.abs(g))

        nrmse = rmse / gt_mean if gt_mean > _NORM_FLOOR else np.nan

        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((g - np.mean(g)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

        rows.append({
            "Variable": var,
            "Year":     int(year),
            "Units":    units,
            "N":        int(mask.sum()),
            "RMSE":     rmse,
            "nRMSE":    nrmse,
            "MAE":      mae,
            "R2":       r2,
            "Bias":     bias,
            "GT_Mean":  gt_mean,
        })

    return pd.DataFrame(rows).sort_values(["Variable", "Year"]).reset_index(drop=True)


def compute_portrait_matrix(by_var_region: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot nRMSE into a (Variable x Region) matrix suitable for a portrait
    plot. NaN where fewer than 2 matched pairs exist.

    Returns a wide DataFrame: index = Variable, columns = Region.
    """
    return by_var_region.pivot_table(
        index="Variable", columns="Region", values="nRMSE", aggfunc="first"
    )


def compute_overall_summary(by_var_region: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate across regions to give a single row per variable — the
    headline number for each output dimension.
    """
    rows = []
    for var, grp in by_var_region.groupby("Variable"):
        valid = grp.dropna(subset=["nRMSE"])
        mean_nrmse = (
            np.average(valid["nRMSE"], weights=valid["N"]) if not valid.empty else np.nan
        )
        rows.append({
            "Variable":       var,
            "Units":          grp["Units"].iloc[0],
            "N_Regions":      len(grp),
            "Mean_nRMSE":     mean_nrmse,
            "Max_nRMSE":      grp["nRMSE"].max(),
            "Mean_RMSE":      np.average(grp["RMSE"],  weights=grp["N"]),
            "Mean_MAE":       np.average(grp["MAE"],   weights=grp["N"]),
            "Mean_nMAE":      np.average(grp["nMAE"].fillna(0), weights=grp["N"]),
            "Median_R2":      grp["R2"].median(),  # median: robust to near-zero-variance regions
            "Mean_Bias":      np.average(grp["Bias"],  weights=grp["N"]),
            "Mean_nBias":     np.average(grp["nBias"].fillna(0), weights=grp["N"]),
        })
    return pd.DataFrame(rows).sort_values("Mean_nRMSE", ascending=False).reset_index(drop=True)


def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Run reconstruction error metrics on pre-loaded, pre-normalised DataFrames.

    Parameters
    ----------
    predictions  : canonical long DataFrame (already normalised)
    ground_truth : canonical long DataFrame (required — check is skipped if absent)
    out_dir      : root results directory
    run_id       : run identifier

    Returns
    -------
    dict with keys: check_name, passed, results, summary, unit_warnings, skipped
        results  — per (Variable, Region) error table
        summary  — per-variable headline metrics and portrait matrix
    """
    check_name = "error_metrics"

    if ground_truth is None:
        print("  [error_metrics] No ground truth provided — skipping reconstruction check.")
        return {
            "check_name": check_name,
            "passed":      True,
            "results":     pd.DataFrame(),
            "summary":     pd.DataFrame(),
            "unit_warnings": [],
            "skipped":     ["Ground truth required for reconstruction error metrics"],
        }

    # Align predictions and ground truth on matching scenario keys
    aligned = _align(predictions, ground_truth)

    n_matched = len(aligned)
    n_pred    = len(predictions)
    n_gt      = len(ground_truth)

    if n_matched == 0:
        msg = (
            "No matched (Model, Scenario, Region, Year, Variable) pairs found "
            "between predictions and ground truth. Check that scenario identifiers "
            "are consistent between the two files."
        )
        print(f"  [error_metrics] WARNING: {msg}")
        return {
            "check_name": check_name,
            "passed":      False,
            "results":     pd.DataFrame(),
            "summary":     pd.DataFrame(),
            "unit_warnings": [],
            "skipped":     [msg],
        }

    match_rate = n_matched / max(n_pred, n_gt)
    print(f"  [error_metrics] Matched {n_matched:,} rows "
          f"({match_rate:.1%} of larger file). "
          f"Pred rows: {n_pred:,}, GT rows: {n_gt:,}.")

    # Compute metrics
    by_var_region = compute_by_variable_region(aligned)
    by_var_year   = compute_by_variable_year(aligned)
    overall       = compute_overall_summary(by_var_region)
    portrait      = compute_portrait_matrix(by_var_region)

    # Check passes if mean nRMSE is below 1.0 for all variables
    # (nRMSE > 1.0 means the model error exceeds the typical magnitude of the
    # ground truth values — a conservative signal of poor reconstruction).
    worst_nrmse = overall["Mean_nRMSE"].max()
    passed = bool(worst_nrmse < 1.0) if not np.isnan(worst_nrmse) else True

    # Save outputs
    out_path = make_out_dir(out_dir, run_id, check_name)
    save_check_outputs(out_path, by_var_region, overall)

    by_var_year.to_csv(out_path / "by_variable_year.csv", index=False)
    portrait.to_csv(out_path / "portrait_matrix.csv")

    print(f"  [error_metrics] Results saved to {out_path}")
    print(f"  [error_metrics] Worst mean nRMSE: {worst_nrmse:.4f} "
          f"({'PASS' if passed else 'WARN — nRMSE > 1.0 for at least one variable'})")

    return {
        "check_name":    check_name,
        "passed":        passed,
        "results":       by_var_region,
        "summary":       overall,
        "unit_warnings": [],
        "skipped":       [],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruction error metrics (nRMSE, RMSE, MAE, R², bias) "
                    "for IAM emulation predictions with 1:1 ground truth correspondence."
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

    status = "PASSED" if result["passed"] else "WARN"
    print(f"\nError metrics check: {status}")
    if not result["summary"].empty:
        print("\nPer-variable summary (sorted by mean nRMSE, descending):")
        print(result["summary"][["Variable", "Mean_nRMSE", "Median_R2", "Mean_Bias"]].to_string(index=False))
    print(f"\nFull results saved to {args.out_dir}/{args.run_id}/error_metrics/")
    print("  results.csv         — per (Variable, Region) metrics")
    print("  summary.csv         — per-variable headline metrics")
    print("  by_variable_year.csv — per (Variable, Year) metrics")
    print("  portrait_matrix.csv  — nRMSE pivoted as Variable × Region")


if __name__ == "__main__":
    main()
