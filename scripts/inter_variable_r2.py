"""
Inter-variable correlation R² check for ML-IAM validation.

For every pair of target variables, computes the squared Pearson correlation
(R²) across all (scenario, timestep) observations.  Comparing this matrix
between predictions/generated scenarios and the AR6 ground truth shows whether
the model preserves the same variable relationships as the training data.

This is the same metric used by Li et al. (2025) Figure 4 to validate that
synthetic scenarios maintain realistic co-variation between variables.  It is
model-agnostic: it applies equally to Shin's XGBoost predictions and Li's VAE /
CGAN / RCGAN generated outputs.

Outputs (written to results/xgb/<run_id>/inter_variable_r2/):
    report.txt              — text summary
    r2_matrix_pred.csv      — NxN R² matrix for predictions / generated outputs
    r2_matrix_gt.csv        — NxN R² matrix for AR6 ground truth
    r2_pairwise.csv         — long-form comparison: Var_A, Var_B, r2_pred,
                              r2_gt, delta (= r2_pred − r2_gt)

Usage (XGBoost pipeline):
    python inter_variable_r2.py --run_id xgb_04
    python inter_variable_r2.py --run_id xgb_04 --top_n 30

Programmatic API (used by run_li_all.py):
    from inter_variable_r2 import run_inter_variable_r2

    run_inter_variable_r2(
        pred_data, pred_values, pred_targets,   # generated / predicted
        gt_data,   gt_values,   gt_targets,     # AR6 ground truth
        run_id="li_vae_01",
        out_dir=Path("..."),
    )
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_ml_iam_root = os.environ.get("ML_IAM_ROOT")
if not _ml_iam_root:
    _ml_iam_root = str(Path(__file__).resolve().parent.parent.parent / "ml-iam")
REPO_ROOT = Path(_ml_iam_root)

sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Tee
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


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_r2_matrix(values: np.ndarray, targets: list[str]) -> pd.DataFrame:
    """
    Compute a symmetric NxN matrix of squared Pearson correlations (R²) between
    all pairs of target variables.

    Parameters
    ----------
    values : np.ndarray, shape (n_rows, n_targets)
        One row per (scenario, timestep) observation.
    targets : list[str]
        Variable names corresponding to columns of ``values``.

    Returns
    -------
    pd.DataFrame
        NxN symmetric DataFrame indexed and columned by target names.
        Diagonal entries are 1.0.  NaN where a variable has zero variance.
    """
    df = pd.DataFrame(values, columns=targets)
    # pearson correlation — handles NaN pairwise, zero-variance → NaN
    r = df.corr(method="pearson")
    r2 = r ** 2
    return r2


def build_pairwise_df(
    r2_pred: pd.DataFrame,
    r2_gt: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert two R² matrices to a long-form DataFrame of variable pairs.

    Only upper-triangle pairs (excluding the diagonal) are returned to avoid
    duplicates.

    Returns a DataFrame with columns:
        Var_A, Var_B, r2_pred, r2_gt, delta
    sorted by |delta| descending.
    """
    # Align to the intersection of variables present in both matrices
    shared = [v for v in r2_pred.index if v in r2_gt.index]
    r2_pred = r2_pred.loc[shared, shared]
    r2_gt   = r2_gt.loc[shared, shared]

    rows = []
    n = len(shared)
    for i in range(n):
        for j in range(i + 1, n):
            rows.append({
                "Var_A":   shared[i],
                "Var_B":   shared[j],
                "r2_pred": r2_pred.iloc[i, j],
                "r2_gt":   r2_gt.iloc[i, j],
            })

    pairwise = pd.DataFrame(rows)
    pairwise["delta"] = pairwise["r2_pred"] - pairwise["r2_gt"]
    pairwise["abs_delta"] = pairwise["delta"].abs()
    pairwise = pairwise.sort_values("abs_delta", ascending=False).reset_index(drop=True)
    return pairwise


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_overview(pairwise: pd.DataFrame, r2_pred: pd.DataFrame, r2_gt: pd.DataFrame):
    n_pairs = len(pairwise)
    mad     = pairwise["abs_delta"].mean()
    mean_pred = pairwise["r2_pred"].mean()
    mean_gt   = pairwise["r2_gt"].mean()

    # How many pairs have R² within 0.05 / 0.10 of each other
    within_05 = (pairwise["abs_delta"] <= 0.05).sum()
    within_10 = (pairwise["abs_delta"] <= 0.10).sum()

    print(f"\n{'='*60}")
    print("INTER-VARIABLE R² OVERVIEW")
    print(f"{'='*60}")
    print(f"  Variable pairs compared   : {n_pairs:,}")
    print(f"  Mean R² (predictions)     : {mean_pred:.4f}")
    print(f"  Mean R² (ground truth)    : {mean_gt:.4f}")
    print(f"  Mean |delta|              : {mad:.4f}")
    print(f"  Pairs within Δ ≤ 0.05     : {within_05:,}  ({100*within_05/n_pairs:.1f}%)")
    print(f"  Pairs within Δ ≤ 0.10     : {within_10:,}  ({100*within_10/n_pairs:.1f}%)")
    print(f"  Max |delta|               : {pairwise['abs_delta'].max():.4f}")


