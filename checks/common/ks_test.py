"""
Kolmogorov-Smirnov distributional test with Bonferroni correction.

For each output variable, performs a two-sample KS test comparing the
distribution of emulator predictions against the IAM ground truth. Tests
whether the two samples come from the same distribution — capturing
differences in shape, skewness, and modality that mean/variance checks miss.

Bonferroni correction is applied across all variables to control the
familywise error rate (probability of at least one false positive).

The KS statistic D is the maximum absolute difference between the two
empirical CDFs and serves as its own effect size (0 = identical, 1 = no
overlap). It is always reported alongside the corrected p-value so that
statistically significant but practically negligible differences can be
identified.

Requires ground truth. Applicable to both reconstruction and generative runs
— no pairing between scenarios is required.

Usage (standalone):
    python checks/common/ks_test.py \\
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
from scipy.stats import ks_2samp

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import (
    load_csv, normalize_to_canonical,
    make_out_dir, save_check_outputs,
)

# Significance level before Bonferroni correction
_ALPHA = 0.05

# Minimum number of samples required to run the KS test for a variable
_MIN_SAMPLES = 10

# D statistic thresholds for effect size labelling
_D_SMALL  = 0.1
_D_MEDIUM = 0.3


def _effect_size_label(d: float) -> str:
    if d < _D_SMALL:
        return "negligible"
    if d < _D_MEDIUM:
        return "small"
    return "large"


def run_ks_tests(
    predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
    alpha: float = _ALPHA,
) -> pd.DataFrame:
    """
    Run two-sample KS test per variable, pooling across all regions and years.

    Bonferroni correction: adjusted threshold = alpha / n_tests, where
    n_tests is the number of variables successfully tested.

    Returns DataFrame with columns:
        Variable, Units, N_pred, N_gt,
        KS_stat, P_value, P_value_corrected, Alpha_corrected,
        Effect_size, Status
    """
    variables = sorted(
        set(predictions["Variable"].unique()) & set(ground_truth["Variable"].unique())
    )

    rows = []
    for var in variables:
        p_vals = predictions[predictions["Variable"] == var]["Value"].dropna().values
        g_vals = ground_truth[ground_truth["Variable"] == var]["Value"].dropna().values
        units  = predictions[predictions["Variable"] == var]["Units"].iloc[0] \
                 if len(predictions[predictions["Variable"] == var]) > 0 else "unknown"

        if len(p_vals) < _MIN_SAMPLES or len(g_vals) < _MIN_SAMPLES:
            continue

        stat, pval = ks_2samp(p_vals, g_vals)
        rows.append({
            "Variable": var,
            "Units":    units,
            "N_pred":   len(p_vals),
            "N_gt":     len(g_vals),
            "KS_stat":  round(stat, 4),
            "P_value":  pval,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Bonferroni correction
    n_tests = len(df)
    alpha_corrected = alpha / n_tests
    df["P_value_corrected"] = (df["P_value"] * n_tests).clip(upper=1.0)
    df["Alpha_corrected"]   = round(alpha_corrected, 6)
    df["Effect_size"]       = df["KS_stat"].apply(_effect_size_label)
    df["Status"]            = df["P_value_corrected"].apply(
        lambda p: "PASS" if p >= alpha else "FAIL"
    )

    return df.sort_values("KS_stat", ascending=False).reset_index(drop=True)


def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    alpha: float = _ALPHA,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Run KS test with Bonferroni correction.

    Parameters
    ----------
    predictions  : canonical long DataFrame (already normalised)
    ground_truth : canonical long DataFrame (required — check is skipped if absent)
    alpha        : significance level before Bonferroni correction (default 0.05)
    out_dir      : root results directory
    run_id       : run identifier
    """
    check_name = "ks_test"

    if ground_truth is None:
        print("  [ks_test] No ground truth provided — skipping.")
        return {
            "check_name":    check_name,
            "passed":        True,
            "results":       pd.DataFrame(),
            "summary":       pd.DataFrame(),
            "unit_warnings": [],
            "skipped":       ["Ground truth required for KS test"],
        }

    results = run_ks_tests(predictions, ground_truth, alpha)

    if results.empty:
        msg = "No variables with sufficient samples found."
        print(f"  [ks_test] WARNING: {msg}")
        return {
            "check_name":    check_name,
            "passed":        True,
            "results":       pd.DataFrame(),
            "summary":       pd.DataFrame(),
            "unit_warnings": [],
            "skipped":       [msg],
        }

    n_tests  = len(results)
    n_fail   = (results["Status"] == "FAIL").sum()
    n_pass   = (results["Status"] == "PASS").sum()
    passed   = n_fail == 0
    mean_d   = results["KS_stat"].mean()

    print(f"  [ks_test] {n_tests} variables tested "
          f"(Bonferroni α = {alpha}/{n_tests} = {alpha/n_tests:.4f})")
    print(f"  [ks_test] PASS: {n_pass}  FAIL: {n_fail}  "
          f"Mean D statistic: {mean_d:.4f}")

    # Summary: one row per variable with key metrics
    summary = results[["Variable", "Units", "N_pred", "N_gt",
                        "KS_stat", "P_value_corrected", "Effect_size", "Status"]].copy()

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
        description="KS test with Bonferroni correction — compares emulator "
                    "output distributions against IAM ground truth per variable."
    )
    parser.add_argument("--predictions",  required=True)
    parser.add_argument("--ground_truth", required=True)
    parser.add_argument("--run_id",       required=True)
    parser.add_argument("--out_dir",      default="results")
    parser.add_argument("--alpha", type=float, default=_ALPHA,
                        help=f"Significance level before Bonferroni correction "
                             f"(default: {_ALPHA})")

    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth))

    result = run(
        predictions=pred,
        ground_truth=gt,
        alpha=args.alpha,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    status = "PASSED" if result["passed"] else "FAILED"
    print(f"\nKS test: {status}")
    if not result["summary"].empty:
        print("\nPer-variable results (sorted by D statistic, descending):")
        print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
