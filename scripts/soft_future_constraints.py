"""
Soft future constraints check for ML-IAM predictions.

Checks predicted values at specific future years against domain-knowledge
plausibility bounds drawn from the AR6 scenario vetting process (Table 11,
Nicholls et al. 2022). These criteria were used in AR6 not as hard exclusion
rules but as flags for potentially problematic scenarios.

Unlike the hard historical constraints (which check against observed 2020
data), these checks are warranted through the constraint-violation argument:
the IAMs were themselves vetted against these criteria, so if an emulator
violates them where the parent IAM would not, that is an emulation failure.

Available sub-checks:

  co2_not_negative_2030     -- CO₂ total (EIP) > 0 in 2030
  ccs_2030                  -- CCS from energy in 2030 < 2,000 MtCO₂/yr
  nuclear_electricity_2030  -- Electricity from nuclear in 2030 < 20 EJ/yr
  ch4_2040                  -- CH₄ emissions in 2040 in [100, 1000] MtCH₄/yr

Each sub-check requires specific variables. If they are absent from this
run's target set the sub-check is automatically skipped and recorded as such.

Each scenario-region is classified as:
  PASS  -- meets the criterion
  FAIL  -- violates the criterion
  SKIP  -- required variable(s) not present in this run

Belongs to the 'Historical and domain knowledge comparison' validation family.

Usage:
    python soft_future_constraints.py --run_id xgb_04
    python soft_future_constraints.py --run_id xgb_04 --use_ground_truth
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
# Constraint definitions
# ---------------------------------------------------------------------------
# Each entry describes one sub-check. Fields:
#
#   name         : str       - identifier used in output and reports
#   label        : str       - human-readable description
#   required     : list[str] - variables that must all be in the run's targets
#   compute_fn   : callable(wide_df) -> pd.Series
#                  wide_df has one row per scenario-region, columns are variables
#   year         : int       - year at which to evaluate the constraint
#   lower_bound  : float or None - value must be >= this (None = no lower bound)
#   upper_bound  : float or None - value must be <= this (None = no upper bound)
#   unit         : str
#   source       : str
#   note         : str or None

CONSTRAINTS: list[dict] = [
    {
        "name":        "co2_not_negative_2030",
        "label":       "No net-negative CO₂ before 2030",
        "required":    ["Emissions|CO2"],
        "compute_fn":  lambda df: df["Emissions|CO2"],
        "year":        2030,
        "lower_bound": 0.0,
        "upper_bound": None,
        "unit":        "MtCO₂/yr",
        "source":      "AR6 vetting criteria (Table 11)",
        "note": (
            "CO₂ total (EIP) must remain positive in 2030. Net-negative CO₂ "
            "before 2030 is considered physically implausible given current CCS "
            "deployment rates. Checks Emissions|CO2 > 0 at 2030."
        ),
    },
    {
        "name":          "ccs_2030",
        "label":         "CCS from energy in 2030 < 2,000 MtCO₂/yr",
        "required":      ["Carbon Sequestration|CCS"],
        "compute_fn":    lambda df: df["Carbon Sequestration|CCS"],
        "year":          2030,
        "typical_value": 300.0,
        "lower_bound":   None,
        "upper_bound":   2_000.0,
        "unit":        "MtCO₂/yr",
        "source":      "AR6 vetting criteria (Table 11)",
        "note": (
            "CCS deployment above 2,000 MtCO₂/yr by 2030 is considered "
            "implausible given current and near-term infrastructure capacity. "
            "This variable is often absent from energy-system IAM emulators; "
            "check will be skipped if not in the target set."
        ),
    },
    {
        "name":          "nuclear_electricity_2030",
        "label":         "Electricity from nuclear in 2030 < 20 EJ/yr",
        "required":      ["Secondary Energy|Electricity|Nuclear"],
        "compute_fn":    lambda df: df["Secondary Energy|Electricity|Nuclear"],
        "year":          2030,
        "typical_value": 12.0,
        "lower_bound":   None,
        "upper_bound":   20.0,
        "unit":        "EJ/yr",
        "source":      "AR6 vetting criteria (Table 11)",
        "note": (
            "Electricity from nuclear above 20 EJ/yr by 2030 is considered "
            "implausible given current capacity and build rates. "
            "Uses Secondary Energy|Electricity|Nuclear."
        ),
    },
    {
        "name":          "ch4_2040",
        "label":         "CH₄ emissions in 2040 in [100, 1000] MtCH₄/yr",
        "required":      ["Emissions|CH4"],
        "compute_fn":    lambda df: df["Emissions|CH4"],
        "year":          2040,
        "typical_value": 300.0,
        "lower_bound":   100.0,
        "upper_bound":   1_000.0,
        "unit":        "MtCH₄/yr",
        "source":      "AR6 vetting criteria (Table 11)",
        "note": (
            "CH₄ emissions below 100 or above 1,000 MtCH₄/yr in 2040 are "
            "considered implausible. Values below 100 imply implausibly rapid "
            "methane abatement; values above 1,000 imply no mitigation at all."
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
# Unit normalisation (shared logic — see hard_historical_constraints.py)
# ---------------------------------------------------------------------------

_CONVERSIONS: dict[tuple[str, str], float] = {
    ("PJ",      "EJ"):      1e-3,
    ("EJ",      "PJ"):      1e3,
    ("PJ/yr",   "EJ/yr"):   1e-3,
    ("EJ/yr",   "PJ/yr"):   1e3,
    ("GJ",      "EJ"):      1e-9,
    ("TJ",      "EJ"):      1e-6,
    ("GtCO2",    "MtCO2"):  1e3,
    ("MtCO2",    "GtCO2"):  1e-3,
    ("GtCO2/yr", "MtCO2/yr"): 1e3,
    ("MtC",      "MtCO2"):  44.0 / 12.0,
    ("GtC",      "MtCO2"):  44.0 / 12.0 * 1e3,
    ("Mt CO2/yr",  "MtCO2/yr"): 1.0,
    ("Mt CO2",     "MtCO2"):    1.0,
    ("Gt CO2/yr",  "MtCO2/yr"): 1e3,
    ("Mt CH4/yr",  "MtCH4/yr"): 1.0,
    ("Mt CH4",     "MtCH4"):    1.0,
    ("Mt N2O/yr",  "MtN2O/yr"): 1.0,
    ("Mt N2O",     "MtN2O"):    1.0,
    ("GtCH4",   "MtCH4"):   1e3,
    ("MtCH4",   "GtCH4"):   1e-3,
    ("GtN2O",   "MtN2O"):   1e3,
    ("MtN2O",   "GtN2O"):   1e-3,
}

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
    for prefix, unit in _VAR_CANONICAL:
        if variable.startswith(prefix):
            return unit
    return None


def _conversion_factor(from_unit: str, to_unit: str) -> Optional[float]:
    f, t = from_unit.strip(), to_unit.strip()
    f_base = f.rstrip("/yr")
    t_base = t.rstrip("/yr")
    if f == t or f_base == t_base:
        return 1.0
    return _CONVERSIONS.get((f, t)) or _CONVERSIONS.get((f_base, t_base))


def load_units_map(repo_root: Path, units_config_path: Optional[str] = None) -> dict[str, str]:
    if units_config_path:
        import json
        try:
            with open(units_config_path) as fh:
                units = json.load(fh)
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


def normalize_to_canonical(long: pd.DataFrame, units_map: dict[str, str]) -> pd.DataFrame:
    long = long.copy()
    converted, warned = [], []
    for var in long["Variable"].unique():
        target_unit = _canonical_unit_for(var)
        if target_unit is None:
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
# Per-constraint check logic
# ---------------------------------------------------------------------------

def _filter_world(long: pd.DataFrame, world_region: str) -> tuple[pd.DataFrame, bool]:
    """
    Filter to the global aggregate region.

    AR6 vetting criteria are global values, so these checks must run against
    the World aggregate rather than individual sub-regions. Falls back to all
    rows with a warning flag if the world_region label is not present.
    """
    if world_region in long["Region"].values:
        return long[long["Region"] == world_region].copy(), False
    else:
        return long.copy(), True


_UNITS_WARN_THRESHOLD = 100.0


def check_unit_plausibility(result: pd.DataFrame, constraint: dict) -> Optional[str]:
    """Return a warning string if computed values look implausibly off from the typical value."""
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
    unit_warning : str or None
    """
    missing = [v for v in constraint["required"] if v not in available_vars]
    if missing:
        return None, "skip", missing, None

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

    lo = constraint["lower_bound"]
    hi = constraint["upper_bound"]
    wide["status"] = wide["computed_value"].apply(
        lambda v: "FAIL" if (
            (lo is not None and v < lo) or
            (hi is not None and v > hi)
        ) else "PASS"
    )
    wide["constraint_name"] = constraint["name"]

    unit_warning = check_unit_plausibility(wide, constraint)
    return wide[IDX + ["computed_value", "year_used", "status", "constraint_name"]], "run", [], unit_warning


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _bounds_str(constraint: dict) -> str:
    lo   = constraint["lower_bound"]
    hi   = constraint["upper_bound"]
    unit = constraint["unit"]
    lo_s = f"{lo:.4g}" if lo is not None else "—"
    hi_s = f"{hi:.4g}" if hi is not None else "—"
    return f"[{lo_s}, {hi_s}] {unit}"


