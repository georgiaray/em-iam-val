"""
Hard historical constraints check.

Checks World-level predictions at the 2020 reference year against the
historical anchor values used in the AR6 scenario vetting process
(Table 11, Nicholls et al. 2022).

Each sub-check requires specific variables. If they are absent from the
dataset, that sub-check is skipped and recorded.

Status per scenario:
    PASS  — within inner (IP-range) tolerance
    WARN  — within outer tolerance but outside inner
    FAIL  — outside outer tolerance

Belongs to the 'Historical and domain knowledge comparison' validation family.

Usage (standalone):
    python checks/hard_historical_constraints.py \\
        --predictions adapted-data/xgb_04_predictions.csv \\
        --ground_truth adapted-data/xgb_04_ground_truth.csv \\
        --run_id xgb_04
"""

import sys
from pathlib import Path
from typing import Optional
import argparse
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import (
    IDX, load_csv, normalize_to_canonical,
    make_out_dir, save_check_outputs,
    _nearest_year, _filter_world, _UNITS_WARN_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Constraint definitions  (all bounds in canonical units: EJ, MtCO2, MtCH4)
# ---------------------------------------------------------------------------

def _tol(ref, outer, inner=None):
    i = inner if inner is not None else outer
    return ref*(1-outer), ref*(1+outer), ref*(1-i), ref*(1+i)


_co2_ol, _co2_oh, _co2_il, _co2_ih = _tol(37_646, 0.20, 0.10)
_ch4_ol, _ch4_oh, _ch4_il, _ch4_ih = _tol(379,    0.20, 0.20)
_pe_ol,  _pe_oh,  _pe_il,  _pe_ih  = _tol(578,    0.20, 0.10)
_nuc_ol, _nuc_oh, _nuc_il, _nuc_ih = _tol(9.77,   0.30, 0.20)
_sw_ol,  _sw_oh,  _sw_il,  _sw_ih  = _tol(8.51,   0.50, 0.25)

CONSTRAINTS: list[dict] = [
    {
        "name": "co2_eip_2020", "label": "CO2 EIP emissions (2020)",
        "required": ["Emissions|CO2"],
        "compute_fn": lambda df: df["Emissions|CO2"],
        "year": 2020,
        "outer_lower": _co2_ol, "outer_upper": _co2_oh,
        "inner_lower": _co2_il, "inner_upper": _co2_ih,
        "unit": "MtCO2/yr", "typical_value": 37_646,
        "source": "EDGAR v6 IPCC and CEDS, 2019 values",
        "note": "Reference 37,646 MtCO2/yr (+-20% outer, +-10% IP). EIP only.",
    },
    {
        "name": "ch4_2020", "label": "CH4 emissions (2020)",
        "required": ["Emissions|CH4"],
        "compute_fn": lambda df: df["Emissions|CH4"],
        "year": 2020,
        "outer_lower": _ch4_ol, "outer_upper": _ch4_oh,
        "inner_lower": _ch4_il, "inner_upper": _ch4_ih,
        "unit": "MtCH4/yr", "typical_value": 379,
        "source": "EDGAR v6 IPCC and CEDS, 2019 values",
        "note": "Reference 379 MtCH4/yr (+-20% outer and IP range).",
    },
    {
        "name": "co2_change_2010_2020", "label": "CO2 EIP % change 2010-2020",
        "required": ["Emissions|CO2"],
        "compute_fn": None,  # handled via special='pct_change'
        "year": [2010, 2020],
        "outer_lower": 0.0, "outer_upper": 0.50,
        "inner_lower": None, "inner_upper": None,
        "unit": "fraction", "typical_value": None,
        "source": "EDGAR v6 IPCC and CEDS, 2019 values",
        "note": "Checks CO2 EIP grew 0-50% from 2010 to 2020.",
        "special": "pct_change",
    },
    {
        "name": "ccs_2020", "label": "CCS from energy (2020)",
        "required": ["Carbon Sequestration|CCS"],
        "compute_fn": lambda df: df["Carbon Sequestration|CCS"],
        "year": 2020,
        "outer_lower": 0.0, "outer_upper": 250.0,
        "inner_lower": None, "inner_upper": 100.0,
        "unit": "MtCO2/yr", "typical_value": 50,
        "source": "AR6 vetting criteria (Table 11)",
        "note": "Range 0-250 outer; 0-100 IP. Often absent from target set.",
    },
    {
        "name": "primary_energy_2020", "label": "Primary energy total (2020)",
        "required": ["Primary Energy"],
        "compute_fn": lambda df: df["Primary Energy"],
        "year": 2020,
        "outer_lower": _pe_ol, "outer_upper": _pe_oh,
        "inner_lower": _pe_il, "inner_upper": _pe_ih,
        "unit": "EJ", "typical_value": 578,
        "source": "IEA 2019; trends extrapolated to 2020",
        "note": "Reference 578 EJ (+-20% outer, +-10% IP).",
    },
    {
        "name": "nuclear_energy_2020", "label": "Nuclear primary energy (2020)",
        "required": ["Primary Energy|Nuclear"],
        "compute_fn": lambda df: df["Primary Energy|Nuclear"],
        "year": 2020,
        "outer_lower": _nuc_ol, "outer_upper": _nuc_oh,
        "inner_lower": _nuc_il, "inner_upper": _nuc_ih,
        "unit": "EJ", "typical_value": 9.77,
        "source": "AR6 vetting criteria; IEA 2020 direct equivalent",
        "note": "Reference 9.77 EJ (+-30% outer, +-20% IP). Primary Energy|Nuclear checks "
                "primary energy accounting convention (direct vs thermal equivalent).",
    },
    {
        "name": "solar_wind_2020", "label": "Solar + wind primary energy (2020)",
        "required": ["Primary Energy|Solar", "Primary Energy|Wind"],
        "compute_fn": lambda df: df["Primary Energy|Solar"] + df["Primary Energy|Wind"],
        "year": 2020,
        "outer_lower": _sw_ol, "outer_upper": _sw_oh,
        "inner_lower": _sw_il, "inner_upper": _sw_ih,
        "unit": "EJ", "typical_value": 8.51,
        "source": "AR6 vetting criteria; IEA/IRENA/BP/EMBERS 2020",
        "note": "Reference 8.51 EJ (+-50% outer, +-25% IP). Primary Energy|Solar + Wind.",
    },
]


# ---------------------------------------------------------------------------
# Check logic
# ---------------------------------------------------------------------------

def _classify(val, outer_lower, outer_upper, inner_lower, inner_upper) -> str:
    if pd.isna(val):
        return "MISSING"
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


def _run_standard(long: pd.DataFrame, constraint: dict,
                  available_years: set) -> pd.DataFrame:
    """Run a single-year constraint. Returns one row per scenario."""
    year = _nearest_year(available_years, constraint["year"])
    subset = long[
        (long["Year"] == year) &
        (long["Variable"].isin(constraint["required"]))
    ]
    if subset.empty:
        return pd.DataFrame()
    wide = subset.pivot_table(
        index=IDX, columns="Variable", values="Value", aggfunc="first"
    ).reset_index()
    wide["computed_value"] = constraint["compute_fn"](wide)
    wide["year_used"] = year
    return wide[IDX + ["computed_value", "year_used"]]


def _run_pct_change(long: pd.DataFrame, constraint: dict,
                    available_years: set) -> pd.DataFrame:
    """Run 2010-2020 % change check. Returns one row per scenario."""
    y0 = _nearest_year(available_years, constraint["year"][0])
    y1 = _nearest_year(available_years, constraint["year"][1])
    var = constraint["required"][0]
    s0 = long[(long["Year"] == y0) & (long["Variable"] == var)][IDX + ["Value"]].rename(columns={"Value": "v0"})
    s1 = long[(long["Year"] == y1) & (long["Variable"] == var)][IDX + ["Value"]].rename(columns={"Value": "v1"})
    merged = s0.merge(s1, on=IDX)
    merged["computed_value"] = (merged["v1"] - merged["v0"]) / merged["v0"].abs()
    merged["year_used"] = f"{y0}-{y1}"
    return merged[IDX + ["computed_value", "year_used"]]


def _unit_warning(result: pd.DataFrame, constraint: dict) -> Optional[str]:
    typical = constraint.get("typical_value")
    if typical is None or result.empty:
        return None
    median_val = result["computed_value"].median()
    if pd.isna(median_val) or median_val == 0 or typical == 0:
        return None
    ratio = abs(median_val / typical)
    if ratio >= _UNITS_WARN_THRESHOLD or ratio <= 1.0 / _UNITS_WARN_THRESHOLD:
        factor = ratio if ratio >= _UNITS_WARN_THRESHOLD else 1.0 / ratio
        direction = "higher" if median_val > typical else "lower"
        return (
            f"POSSIBLE UNIT MISMATCH: median {median_val:.4g} is ~{factor:.0f}x "
            f"{direction} than expected {typical:.4g} {constraint.get('unit','')}. "
            f"Check units for {', '.join(constraint['required'])}"
        )
    return None


def run_constraint(long: pd.DataFrame, constraint: dict,
                   available_vars: set, available_years: set):
    """Run one constraint. Returns (result_df|None, status, missing, unit_warning)."""
    missing = [v for v in constraint["required"] if v not in available_vars]
    if missing:
        return None, "skip", missing, None

    special = constraint.get("special")
    result = _run_pct_change(long, constraint, available_years) \
             if special == "pct_change" \
             else _run_standard(long, constraint, available_years)

    if result.empty:
        return None, "no_data", [], None

    result["status"] = result["computed_value"].apply(
        lambda v: _classify(
            v,
            constraint["outer_lower"], constraint["outer_upper"],
            constraint.get("inner_lower"), constraint.get("inner_upper"),
        )
    )
    result["constraint_name"] = constraint["name"]
    return result, "run", [], _unit_warning(result, constraint)


def _run_all(long: pd.DataFrame, world_region: str):
    """Run all constraints. Returns (results_df, skipped_list, unit_warnings_list)."""
    filtered, fallback = _filter_world(long, world_region)
    if fallback:
        print(f"  [WARN] '{world_region}' not found — running against all regions")
        filtered = long

    available_vars  = set(filtered["Variable"].unique())
    available_years = set(filtered["Year"].unique())

    all_results, skipped, unit_warnings = [], [], []
    for c in CONSTRAINTS:
        result, status, missing, warn = run_constraint(
            filtered, c, available_vars, available_years
        )
        if result is not None:
            all_results.append(result)
        else:
            skipped.append((c["name"], missing or [status]))
            print(f"  Skip '{c['name']}': {missing or status}")
        if warn:
            unit_warnings.append((c["name"], warn))
            print(f"  {warn}")

    combined = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    return combined, skipped, unit_warnings


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

def run(
    predictions: pd.DataFrame,
    ground_truth: Optional[pd.DataFrame] = None,
    world_region: str = "World",
    out_dir: str = "results",
    run_id: str = "run",
    **kwargs,
) -> dict:
    """
    Run hard historical constraints on pre-loaded, pre-normalised DataFrames.
    """
    print(f"\n{'='*60}")
    print(f"  HARD HISTORICAL CONSTRAINTS  |  run_id: {run_id}")
    print(f"{'='*60}")

    results, skipped, unit_warnings = _run_all(predictions, world_region)
    out_path = make_out_dir(out_dir, run_id, "hard_historical_constraints")

    if results.empty:
        save_check_outputs(out_path, pd.DataFrame(),
                           skipped=[f"{n}: {m}" for n, m in skipped],
                           unit_warnings=[w for _, w in unit_warnings])
        return dict(check_name="hard_historical_constraints", passed=True,
                    results=pd.DataFrame(), summary=pd.DataFrame(),
                    unit_warnings=[w for _, w in unit_warnings],
                    skipped=[n for n, _ in skipped])

    summary = (results.groupby("constraint_name")["status"]
               .value_counts().unstack(fill_value=0).reset_index())
    for col in ("PASS", "WARN", "FAIL"):
        if col not in summary.columns:
            summary[col] = 0

    passed = "FAIL" not in results["status"].values

    save_check_outputs(out_path, results, summary,
                       skipped=[f"{n}: {m}" for n, m in skipped],
                       unit_warnings=[w for _, w in unit_warnings])
    if unit_warnings:
        pd.DataFrame(unit_warnings, columns=["constraint", "warning"]).to_csv(
            out_path / "unit_warnings.csv", index=False)
    if skipped:
        pd.DataFrame(skipped, columns=["constraint", "missing"]).to_csv(
            out_path / "skipped.csv", index=False)

    if ground_truth is not None:
        gt_results, gt_skip, gt_warn = _run_all(ground_truth, world_region)
        if not gt_results.empty:
            gt_out = make_out_dir(out_dir, run_id, "hard_historical_constraints_ground_truth")
            gt_summary = (gt_results.groupby("constraint_name")["status"]
                          .value_counts().unstack(fill_value=0).reset_index())
            save_check_outputs(gt_out, gt_results, gt_summary,
                               skipped=[f"{n}: {m}" for n, m in gt_skip],
                               unit_warnings=[w for _, w in gt_warn])

    print(f"\n  Summary:")
    for _, row in summary.iterrows():
        print(f"    {row['constraint_name']:<30}  "
              f"PASS {row.get('PASS',0):>5}  WARN {row.get('WARN',0):>5}  FAIL {row.get('FAIL',0):>5}")
    if skipped:
        print(f"\n  Skipped: {[n for n, _ in skipped]}")

    return dict(check_name="hard_historical_constraints", passed=passed,
                results=results, summary=summary,
                unit_warnings=[w for _, w in unit_warnings],
                skipped=[n for n, _ in skipped])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Hard historical constraints check")
    parser.add_argument("--predictions",  required=True)
    parser.add_argument("--ground_truth", default=None)
    parser.add_argument("--run_id",       required=True)
    parser.add_argument("--out_dir",      default="results")
    parser.add_argument("--world_region", default="World")
    args = parser.parse_args()

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth)) if args.ground_truth else None

    result = run(predictions=pred, ground_truth=gt,
                 world_region=args.world_region, out_dir=args.out_dir, run_id=args.run_id)
    print(f"\n  {'PASSED' if result['passed'] else 'FAILED'}  "
          f"({len(result['skipped'])} sub-checks skipped)")


if __name__ == "__main__":
    main()
