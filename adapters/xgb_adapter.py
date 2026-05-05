"""
XGBoost (Shin et al. / ml-iam) adapter.

Loads model artifacts from the ml-iam RunStore and writes canonical CSVs
for use by the em-iam-val validation framework.

Usage:
    python adapters/xgb_adapter.py --run_id xgb_04 --out_dir adapted-data/

Outputs:
    adapted-data/xgb_04_predictions.csv
    adapted-data/xgb_04_ground_truth.csv

The Units column is populated from ml-iam's UNITS_BY_OUTPUT config.
Note: the ml-iam config may contain unit labeling errors (e.g. Secondary
Energy variables declared as EJ/yr but stored as PJ/yr). This adapter
faithfully reports what the config declares. The framework's unit
plausibility check will flag values that appear implausible.
"""

import sys
import os
from pathlib import Path
import argparse
import pandas as pd
import numpy as np


def build_canonical_long(test_data, values_array, targets, units_map):
    """
    Build canonical long-format DataFrame.

    Parameters
    ----------
    test_data     : DataFrame with index columns including Model, Scenario,
                    Region, Scenario_Category, Year
    values_array  : numpy array of shape (n_rows, n_targets) — inverse-scaled
    targets       : list of variable names aligned to values_array columns
    units_map     : dict mapping variable name -> unit string

    Returns
    -------
    Long-format DataFrame with columns:
        Model, Scenario, Region, Scenario_Category, Year, Variable, Value, Units
    """
    index_cols = ["Model", "Scenario", "Region", "Scenario_Category", "Year"]
    idx  = test_data[index_cols].reset_index(drop=True)
    wide = pd.DataFrame(values_array, columns=targets)
    combined = pd.concat([idx, wide], axis=1)

    long = combined.melt(
        id_vars=index_cols,
        value_vars=targets,
        var_name="Variable",
        value_name="Value",
    )
    long["Units"] = long["Variable"].map(units_map).fillna("unknown")
    return long[["Model", "Scenario", "Region", "Scenario_Category",
                 "Year", "Variable", "Value", "Units"]]


def run(run_id, out_dir="adapted-data", ml_iam_root=None):
    """
    Run XGBoost adapter.

    Args:
        run_id: ml-iam run identifier
        out_dir: Output directory for canonical CSVs
        ml_iam_root: Path to ml-iam repository (default: ../ml-iam from cwd)

    Returns:
        dict with summary info
    """
    # Locate ml-iam
    if ml_iam_root is None:
        ml_iam_root = os.environ.get("ML_IAM_ROOT", "../ml-iam")

    ml_iam_path = Path(ml_iam_root).resolve()
    if not ml_iam_path.exists():
        raise FileNotFoundError(f"ml-iam not found at {ml_iam_path}")

    print(f"Using ml-iam at {ml_iam_path}")

    # Add ml-iam to path
    sys.path.insert(0, str(ml_iam_path))

    # Import ml-iam components
    try:
        from src.utils.run_store import RunStore
        from scripts.train_xgb import derive_splits
        from configs.data import UNITS_BY_OUTPUT
    except ImportError as e:
        raise ImportError(f"Could not import ml-iam components: {e}")

    # Load data via RunStore (ml-iam API)
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

    print(f"  Targets : {len(targets)} variables")
    print(f"  Rows    : {len(test_data):,}")

    # Build canonical DataFrames
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    predictions_df  = build_canonical_long(test_data, preds,  targets, UNITS_BY_OUTPUT)
    ground_truth_df = build_canonical_long(test_data, y_test, targets, UNITS_BY_OUTPUT)

    pred_path = out_path / f"{run_id}_predictions.csv"
    gt_path   = out_path / f"{run_id}_ground_truth.csv"

    predictions_df.to_csv(pred_path,  index=False)
    ground_truth_df.to_csv(gt_path,   index=False)
    print(f"\n  Saved: {pred_path}")
    print(f"  Saved: {gt_path}")

    # Print summary
    print("\nAdapter Summary:")
    print(f"  Predictions: {len(predictions_df)} rows, {predictions_df['Variable'].nunique()} variables")
    print(f"  Units used: {set(predictions_df['Units'].unique())}")

    print(f"\n  Variables : {', '.join(targets)}")
    print(f"  Units     : {dict(zip(targets, [UNITS_BY_OUTPUT.get(t, 'unknown') for t in targets]))}")

    return {
        "run_id":             run_id,
        "predictions_path":   str(pred_path),
        "ground_truth_path":  str(gt_path),
        "n_rows":             len(predictions_df),
        "n_variables":        len(targets),
    }


def main():
    parser = argparse.ArgumentParser(
        description="XGBoost adapter for em-iam-val validation framework"
    )
    parser.add_argument("--run_id", required=True, help="ml-iam run identifier (required)")
    parser.add_argument("--out_dir", default="adapted-data", help="Output directory (default: adapted-data/)")
    parser.add_argument("--ml_iam_root", help="Path to ml-iam repository (default: env ML_IAM_ROOT or ../ml-iam)")

    args = parser.parse_args()

    result = run(args.run_id, args.out_dir, args.ml_iam_root)

    print("\nAdapter completed successfully.")


if __name__ == "__main__":
    main()
