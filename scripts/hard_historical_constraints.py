"""
Hard historical constraints check for ML-IAM predictions.

Checks predicted values at the 2020 reference year against the historical
anchor values used in the AR6 scenario vetting process (Table 11, Nicholls
et al. 2022 / AR6 scenario vetting paper).

Each sub-check specifies the variables it requires. If any required variable
is absent from this run's target set, that sub-check is automatically skipped
and recorded as such in the report. Available sub-checks are:

  co2_eip_2020          -- CO₂ EIP emissions at 2020 vs 37,646 MtCO₂/yr (±20%/±10%)
  ch4_2020              -- CH₄ emissions at 2020 vs 379 MtCH₄/yr (±20%)
  co2_change_2010_2020  -- CO₂ EIP % change 2010-2020; expected range 0–50%
  ccs_2020              -- CCS from energy at 2020; expected 0–250 (IP: 0–100) MtCO₂/yr
  primary_energy_2020   -- Primary energy total at 2020 vs 578 EJ (±20%/±10%)
  nuclear_energy_2020   -- Nuclear primary energy at 2020 vs 9.77 EJ (±30%/±20%)
  solar_wind_2020       -- Solar+wind primary energy at 2020 vs 8.51 EJ (±50%/±25%)

Each scenario-region is classified as:
  PASS  -- within the inner (IP-range) tolerance
  WARN  -- within outer tolerance but outside inner tolerance
  FAIL  -- outside outer tolerance
  SKIP  -- required variable(s) not present in this run

Belongs to the 'Historical and domain knowledge comparison' validation family.

Usage:
    python hard_historical_constraints.py --run_id xgb_04
    python hard_historical_constraints.py --run_id xgb_04 --use_ground_truth
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

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
# Unit normalisation
# ---------------------------------------------------------------------------
# All checks in this file use reference values expressed in canonical units:
#   Energy   : EJ
#   CO₂      : MtCO₂
#   CH₄      : MtCH₄
#
# Before any check runs, the long-format data is normalised to these canonical
# units via normalize_to_canonical(). This makes the framework agnostic to
# whatever unit convention the source dataset uses (PJ, GJ, GtCO₂, etc.).
#
# Unit information is resolved in this order:
#   1. A units_map passed explicitly (e.g. from a --units_config JSON file).
#   2. ml-iam's UNITS_BY_OUTPUT config, if importable.
#   3. Identity (no conversion) with a printed warning for any variable whose
#      unit cannot be determined.

# Canonical units for this framework
CANONICAL_UNITS: dict[str, str] = {
    "energy":   "EJ",
    "co2":      "MtCO2",
    "ch4":      "MtCH4",
    "n2o":      "MtN2O",
}

# All known pairwise conversions: (from_unit, to_unit) -> multiplier
_CONVERSIONS: dict[tuple[str, str], float] = {
    # Energy
    ("PJ",      "EJ"):      1e-3,
    ("EJ",      "PJ"):      1e3,
    ("PJ/yr",   "EJ/yr"):   1e-3,
    ("EJ/yr",   "PJ/yr"):   1e3,
    ("GJ",      "EJ"):      1e-9,
    ("TJ",      "EJ"):      1e-6,
    # Carbon
    ("GtCO2",    "MtCO2"):  1e3,
    ("MtCO2",    "GtCO2"):  1e-3,
    ("GtCO2/yr", "MtCO2/yr"): 1e3,
    ("MtC",      "MtCO2"):  44.0 / 12.0,
    ("GtC",      "MtCO2"):  44.0 / 12.0 * 1e3,
    # Spaced variants (e.g. "Mt CO2/yr" as used in some configs)
    ("Mt CO2/yr",  "MtCO2/yr"): 1.0,
    ("Mt CO2",     "MtCO2"):    1.0,
    ("Gt CO2/yr",  "MtCO2/yr"): 1e3,
    ("Mt CH4/yr",  "MtCH4/yr"): 1.0,
    ("Mt CH4",     "MtCH4"):    1.0,
    ("Mt N2O/yr",  "MtN2O/yr"): 1.0,
    ("Mt N2O",     "MtN2O"):    1.0,
    # Methane / other GHGs
    ("GtCH4",   "MtCH4"):   1e3,
    ("MtCH4",   "GtCH4"):   1e-3,
    ("GtN2O",   "MtN2O"):   1e3,
    ("MtN2O",   "GtN2O"):   1e-3,
}

# Which canonical unit applies to each variable (matched by prefix)
_VAR_CANONICAL: list[tuple[str, str]] = [
    ("Primary Energy",         "EJ"),
    ("Secondary Energy",       "EJ"),
    ("Final Energy",           "EJ"),
    ("Emissions|CO2",          "MtCO2"),
    ("Emissions|CH4",          "MtCH4"),
    ("Emissions|N2O",          "MtN2O"),
    ("Carbon Sequestration",   "MtCO2"),
]


def _canonical_unit_for(variable: str) -> Optional[str]:
    """Return the canonical unit for a variable based on prefix matching."""
    for prefix, unit in _VAR_CANONICAL:
        if variable.startswith(prefix):
            return unit
    return None


def _conversion_factor(from_unit: str, to_unit: str) -> Optional[float]:
    """Return multiplier to convert from_unit -> to_unit, or None if unknown."""
    f = from_unit.strip()
    t = to_unit.strip()
    # Strip /yr suffix for matching (direction doesn't affect magnitude)
    f_base = f.rstrip("/yr").rstrip("/Yr")
    t_base = t.rstrip("/yr").rstrip("/Yr")
    if f == t or f_base == t_base:
        return 1.0
    return _CONVERSIONS.get((f, t)) or _CONVERSIONS.get((f_base, t_base))


def load_units_map(repo_root: Path, units_config_path: Optional[str] = None) -> dict[str, str]:
    """
    Build a {variable: unit} mapping from available sources.

    Priority:
      1. units_config_path (JSON file: {"Variable|Name": "unit", ...})
      2. ml-iam UNITS_BY_OUTPUT config (auto-detected from repo_root)
      3. Empty dict (no conversions applied; warnings issued at check time)
    """
    if units_config_path:
        import json
        try:
            with open(units_config_path) as f:
                units = json.load(f)
            print(f"  Units loaded from: {units_config_path}  ({len(units)} variables)")
            return units
        except Exception as e:
            print(f"  [WARN] Could not load units config '{units_config_path}': {e}")

    try:
        from configs.data import UNITS_BY_OUTPUT
        units = dict(UNITS_BY_OUTPUT)
        print(f"  Units loaded from ml-iam configs.data  ({len(units)} variables)")
        return units
    except Exception:
        pass

    print("  [WARN] No unit configuration found. Checks will run on raw data units.")
    return {}


def normalize_to_canonical(
    long: pd.DataFrame,
    units_map: dict[str, str],
) -> pd.DataFrame:
    """
    Convert all variable values in a long-format DataFrame to canonical units.

    For each variable:
      - Determine its canonical target unit from _VAR_CANONICAL prefix matching.
      - Look up its actual unit in units_map.
      - Apply the conversion factor if needed.
      - Variables with unknown units or no conversion path are left unchanged
        with a warning.

    Returns a copy of the DataFrame with values converted in-place.
    """
    long = long.copy()
    variables = long["Variable"].unique()
    converted, unchanged, warned = [], [], []

    for var in variables:
        target_unit = _canonical_unit_for(var)
        if target_unit is None:
            unchanged.append(var)
            continue

        data_unit = units_map.get(var)
        if data_unit is None:
            warned.append(f"{var} (no unit in map)")
            continue

        factor = _conversion_factor(data_unit, target_unit)
        if factor is None:
            warned.append(f"{var} ({data_unit} → {target_unit}: no conversion known)")
            continue

        if factor != 1.0:
            long.loc[long["Variable"] == var, "Value"] *= factor
            converted.append(f"{var}: {data_unit} → {target_unit} (×{factor})")

    if converted:
        print(f"\n  Unit conversions applied ({len(converted)}):")
        for c in converted:
            print(f"    {c}")
    if warned:
        print(f"\n  [WARN] Could not convert {len(warned)} variable(s) — used as-is:")
        for w in warned:
            print(f"    {w}")

    return long


# ---------------------------------------------------------------------------
# Constraint definitions
# ---------------------------------------------------------------------------
# Each entry describes one sub-check. Fields:
#
#   name           : str       - identifier used in output and reports
#   label          : str       - human-readable description
#   required       : list[str] - variables that must all be in the run's targets;
#                                if any are missing the check is skipped
#   compute_fn     : callable(wide_df) -> pd.Series, or None for special cases
#                    wide_df has one row per scenario-region, columns are variables
#   year           : int or list[int] - reference year(s) to extract
#   reference_unit : str - unit the reference bounds are expressed in
#                    (the framework converts to the data's actual unit at runtime)
#   outer_lower  : float or None - outer pass/fail lower bound
#   outer_upper  : float or None - outer pass/fail upper bound
#   inner_lower  : float or None - inner (IP range) lower bound; triggers WARN
#   inner_upper  : float or None - inner (IP range) upper bound; triggers WARN
#   unit         : str
#   source       : str
#   note         : str or None
#   special      : str or None - set to 'pct_change' for the CO2 change check

def _tol_bounds(ref: float, outer: float, inner: Optional[float] = None):
    """Build (outer_lo, outer_hi, inner_lo, inner_hi) from reference and tolerance fractions."""
    tol_in = inner if inner is not None else outer
    return (
        ref * (1.0 - outer),
        ref * (1.0 + outer),
        ref * (1.0 - tol_in),
        ref * (1.0 + tol_in),
    )


_co2_ol, _co2_oh, _co2_il, _co2_ih = _tol_bounds(37_646.0, 0.20, 0.10)
_ch4_ol, _ch4_oh, _ch4_il, _ch4_ih = _tol_bounds(379.0,    0.20, 0.20)
_pe_ol,  _pe_oh,  _pe_il,  _pe_ih  = _tol_bounds(578.0,    0.20, 0.10)
_nuc_ol, _nuc_oh, _nuc_il, _nuc_ih = _tol_bounds(9.77,     0.30, 0.20)
_sw_ol,  _sw_oh,  _sw_il,  _sw_ih  = _tol_bounds(8.51,     0.50, 0.25)

CONSTRAINTS: list[dict] = [
    {
        "name":           "co2_eip_2020",
        "label":          "CO₂ EIP emissions (2020)",
        "required":       ["Emissions|CO2"],
        "compute_fn":     lambda df: df["Emissions|CO2"],
        "year":           2020,
        "reference_unit": "MtCO2",
        "typical_value":  37_646.0,
        "outer_lower":    _co2_ol,
        "outer_upper":    _co2_oh,
        "inner_lower":    _co2_il,
        "inner_upper":    _co2_ih,
        "unit":           "MtCO₂/yr",
        "source":         "EDGAR v6 IPCC and CEDS, 2019 values",
        "note": (
            "Reference value 37,646 MtCO₂/yr (±20% outer, ±10% IP range). "
            "Emissions|CO2 in IAM databases covers EIP (energy and industrial "
            "processes) only; AFOLU CO₂ is excluded."
        ),
    },
    {
        "name":           "ch4_2020",
        "label":          "CH₄ emissions (2020)",
        "required":       ["Emissions|CH4"],
        "compute_fn":     lambda df: df["Emissions|CH4"],
        "year":           2020,
        "reference_unit": "MtCH4",
        "typical_value":  379.0,
        "outer_lower":    _ch4_ol,
        "outer_upper":    _ch4_oh,
        "inner_lower":    _ch4_il,
        "inner_upper":    _ch4_ih,
        "unit":           "MtCH₄/yr",
        "source":         "EDGAR v6 IPCC and CEDS, 2019 values",
        "note":        "Reference value 379 MtCH₄/yr (±20% outer and IP range).",
    },
    {
        "name":           "co2_change_2010_2020",
        "label":          "CO₂ EIP % change 2010–2020",
        "required":       ["Emissions|CO2"],
        "compute_fn":     None,   # handled via 'pct_change' special case
        "year":           [2010, 2020],
        "reference_unit": None,   # dimensionless ratio — no unit conversion needed
        "outer_lower":    0.0,
        "outer_upper":    0.50,
        "inner_lower":    None,
        "inner_upper":    None,
        "unit":           "fraction (0.30 = 30% increase)",
        "source":      "EDGAR v6 IPCC and CEDS, 2019 values",
        "note": (
            "Checks that CO₂ EIP grew by 0–50% from 2010 to 2020. "
            "No IP range defined for this criterion. "
            "Years are matched to the nearest available year in the dataset."
        ),
        "special":     "pct_change",
    },
    {
        "name":           "ccs_2020",
        "label":          "CCS from energy (2020)",
        "required":       ["Carbon Sequestration|CCS"],
        "compute_fn":     lambda df: df["Carbon Sequestration|CCS"],
        "year":           2020,
        "reference_unit": "MtCO2",
        "typical_value":  50.0,
        "outer_lower":    0.0,
        "outer_upper":    250.0,
        "inner_lower":    None,
        "inner_upper":    100.0,
        "unit":           "MtCO₂/yr",
        "source":      "AR6 vetting criteria (Table 11)",
        "note": (
            "Range: 0–250 MtCO₂/yr (outer); 0–100 MtCO₂/yr (IP range upper). "
            "This variable is often absent from energy-system IAM emulators; "
            "check will be skipped if not in the target set."
        ),
    },
    {
        "name":           "primary_energy_2020",
        "label":          "Primary energy total (2020)",
        "required":       ["Primary Energy"],
        "compute_fn":     lambda df: df["Primary Energy"],
        "year":           2020,
        "reference_unit": "EJ",
        "typical_value":  578.0,
        "outer_lower":    _pe_ol,
        "outer_upper":    _pe_oh,
        "inner_lower":    _pe_il,
        "inner_upper":    _pe_ih,
        "unit":           "EJ",
        "source":      "IEA 2019; trends extrapolated to 2020",
        "note": (
            "Reference value 578 EJ (±20% outer, ±10% IP range). "
            "Requires 'Primary Energy' as a direct target variable; skipped "
            "if only sub-components are present."
        ),
    },
    {
        "name":           "nuclear_energy_2020",
        "label":          "Nuclear primary energy (2020)",
        "required":       ["Primary Energy|Nuclear"],
        "compute_fn":     lambda df: df["Primary Energy|Nuclear"],
        "year":           2020,
        "reference_unit": "EJ",
        "typical_value":  9.77,
        "outer_lower":    _nuc_ol,
        "outer_upper":    _nuc_oh,
        "inner_lower":    _nuc_il,
        "inner_upper":    _nuc_ih,
        "unit":           "EJ",
        "source":         "AR6 vetting criteria (Table 11); IEA 2020 direct equivalent",
        "note": (
            "Reference value 9.77 EJ (±30% outer, ±20% IP range). "
            "Uses Primary Energy|Nuclear. The AR6 vetting check is designed to "
            "detect reporting errors from different primary energy accounting "
            "conventions (direct vs thermal equivalent). Secondary energy "
            "electricity cannot substitute — it would not catch such errors."
        ),
    },
    {
        "name":           "solar_wind_2020",
        "label":          "Solar + wind primary energy (2020)",
        "required":       ["Primary Energy|Solar", "Primary Energy|Wind"],
        "typical_value":  8.51,
        "compute_fn":     lambda df: df["Primary Energy|Solar"] + df["Primary Energy|Wind"],
        "year":           2020,
        "reference_unit": "EJ",
        "outer_lower":    _sw_ol,
        "outer_upper":    _sw_oh,
        "inner_lower":    _sw_il,
        "inner_upper":    _sw_ih,
        "unit":           "EJ",
        "source":         "AR6 vetting criteria (Table 11); IEA/IRENA/BP/EMBERS 2020",
        "note": (
            "Reference value 8.51 EJ (±50% outer, ±25% IP range). "
            "Uses Primary Energy|Solar + Primary Energy|Wind. As with nuclear, "
            "the check targets primary energy accounting fidelity specifically."
        ),
    },
]


# ---------------------------------------------------------------------------
# Loading and helpers
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


def build_long(test_data, values, targets):
    index_cols = ["Model", "Scenario", "Region", "Scenario_Category", "Year"]
    idx  = test_data[index_cols].reset_index(drop=True)
    wide = pd.DataFrame(values, columns=targets)
    combined = pd.concat([idx, wide], axis=1)
    return combined.melt(
        id_vars=index_cols,
        value_vars=targets,
        var_name="Variable",
        value_name="Value",
    )


def _nearest_year(available: set, target: int) -> int:
    if target in available:
        return target
    return min(available, key=lambda y: abs(y - target))


IDX = ["Model", "Scenario", "Region", "Scenario_Category"]


# ---------------------------------------------------------------------------
# Per-constraint check logic
# ---------------------------------------------------------------------------

def _filter_world(long: pd.DataFrame, world_region: str) -> tuple[pd.DataFrame, bool]:
    """
    Filter to the global aggregate region.

    AR6 vetting criteria are global values, so these checks must run against
    the World aggregate rather than individual sub-regions. If the specified
    world_region is not present in the data (e.g. a World-only dataset that
    uses a different label), fall back to all rows and return a warning flag.
    """
    if world_region in long["Region"].values:
        return long[long["Region"] == world_region].copy(), False
    else:
        return long.copy(), True  # True = fallback warning


def _run_standard(long: pd.DataFrame, constraint: dict, available_years: set,
                  world_region: str = "World") -> pd.DataFrame:
    """Run a single-year, single-expression constraint check."""
    filtered, fallback = _filter_world(long, world_region)
    if fallback:
        print(f"  [WARN] Region '{world_region}' not found — running against all regions. "
              f"Results may not match global reference values.")

    year   = _nearest_year(available_years, constraint["year"])
    subset = filtered[
        (filtered["Variable"].isin(constraint["required"])) &
        (filtered["Year"] == year)
    ]

    wide = subset.pivot_table(
        index=IDX, columns="Variable", values="Value", aggfunc="first"
    ).reset_index()

    wide["computed_value"] = constraint["compute_fn"](wide)
    wide["year_used"]      = year
    return wide[IDX + ["computed_value", "year_used"]]


def _run_pct_change(long: pd.DataFrame, constraint: dict, available_years: set,
                    world_region: str = "World") -> pd.DataFrame:
    """Run the CO₂ 2010-2020 % change check."""
    filtered, fallback = _filter_world(long, world_region)
    if fallback:
        print(f"  [WARN] Region '{world_region}' not found — running against all regions.")

    y0 = _nearest_year(available_years, constraint["year"][0])
    y1 = _nearest_year(available_years, constraint["year"][1])

    var = constraint["required"][0]
    s0  = filtered[(filtered["Variable"] == var) & (filtered["Year"] == y0)][IDX + ["Value"]].rename(columns={"Value": "v0"})
    s1  = filtered[(filtered["Variable"] == var) & (filtered["Year"] == y1)][IDX + ["Value"]].rename(columns={"Value": "v1"})

    merged = s0.merge(s1, on=IDX)
    merged["computed_value"] = (merged["v1"] - merged["v0"]) / merged["v0"].abs()
    merged["year_used"]      = f"{y0}-{y1}"
    return merged[IDX + ["computed_value", "year_used"]]


def _classify(val: float, outer_lower, outer_upper, inner_lower, inner_upper) -> str:
    """Classify a single value as PASS / WARN / FAIL."""
    outside_outer = (
        (outer_lower is not None and val < outer_lower) or
        (outer_upper is not None and val > outer_upper)
    )
    if outside_outer:
        return "FAIL"

    has_inner = inner_lower is not None or inner_upper is not None
    if has_inner:
        outside_inner = (
            (inner_lower is not None and val < inner_lower) or
            (inner_upper is not None and val > inner_upper)
        )
        if outside_inner:
            return "WARN"

    return "PASS"


_UNITS_WARN_THRESHOLD = 100.0  # flag if median is this many times off the typical value


def check_unit_plausibility(result: pd.DataFrame, constraint: dict) -> Optional[str]:
    """
    Compare the median computed value against the constraint's typical_value.
    If the ratio is more than _UNITS_WARN_THRESHOLD in either direction, return
    a warning string suggesting a possible unit mismatch. Returns None if the
    values look plausible or if no typical_value is defined.
    """
    typical = constraint.get("typical_value")
    if typical is None or typical == 0:
        return None
    if result.empty or result["computed_value"].dropna().empty:
        return None

    median_val = result["computed_value"].median()
    if median_val == 0:
        return None

    ratio = abs(median_val / typical)
    if ratio >= _UNITS_WARN_THRESHOLD or ratio <= 1.0 / _UNITS_WARN_THRESHOLD:
        factor = ratio if ratio >= _UNITS_WARN_THRESHOLD else 1.0 / ratio
        direction = "higher" if median_val > typical else "lower"
        return (
            f"⚠️  POSSIBLE UNIT MISMATCH — median computed value ({median_val:.4g}) "
            f"is ~{factor:.0f}× {direction} than the expected reference "
            f"({typical:.4g} {constraint.get('unit', '')}). "
            f"Are you sure your units config is correct for "
            f"{', '.join(constraint['required'])}?"
        )
    return None


def run_constraint(
    long: pd.DataFrame,
    constraint: dict,
    available_vars: set,
    available_years: set,
    world_region: str = "World",
) -> tuple[pd.DataFrame | None, str, list[str], Optional[str]]:
    """
    Run a single constraint check.

    Returns
    -------
    result_df    : pd.DataFrame or None
    run_status   : 'run' | 'skip'
    missing      : list of missing variable names (empty if run_status == 'run')
    unit_warning : str or None — red-flag message if values look implausible
    """
    missing = [v for v in constraint["required"] if v not in available_vars]
    if missing:
        return None, "skip", missing, None

    special = constraint.get("special")
    if special == "pct_change":
        result = _run_pct_change(long, constraint, available_years, world_region)
    else:
        result = _run_standard(long, constraint, available_years, world_region)

    result["status"] = result["computed_value"].apply(
        lambda v: _classify(
            v,
            constraint["outer_lower"],
            constraint["outer_upper"],
            constraint["inner_lower"],
            constraint["inner_upper"],
        )
    )
    result["constraint_name"] = constraint["name"]
    unit_warning = check_unit_plausibility(result, constraint)
    return result, "run", [], unit_warning


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _bounds_str(constraint: dict) -> str:
    ol = constraint.get("outer_lower")
    oh = constraint.get("outer_upper")
    il = constraint.get("inner_lower")
    ih = constraint.get("inner_upper")
    unit = constraint.get("unit", "")
    outer = f"[{ol:.4g}, {oh:.4g}]" if ol is not None and oh is not None else \
            f"[{ol:.4g}, —]" if ol is not None else f"[—, {oh:.4g}]"
    inner_parts = []
    if il is not None:
        inner_parts.append(f"inner lo: {il:.4g}")
    if ih is not None:
        inner_parts.append(f"inner hi: {ih:.4g}")
    inner = f"  (IP range: {', '.join(inner_parts)})" if inner_parts else ""
    return f"{outer} {unit}{inner}"


def report_constraints_overview(skipped: list[tuple], results: list[pd.DataFrame], constraints_run: list[dict]):
    print(f"\n{'='*60}")
    print("HARD HISTORICAL CONSTRAINTS — OVERVIEW")
    print(f"{'='*60}")

    print(f"\n  Sub-checks defined : {len(CONSTRAINTS)}")
    print(f"  Sub-checks run     : {len(constraints_run)}")
    print(f"  Sub-checks skipped : {len(skipped)}")

    if skipped:
        print(f"\n  Skipped (missing variables):")
        for name, missing in skipped:
            print(f"    {name:<30}  missing: {', '.join(missing)}")


def report_per_constraint(result: pd.DataFrame, constraint: dict):
    name  = constraint["name"]
    label = constraint["label"]
    n     = len(result)
    if n == 0:
        print(f"\n  {label}: no data.")
        return

    counts = result["status"].value_counts()
    n_pass = counts.get("PASS", 0)
    n_warn = counts.get("WARN", 0)
    n_fail = counts.get("FAIL", 0)

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Bounds : {_bounds_str(constraint)}")
    if constraint.get("note"):
        print(f"  Note   : {constraint['note']}")
    print(f"{'='*60}")
    print(f"  Scenario-regions: {n:,}")
    print(f"    PASS : {n_pass:>6,}  ({100*n_pass/n:.1f}%)")
    print(f"    WARN : {n_warn:>6,}  ({100*n_warn/n:.1f}%)  (within outer, outside IP range)")
    print(f"    FAIL : {n_fail:>6,}  ({100*n_fail/n:.1f}%)")

    print(f"\n  Value distribution:")
    for p, q in zip([0, 5, 25, 50, 75, 95, 100],
                    np.percentile(result["computed_value"].dropna(), [0, 5, 25, 50, 75, 95, 100])):
        print(f"    p{p:>3}: {q:>12.4g}  {constraint['unit']}")

    if n_fail > 0:
        print(f"\n  Worst FAIL cases (by deviation from outer bounds):")
        fails = result[result["status"] == "FAIL"].copy()
        ol = constraint.get("outer_lower")
        oh = constraint.get("outer_upper")
        fails["deviation"] = fails["computed_value"].apply(
            lambda v: max(
                (ol - v) if ol is not None and v < ol else 0.0,
                (v - oh) if oh is not None and v > oh else 0.0,
            )
        )
        for _, row in fails.nlargest(10, "deviation").iterrows():
            print(
                f"    {row['Model']:<20} | {row['Scenario']:<25} | {row['Region']:<15}  "
                f"value: {row['computed_value']:>10.4g}  year: {row['year_used']}"
            )


def report_summary_table(results: list[pd.DataFrame], constraints_run: list[dict]):
    print(f"\n{'='*60}")
    print("SUMMARY TABLE (pass/warn/fail rates per sub-check)")
    print(f"{'='*60}")
    for result, constraint in zip(results, constraints_run):
        n     = len(result)
        if n == 0:
            continue
        counts = result["status"].value_counts()
        n_pass = counts.get("PASS", 0)
        n_warn = counts.get("WARN", 0)
        n_fail = counts.get("FAIL", 0)
        print(
            f"  {constraint['name']:<30}  "
            f"PASS {100*n_pass/n:5.1f}%  "
            f"WARN {100*n_warn/n:5.1f}%  "
            f"FAIL {100*n_fail/n:5.1f}%"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Hard historical constraints check for ML-IAM predictions"
    )
    parser.add_argument("--run_id", required=True, help="Run ID, e.g. xgb_04")
    parser.add_argument(
        "--use_ground_truth", action="store_true",
        help="Check AR6 ground truth instead of model predictions."
    )
    parser.add_argument(
        "--world_region", type=str, default="World",
        help=(
            "Region label used for the global aggregate (default: 'World'). "
            "All checks are run against this region only, since the AR6 vetting "
            "criteria are global values. If this label is not present in the data, "
            "falls back to all regions with a warning."
        )
    )
    parser.add_argument(
        "--units_config", type=str, default=None,
        help=(
            "Path to a JSON file mapping variable names to units "
            "(e.g. {\"Primary Energy|Nuclear\": \"PJ/yr\"}). "
            "If not provided, the framework attempts to load units from ml-iam's "
            "configs.data.UNITS_BY_OUTPUT. Variables whose units cannot be "
            "determined are used as-is with a warning."
        )
    )
    args = parser.parse_args()

    test_data, preds, y_test, targets = load_predictions(args.run_id)

    values     = y_test if args.use_ground_truth else preds
    out_subdir = "hard_historical_constraints_ground_truth" if args.use_ground_truth \
                 else "hard_historical_constraints"

    out_dir = REPO_ROOT / "results" / "xgb" / args.run_id / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = _Tee(out_dir / "report.txt")

    long = build_long(test_data, values, targets)
    available_regions = set(long["Region"].unique())

    print(f"\n  Available years in dataset    : {sorted(long['Year'].unique())}")
    print(f"  Available variables           : {long['Variable'].nunique()}")
    print(f"  Available regions             : {len(available_regions)}")
    print(f"  World region label            : '{args.world_region}'")
    if args.world_region in available_regions:
        n_world = long[long["Region"] == args.world_region]["Scenario"].nunique()
        print(f"  World-level scenarios found   : {n_world}")
    else:
        print(f"  [WARN] '{args.world_region}' not in data — will fall back to all regions")

    # Normalise all variables to canonical units before running any checks
    units_map = load_units_map(REPO_ROOT, args.units_config)
    long = normalize_to_canonical(long, units_map)

    available_vars  = set(long["Variable"].unique())
    available_years = set(long["Year"].unique())

    # Run all constraints
    skipped         = []   # list of (name, missing_vars)
    results         = []   # list of DataFrames, one per run constraint
    constraints_run = []   # list of constraint dicts that ran
    unit_warnings   = []   # list of (name, warning_str) for plausibility flags

    for constraint in CONSTRAINTS:
        result, status, missing, unit_warn = run_constraint(
            long, constraint, available_vars, available_years, args.world_region
        )
        if status == "skip":
            print(f"\n  Skipping '{constraint['name']}': missing variables: {missing}")
            skipped.append((constraint["name"], missing))
        else:
            results.append(result)
            constraints_run.append(constraint)
            if unit_warn:
                print(f"\n  *** UNIT WARNING *** {unit_warn}")
                unit_warnings.append((constraint["name"], unit_warn))

    # Reports
    report_constraints_overview(skipped, results, constraints_run)
    for result, constraint in zip(results, constraints_run):
        report_per_constraint(result, constraint)
    report_summary_table(results, constraints_run)

    # Save outputs
    all_results = []
    for result, constraint in zip(results, constraints_run):
        all_results.append(result)

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        combined.to_csv(out_dir / "all_results.csv", index=False)
        combined[combined["status"] == "FAIL"].to_csv(out_dir / "failures.csv", index=False)
        combined[combined["status"] == "WARN"].to_csv(out_dir / "warnings.csv", index=False)

    # Skipped summary
    if skipped:
        pd.DataFrame(skipped, columns=["constraint_name", "missing_variables"]).to_csv(
            out_dir / "skipped.csv", index=False
        )

    # Unit warnings
    if unit_warnings:
        pd.DataFrame(unit_warnings, columns=["constraint_name", "warning"]).to_csv(
            out_dir / "unit_warnings.csv", index=False
        )

    print(f"\n{'='*60}")
    print(f"Results saved to: {out_dir}")
    print(f"{'='*60}\n")

    if isinstance(sys.stdout, _Tee):
        sys.stdout.close()


if __name__ == "__main__":
    main()