def report_top_pairs(pairwise: pd.DataFrame, n: int = 20):
    print(f"\n{'='*60}")
    print(f"TOP {n} PAIRS BY |Δ R²| (predictions vs ground truth)")
    print(f"{'='*60}")
    top = pairwise.head(n)
    if top.empty:
        print("  No pairs found.")
        return
    for _, row in top.iterrows():
        direction = "pred>gt" if row["delta"] > 0 else "pred<gt"
        pred_str = f"{row['r2_pred']:.3f}" if not np.isnan(row["r2_pred"]) else "  NaN"
        gt_str   = f"{row['r2_gt']:.3f}"   if not np.isnan(row["r2_gt"])   else "  NaN"
        print(
            f"  {row['Var_A']:<45}  ×  {row['Var_B']:<45}  "
            f"pred={pred_str}  gt={gt_str}  Δ={row['delta']:+.3f}  [{direction}]"
        )


def report_by_variable(pairwise: pd.DataFrame):
    """Mean |delta| aggregated per variable (across all its pairs)."""
    print(f"\n{'='*60}")
    print("MEAN |Δ R²| BY VARIABLE  (across all pairs for that variable)")
    print(f"{'='*60}")

    records = []
    all_vars = sorted(set(pairwise["Var_A"].tolist() + pairwise["Var_B"].tolist()))
    for var in all_vars:
        mask = (pairwise["Var_A"] == var) | (pairwise["Var_B"] == var)
        sub  = pairwise[mask]
        records.append({
            "Variable":      var,
            "n_pairs":       len(sub),
            "mean_abs_delta": sub["abs_delta"].mean(),
            "max_abs_delta":  sub["abs_delta"].max(),
        })

    var_df = (
        pd.DataFrame(records)
        .sort_values("mean_abs_delta", ascending=False)
        .reset_index(drop=True)
    )
    for _, row in var_df.iterrows():
        print(
            f"  {row['Variable']:<50}  "
            f"mean|Δ|={row['mean_abs_delta']:.4f}  "
            f"max|Δ|={row['max_abs_delta']:.4f}  "
            f"({int(row['n_pairs'])} pairs)"
        )


# ---------------------------------------------------------------------------
# Public programmatic API (used by run_li_all.py)
# ---------------------------------------------------------------------------

