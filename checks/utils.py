"""
Shared utilities for em-iam-val check scripts.

File format (IAMC wide)
-----------------------
Input and output files follow the IAMC timeseries format:
    Model, Scenario, Region, Variable, Unit, <year>, <year>, ...

where year columns are integers (e.g. 2010, 2020, ..., 2100).
load_csv() accepts this format directly — no adapter or pre-conversion needed.

Internal format (long)
----------------------
All internal processing uses a long format with columns:
    Model, Scenario, Region, Year, Variable, Value, Units

load_csv() converts IAMC wide to long automatically on load.

Canonical units
---------------
    Energy    : EJ
    CO2       : MtCO2
    CH4       : MtCH4
    N2O       : MtN2O
    CO2eq     : MtCO2eq  (Kyoto gases aggregates — not converted)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
import sys


CANONICAL_COLUMNS = ["Model", "Scenario", "Region", "Year", "Variable", "Value", "Units"]
IDX = ["Model", "Scenario", "Region"]

# IAMC wide-format metadata columns (everything else in an IAMC file is a year column)
IAMC_META = ["Model", "Scenario", "Region", "Variable", "Unit"]

_CONVERSIONS = {
    ("PJ", "EJ"): 1e-3, ("EJ", "PJ"): 1e3,
    ("PJ/yr", "EJ/yr"): 1e-3, ("EJ/yr", "PJ/yr"): 1e3,
    ("GJ", "EJ"): 1e-9, ("TJ", "EJ"): 1e-6,
    ("GtCO2", "MtCO2"): 1e3, ("MtCO2", "GtCO2"): 1e-3,
    ("GtCO2/yr", "MtCO2/yr"): 1e3,
    ("MtC", "MtCO2"): 44/12, ("GtC", "MtCO2"): 44/12*1e3,
    ("Mt CO2/yr", "MtCO2/yr"): 1.0, ("Mt CO2", "MtCO2"): 1.0,
    ("Gt CO2/yr", "MtCO2/yr"): 1e3,
    ("Mt CH4/yr", "MtCH4/yr"): 1.0, ("Mt CH4", "MtCH4"): 1.0,
    ("GtCH4", "MtCH4"): 1e3, ("MtCH4", "GtCH4"): 1e-3,
    ("Mt N2O/yr", "MtN2O/yr"): 1.0, ("Mt N2O", "MtN2O"): 1.0,
    ("GtN2O", "MtN2O"): 1e3, ("MtN2O", "GtN2O"): 1e-3,
}

_VAR_CANONICAL = [
    ("Primary Energy", "EJ"),
    ("Secondary Energy", "EJ"),
    ("Final Energy", "EJ"),
    ("Emissions|CO2", "MtCO2"),
    ("Emissions|CH4", "MtCH4"),
    ("Emissions|N2O", "MtN2O"),
    ("Carbon Sequestration", "MtCO2"),
]

_UNITS_WARN_THRESHOLD = 100.0


class _Tee:
    """
    Replace sys.stdout so output goes to both the terminal and a log file.

    Usage:
        tee = _Tee(path / "report.txt")
        sys.stdout = tee
        ...
        tee.close()   # restores sys.stdout
    """

    def __init__(self, path: Path):
        self._file    = open(path, "w")
        self._stdout  = sys.stdout
        sys.stdout    = self

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def close(self):
        sys.stdout = self._stdout
        self._file.close()


def _is_iamc(df: pd.DataFrame) -> bool:
    """Return True if df looks like IAMC wide format."""
    return all(c in df.columns for c in IAMC_META)


def _iamc_to_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert an IAMC wide-format DataFrame to internal long format.

    IAMC columns: Model, Scenario, Region, Variable, Unit, <year>, <year>, ...
    Output columns: Model, Scenario, Region, Year, Variable, Value, Units
    """
    year_cols = [c for c in df.columns if c not in IAMC_META]
    if not year_cols:
        raise ValueError("IAMC format detected but no year columns found.")
    try:
        [int(c) for c in year_cols]
    except (ValueError, TypeError):
        raise ValueError(
            f"IAMC format detected but non-integer columns found alongside metadata: {year_cols}"
        )
    long = df.melt(
        id_vars=IAMC_META,
        value_vars=year_cols,
        var_name="Year",
        value_name="Value",
    )
    long["Year"] = long["Year"].astype(int)
    long = long.rename(columns={"Unit": "Units"})
    return long[CANONICAL_COLUMNS]


