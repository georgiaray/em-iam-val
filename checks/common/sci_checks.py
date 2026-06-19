"""
Verpoort constraints check.

Implements scenario vetting criteria from Verpoort et al. (2025),
"Definitions of vetting criteria for integrated assessment modelling scenarios",
published by the Integrated Assessment Modelling Consortium (IAMC).

    https://philippverpoort.github.io/scenario-vetting-criteria/
    https://github.com/PhilippVerpoort/scenario-vetting-criteria

Data (thresholds and reference values) are fetched directly from the public
GitHub repository and cached locally in checks/sci_cache/. To refresh
cached data, delete that directory and rerun.

The scenario_vetting_criteria Python package is not used directly due to a
known data-directory issue with some installation methods.

Checks implemented:
  hist_co2_eip    CO2 EIP at 2010/2015/2020/2025 vs CEDS-2025 (Hoesly, 2025)
  hist_coal       Primary Energy|Coal at 2010/2015/2020/2025 vs BP Statistical Review
  hist_oil        Primary Energy|Oil at 2010/2015/2020/2025 vs BP Statistical Review
  hist_gas        Primary Energy|Gas at 2010/2015/2020/2025 vs BP Statistical Review
  nearterm_ccs    Carbon Sequestration|CCS at 2030 (IEA CCUS Database)
  longterm_ccs    Carbon Sequestration|CCS at 2035 and 2040 (Kazlou, 2024)

Not implemented — IEA data licensing:
  Verpoort also defines a check for Final Energy against IEA World Energy
  Balances 2024. The IEA does not permit free redistribution of its data, so
  reference values cannot be bundled here. To add this check: obtain IEA-EB-2024
  (https://www.iea.org/reports/world-energy-balances), read off the World totals
  for 2010, 2015, 2020, and 2025, add an entry to MANUAL_REFERENCE_DATA, and
  add the constraint definition to CONSTRAINTS. The threshold multipliers are
  already in the Verpoort repository and will be picked up automatically.

Status per scenario:
    PASS  — within medium-concern bounds
    WARN  — outside medium-concern but within strong-concern bounds
    FAIL  — outside strong-concern (exclusion-level) bounds

Belongs to the 'Historical and domain knowledge comparison' validation family.

Usage (standalone):
    python checks/sci_checks.py \\
        --predictions adapted-data/shin_01_predictions.csv \\
        --ground_truth adapted-data/shin_01_ground_truth.csv \\
        --run_id shin_01
"""

import sys
import io
import urllib.request
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

REPO_ROOT   = Path(__file__).resolve().parent.parent
CACHE_DIR   = Path(__file__).parent / "sci_cache"
GITHUB_BASE = "https://raw.githubusercontent.com/PhilippVerpoort/scenario-vetting-criteria/main/inst/extdata"


# ---------------------------------------------------------------------------
# GitHub fetch with local caching
# ---------------------------------------------------------------------------

