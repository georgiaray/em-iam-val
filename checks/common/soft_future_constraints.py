"""
Soft future constraints check.

Checks World-level predictions at specific future years against domain-knowledge
plausibility bounds drawn from the AR6 scenario vetting process (Table 11,
Nicholls et al. 2022). These were flagged in AR6 as potentially problematic
but not used as hard exclusion criteria.

Warranted via the constraint-violation argument: the IAMs were themselves
vetted against these criteria.

Status per scenario:
    PASS  — meets the criterion
    FAIL  — violates the criterion

Belongs to the 'Historical and domain knowledge comparison' validation family.

Usage (standalone):
    python checks/soft_future_constraints.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
        --ground_truth adapted-data/shin_01_ground_truth.csv \\
        --run_id shin_01
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
# Constraint definitions
# ---------------------------------------------------------------------------
# lower_bound / upper_bound: the check fails outside these (None = unconstrained)
# typical_value: used for unit plausibility check

CONSTRAINTS: list[dict] = [
    {
        "name": "co2_not_negative_2030",
        "label": "No net-negative CO2 before 2030",
        "required": ["Emissions|CO2"],
        "compute_fn": lambda df: df["Emissions|CO2"],
        "year": 2030,
        "lower_bound": 0.0, "upper_bound": None,
        "unit": "MtCO2/yr", "typical_value": 20_000,
        "source": "AR6 vetting criteria (Table 11)",
        "note": "CO2 total (EIP) must remain positive in 2030. "
                "Net-negative CO2 before 2030 is physically implausible.",
    },
    {
        "name": "ccs_2030",
        "label": "CCS from energy in 2030 < 2,000 MtCO2/yr",
        "required": ["Carbon Sequestration|CCS"],
        "compute_fn": lambda df: df["Carbon Sequestration|CCS"],
        "year": 2030,
        "lower_bound": None, "upper_bound": 2_000.0,
        "unit": "MtCO2/yr", "typical_value": 300,
        "source": "AR6 vetting criteria (Table 11)",
        "note": "CCS above 2,000 MtCO2/yr by 2030 is implausible.",
    },
    {
        "name": "nuclear_electricity_2030",
        "label": "Nuclear electricity in 2030 < 20 EJ/yr",
        "required": ["Secondary Energy|Electricity|Nuclear"],
        "compute_fn": lambda df: df["Secondary Energy|Electricity|Nuclear"],
        "year": 2030,
        "lower_bound": None, "upper_bound": 20.0,
        "unit": "EJ/yr", "typical_value": 12,
        "source": "AR6 vetting criteria (Table 11)",
        "note": "Nuclear electricity above 20 EJ/yr by 2030 is implausible.",
    },
    {
        "name": "ch4_2040",
        "label": "CH4 emissions in 2040 in [100, 1000] MtCH4/yr",
        "required": ["Emissions|CH4"],
        "compute_fn": lambda df: df["Emissions|CH4"],
        "year": 2040,
        "lower_bound": 100.0, "upper_bound": 1_000.0,
        "unit": "MtCH4/yr", "typical_value": 300,
        "source": "AR6 vetting criteria (Table 11)",
        "note": "CH4 below 100 or above 1,000 MtCH4/yr in 2040 is implausible.",
    },
]


# ---------------------------------------------------------------------------
# Check logic
# ---------------------------------------------------------------------------

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

    year   = _nearest_year(available_years, constraint["year"])
    subset = long[
        (long["Year"] == year) &
        (long["Variable"].isin(constraint["required"]))
    ]
    if subset.empty:
        return None, "no_data", [], None

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

    result = wide[IDX + ["computed_value", "year_used", "status", "constraint_name"]]
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
    Run soft future constraints on pre-loaded, pre-normalised DataFrames.
    """
    print(f"\n{'='*60}")
    print(f"  SOFT FUTURE CONSTRAINTS  |  run_id: {run_id}")
    print(f"{'='*60}")

    results, skipped, unit_warnings = _run_all(predictions, world_region)
    out_path = make_out_dir(out_dir, run_id, "soft_future_constraints")

    if results.empty:
        save_check_outputs(out_path, pd.DataFrame(),
                           skipped=[f"{n}: {m}" for n, m in skipped],
                           unit_warnings=[w for _, w in unit_warnings])
        return dict(check_name="soft_future_constraints", passed=True,
                    results=pd.DataFrame(), summary=pd.DataFrame(),
                    unit_warnings=[w for _, w in unit_warnings],
                    skipped=[n for n, _ in skipped])

    summary = (results.groupby("constraint_name")["status"]
               .value_counts().unstack(fill_value=0).reset_index())
    for col in ("PASS", "FAIL"):
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
            gt_out = make_out_dir(out_dir, run_id, "soft_future_constraints_ground_truth")
            gt_summary = (gt_results.groupby("constraint_name")["status"]
                          .value_counts().unstack(fill_value=0).reset_index())
            save_check_outputs(gt_out, gt_results, gt_summary,
                               skipped=[f"{n}: {m}" for n, m in gt_skip],
                               unit_warnings=[w for _, w in gt_warn])

    print(f"\n  Summary:")
    for _, row in summary.iterrows():
        print(f"    {row['constraint_name']:<35}  "
              f"PASS {row.get('PASS',0):>5}  FAIL {row.get('FAIL',0):>5}")
    if skipped:
        print(f"\n  Skipped: {[n for n, _ in skipped]}")

    return dict(check_name="soft_future_constraints", passed=passed,
                results=results, summary=summary,
                unit_warnings=[w for _, w in unit_warnings],
                skipped=[n for n, _ in skipped])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Soft future constraints check")
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
