"""
GCAMnet -> IAMC translation layer.

GCAMnet's adapter (gcamnet_adapter.py) produces IAMC-*formatted* CSVs, but the
Variable strings are still GCAMnet's flat native names (e.g.
"energy_supply_primary_coal"). Several common checks (physical_bounds_check,
hard_historical_constraints, soft_future_constraints, sci_checks) match
against canonical IAMC strings (e.g. "Primary Energy|Coal"), so against the
raw gcamnet_01 files they silently skip nearly everything.

This script does NOT touch the existing gcamnet_01 files. It reads them and
writes a second, separate dataset under a new run_id containing only a
straight 1:1 rename of the GCAMnet variables that genuinely correspond to an
IAMC variable (16 variables: 8 Primary Energy|<fuel> incl. "|Other", 8
Secondary Energy|Electricity|<fuel> incl. "|Other"), at GCAMnet's native
32-region granularity. The "_other" residual is renamed to the standard IAMC
"|Other" catch-all leaf -- that's still a value GCAMnet predicts directly,
just relabeled, not a derived value.

This script deliberately builds NOTHING that isn't already in GCAMnet's own
output:
  - No derived aggregate totals (no summed "Primary Energy" or "Secondary
    Energy|Electricity" parent series) -- GCAMnet doesn't predict these
    itself, only its fuel-level components.
  - No "World" total and no R5/R6/R10 regional aggregation -- GCAMnet's
    native output is 32 individual regions; it never predicts a world total
    or any region grouping, so constructing one would be summing the
    model's own output back at itself rather than testing it against
    anything.
  - Regions are left exactly as GCAMnet names them (e.g. "China", "USA"),
    not remapped to IAMC region codes.

Consequence: checks that need a parent/world/region-grouping variable that
doesn't exist in this dataset (sum_check's hierarchy check,
regional_consistency) will find no matching variables and skip cleanly --
that's expected and correct behavior, not a bug to fix. Checks that only
need GCAMnet's own per-region, per-fuel values (physical_bounds_check,
hard_historical_constraints, soft_future_constraints, sci_checks at
fuel-level granularity) get a real, non-vacuous variable name match.

What this does NOT fix (permanent scope gap, not a naming problem):
  - Emissions|CO2, Emissions|CH4, Carbon Sequestration|CCS: GCAMnet never
    predicts these. All CO2/CH4/CCS sub-checks in hard_historical,
    soft_future and sci_checks will still skip.
  - Secondary Energy|Electricity|Hydro, |Geothermal (and the Primary Energy
    equivalents): GCAMnet bundles these into a single "other" residual with
    no separate breakdown. That residual is mapped to "|Other" as a whole
    but is NOT further split into Hydro vs. Geothermal -- there's no honest
    way to do that from GCAMnet's output alone.

Usage:
    python adapters/gcamnet_iamc_translate.py \\
        --predictions adapted-data/gcamnet_01_sub_predictions.csv \\
        --ground_truth adapted-data/gcamnet_01_sub_ground_truth.csv \\
        --run_id gcamnet_01_iamc --out_dir adapted-data/
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))
from utils import load_csv, long_to_iamc  # noqa: E402


# ---------------------------------------------------------------------------
# Variable mapping: GCAMnet flat name -> canonical IAMC string. Straight 1:1
# renames of variables GCAMnet predicts directly -- nothing summed, derived,
# or aggregated. "_other" maps to the standard IAMC "|Other" catch-all leaf
# because GCAMnet predicts that residual value directly too; it's just
# named "_other" instead of "|Other".
# ---------------------------------------------------------------------------
VARIABLE_MAP = {
    "energy_supply_primary_coal":    "Primary Energy|Coal",
    "energy_supply_primary_oil":     "Primary Energy|Oil",
    "energy_supply_primary_gas":     "Primary Energy|Gas",
    "energy_supply_primary_solar":   "Primary Energy|Solar",
    "energy_supply_primary_wind":    "Primary Energy|Wind",
    "energy_supply_primary_nuclear": "Primary Energy|Nuclear",
    "energy_supply_primary_biomass": "Primary Energy|Biomass",
    "energy_supply_primary_other":   "Primary Energy|Other",

    "energy_supply_electricity_coal":    "Secondary Energy|Electricity|Coal",
    "energy_supply_electricity_oil":     "Secondary Energy|Electricity|Oil",
    "energy_supply_electricity_gas":     "Secondary Energy|Electricity|Gas",
    "energy_supply_electricity_solar":   "Secondary Energy|Electricity|Solar",
    "energy_supply_electricity_wind":    "Secondary Energy|Electricity|Wind",
    "energy_supply_electricity_biomass": "Secondary Energy|Electricity|Biomass",
    "energy_supply_electricity_nuclear": "Secondary Energy|Electricity|Nuclear",
    "energy_supply_electricity_other":   "Secondary Energy|Electricity|Other",
}


def translate(long_df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename GCAMnet's native variable names to canonical IAMC strings.

    No aggregation, no derived totals, no region remapping -- output is
    exactly GCAMnet's own predicted values, at its native region
    granularity, just relabeled.
    """
    renamed = long_df[long_df["Variable"].isin(VARIABLE_MAP)].copy()
    renamed["Variable"] = renamed["Variable"].map(VARIABLE_MAP)
    return renamed


def run(predictions_path: str, ground_truth_path: str, run_id: str,
        out_dir: str = "adapted-data") -> dict:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(f"Loading predictions from {predictions_path}")
    pred_long = load_csv(predictions_path)
    print(f"  {len(pred_long):,} rows, {pred_long['Variable'].nunique()} variables, "
          f"{pred_long['Region'].nunique()} regions")

    print(f"Loading ground truth from {ground_truth_path}")
    gt_long = load_csv(ground_truth_path)
    print(f"  {len(gt_long):,} rows")

    print("\nTranslating predictions...")
    pred_iamc = translate(pred_long)
    print(f"  -> {len(pred_iamc):,} rows, {pred_iamc['Variable'].nunique()} variables, "
          f"{pred_iamc['Region'].nunique()} regions")

    print("Translating ground truth...")
    gt_iamc = translate(gt_long)
    print(f"  -> {len(gt_iamc):,} rows")

    pred_out = out_path / f"{run_id}_predictions.csv"
    gt_out = out_path / f"{run_id}_ground_truth.csv"

    long_to_iamc(pred_iamc).to_csv(pred_out, index=False)
    long_to_iamc(gt_iamc).to_csv(gt_out, index=False)
    print(f"\nSaved: {pred_out}")
    print(f"Saved: {gt_out}")

    return {
        "run_id": run_id,
        "predictions_path": str(pred_out),
        "ground_truth_path": str(gt_out),
        "n_variables": pred_iamc["Variable"].nunique(),
    }


def main():
    parser = argparse.ArgumentParser(description="GCAMnet -> IAMC translation layer")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--ground_truth", required=True)
    parser.add_argument("--run_id", default="gcamnet_01_iamc")
    parser.add_argument("--out_dir", default="adapted-data")
    args = parser.parse_args()
    run(args.predictions, args.ground_truth, args.run_id, args.out_dir)
    print("\nTranslation completed successfully.")


if __name__ == "__main__":
    main()
