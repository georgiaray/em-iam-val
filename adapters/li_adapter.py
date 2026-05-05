"""
Li et al. (Deep-IAM) adapter.

Loads Li et al. generated outputs and AR6 ground truth, writes canonical CSVs
for use by the em-iam-val validation framework.

Usage:
    python adapters/li_adapter.py --model vae --run_id li_vae_01 --out_dir adapted-data/

Outputs:
    adapted-data/li_vae_01_predictions.csv
    adapted-data/li_vae_01_ground_truth.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE     = Path(__file__).resolve().parent
_LI_ROOT  = _HERE.parent.parent / "Li-emulation" / "Policy-Generative Model"

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

LI_UNITS: dict[str, str] = {
    "Emissions|Kyoto Gases":    "MtCO2eq/yr",
    "Carbon Sequestration|CCS": "MtCO2/yr",
}
DEFAULT_ENERGY_UNIT = "EJ/yr"


def _get_unit(variable: str) -> str:
    if variable in LI_UNITS:
        return LI_UNITS[variable]
    if any(p in variable for p in ("Primary Energy", "Secondary Energy", "Final Energy")):
        return DEFAULT_ENERGY_UNIT
    if "Emissions" in variable:
        if "CO2" in variable:
            return "MtCO2/yr"
        if "CH4" in variable:
            return "MtCH4/yr"
        if "N2O" in variable:
            return "MtN2O/yr"
    return "unknown"


# ---------------------------------------------------------------------------
# Generated output loading
# ---------------------------------------------------------------------------

_DEFAULT_PATHS: dict[str, tuple[str, str]] = {
    "vae":   ("gen_data_vae.npy",   "gen_labels_vae.npy"),
    "cgan":  ("gen_data_cgan.npy",  "gen_labels_cgan.npy"),
    "rcgan": ("gen_data_rcgan.npy", "gen_labels_rcgan.npy"),
}

FEATURE_NAMES: list[str] = [
    "Carbon Sequestration|CCS",
    "Final Energy|Liquids",
    "Primary Energy|Gas",
    "Primary Energy|Oil",
    "Primary Energy|Coal",
    "Secondary Energy|Electricity|Nuclear",
    "Secondary Energy|Electricity|Hydro",
    "Secondary Energy|Electricity",
    "Secondary Energy|Electricity|Oil",
    "Secondary Energy|Electricity|Coal",
    "Secondary Energy|Electricity|Gas",
    "Secondary Energy|Electricity|Wind",
    "Secondary Energy|Electricity|Solar",
    "Secondary Energy|Electricity|Biomass",
    "Secondary Energy|Electricity|Geothermal",
    "Emissions|Kyoto Gases",
]

TIMESTEPS: list[int] = list(range(2020, 2110, 10))

CATEGORY_MAP: dict[int, str] = {0: "C1234", 1: "C56", 2: "C78"}


def _load_generated(model: str, data_path=None, labels_path=None):
    model_key = model.lower()
    default_data, default_labels = _DEFAULT_PATHS[model_key]
    data_file   = Path(data_path)   if data_path   else _LI_ROOT / default_data
    labels_file = Path(labels_path) if labels_path else _LI_ROOT / default_labels

    for p in (data_file, labels_file):
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")

    gen_data   = np.load(data_file,   allow_pickle=False)
    gen_labels = np.load(labels_file, allow_pickle=False)

    print(f"  gen_data shape  : {gen_data.shape}")
    print(f"  gen_labels shape: {gen_labels.shape}")

    n_scenarios, n_timesteps, n_features = gen_data.shape
    targets = FEATURE_NAMES[:n_features]

    model_label  = model.upper()
    scenario_ids = [f"gen_{i:05d}" for i in range(n_scenarios)]

    records = []
    for i in range(n_scenarios):
        cat = CATEGORY_MAP.get(int(gen_labels[i]), f"C{int(gen_labels[i])}")
        for t, year in enumerate(TIMESTEPS):
            records.append({
                "Model":             model_label,
                "Scenario":          scenario_ids[i],
                "Region":            "World",
                "Scenario_Category": cat,
                "Year":              year,
                "_si":               i,
                "_ti":               t,
            })

    index_df = pd.DataFrame(records)
    si = index_df["_si"].to_numpy()
    ti = index_df["_ti"].to_numpy()
    values = gen_data[si, ti, :].astype(float)
    test_data = index_df.drop(columns=["_si", "_ti"])

    print(f"  {n_scenarios:,} scenarios × {n_timesteps} timesteps → {len(test_data):,} rows | {len(targets)} variables")
    return test_data, values, targets


# ---------------------------------------------------------------------------
# Ground truth loading
# ---------------------------------------------------------------------------

VARIABLE_MAP: dict[str, str] = {
    "PrimaryEnergy_Coal":                     "Primary Energy|Coal",
    "Primary Energy_Oil":                     "Primary Energy|Oil",
    "SecondaryEnergy_Electricity":            "Secondary Energy|Electricity",
    "SecondaryEnergy_Electricity_Biomass":    "Secondary Energy|Electricity|Biomass",
    "SecondaryEnergy_Electricity_Coal":       "Secondary Energy|Electricity|Coal",
    "SecondaryEnergy_Electricity_Gas":        "Secondary Energy|Electricity|Gas",
    "SecondaryEnergy_Electricity_Geothermal": "Secondary Energy|Electricity|Geothermal",
    "SecondaryEnergy_Electricity_Hydro":      "Secondary Energy|Electricity|Hydro",
    "SecondaryEnergy_Electricity_Nuclear":    "Secondary Energy|Electricity|Nuclear",
    "SecondaryEnergy_Electricity_Oil":        "Secondary Energy|Electricity|Oil",
    "SecondaryEnergy_Electricity_Solar":      "Secondary Energy|Electricity|Solar",
    "SecondaryEnergy_Electricity_Wind":       "Secondary Energy|Electricity|Wind",
    "Final Energy_Liquids":                   "Final Energy|Liquids",
    "Final Energy_Solids":                    "Final Energy|Solids",
    "Secondary Energy_Gases":                 "Secondary Energy|Gases",
    "Kyoto Gases":                            "Emissions|Kyoto Gases",
    "Carbon_Sequestration_CCS_imputed":       "Carbon Sequestration|CCS",
    "PrimaryEnergy_imputed":                  "Primary Energy",
    "Primary Energy_Gas":                     "Primary Energy|Gas",
}

YEAR_COLS = [str(y) for y in range(2010, 2110, 10)]
FAILED_VETTING = {"failed-vetting", "no-climate-assessment"}


def _load_ground_truth(li_path=None, drop_failed=True):
    path = Path(li_path) if li_path else _LI_ROOT
    if not path.exists():
        raise FileNotFoundError(f"Li data path not found: {path}")

    long_dfs, found_vars = [], []

    for stem, iamc_name in VARIABLE_MAP.items():
        csv_path = path / f"{stem}.csv"
        if not csv_path.exists():
            print(f"  [skip ] {stem}.csv — not found")
            continue

        df = pd.read_csv(csv_path)
        year_cols = [c for c in YEAR_COLS if c in df.columns]
        if not year_cols or not {"Model", "Scenario", "Category"}.issubset(df.columns):
            print(f"  [skip ] {stem}.csv — missing required columns or years")
            continue

        df_long = df.melt(
            id_vars=["Model", "Scenario", "Category"],
            value_vars=year_cols,
            var_name="Year", value_name="Value",
        )
        df_long["Year"]     = df_long["Year"].astype(int)
        df_long["Variable"] = iamc_name
        long_dfs.append(df_long)
        found_vars.append(iamc_name)
        print(f"  [load ] {iamc_name:<50}  ({df['Scenario'].nunique()} scenarios, {len(year_cols)} timesteps)")

    if not long_dfs:
        raise ValueError(f"No matching CSV files found in {path}")

    combined = pd.concat(long_dfs, ignore_index=True)
    combined["Region"] = "World"
    combined = combined.rename(columns={"Category": "Scenario_Category"})

    if drop_failed:
        mask = combined["Scenario_Category"].isin(FAILED_VETTING)
        n_dropped = combined.loc[mask, "Scenario"].nunique()
        if n_dropped:
            combined = combined[~mask].copy()
            print(f"\n  [info ] Dropped {n_dropped} failed-vetting / no-climate-assessment scenarios")

    wide = combined.pivot_table(
        index=["Model", "Scenario", "Region", "Scenario_Category", "Year"],
        columns="Variable", values="Value", aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    wide = wide.sort_values(["Model", "Scenario", "Year"]).reset_index(drop=True)

    seen, targets = set(), []
    for v in found_vars:
        if v not in seen and v in wide.columns:
            targets.append(v)
            seen.add(v)

    index_cols = ["Model", "Scenario", "Region", "Scenario_Category", "Year"]
    test_data = wide[index_cols].copy()
    values    = wide[targets].to_numpy(dtype=float)

    print(f"\n  Loaded {len(test_data):,} rows | {len(targets)} variables | {test_data['Scenario'].nunique()} unique scenarios")
    return test_data, values, targets


# ---------------------------------------------------------------------------
# Canonical long builder
# ---------------------------------------------------------------------------

def _build_canonical_long(test_data: pd.DataFrame, values: np.ndarray,
                           targets: list[str]) -> pd.DataFrame:
    index_cols = ["Model", "Scenario", "Region", "Scenario_Category", "Year"]
    idx  = test_data[index_cols].reset_index(drop=True)
    wide = pd.DataFrame(values, columns=targets)
    combined = pd.concat([idx, wide], axis=1)
    long = combined.melt(
        id_vars=index_cols, value_vars=targets,
        var_name="Variable", value_name="Value",
    )
    long["Units"] = long["Variable"].apply(_get_unit)
    return long[["Model", "Scenario", "Region", "Scenario_Category",
                 "Year", "Variable", "Value", "Units"]]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(model: str, run_id: str, out_dir: str = "adapted-data",
        li_path=None, data_path=None, labels_path=None):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Predictions
    print(f"\nLoading {model.upper()} generated outputs")
    pred_td, pred_vals, pred_targets = _load_generated(
        model, data_path=data_path, labels_path=labels_path
    )
    pred_long = _build_canonical_long(pred_td, pred_vals, pred_targets)
    pred_path = out_path / f"{run_id}_predictions.csv"
    pred_long.to_csv(pred_path, index=False)
    print(f"\n  Saved: {pred_path}")

    # Ground truth
    print(f"\nLoading Li ground truth data from: {li_path or _LI_ROOT}")
    gt_td, gt_vals, gt_targets = _load_ground_truth(li_path=li_path)
    gt_long = _build_canonical_long(gt_td, gt_vals, gt_targets)
    gt_path = out_path / f"{run_id}_ground_truth.csv"
    gt_long.to_csv(gt_path, index=False)
    print(f"  Saved: {gt_path}")

    print(f"\n  Predictions : {len(pred_long):,} rows, {pred_long['Variable'].nunique()} variables")
    print(f"  Ground truth: {len(gt_long):,} rows, {gt_long['Variable'].nunique()} variables")
    print(f"  Units       : {sorted(pred_long['Units'].unique())}")

    return {
        "run_id":            run_id,
        "predictions_path":  str(pred_path),
        "ground_truth_path": str(gt_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Li et al. adapter for em-iam-val")
    parser.add_argument("--model",       required=True, choices=["vae", "cgan", "rcgan"])
    parser.add_argument("--run_id",      required=True)
    parser.add_argument("--out_dir",     default="adapted-data")
    parser.add_argument("--li_path",     default=None, help="Path to Li CSV folder")
    parser.add_argument("--data_path",   default=None, help="Path to gen_data .npy")
    parser.add_argument("--labels_path", default=None, help="Path to gen_labels .npy")
    args = parser.parse_args()

    run(model=args.model, run_id=args.run_id, out_dir=args.out_dir,
        li_path=args.li_path, data_path=args.data_path, labels_path=args.labels_path)
    print("\nAdapter completed successfully.")


if __name__ == "__main__":
    main()