def report_overview(skipped: list, results: list, constraints_run: list):
    print(f"\n{'='*60}")
    print("SOFT FUTURE CONSTRAINTS — OVERVIEW")
    print(f"{'='*60}")
    print(f"\n  Sub-checks defined : {len(CONSTRAINTS)}")
    print(f"  Sub-checks run     : {len(constraints_run)}")
    print(f"  Sub-checks skipped : {len(skipped)}")

    if skipped:
        print(f"\n  Skipped (missing variables):")
        for name, missing in skipped:
            print(f"    {name:<35}  missing: {', '.join(missing)}")


def report_per_constraint(result: pd.DataFrame, constraint: dict):
    n = len(result)
    if n == 0:
        print(f"\n  {constraint['label']}: no data.")
        return

    n_pass = (result["status"] == "PASS").sum()
    n_fail = (result["status"] == "FAIL").sum()

    print(f"\n{'='*60}")
    print(f"  {constraint['label']}")
    print(f"  Bounds : {_bounds_str(constraint)}")
    print(f"  Year   : {constraint['year']} (nearest available used)")
    if constraint.get("note"):
        print(f"  Note   : {constraint['note']}")
    print(f"{'='*60}")
    print(f"  Scenario-regions: {n:,}")
    print(f"    PASS : {n_pass:>6,}  ({100*n_pass/n:.1f}%)")
    print(f"    FAIL : {n_fail:>6,}  ({100*n_fail/n:.1f}%)")

    print(f"\n  Value distribution (at year {result['year_used'].iloc[0]}):")
    for p, q in zip([0, 5, 25, 50, 75, 95, 100],
                    np.percentile(result["computed_value"].dropna(), [0, 5, 25, 50, 75, 95, 100])):
        print(f"    p{p:>3}: {q:>12.4g}  {constraint['unit']}")

    if n_fail > 0:
        print(f"\n  Failing scenarios (up to 15):")
        lo = constraint["lower_bound"]
        hi = constraint["upper_bound"]
        fails = result[result["status"] == "FAIL"].copy()
        fails["deviation"] = fails["computed_value"].apply(
            lambda v: max(
                (lo - v) if lo is not None and v < lo else 0.0,
                (v - hi) if hi is not None and v > hi else 0.0,
            )
        )
        for _, row in fails.nlargest(15, "deviation").iterrows():
            print(
                f"    {row['Model']:<20} | {row['Scenario']:<25} | {row['Region']:<15}  "
                f"value: {row['computed_value']:>10.4g}"
            )


