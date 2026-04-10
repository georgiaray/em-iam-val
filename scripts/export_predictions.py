"""
Export model predictions and AR6 ground truth in long (tidy) format.

Reads the trained model artifacts for a given run ID and writes two CSVs to
results/xgb/<run_id>/predictions/:

    predictions_long.csv   — inverse-transformed model predictions
    groundtruth_long.csv   — inverse-transformed AR6 test-set ground truth

Both files have columns:
    Model, Scenario, Region, Scenario_Category, Year, Variable, Value

These CSVs are consumed by the report generator (make_val_report.py) for
inter-variable correlation analysis and any other metric that needs access
to raw variable values rather than the aggregated check outputs.

Usage (standalone):
    python export_predictions.py --run_id xgb_04

Usage (called by run_all.py):
    Automatically invoked as part of run_all.py before report generation.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ml_iam_root = os.environ.get("ML_IAM_ROOT")
if not _ml_iam_root:
    _ml_iam_root = str(Path(__file__).resolve().parent.parent.parent / "ml-iam")
REPO_ROOT = Path(_ml_iam_root)
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

INDEX_COLS = ["Model", "Scenario", "Region", "Scenario_Category", "Year"]


def export_long(run_id: str) -> tuple[Path, Path]:
    """
    Load predictions and ground truth for *run_id*, inverse-transform, and
    save as long-format CSVs.  Returns (pred_path, gt_path).
    """
    from src.utils.run_store import RunStore
    from scripts.train_xgb import derive_splits

    print(f"\n{'='*60}")
    print(f"  Exporting predictions for run: {run_id}")
    print(f"{'='*60}")

    store  = RunStore(run_id)
    data   = store.load_processed_data()
    splits = derive_splits(data)

    test_data     = splits["test_data"].reset_index(drop=True)
    y_test_scaled = splits["y_test"]
    targets       = splits["targets"]
    y_scaler      = splits["y_scaler"]

    pred_bundle = store.load_predictions()
    preds       = y_scaler.inverse_transform(pred_bundle["preds"])
    y_test      = y_scaler.inverse_transform(y_test_scaled)

    def _to_long(values, label):
        import numpy as np
        idx  = test_data[INDEX_COLS].copy()
        wide = pd.DataFrame(values, columns=targets)
        combined = pd.concat([idx, wide], axis=1)
        long = combined.melt(
            id_vars=INDEX_COLS,
            value_vars=targets,
            var_name="Variable",
            value_name="Value",
        )
        print(f"  {label}: {len(long):,} rows  ({len(targets)} variables × {len(test_data):,} timesteps)")
        return long

    pred_long = _to_long(preds,   "Predictions")
    gt_long   = _to_long(y_test,  "Ground truth")

    out_dir = REPO_ROOT / "results" / "xgb" / run_id / "predictions"
    out_dir.mkdir(parents=True, exist_ok=True)

    pred_path = out_dir / "predictions_long.csv"
    gt_path   = out_dir / "groundtruth_long.csv"

    pred_long.to_csv(pred_path, index=False)
    gt_long.to_csv(gt_path,   index=False)

    print(f"\n  Saved:")
    print(f"    {pred_path}")
    print(f"    {gt_path}")
    print(f"{'='*60}\n")

    return pred_path, gt_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export model predictions and ground truth in long format"
    )
    parser.add_argument("--run_id", required=True, help="Run ID, e.g. xgb_04")
    args = parser.parse_args()
    export_long(args.run_id)


if __name__ == "__main__":
    main()
