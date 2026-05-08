"""
Inter-variable correlation check.

Computes Pearson r² correlation matrices between all predicted variables at
key years (2030, 2050, 2100) and compares against the ground truth correlation
structure. A well-calibrated emulator should preserve the inter-variable
relationships present in the parent simulation.

Belongs to the 'Variance and covariance metrics' validation family.

Usage (standalone):
    python checks/inter_variable_correlation.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
        --ground_truth adapted-data/shin_01_ground_truth.csv \\
        --run_id shin_01

    python checks/inter_variable_correlation.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
        --run_id shin_01 --years 2030 2050 2100
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import (
    CANONICAL_COLUMNS, IDX,
    load_csv, normalize_to_canonical,
    make_out_dir, _Tee,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_YEARS = [2030, 2050, 2100]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_correlation_matrix(long: pd.DataFrame, year: int) -> Optional[pd.DataFrame]:
    """
    Compute Pearson r² correlation matrix across all variables at a given year.

    Pivots to wide format (one row per scenario × region), then computes
    pairwise Pearson r and squares it. Returns None if fewer than 2 variables
    have data at this year.
    """
    sub = long[long["Year"] == year]
    if sub.empty:
        return None

    wide = sub.pivot_table(
        index=["Model", "Scenario", "Region"],
        columns="Variable",
        values="Value",
        aggfunc="first",
    ).dropna(axis=1, how="all")

    if wide.shape[1] < 2:
        return None

    return wide.corr(method="pearson") ** 2


def compare_matrices(
    pred_mat: pd.DataFrame,
    gt_mat: pd.DataFrame,
) -> dict:
    """
    Compare prediction and ground truth r² matrices.

    Returns a dict with:
        common_vars      : list of variables present in both matrices
        pred_aligned     : predictions matrix restricted to common vars
        gt_aligned       : ground truth matrix restricted to common vars
        diff             : signed difference (pred − gt)
        mean_abs_diff    : mean |Δr²| over off-diagonal upper-triangle pairs
    """
    common = [v for v in pred_mat.columns if v in gt_mat.columns]
    pred_aligned = pred_mat.loc[common, common]
    gt_aligned   = gt_mat.loc[common, common]
    diff         = pred_aligned - gt_aligned

    mask = np.triu(np.ones(diff.shape, dtype=bool), k=1)
    mean_abs_diff = float(np.abs(diff.values[mask]).mean()) if mask.any() else float("nan")

    return {
        "common_vars":   common,
        "pred_aligned":  pred_aligned,
        "gt_aligned":    gt_aligned,
        "diff":          diff,
        "mean_abs_diff": mean_abs_diff,
    }


def _short_label(variable: str) -> str:
    """Last segment of an IAMC variable name, for compact axis labels."""
    return variable.split("|")[-1].strip()


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def _annotated_heatmap(ax, mat: pd.DataFrame, title: str, vmin: float = 0,
                        vmax: float = 1, cmap: str = "RdYlGn",
                        fmt: str = "{:.2f}") -> None:
    labels = [_short_label(v) for v in mat.columns]
    ax.imshow(mat.values, vmin=vmin, vmax=vmax, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=6)
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = mat.values[i, j]
            if not np.isnan(val):
                text_color = "black" if 0.2 < abs(val) < 0.8 else "white"
                ax.text(j, i, fmt.format(val), ha="center", va="center",
                        fontsize=5.5, color=text_color)


def make_figure(year: int, pred_mat: pd.DataFrame,
                gt_mat: Optional[pd.DataFrame],
                comparison: Optional[dict]) -> plt.Figure:
    """
    Build a comparison figure for one year.
    With ground truth: 3 panels (pred, GT, diff).
    Without ground truth: 1 panel (pred only).
    """
    n_panels = 3 if gt_mat is not None else 1
    n_vars   = len(pred_mat)
    fig, axes = plt.subplots(
        1, n_panels,
        figsize=(5 * n_panels, max(4, n_vars * 0.55)),
    )
    if n_panels == 1:
        axes = [axes]

    im = axes[0].imshow(pred_mat.values, vmin=0, vmax=1,
                        cmap="RdYlGn", aspect="auto")
    _annotated_heatmap(axes[0], pred_mat, f"Predictions — {year}")
    fig.colorbar(im, ax=axes[0], fraction=0.046, pad=0.04)

    if gt_mat is not None and comparison is not None:
        c = comparison
        _annotated_heatmap(axes[1], c["gt_aligned"], f"Ground Truth — {year}")

        diff_df = c["diff"]
        axes[2].imshow(diff_df.values, vmin=-1, vmax=1, cmap="RdBu_r", aspect="auto")
        diff_labels = [_short_label(v) for v in diff_df.columns]
        axes[2].set_xticks(range(len(diff_labels)))
        axes[2].set_yticks(range(len(diff_labels)))
        axes[2].set_xticklabels(diff_labels, rotation=45, ha="right", fontsize=7)
        axes[2].set_yticklabels(diff_labels, fontsize=7)
        axes[2].set_title(f"Difference (Pred − GT) — {year}",
                          fontsize=10, fontweight="bold", pad=6)
        for i in range(len(diff_labels)):
            for j in range(len(diff_labels)):
                val = diff_df.values[i, j]
                if not np.isnan(val):
                    axes[2].text(j, i, f"{val:+.2f}", ha="center", va="center",
                                 fontsize=5.5, color="black")
        im2 = axes[2].images[0]
        fig.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)

    fig.suptitle(f"Inter-variable Pearson r² — {year}",
                 fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    years: list = None,
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Compute inter-variable Pearson r² matrices and compare against ground truth.

    Parameters
    ----------
    predictions  : canonical long DataFrame
    ground_truth : canonical long DataFrame (optional)
    years        : list of years to evaluate (default [2030, 2050, 2100])
    out_dir      : root results directory
    run_id       : run identifier

    Returns
    -------
    dict with keys: check_name, passed, results, summary, unit_warnings, skipped
    """
    years = years or DEFAULT_YEARS
    check_name = "inter_variable_correlation"

    out_path = make_out_dir(out_dir, run_id, check_name)
    fig_dir  = out_path / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    tee = _Tee(out_path / "report.txt")
    sys.stdout = tee

    try:
        print(f"\n{'='*60}")
        print(f"  INTER-VARIABLE CORRELATION CHECK")
        print(f"  Run ID : {run_id}")
        print(f"  Years  : {years}")
        print(f"{'='*60}")

        predictions  = normalize_to_canonical(predictions)
        if ground_truth is not None:
            ground_truth = normalize_to_canonical(ground_truth)

        available_years = sorted(set(predictions["Year"].unique()) & set(years))
        if not available_years:
            print(f"\n  No data at any of {years} — check skipped.")
            return {
                "check_name":   check_name,
                "passed":       True,
                "results":      pd.DataFrame(),
                "summary":      pd.DataFrame(),
                "unit_warnings": [],
                "skipped":      [f"No data at years {years}"],
            }

        summary_rows = []
        figures      = []

        for year in available_years:
            pred_mat = compute_correlation_matrix(predictions, year)
            gt_mat   = compute_correlation_matrix(ground_truth, year) \
                       if ground_truth is not None else None

            if pred_mat is None:
                print(f"\n  {year}: no data for predictions — skipping.")
                continue

            print(f"\n  {year}: {len(pred_mat)} variables in predictions matrix.")

            comparison = None
            if gt_mat is not None:
                comparison = compare_matrices(pred_mat, gt_mat)
                mad = comparison["mean_abs_diff"]
                print(f"         Mean |Δr²| (off-diagonal): {mad:.4f}")
                summary_rows.append({
                    "Year":                  year,
                    "N_variables":           len(comparison["common_vars"]),
                    "Mean_abs_diff_r2":      round(mad, 4),
                })
            else:
                print(f"         No ground truth — reporting predictions only.")
                summary_rows.append({
                    "Year":       year,
                    "N_variables": len(pred_mat),
                    "Mean_abs_diff_r2": None,
                })

            # Save correlation matrices as CSVs
            pred_mat.to_csv(out_path / f"pred_corr_{year}.csv")
            if gt_mat is not None:
                gt_mat.to_csv(out_path / f"gt_corr_{year}.csv")
                if comparison:
                    comparison["diff"].to_csv(out_path / f"diff_corr_{year}.csv")

            # Make figure
            fig = make_figure(year, pred_mat, gt_mat, comparison)
            fig_path = fig_dir / f"correlations_{year}.png"
            fig.savefig(fig_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            figures.append(str(fig_path))
            print(f"         Figure saved: {fig_path.name}")

        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_csv(out_path / "summary.csv", index=False)

        print(f"\n{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}")
        print(summary_df.to_string(index=False))
        print(f"\n  Results saved to: {out_path}")

        passed = True  # correlation check is informational — no hard pass/fail threshold
        return {
            "check_name":    check_name,
            "passed":        passed,
            "results":       summary_df,
            "summary":       summary_df,
            "unit_warnings": [],
            "skipped":       [],
            "figures":       figures,
        }

    finally:
        tee.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Inter-variable correlation check for IAM emulator predictions"
    )
    parser.add_argument("--predictions",  required=True,
                        help="Path to canonical predictions CSV")
    parser.add_argument("--ground_truth", default=None,
                        help="Path to canonical ground truth CSV (optional)")
    parser.add_argument("--run_id",       required=True,
                        help="Run identifier, e.g. shin_01")
    parser.add_argument("--out_dir",      default="results",
                        help="Root results directory (default: results/)")
    parser.add_argument("--years",        nargs="+", type=int,
                        default=DEFAULT_YEARS,
                        help=f"Years to evaluate (default: {DEFAULT_YEARS})")
    args = parser.parse_args()

    pred = load_csv(args.predictions)
    gt   = load_csv(args.ground_truth) if args.ground_truth else None

    result = run(
        predictions=pred,
        ground_truth=gt,
        years=args.years,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )

    status = "PASSED" if result["passed"] else "FAILED"
    print(f"\n  [{status}] {result['check_name']}")


if __name__ == "__main__":
    main()