def report_by_category(results: list, constraints_run: list):
    print(f"\n{'='*60}")
    print("FAIL RATES BY SCENARIO CATEGORY")
    print(f"{'='*60}")
    for result, constraint in zip(results, constraints_run):
        cat = (
            result.groupby("Scenario_Category")
            .agg(total=("status", "count"), fails=("status", lambda x: (x == "FAIL").sum()))
            .reset_index()
        )
        cat["fail_pct"] = 100 * cat["fails"] / cat["total"]
        cat = cat.sort_values("fail_pct", ascending=False)
        print(f"\n  {constraint['label']}")
        for _, row in cat.iterrows():
            bar = "!" * int(row["fail_pct"] / 5)
            print(
                f"    {str(row['Scenario_Category']):<20}  "
                f"fail: {int(row['fails']):>5} / {int(row['total']):<5}  "
                f"({row['fail_pct']:5.1f}%)  {bar}"
            )


def report_summary_table(results: list, constraints_run: list):
    print(f"\n{'='*60}")
    print("SUMMARY TABLE")
    print(f"{'='*60}")
    for result, constraint in zip(results, constraints_run):
        n      = len(result)
        n_pass = (result["status"] == "PASS").sum()
        n_fail = (result["status"] == "FAIL").sum()
        print(
            f"  {constraint['name']:<35}  "
            f"PASS {100*n_pass/n:5.1f}%  "
            f"FAIL {100*n_fail/n:5.1f}%"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Soft future constraints check for ML-IAM predictions"
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
            "criteria are global values. Falls back to all regions with a warning "
            "if this label is absent."
        )
    )
    parser.add_argument(
        "--units_config", type=str, default=None,
        help=(
            "Path to a JSON file mapping variable names to units. "
            "If not provided, attempts to load from ml-iam's configs.data. "
            "Variables with unknown units are used as-is with a warning."
        )
    )
    args = parser.parse_args()

    test_data, preds, y_test, targets = load_predictions(args.run_id)

    values     = y_test if args.use_ground_truth else preds
    out_subdir = "soft_future_constraints_ground_truth" if args.use_ground_truth \
                 else "soft_future_constraints"

    out_dir = REPO_ROOT / "results" / "xgb" / args.run_id / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = _Tee(out_dir / "report.txt")

    long = build_long(test_data, values, targets)
    available_regions = set(long["Region"].unique())

    print(f"\n  Available years in dataset    : {sorted(long['Year'].unique())}")
    print(f"  Available variables           : {long['Variable'].nunique()}")
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

    skipped         = []
    results         = []
    constraints_run = []
    unit_warnings   = []

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

    report_overview(skipped, results, constraints_run)
    for result, constraint in zip(results, constraints_run):
        report_per_constraint(result, constraint)
    report_by_category(results, constraints_run)
    report_summary_table(results, constraints_run)

    if results:
        combined = pd.concat(results, ignore_index=True)
        combined.to_csv(out_dir / "all_results.csv", index=False)
        combined[combined["status"] == "FAIL"].to_csv(out_dir / "failures.csv", index=False)

    if skipped:
        pd.DataFrame(skipped, columns=["constraint_name", "missing_variables"]).to_csv(
            out_dir / "skipped.csv", index=False
        )

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