def run_inter_variable_r2(
    pred_data:    pd.DataFrame,
    pred_values:  np.ndarray,
    pred_targets: list[str],
    gt_data:      pd.DataFrame,
    gt_values:    np.ndarray,
    gt_targets:   list[str],
    run_id:       str,
    out_dir:      Path,
    top_n:        int = 20,
    label_pred:   str = "predictions",
    label_gt:     str = "ground truth",
) -> bool:
    """
    Compute inter-variable R² comparison and write results to ``out_dir``.

    Parameters
    ----------
    pred_data, pred_values, pred_targets
        Canonical em-iam-val format for the model predictions / generated outputs.
    gt_data, gt_values, gt_targets
        Canonical em-iam-val format for the AR6 ground truth.
    run_id : str
        Used only for display in the report header.
    out_dir : Path
        Directory to write outputs into (created if needed).
    top_n : int
        Number of worst pairs to print in the text report.
    label_pred, label_gt : str
        Display labels for predictions and ground truth in the report.

    Returns
    -------
    bool : True if completed without error, False otherwise.
    """
    import traceback
    out_dir.mkdir(parents=True, exist_ok=True)
    tee = _Tee(out_dir / "report.txt")
    sys.stdout = tee
    try:
        print("=" * 60)
        print("  INTER-VARIABLE R² CHECK")
        print(f"  Run ID : {run_id}")
        print(f"  Pred   : {label_pred}  ({len(pred_targets)} variables, "
              f"{len(pred_data):,} rows)")
        print(f"  GT     : {label_gt}    ({len(gt_targets)} variables, "
              f"{len(gt_data):,} rows)")
        print("=" * 60)

        # Restrict to the intersection of variables present in both
        shared = sorted(set(pred_targets) & set(gt_targets))
        if len(shared) < 2:
            print(f"\n  [SKIP] Only {len(shared)} variable(s) in common between "
                  f"predictions and ground truth — need at least 2.")
            return True

        print(f"\n  Variables in both datasets: {len(shared)} / "
              f"max({len(pred_targets)}, {len(gt_targets)})")
        if len(shared) < max(len(pred_targets), len(gt_targets)):
            only_pred = sorted(set(pred_targets) - set(gt_targets))
            only_gt   = sorted(set(gt_targets)   - set(pred_targets))
            if only_pred:
                print(f"  Only in predictions : {only_pred}")
            if only_gt:
                print(f"  Only in ground truth: {only_gt}")

        pred_idx = [pred_targets.index(v) for v in shared]
        gt_idx   = [gt_targets.index(v)   for v in shared]

        pred_sub = pred_values[:, pred_idx]
        gt_sub   = gt_values[:,   gt_idx]

        print("\n  Computing R² matrices...")
        r2_pred = compute_r2_matrix(pred_sub, shared)
        r2_gt   = compute_r2_matrix(gt_sub,   shared)

        pairwise = build_pairwise_df(r2_pred, r2_gt)

        report_overview(pairwise, r2_pred, r2_gt)
        report_top_pairs(pairwise, n=top_n)
        report_by_variable(pairwise)

        # Save
        r2_pred.to_csv(out_dir / "r2_matrix_pred.csv")
        r2_gt.to_csv(out_dir / "r2_matrix_gt.csv")
        pairwise.to_csv(out_dir / "r2_pairwise.csv", index=False)

        print(f"\n{'='*60}")
        print("Results saved to:")
        print(f"  {out_dir / 'report.txt'}")
        print(f"  {out_dir / 'r2_matrix_pred.csv'}")
        print(f"  {out_dir / 'r2_matrix_gt.csv'}")
        print(f"  {out_dir / 'r2_pairwise.csv'}")
        print(f"{'='*60}\n")
        return True

    except Exception:
        import traceback as tb
        tb.print_exc()
        return False
    finally:
        tee.close()


# ---------------------------------------------------------------------------
# XGBoost pipeline: load via RunStore
# ---------------------------------------------------------------------------

def load_predictions(run_id: str):
    from src.utils.run_store import RunStore
    from scripts.train_xgb import derive_splits

    print(f"\n{'='*60}")
    print(f"Loading artifacts for run: {run_id}")
    print(f"{'='*60}")

    store  = RunStore(run_id)
    data   = store.load_processed_data()
    splits = derive_splits(data)

    test_data     = splits["test_data"]
    y_test_scaled = splits["y_test"]
    targets       = splits["targets"]
    y_scaler      = splits["y_scaler"]

    pred_bundle = store.load_predictions()
    preds  = y_scaler.inverse_transform(pred_bundle["preds"])
    y_test = y_scaler.inverse_transform(y_test_scaled)

    print(f"  Targets: {len(targets)} variables")
    return test_data, preds, y_test, targets


# ---------------------------------------------------------------------------
# Main (XGBoost / run_id based)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Inter-variable correlation R² check for ML-IAM predictions"
    )
    parser.add_argument("--run_id", required=True, help="Run ID, e.g. xgb_04")
    parser.add_argument(
        "--top_n", type=int, default=20,
        help="Number of worst variable pairs to show in the report (default: 20)"
    )
    args = parser.parse_args()

    test_data, preds, y_test, targets = load_predictions(args.run_id)

    out_dir = REPO_ROOT / "results" / "xgb" / args.run_id / "inter_variable_r2"

    success = run_inter_variable_r2(
        pred_data=test_data,
        pred_values=preds,
        pred_targets=targets,
        gt_data=test_data,
        gt_values=y_test,
        gt_targets=targets,
        run_id=args.run_id,
        out_dir=out_dir,
        top_n=args.top_n,
        label_pred="XGBoost predictions",
        label_gt="AR6 ground truth",
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