def _fetch_cached(url: str, cache_name: str) -> str:
    """
    Fetch a URL and cache the result locally. Returns the file content as text.
    Uses cached version if available; fetches fresh if not.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name

    if cache_path.exists():
        return cache_path.read_text()

    print(f"  Fetching {cache_name} from Verpoort GitHub...")
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            content = resp.read().decode()
        cache_path.write_text(content)
        return content
    except Exception as e:
        raise RuntimeError(
            f"Could not fetch {url}: {e}\n"
            f"Check your internet connection or manually download to {cache_path}"
        )


def _load_criteria_thresholds() -> pd.DataFrame:
    """Load criteria-thresholds.csv from Verpoort GitHub."""
    url  = f"{GITHUB_BASE}/criteria-thresholds.csv"
    text = _fetch_cached(url, "criteria-thresholds.csv")
    return pd.read_csv(io.StringIO(text))


def _load_reference_csv(filename: str) -> pd.DataFrame:
    """Load a reference data CSV from the Verpoort GitHub repo."""
    url  = f"{GITHUB_BASE}/reference-data/{filename}"
    text = _fetch_cached(url, f"ref_{filename}")
    # Skip comment lines (lines starting with #)
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    return pd.read_csv(io.StringIO("\n".join(lines)))


def _build_reference_data() -> dict[str, dict]:
    """
    Build reference data dict {variable: {year: value}} from GitHub CSVs.
    Combines base data (2010/2015/2020) with extrapol25 files (2025).
    """
    ref = {}

    # --- CO2 EIP from CEDS-2025 ---
    ceds = _load_reference_csv("CEDS-2025.csv")
    ceds25 = _load_reference_csv("CEDS-2025-extrapol25.csv")
    co2_rows = pd.concat([
        ceds[ceds["variable"] == "Emissions|CO2|Energy and Industrial Processes"],
        ceds25[ceds25["variable"] == "Emissions|CO2|Energy and Industrial Processes"],
    ])
    world_co2 = co2_rows[co2_rows["region"] == "World"]
    # Map Verpoort variable name → our canonical name
    ref["Emissions|CO2"] = {
        int(row["year"]): float(row["value"])
        for _, row in world_co2.iterrows()
    }

    # --- Coal, Oil, Gas from BP Statistical Review ---
    bp    = _load_reference_csv("BP.csv")
    bp25  = _load_reference_csv("BP-extrapol25.csv")
    bp_all = pd.concat([bp, bp25])
    world_bp = bp_all[bp_all["region"] == "World"]

    for var in ["Primary Energy|Coal", "Primary Energy|Oil", "Primary Energy|Gas"]:
        rows = world_bp[world_bp["variable"] == var]
        ref[var] = {
            int(row["period"]): float(row["value"])
            for _, row in rows.iterrows()
        }

    return ref


# ---------------------------------------------------------------------------
# Threshold extraction
# ---------------------------------------------------------------------------

def _extract_threshold(vc: pd.DataFrame, criterion: str, region: str,
                        year: int, level: str, bound: str) -> Optional[float]:
    """Extract a single threshold value, handling comma-separated year lists."""
    for _, row in vc[vc["criterion"] == criterion].iterrows():
        if row["region"] != region or row["level_of_concern"] != level:
            continue
        years = [int(y.strip()) for y in str(row["year"]).split(",") if y.strip().isdigit()]
        if year not in years:
            continue
        val = row.get(bound)
        if pd.notna(val):
            return float(val)
    return None


# ---------------------------------------------------------------------------
# Constraint definitions
# ---------------------------------------------------------------------------

CONSTRAINTS: list[dict] = [
    {
        "name":           "hist_co2_eip",
        "label":          "CO₂ EIP (2010–2025)",
        "required":       ["Emissions|CO2"],
        "vc_criterion":   "hist_emi_energy_industry",
        "ref_variable":   "Emissions|CO2",
        "years":          [2010, 2015, 2020, 2025],
        "threshold_type": "relative",
        "compute_fn":     lambda df: df["Emissions|CO2"],
        "unit":           "MtCO₂/yr",
        "typical_value":  35_000,
        "source":         "Verpoort et al. (2025), CEDS-2025 (Hoesly, 2025)",
    },
    {
        "name":           "hist_primary_coal",
        "label":          "Primary Energy|Coal (2010–2025)",
        "required":       ["Primary Energy|Coal"],
        "vc_criterion":   "hist_pe_fossil",
        "ref_variable":   "Primary Energy|Coal",
        "years":          [2010, 2015, 2020, 2025],
        "threshold_type": "relative",
        "compute_fn":     lambda df: df["Primary Energy|Coal"],
        "unit":           "EJ",
        "typical_value":  155,
        "source":         "Verpoort et al. (2025), BP Statistical Review",
    },
    {
        "name":           "hist_primary_oil",
        "label":          "Primary Energy|Oil (2010–2025)",
        "required":       ["Primary Energy|Oil"],
        "vc_criterion":   "hist_pe_fossil",
        "ref_variable":   "Primary Energy|Oil",
        "years":          [2010, 2015, 2020, 2025],
        "threshold_type": "relative",
        "compute_fn":     lambda df: df["Primary Energy|Oil"],
        "unit":           "EJ",
        "typical_value":  180,
        "source":         "Verpoort et al. (2025), BP Statistical Review",
    },
    {
        "name":           "hist_primary_gas",
        "label":          "Primary Energy|Gas (2010–2025)",
        "required":       ["Primary Energy|Gas"],
        "vc_criterion":   "hist_pe_fossil",
        "ref_variable":   "Primary Energy|Gas",
        "years":          [2010, 2015, 2020, 2025],
        "threshold_type": "relative",
        "compute_fn":     lambda df: df["Primary Energy|Gas"],
        "unit":           "EJ",
        "typical_value":  130,
        "source":         "Verpoort et al. (2025), BP Statistical Review",
    },
    {
        "name":           "nearterm_ccs",
        "label":          "CCS near-term (2030)",
        "required":       ["Carbon Sequestration|CCS"],
        "vc_criterion":   "nearterm_ccus",
        "ref_variable":   None,
        "years":          [2030],
        "threshold_type": "absolute",
        "compute_fn":     lambda df: df["Carbon Sequestration|CCS"],
        "unit":           "MtCO₂/yr",
        "typical_value":  100,
        "source":         "Verpoort et al. (2025), IEA CCUS Database",
    },
    {
        "name":           "longterm_ccs_2035",
        "label":          "CCS long-term (2035)",
        "required":       ["Carbon Sequestration|CCS"],
        "vc_criterion":   "longterm_ccus",
        "ref_variable":   None,
        "years":          [2035],
        "threshold_type": "absolute",
        "compute_fn":     lambda df: df["Carbon Sequestration|CCS"],
        "unit":           "MtCO₂/yr",
        "typical_value":  500,
        "source":         "Verpoort et al. (2025); Kazlou (2024)",
    },
    {
        "name":           "longterm_ccs_2040",
        "label":          "CCS long-term (2040)",
        "required":       ["Carbon Sequestration|CCS"],
        "vc_criterion":   "longterm_ccus",
        "ref_variable":   None,
        "years":          [2040],
        "threshold_type": "absolute",
        "compute_fn":     lambda df: df["Carbon Sequestration|CCS"],
        "unit":           "MtCO₂/yr",
        "typical_value":  2_000,
        "source":         "Verpoort et al. (2025); Kazlou (2024)",
    },
]


# ---------------------------------------------------------------------------
# Threshold resolution
# ---------------------------------------------------------------------------

def _resolve_bounds(constraint: dict, vc: pd.DataFrame, ref: dict,
                     year: int) -> tuple:
    """Return (strong_lower, strong_upper, medium_lower, medium_upper)."""
    crit  = constraint["vc_criterion"]
    ttype = constraint["threshold_type"]

    if ttype == "absolute":
        if crit == "nearterm_ccus":
            sl = _extract_threshold(vc, crit, "World", year, "strong", "lower")
            su = _extract_threshold(vc, crit, "World", year, "strong", "upper")
            ml = _extract_threshold(vc, crit, "World", year, "medium", "lower")
            mu = _extract_threshold(vc, crit, "World", year, "medium", "upper")
            return sl, su, ml, mu
        elif crit == "longterm_ccus":
            mu = _extract_threshold(vc, crit, "World", year, "medium", "upper")
            return None, None, None, mu
        return None, None, None, None

    # Relative: multiplier × reference value
    ref_var = constraint["ref_variable"]
    ref_vals = ref.get(ref_var, {})
    ref_val  = ref_vals.get(year)
    if ref_val is None:
        return None, None, None, None

    sl_mult = _extract_threshold(vc, crit, "World", year, "strong", "lower")
    su_mult = _extract_threshold(vc, crit, "World", year, "strong", "upper")
    ml_mult = _extract_threshold(vc, crit, "World", year, "medium", "lower")
    mu_mult = _extract_threshold(vc, crit, "World", year, "medium", "upper")

    sl = sl_mult * ref_val if sl_mult is not None else None
    su = su_mult * ref_val if su_mult is not None else None
    ml = ml_mult * ref_val if ml_mult is not None else None
    mu = mu_mult * ref_val if mu_mult is not None else None
    return sl, su, ml, mu


# ---------------------------------------------------------------------------
# Check logic
# ---------------------------------------------------------------------------

def _classify(val, strong_lower, strong_upper, medium_lower, medium_upper) -> str:
    if pd.isna(val):
        return "MISSING"
    outside_strong = (
        (strong_lower is not None and val < strong_lower) or
        (strong_upper is not None and val > strong_upper)
    )
    if outside_strong:
        return "FAIL"
    has_medium = medium_lower is not None or medium_upper is not None
    if has_medium:
        outside_medium = (
            (medium_lower is not None and val < medium_lower) or
            (medium_upper is not None and val > medium_upper)
        )
        if outside_medium:
            return "WARN"
    return "PASS"


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
                   available_vars: set, available_years: set,
                   vc: pd.DataFrame, ref: dict):
    missing = [v for v in constraint["required"] if v not in available_vars]
    if missing:
        return None, "skip", missing, None

    results = []
    for year in constraint["years"]:
        y = _nearest_year(available_years, year)
        subset = long[
            (long["Year"] == y) &
            (long["Variable"].isin(constraint["required"]))
        ]
        if subset.empty:
            continue
        wide = subset.pivot_table(
            index=IDX, columns="Variable", values="Value", aggfunc="first"
        ).reset_index()
        wide["computed_value"] = constraint["compute_fn"](wide)
        wide["year_used"] = y

        sl, su, ml, mu = _resolve_bounds(constraint, vc, ref, year)
        if sl is None and su is None and ml is None and mu is None:
            continue

        wide["status"] = wide["computed_value"].apply(
            lambda v: _classify(v, sl, su, ml, mu)
        )
        wide["constraint_name"] = constraint["name"]
        results.append(wide[IDX + ["computed_value", "year_used", "status", "constraint_name"]])

    if not results:
        return None, "no_data", [], None

    result = pd.concat(results, ignore_index=True)
    return result, "run", [], _unit_warning(result, constraint)


def _run_all(long: pd.DataFrame, vc: pd.DataFrame, ref: dict, world_region: str):
    filtered, fallback = _filter_world(long, world_region)
    if fallback:
        msg = (f"no '{world_region}' region in dataset — these are World-level "
               f"checks and cannot be meaningfully evaluated on regional data")
        print(f"  [SKIP] {msg}")
        skipped = [(c["name"], msg) for c in CONSTRAINTS]
        return pd.DataFrame(), skipped, []

    available_vars  = set(filtered["Variable"].unique())
    available_years = set(filtered["Year"].unique())

    all_results, skipped, unit_warnings = [], [], []
    for c in CONSTRAINTS:
        result, status, missing, warn = run_constraint(
            filtered, c, available_vars, available_years, vc, ref
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
    print(f"\n{'='*60}")
    print(f"  VERPOORT CONSTRAINTS  |  run_id: {run_id}")
    print(f"{'='*60}")

    vc  = _load_criteria_thresholds()
    ref = _build_reference_data()
    print(f"  Thresholds: {len(vc)} criteria loaded")
    print(f"  Reference data: {list(ref.keys())}")

    results, skipped, unit_warnings = _run_all(predictions, vc, ref, world_region)
    out_path = make_out_dir(out_dir, run_id, "sci_checks")

    if results.empty:
        save_check_outputs(out_path, pd.DataFrame(),
                           skipped=[f"{n}: {m}" for n, m in skipped],
                           unit_warnings=[w for _, w in unit_warnings])
        return dict(check_name="sci_checks", passed=True,
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
        pd.DataFrame(skipped, columns=["constraint", "reason"]).to_csv(
            out_path / "skipped.csv", index=False)

    if ground_truth is not None:
        gt_results, gt_skip, gt_warn = _run_all(ground_truth, vc, ref, world_region)
        if not gt_results.empty:
            gt_out = make_out_dir(out_dir, run_id, "sci_checks_ground_truth")
            gt_summary = (gt_results.groupby("constraint_name")["status"]
                          .value_counts().unstack(fill_value=0).reset_index())
            save_check_outputs(gt_out, gt_results, gt_summary,
                               skipped=[f"{n}: {m}" for n, m in gt_skip],
                               unit_warnings=[w for _, w in gt_warn])

    print(f"\n  Summary:")
    for _, row in summary.iterrows():
        print(f"    {row['constraint_name']:<25}  "
              f"PASS {row.get('PASS',0):>5}  WARN {row.get('WARN',0):>5}  FAIL {row.get('FAIL',0):>5}")
    if skipped:
        print(f"  Skipped: {[n for n, _ in skipped]}")

    return dict(check_name="sci_checks", passed=passed,
                results=results, summary=summary,
                unit_warnings=[w for _, w in unit_warnings],
                skipped=[n for n, _ in skipped])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Verpoort constraints check")
    parser.add_argument("--predictions",  required=True)
    parser.add_argument("--ground_truth", default=None)
    parser.add_argument("--run_id",       required=True)
    parser.add_argument("--out_dir",      default="results")
    parser.add_argument("--world_region", default="World")
    parser.add_argument("--refresh_cache", action="store_true",
                        help="Delete and re-fetch cached Verpoort data files")
    args = parser.parse_args()

    if args.refresh_cache and CACHE_DIR.exists():
        import shutil
        shutil.rmtree(CACHE_DIR)
        print(f"  Cache cleared: {CACHE_DIR}")

    pred = normalize_to_canonical(load_csv(args.predictions))
    gt   = normalize_to_canonical(load_csv(args.ground_truth)) if args.ground_truth else None

    result = run(predictions=pred, ground_truth=gt,
                 world_region=args.world_region, out_dir=args.out_dir, run_id=args.run_id)
    print(f"\n  {'PASSED' if result['passed'] else 'FAILED'}  |  "
          f"{len(result['skipped'])} skipped")


if __name__ == "__main__":
    main()
