"""
GCAMnet (Holmes et al. 2026) adapter.

GCAMnet is a DNN emulator of GCAM (energy/land/water sectors) trained and
run via the separate GCAMnet repo (conda env, not this poetry env). It is a
reconstruction-type emulator -- deterministic region/year/quantity outputs
with a 1:1 correspondence to ground truth, same category as Shin et al.'s
ML-IAM -- so this follows shin_adapter.py's pattern.

Input: predictions.csv / actuals.csv as written by GCAMnet's inference.py
(pipe-separated, quote_style="non_numeric"). Schema: region, year, then one
column per output variable (e.g. energy_demand_elec_building, water_demand_crops).
Rows are ordered as itertools.product(regions, years) repeated once per test
sample, so groupby(["region", "year"]).cumcount() recovers the sample index
without needing GCAMnet's config (region/year counts) at all.

Units are taken from GCAMnet's ml_gcam/config/config.toml ([data.outputs.<key>.units]),
hardcoded below since em-iam-val uses a separate Python env with no access to
the ml_gcam package.

Usage:
    python adapters/gcamnet_adapter.py \\
        --predictions /path/to/GCAMnet/predictions.csv \\
        --actuals /path/to/GCAMnet/actuals.csv \\
        --run_id gcamnet_01 --out_dir adapted-data/

Outputs:
    adapted-data/gcamnet_01_predictions.csv
    adapted-data/gcamnet_01_ground_truth.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))
from utils import long_to_iamc

MODEL_NAME = "GCAMnet"

# From GCAMnet's ml_gcam/config/config.toml [data.outputs.<key>].units
UNITS_BY_OUTPUT = {
    "energy_demand_elec_transport": "EJ",
    "energy_demand_elec_industry": "EJ",
    "energy_demand_elec_building": "EJ",
    "energy_demand_fuel_fossil_transport": "EJ",
    "energy_demand_fuel_fossil_industry": "EJ",
    "energy_demand_fuel_fossil_building": "EJ",
    "energy_demand_fuel_biomass_industry": "EJ",
    "energy_demand_fuel_biomass_building": "EJ",
    "energy_price_electricity": "1975$/GJ",
    "energy_price_coal": "1975$/GJ",
    "energy_price_gas": "1975$/GJ",
    "energy_price_oil": "1975$/GJ",
    "energy_supply_electricity_coal": "EJ",
    "energy_supply_electricity_oil": "EJ",
    "energy_supply_electricity_gas": "EJ",
    "energy_supply_electricity_solar": "EJ",
    "energy_supply_electricity_wind": "EJ",
    "energy_supply_electricity_biomass": "EJ",
    "energy_supply_electricity_nuclear": "EJ",
    "energy_supply_electricity_other": "EJ",
    "energy_supply_primary_coal": "EJ",
    "energy_supply_primary_oil": "EJ",
    "energy_supply_primary_gas": "EJ",
    "energy_supply_primary_solar": "EJ",
    "energy_supply_primary_wind": "EJ",
    "energy_supply_primary_biomass": "EJ",
    "energy_supply_primary_nuclear": "EJ",
    "energy_supply_primary_other": "EJ",
    "land_demand_feed": "Mt",
    "land_demand_food": "Mt",
    "land_price_biomass": "1975$/GJ",
    "land_price_forest": "1975$/m3",
    "land_allocation_forest": "thousand km2",
    "land_allocation_biomass": "thousand km2",
    "land_allocation_pasture": "thousand km2",
    "land_allocation_grass_shrub": "thousand km2",
    "land_allocation_other": "thousand km2",
    "land_production_forest": "billion m3",
    "land_production_biomass": "EJ",
    "land_production_pasture": "Mt",
    "land_production_grass_shrub": "Mt",
    "land_production_other": "Mt",
    "water_demand_crops": "km3",
    "water_demand_electricity": "km3",
}


def _load_wide(path: Path) -> pd.DataFrame:
    """
    Load a GCAMnet inference CSV (pipe-separated, quoted non-numerics).

    Dtypes are pinned tight (float32 values, category region, int16 year) so
    the in-memory footprint stays well under the dataset's ~100MB on-disk
    size -- the unconstrained default (float64 + object dtype) is what
    triggered an OOM kill on the first attempt at this conversion.
    """
    header = pd.read_csv(path, sep="|", nrows=0).columns.tolist()
    value_cols = [c for c in header if c in UNITS_BY_OUTPUT]
    dtype = {c: "float32" for c in value_cols}
    dtype["region"] = "category"
    dtype["year"] = "int16"
    return pd.read_csv(path, sep="|", dtype=dtype)


def build_canonical_long(wide: pd.DataFrame) -> pd.DataFrame:
    """
    Convert GCAMnet's region/year-wide-by-variable CSV into canonical long
    format.

    Parameters
    ----------
    wide : DataFrame with columns region, year, <output variable columns...>

    Returns
    -------
    Long-format DataFrame with columns:
        Model, Scenario, Region, Year, Variable, Value, Units
    (Model, Scenario, Region, Variable, Units are category dtype to keep
    memory bounded across the ~9M-row melt.)
    """
    # Recover sample index: rows are product(regions, years) repeated once per
    # test sample, so the n-th occurrence of a given (region, year) pair is
    # sample n -- regardless of how many regions/years there are.
    sample_idx = wide.groupby(["region", "year"]).cumcount()

    value_vars = [c for c in wide.columns if c in UNITS_BY_OUTPUT]
    missing = [c for c in wide.columns if c not in UNITS_BY_OUTPUT and c not in ("region", "year")]
    if missing:
        print(f"  WARNING: {len(missing)} columns not in UNITS_BY_OUTPUT, dropped: {missing}")

    id_frame = pd.DataFrame({
        "region": wide["region"].values,
        "year": wide["year"].values,
        "__sample_idx": sample_idx.values,
    })
    long = pd.concat([id_frame, wide[value_vars]], axis=1).melt(
        id_vars=["region", "year", "__sample_idx"],
        value_vars=value_vars,
        var_name="Variable",
        value_name="Value",
    )
    del id_frame

    out = pd.DataFrame({
        "Model": pd.Categorical([MODEL_NAME] * len(long)),
        "Scenario": ("test_" + long["__sample_idx"].astype(str)).astype("category"),
        "Region": long["region"].astype("category"),
        "Year": long["year"].astype("int16"),
        "Variable": long["Variable"].astype("category"),
        "Value": long["Value"].astype("float32"),
        "Units": long["Variable"].map(UNITS_BY_OUTPUT).astype("category"),
    })
    del long
    return out


def _convert_one(src_path: str, out_path: Path) -> tuple:
    """Load one wide CSV, convert to IAMC, write it, and free memory before returning."""
    import gc

    wide = _load_wide(Path(src_path))
    n_rows, n_regions, n_years = len(wide), wide["region"].nunique(), wide["year"].nunique()

    long = build_canonical_long(wide)
    del wide
    gc.collect()

    n_vars = long["Variable"].nunique()
    n_scenarios = long["Scenario"].nunique()

    iamc = long_to_iamc(long)
    del long
    gc.collect()

    iamc.to_csv(out_path, index=False)
    del iamc
    gc.collect()

    return n_rows, n_regions, n_years, n_vars, n_scenarios


def run(predictions_path: str, actuals_path: str, run_id: str, out_dir: str = "adapted-data") -> dict:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    pred_out = out_path / f"{run_id}_predictions.csv"
    gt_out = out_path / f"{run_id}_ground_truth.csv"

    # Process one file fully (load -> long -> IAMC -> write -> free) before
    # touching the other, so peak memory is one dataset's worth, not both.
    n_rows, n_regions, n_years, n_vars, n_scenarios = _convert_one(predictions_path, pred_out)
    print(f"  Predictions: {n_rows:,} rows, {n_regions} regions, {n_years} years, "
          f"{n_vars} variables, {n_scenarios} samples")
    print(f"  Saved: {pred_out}")

    gt_rows, *_ = _convert_one(actuals_path, gt_out)
    print(f"  Ground truth: {gt_rows:,} rows")
    print(f"  Saved: {gt_out}")

    return {
        "run_id": run_id,
        "predictions_path": str(pred_out),
        "ground_truth_path": str(gt_out),
        "n_rows": n_rows,
        "n_variables": n_vars,
    }


def main():
    parser = argparse.ArgumentParser(
        description="GCAMnet adapter for em-iam-val validation framework"
    )
    parser.add_argument("--predictions", required=True, help="Path to GCAMnet predictions.csv")
    parser.add_argument("--actuals", required=True, help="Path to GCAMnet actuals.csv (ground truth)")
    parser.add_argument("--run_id", default="gcamnet_01", help="Run identifier (default: gcamnet_01)")
    parser.add_argument("--out_dir", default="adapted-data", help="Output directory (default: adapted-data/)")

    args = parser.parse_args()
    run(args.predictions, args.actuals, args.run_id, args.out_dir)
    print("\nAdapter completed successfully.")


if __name__ == "__main__":
    main()