def long_to_iamc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert internal long-format DataFrame to IAMC wide format.

    Input columns:  Model, Scenario, Region, Year, Variable, Value, Units
    Output columns: Model, Scenario, Region, Variable, Unit, <year>, <year>, ...
    """
    unit_map = df.groupby("Variable")["Units"].first()
    wide = df.pivot_table(
        index=["Model", "Scenario", "Region", "Variable"],
        columns="Year",
        values="Value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    wide.insert(4, "Unit", wide["Variable"].map(unit_map))
    year_cols = sorted([c for c in wide.columns if c not in IAMC_META])
    return wide[IAMC_META + year_cols]


def validate_format(df: pd.DataFrame) -> None:
    """
    Validate that df has all internal long-format canonical columns.

    Raises ValueError if any columns are missing.
    """
    missing = [col for col in CANONICAL_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Missing canonical columns: {missing}\n"
            f"Required: {CANONICAL_COLUMNS}\n"
            f"Found: {list(df.columns)}"
        )


def load_csv(path: str) -> pd.DataFrame:
    """
    Load a CSV file in IAMC wide format or internal long format.

    IAMC wide format (Model, Scenario, Region, Variable, Unit, <years>...)
    is detected automatically and converted to internal long format on load.
    """
    df = pd.read_csv(path)
    if _is_iamc(df):
        df = _iamc_to_long(df)
    validate_format(df)
    return df


def _nearest_year(available: set, target: int) -> int:
    """Find nearest available year to target."""
    if target in available:
        return target
    return min(available, key=lambda x: abs(x - target))


def _filter_world(long: pd.DataFrame, world_region: str = "World") -> Tuple[pd.DataFrame, bool]:
    """
    Filter to world_region if it exists, otherwise return full data.

    Returns (filtered_df, fallback_bool) where fallback_bool is True if World was not found.
    """
    if world_region in long["Region"].values:
        return long[long["Region"] == world_region].copy(), False
    else:
        return long.copy(), True


def _canonical_unit_for(variable: str) -> Optional[str]:
    """Return canonical unit for variable using prefix matching."""
    for var_prefix, unit in _VAR_CANONICAL:
        if variable.startswith(var_prefix):
            return unit
    return None


def _conversion_factor(from_unit: str, to_unit: str) -> Optional[float]:
    """
    Get conversion factor to convert from_unit to to_unit.

    Returns 1.0 if units are identical, None if conversion is unknown.
    Lookup is attempted with original units first, then with /yr suffix
    stripped (so "PJ/yr" -> "EJ" matches the ("PJ", "EJ") entry).
    """
    if from_unit == to_unit:
        return 1.0

    # Direct lookup with original units
    if (from_unit, to_unit) in _CONVERSIONS:
        return _CONVERSIONS[(from_unit, to_unit)]

    # Strip /yr suffix and retry — handles e.g. "PJ/yr" -> "EJ"
    # rstrip("/yr") strips the individual chars {/, y, r} from the right.
    # "PJ/yr" -> "PJ", "EJ/yr" -> "EJ", "EJ" -> "EJ" (unchanged)
    from_base = from_unit.rstrip("/yr").strip()
    to_base   = to_unit.rstrip("/yr").strip()

    if from_base == to_base:
        return 1.0

    for pair in [
        (from_base, to_base),
        (from_unit, to_base),
        (from_base, to_unit),
    ]:
        if pair in _CONVERSIONS:
            return _CONVERSIONS[pair]

    return None


def normalize_to_canonical(long: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize all values to canonical units.

    For each Variable, reads its Units from the data, converts Value column,
    and updates Units column. Prints conversion summary. Returns a copy.
    """
    result = long.copy()
    conversions_applied = []

    for var in result["Variable"].unique():
        var_mask = result["Variable"] == var
        var_data = result[var_mask].copy()

        # Get canonical unit for this variable
        canonical = _canonical_unit_for(var)
        if canonical is None:
            continue

        # Get unique units for this variable in the data
        units_in_var = var_data["Units"].unique()

        for unit_str in units_in_var:
            if pd.isna(unit_str) or unit_str == "unknown":
                continue

            unit_mask = var_mask & (result["Units"] == unit_str)
            factor = _conversion_factor(unit_str, canonical)

            if factor is None:
                print(f"  WARNING: Unknown conversion {unit_str} -> {canonical} for {var}. Skipping.")
                continue

            if factor != 1.0:
                result.loc[unit_mask, "Value"] = result.loc[unit_mask, "Value"] * factor
                result.loc[unit_mask, "Units"] = canonical
                conversions_applied.append(f"  {var}: {unit_str} -> {canonical} (factor: {factor})")

    if conversions_applied:
        print("Unit normalizations applied:")
        for line in conversions_applied:
            print(line)
    else:
        print("No unit conversions needed.")

    return result


def check_unit_plausibility(
    result_df: pd.DataFrame,
    typical_value: float,
    required_vars: list,
    unit_str: str
) -> Optional[str]:
    """
    Check if computed values are plausibly scaled.

    Returns warning string if median value is >100x off typical_value, else None.
    """
    if result_df.empty or "Value" not in result_df.columns:
        return None

    median_val = result_df["Value"].median()
    if pd.isna(median_val) or median_val == 0:
        return None

    ratio = abs(median_val - typical_value) / typical_value if typical_value != 0 else np.inf

    if ratio > _UNITS_WARN_THRESHOLD:
        return (
            f"Unit plausibility warning: median value {median_val:.2f} {unit_str} "
            f"is {ratio:.1f}x away from typical {typical_value} {unit_str}. "
            f"Check variable units."
        )

    return None


def make_out_dir(out_dir: str, run_id: str, check_name: str) -> Path:
    """Create and return output directory for check results."""
    out_path = Path(out_dir) / run_id / check_name
    out_path.mkdir(parents=True, exist_ok=True)
    return out_path


def save_check_outputs(
    out_dir: Path,
    results: pd.DataFrame,
    summary: pd.DataFrame = None,
    unit_warnings: list = None,
    skipped: list = None
) -> None:
    """Save check results to CSVs in out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save results
    results_path = out_dir / "results.csv"
    results.to_csv(results_path, index=False)

    # Save summary if provided
    if summary is not None and not summary.empty:
        summary_path = out_dir / "summary.csv"
        summary.to_csv(summary_path, index=False)

    # Save warnings if provided
    if unit_warnings:
        warnings_path = out_dir / "unit_warnings.txt"
        with open(warnings_path, "w") as f:
            for warning in unit_warnings:
                f.write(warning + "\n")

    # Save skipped info if provided
    if skipped:
        skipped_path = out_dir / "skipped.txt"
        with open(skipped_path, "w") as f:
            for item in skipped:
                f.write(item + "\n")
