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
# Constraint definitions
# ---------------------------------------------------------------------------
# Each entry describes one sub-check. Fields:
#
#   name         : str       - identifier used in output and reports
#   label        : str       - human-readable description
#   required     : list[str] - variables that must all be in the run's targets;
#                              if any are missing the check is skipped
#   compute_fn   : callable(wide_df) -> pd.Series, or None for special cases
#                  wide_df has one row per scenario-region, columns are variables
#   year         : int or list[int] - reference year(s) to extract
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
        "name":        "co2_eip_2020",
        "label":       "CO₂ EIP emissions (2020)",
        "required":    ["Emissions|CO2"],
        "compute_fn":  lambda df: df["Emissions|CO2"],
        "year":        2020,
        "outer_lower": _co2_ol,
        "outer_upper": _co2_oh,
        "inner_lower": _co2_il,
        "inner_upper": _co2_ih,
        "unit":        "MtCO₂/yr",
        "source":      "EDGAR v6 IPCC and CEDS, 2019 values",
        "note": (
            "Reference value 37,646 MtCO₂/yr (±20% outer, ±10% IP range). "
            "Emissions|CO2 in IAM databases covers EIP (energy and industrial "
            "processes) only; AFOLU CO₂ is excluded."
        ),
    },
    {
        "name":        "ch4_2020",
        "label":       "CH₄ emissions (2020)",
        "required":    ["Emissions|CH4"],
        "compute_fn":  lambda df: df["Emissions|CH4"],
        "year":        2020,
        "outer_lower": _ch4_ol,
        "outer_upper": _ch4_oh,
        "inner_lower": _ch4_il,
        "inner_upper": _ch4_ih,
        "unit":        "MtCH₄/yr",
        "source":      "EDGAR v6 IPCC and CEDS, 2019 values",
        "note":        "Reference value 379 MtCH₄/yr (±20% outer and IP range).",
    },
    {
        "name":        "co2_change_2010_2020",
        "label":       "CO₂ EIP % change 2010–2020",
        "required":    ["Emissions|CO2"],
        "compute_fn":  None,   # handled via 'pct_change' special case
        "year":        [2010, 2020],
        "outer_lower": 0.0,    # stored as fraction, e.g. 0.0 = no change
        "outer_upper": 0.50,   # 50% increase
        "inner_lower": None,
        "inner_upper": None,
        "unit":        "fraction (0.30 = 30% increase)",
        "source":      "EDGAR v6 IPCC and CEDS, 2019 values",
        "note": (
            "Checks that CO₂ EIP grew by 0–50% from 2010 to 2020. "
            "No IP range defined for this criterion. "
            "Years are matched to the nearest available year in the dataset."
        ),
        "special":     "pct_change",
    },
    {
        "name":        "ccs_2020",
        "label":       "CCS from energy (2020)",
        "required":    ["Carbon Sequestration|CCS"],
        "compute_fn":  lambda df: df["Carbon Sequestration|CCS"],
        "year":        2020,
        "outer_lower": 0.0,
        "outer_upper": 250.0,
        "inner_lower": None,
        "inner_upper": 100.0,
        "unit":        "MtCO₂/yr",
        "source":      "AR6 vetting criteria (Table 11)",
        "note": (
            "Range: 0–250 MtCO₂/yr (outer); 0–100 MtCO₂/yr (IP range upper). "
            "This variable is often absent from energy-system IAM emulators; "
            "check will be skipped if not in the target set."
        ),
    },
    {
        "name":        "primary_energy_2020",
        "label":       "Primary energy total (2020)",
        "required":    ["Primary Energy"],
        "compute_fn":  lambda df: df["Primary Energy"],
        "year":        2020,
        "outer_lower": _pe_ol,
        "outer_upper": _pe_oh,
        "inner_lower": _pe_il,
        "inner_upper": _pe_ih,
        "unit":        "EJ",
        "source":      "IEA 2019; trends extrapolated to 2020",
        "note": (
            "Reference value 578 EJ (±20% outer, ±10% IP range). "
            "Requires 'Primary Energy' as a direct target variable; skipped "
            "if only sub-components are present."
        ),
    },
    {
        "name":        "nuclear_energy_2020",
        "label":       "Nuclear primary energy (2020)",
        "required":    ["Primary Energy|Nuclear"],
        "compute_fn":  lambda df: df["Primary Energy|Nuclear"],
        "year":        2020,
        "outer_lower": _nuc_ol,
        "outer_upper": _nuc_oh,
        "inner_lower": _nuc_il,
        "inner_upper": _nuc_ih,
        "unit":        "EJ",
        "source":      "IEA 2020 (direct equivalent accounting)",
        "note":        "Reference value 9.77 EJ (±30% outer, ±20% IP range).",
    },
    {
        "name":        "solar_wind_2020",
        "label":       "Solar + wind primary energy (2020)",
        "required":    ["Primary Energy|Solar", "Primary Energy|Wind"],
        "compute_fn":  lambda df: df["Primary Energy|Solar"] + df["Primary Energy|Wind"],
        "year":        2020,
        "outer_lower": _sw_ol,
        "outer_upper": _sw_oh,
        "inner_lower": _sw_il,
        "inner_upper": _sw_ih,
        "unit":        "EJ",
        "source":      "IEA 2020, IRENA, BP, EMBERS; trends extrapolated to 2020",
        "note": (
            "Reference value 8.51 EJ (±50% outer, ±25% IP range). "
            "Computed as Primary Energy|Solar + Primary Energy|Wind."
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


def run_constraint(
    long: pd.DataFrame,
    constraint: dict,
    available_vars: set,
    available_years: set,
    world_region: str = "World",
) -> tuple[pd.DataFrame | None, str, list[str]]:
    """
    Run a single constraint check.

    Returns
    -------
    result_df : pd.DataFrame or None
    run_status: 'run' | 'skip'
    missing   : list of missing variable names (empty if run_status == 'run')
    """
    missing = [v for v in constraint["required"] if v not in available_vars]
    if missing:
        return None, "skip", missing

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
    return result, "run", []


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
    args = parser.parse_args()

    test_data, preds, y_test, targets = load_predictions(args.run_id)

    values     = y_test if args.use_ground_truth else preds
    out_subdir = "hard_historical_constraints_ground_truth" if args.use_ground_truth \
                 else "hard_historical_constraints"

    out_dir = REPO_ROOT / "results" / "xgb" / args.run_id / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = _Tee(out_dir / "report.txt")

    long = build_long(test_data, values, targets)
    available_vars  = set(long["Variable"].unique())
    available_years = set(long["Year"].unique())
    available_regions = set(long["Region"].unique())

    print(f"\n  Available years in dataset    : {sorted(available_years)}")
    print(f"  Available variables           : {len(available_vars)}")
    print(f"  Available regions             : {len(available_regions)}")
    print(f"  World region label            : '{args.world_region}'")
    if args.world_region in available_regions:
        n_world = long[long["Region"] == args.world_region]["Scenario"].nunique()
        print(f"  World-level scenarios found   : {n_world}")
    else:
        print(f"  [WARN] '{args.world_region}' not in data — will fall back to all regions")

    # Run all constraints
    skipped         = []   # list of (name, missing_vars)
    results         = []   # list of DataFrames, one per run constraint
    constraints_run = []   # list of constraint dicts that ran

    for constraint in CONSTRAINTS:
        result, status, missing = run_constraint(
            long, constraint, available_vars, available_years, args.world_region
        )
        if status == "skip":
            print(f"\n  Skipping '{constraint['name']}': missing variables: {missing}")
            skipped.append((constraint["name"], missing))
        else:
            results.append(result)
            constraints_run.append(constraint)

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

    print(f"\n{'='*60}")
    print(f"Results saved to: {out_dir}")
    print(f"{'='*60}\n")

    if isinstance(sys.stdout, _Tee):
        sys.stdout.close()


if __name__ == "__main__":
    main()
