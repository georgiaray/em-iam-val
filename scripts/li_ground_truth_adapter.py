"""
Li et al. ground truth data adapter for em-iam-val.

Loads the AR6 scenario CSVs from the Li et al. (Deep-IAM) Zenodo deposit and
reshapes them into the canonical format expected by the em-iam-val validation checks:

    test_data  : pd.DataFrame  — index columns [Model, Scenario, Region,
                                  Scenario_Category, Year]
    values     : np.ndarray    — shape (n_rows, n_targets), float64
    targets    : list[str]     — IAMC variable names, length n_targets

The Li ground truth data is World-level only (no regional breakdown) and uses
10-year timesteps (2010–2100). Both of these differ from the ml-iam / AR6 pipeline:
  - Region is synthesised as "World" for every row.
  - Growth-rate checks will compute 10-year period-on-period rates, not 5-year.
    This is noted in the runner and should be flagged in any report.

Usage
-----
    from li_ground_truth_adapter import load_li_ground_truth

    test_data, values, targets = load_li_ground_truth()          # defaults
    test_data, values, targets = load_li_ground_truth(
        li_path="/path/to/Li-emulation/Policy-Generative Model",
        drop_failed_vetting=True,
    )

The default li_path assumes the Li-emulation folder sits adjacent to the
em-iam-val and ml-iam repos, i.e.:
    coding/
        em-iam-val/
        ml-iam/
        Li-emulation/
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Default data path
# ---------------------------------------------------------------------------

# Assumes coding/Li-emulation/Policy-Generative Model/ relative to this file
_HERE = Path(__file__).resolve().parent
DEFAULT_LI_PATH = _HERE.parent.parent / "Li-emulation" / "Policy-Generative Model"

# ---------------------------------------------------------------------------
# Variable map: CSV filename stem → IAMC variable name
#
# Keyed on the Policy-Generative Model folder (the most complete set, used
# in the paper's main generative modelling experiments). The "also_in" comment
# shows which other folders carry the same file.
# ---------------------------------------------------------------------------

VARIABLE_MAP: dict[str, str] = {
    # Primary Energy
    "PrimaryEnergy_Coal":                    "Primary Energy|Coal",
    "Primary Energy_Oil":                    "Primary Energy|Oil",

    # Secondary Energy — Electricity (parent + all children)
    "SecondaryEnergy_Electricity":           "Secondary Energy|Electricity",
    "SecondaryEnergy_Electricity_Biomass":   "Secondary Energy|Electricity|Biomass",
    "SecondaryEnergy_Electricity_Coal":      "Secondary Energy|Electricity|Coal",
    "SecondaryEnergy_Electricity_Gas":       "Secondary Energy|Electricity|Gas",
    "SecondaryEnergy_Electricity_Geothermal":"Secondary Energy|Electricity|Geothermal",
    "SecondaryEnergy_Electricity_Hydro":     "Secondary Energy|Electricity|Hydro",
    "SecondaryEnergy_Electricity_Nuclear":   "Secondary Energy|Electricity|Nuclear",
    "SecondaryEnergy_Electricity_Oil":       "Secondary Energy|Electricity|Oil",
    "SecondaryEnergy_Electricity_Solar":     "Secondary Energy|Electricity|Solar",
    "SecondaryEnergy_Electricity_Wind":      "Secondary Energy|Electricity|Wind",

    # Final Energy
    "Final Energy_Liquids":                  "Final Energy|Liquids",
    "Final Energy_Solids":                   "Final Energy|Solids",
    "Secondary Energy_Gases":               "Secondary Energy|Gases",

    # Emissions / Sequestration
    "Kyoto Gases":                           "Emissions|Kyoto Gases",
    "Carbon_Sequestration_CCS_imputed":      "Carbon Sequestration|CCS",

    # Aggregates (imputed, used in generative model training)
    "PrimaryEnergy_imputed":                 "Primary Energy",
}

# Extra variables available in the Feature selection folder (not in
# Policy-Generative Model) — included when the caller provides a broader path.
EXTRA_VARIABLE_MAP: dict[str, str] = {
    "Primary Energy_Gas":                    "Primary Energy|Gas",
    "Primary Energy_Solar":                  "Primary Energy|Solar",
    "Final Energy_Gases":                    "Final Energy|Gases",
    "Final_Energy_ts_imputed":               "Final Energy",
    "SecondaryEnergyElectricity_imputed":    "Secondary Energy|Electricity",
}

# Year columns present in all Li ground truth CSVs
YEAR_COLS: list[str] = [str(y) for y in range(2010, 2110, 10)]

# Category values that indicate a scenario failed IAMC vetting and should
# normally be excluded from validation.
FAILED_VETTING_VALUES: set[str] = {"failed-vetting", "no-climate-assessment"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_li_ground_truth(
    li_path: str | Path | None = None,
    drop_failed_vetting: bool = True,
    variables: list[str] | None = None,
    verbose: bool = True,
) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """
    Load and reshape Li et al. ground truth CSV data into the em-iam-val canonical format.

    Parameters
    ----------
    li_path : path-like, optional
        Directory containing the Li et al. ground truth CSV files. Defaults to
        ``coding/Li-emulation/Policy-Generative Model/``.
        Pass the Feature-selection folder to get a wider variable set.
    drop_failed_vetting : bool
        If True (default), rows whose Category is "failed-vetting" or
        "no-climate-assessment" are excluded before building the array.
    variables : list[str], optional
        Restrict to a specific list of IAMC variable names. Defaults to all
        found in the folder.
    verbose : bool
        Print per-variable load status.

    Returns
    -------
    test_data : pd.DataFrame
        One row per (Model, Scenario, Region, Scenario_Category, Year).
        No variable columns — index only.
    values : np.ndarray
        Shape (n_rows, n_targets), dtype float64. NaNs where data is missing.
    targets : list[str]
        IAMC variable names corresponding to columns of ``values``.
    """
    path = Path(li_path) if li_path is not None else DEFAULT_LI_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Li ground truth data path not found: {path}\n"
            f"Set li_path explicitly or ensure Li-emulation is at {DEFAULT_LI_PATH.parent}"
        )

    # Build the combined variable map for this folder
    vmap = {**VARIABLE_MAP, **EXTRA_VARIABLE_MAP}

    long_dfs: list[pd.DataFrame] = []
    found_vars: list[str] = []

    _log = print if verbose else lambda *a, **k: None
    _log(f"\nLoading Li ground truth data from: {path}")

    for stem, iamc_name in vmap.items():
        if variables is not None and iamc_name not in variables:
            continue

        csv_path = path / f"{stem}.csv"
        if not csv_path.exists():
            _log(f"  [skip ] {stem}.csv — not found")
            continue

        df = pd.read_csv(csv_path)

        # Identify year columns actually present
        year_cols = [c for c in YEAR_COLS if c in df.columns]
        if not year_cols:
            _log(f"  [skip ] {stem}.csv — no year columns found")
            continue

        required = {"Model", "Scenario", "Category"}
        if not required.issubset(df.columns):
            missing = required - set(df.columns)
            _log(f"  [skip ] {stem}.csv — missing columns: {missing}")
            continue

        # Melt wide → long
        df_long = df.melt(
            id_vars=["Model", "Scenario", "Category"],
            value_vars=year_cols,
            var_name="Year",
            value_name="Value",
        )
        df_long["Year"] = df_long["Year"].astype(int)
        df_long["Variable"] = iamc_name

        long_dfs.append(df_long)
        found_vars.append(iamc_name)
        n_scenarios = df["Scenario"].nunique()
        _log(f"  [load ] {iamc_name:<50}  ({n_scenarios} scenarios, {len(year_cols)} timesteps)")

    if not long_dfs:
        raise ValueError(
            f"No matching CSV files found in {path}.\n"
            f"Expected files named like: {list(VARIABLE_MAP.keys())[:3]} ..."
        )

    # -----------------------------------------------------------------------
    # Combine, standardise, optionally filter
    # -----------------------------------------------------------------------
    combined = pd.concat(long_dfs, ignore_index=True)

    # Standardise column names to match em-iam-val canonical format
    combined["Region"] = "World"
    combined = combined.rename(columns={"Category": "Scenario_Category"})

    if drop_failed_vetting:
        mask = combined["Scenario_Category"].isin(FAILED_VETTING_VALUES)
        n_dropped = combined.loc[mask, "Scenario"].nunique()
        if n_dropped:
            combined = combined[~mask].copy()
            _log(f"\n  [info ] Dropped {n_dropped} failed-vetting / no-climate-assessment scenarios")

    # -----------------------------------------------------------------------
    # Pivot to wide: one row per (Model, Scenario, Region, Category, Year),
    # one column per variable — matching the shape the checks expect.
    # -----------------------------------------------------------------------
    wide = combined.pivot_table(
        index=["Model", "Scenario", "Region", "Scenario_Category", "Year"],
        columns="Variable",
        values="Value",
        aggfunc="first",      # each (scenario, year, variable) should be unique
    ).reset_index()
    wide.columns.name = None

    wide = wide.sort_values(["Model", "Scenario", "Year"]).reset_index(drop=True)

    # Deduplicate targets in case two stems mapped to the same IAMC name
    seen: set[str] = set()
    targets: list[str] = []
    for v in found_vars:
        if v not in seen and v in wide.columns:
            targets.append(v)
            seen.add(v)

    index_cols = ["Model", "Scenario", "Region", "Scenario_Category", "Year"]
    test_data = wide[index_cols].copy()
    values = wide[targets].to_numpy(dtype=float)

    _log(
        f"\n  Loaded {len(test_data):,} rows  |  "
        f"{len(targets)} variables  |  "
        f"{test_data['Scenario'].nunique()} unique scenarios\n"
    )

    return test_data, values, targets


# ---------------------------------------------------------------------------
# CLI convenience — print a summary of what's available
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Summarise available Li ground truth data")
    parser.add_argument(
        "--li_path", default=None,
        help="Path to the Li ground truth CSV folder (default: coding/Li-emulation/Policy-Generative Model)"
    )
    args = parser.parse_args()

    td, vals, tgts = load_li_ground_truth(li_path=args.li_path)
    print(f"test_data shape : {td.shape}")
    print(f"values shape    : {vals.shape}")
    print(f"targets         : {tgts}")
    print(f"\nScenario categories:\n{td['Scenario_Category'].value_counts().to_string()}")
    print(f"\nYear range      : {td['Year'].min()}–{td['Year'].max()}")
