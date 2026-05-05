"""
Validation report generator.

Reads results from results/<run_id>/ and generates a Markdown report
with summary tables and figures. Works identically for any dataset —
no XGBoost or Li-specific code.

Must be run after validate.py has produced results.

Usage:
    python make_val_report.py --run_id xgb_04
    python make_val_report.py --run_id li_vae_01 --title "Li VAE validation"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT   = Path(__file__).resolve().parent
RESULTS_DIR = REPO_ROOT / "results"
REPORTS_DIR = REPO_ROOT / "reports"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(run_dir: Path, check: str, filename: str) -> pd.DataFrame | None:
    path = run_dir / check / filename
    if path.exists():
        return pd.read_csv(path)
    return None


def _pct(n, total):
    return f"{100*n/total:.1f}%" if total else "—"


def _md_table(df: pd.DataFrame) -> str:
    def _esc(s): return str(s).replace("|", "\\|")
    cols   = df.columns.tolist()
    header = "| " + " | ".join(_esc(c) for c in cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            cells.append(_esc(f"{v:.4f}" if isinstance(v, float) else v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def _overview_row(run_dir: Path, check: str, label: str) -> dict:
    """Return a one-line summary row for a check (for the overview table)."""
    s = _load(run_dir, check, "summary.csv")
    if s is None:
        return {"Check": label, "Status": "not run", "Key metric": "—", "GT available": "—"}

    # Determine pass rate
    if "PASS" in s.columns and "FAIL" in s.columns:
        total = s["PASS"].sum() + s["FAIL"].sum() + s.get("WARN", pd.Series([0])).sum()
        n_pass = s["PASS"].sum()
        metric = f"pass rate {_pct(n_pass, total)}"
    elif "Pass_Rate" in s.columns:
        metric = f"mean pass rate {s['Pass_Rate'].mean()*100:.1f}%"
    elif "Mean_abs_diff_r2" in s.columns:
        metric = f"mean |Δr²| {s['Mean_abs_diff_r2'].mean():.4f}"
    else:
        metric = "—"

    gt_exists = (run_dir / f"{check}_ground_truth" / "summary.csv").exists()
    return {"Check": label, "Key metric": metric, "GT available": "✓" if gt_exists else "✗"}


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def section_constraint_check(run_dir: Path, check: str, title: str, blurb: str) -> str:
    """Generic section for hard_historical_constraints and soft_future_constraints."""
    pred = _load(run_dir, check, "summary.csv")
    gt   = _load(run_dir, f"{check}_ground_truth", "summary.csv")
    skipped = run_dir / check / "skipped.txt"
    unit_warn = run_dir / check / "unit_warnings.txt"

    if pred is None:
        return f"_Results not found. Run `validate.py` first._\n"

    blocks = [blurb]

    # Build combined table
    for col in ("PASS", "WARN", "FAIL"):
        if col not in pred.columns:
            pred[col] = 0

    total = pred["PASS"] + pred.get("WARN", 0) + pred["FAIL"]
    tbl = pred[["constraint_name"]].copy()
    tbl["N"]        = total
    tbl["Pass (%)"] = (100 * pred["PASS"] / total.replace(0, np.nan)).round(1)
    if "WARN" in pred.columns and pred["WARN"].sum() > 0:
        tbl["Warn (%)"] = (100 * pred["WARN"] / total.replace(0, np.nan)).round(1)
    tbl["Fail (%)"] = (100 * pred["FAIL"] / total.replace(0, np.nan)).round(1)

    if gt is not None:
        for col in ("PASS", "WARN", "FAIL"):
            if col not in gt.columns:
                gt[col] = 0
        gt_total = gt["PASS"] + gt.get("WARN", 0) + gt["FAIL"]
        tbl = tbl.merge(
            gt[["constraint_name"]].assign(**{
                "GT Pass (%)": (100 * gt["PASS"] / gt_total.replace(0, np.nan)).round(1),
                "GT Fail (%)": (100 * gt["FAIL"] / gt_total.replace(0, np.nan)).round(1),
            }),
            on="constraint_name", how="left"
        )

    tbl = tbl.rename(columns={"constraint_name": "Sub-check"})
    blocks.append(_md_table(tbl.fillna("—")))

    # Skipped
    if skipped.exists():
        txt = skipped.read_text().strip()
        if txt:
            blocks.append(f"\n_Skipped (required variables absent): {txt.replace(chr(10), ', ')}_")

    # Unit warnings
    if unit_warn.exists():
        txt = unit_warn.read_text().strip()
        if txt:
            for line in txt.splitlines():
                blocks.append(f'\n<p style="color:red;font-weight:bold">⚠️ {line}</p>')

    return "\n\n".join(blocks) + "\n"


def section_plausibility(run_dir: Path) -> str:
    pred = _load(run_dir, "check_plausibility", "summary.csv")
    gt   = _load(run_dir, "check_plausibility_ground_truth", "summary.csv")
    if pred is None:
        return "_Results not found._\n"

    blurb = ("Period-on-period growth rates checked against empirically-derived bounds "
             "from the ground truth data. Violations indicate trajectories with implausible "
             "dynamics.")

    def _make_tbl(df, label):
        df = df.copy()
        if "Pass_Rate" in df.columns:
            df["Pass (%)"] = (df["Pass_Rate"] * 100).round(1)
        cols = ["Scenario_Category", "Pass_Count", "Fail_Count"]
        if "Pass (%)" in df.columns:
            cols.append("Pass (%)")
        return df[cols]

    pred_tbl = _make_tbl(pred, "Predictions")
    blocks   = [blurb]

    if gt is not None:
        # Check if categories align enough to merge
        pred_cats = set(pred["Scenario_Category"])
        gt_cats   = set(gt["Scenario_Category"])
        if pred_cats & gt_cats:  # overlap exists — merge
            gt["GT Pass (%)"] = (gt["Pass_Rate"] * 100).round(1) if "Pass_Rate" in gt.columns else np.nan
            tbl = pred_tbl.merge(gt[["Scenario_Category","GT Pass (%)"]], on="Scenario_Category", how="left")
            blocks.append(_md_table(tbl))
        else:  # different category systems — show separately
            gt_tbl = _make_tbl(gt, "Ground truth")
            blocks.append("**Predictions:**\n\n" + _md_table(pred_tbl))
            blocks.append("**Ground truth** (different category labelling — shown separately):\n\n" + _md_table(gt_tbl))
    else:
        blocks.append(_md_table(pred_tbl))

    return "\n\n".join(blocks) + "\n"


def section_sum_check(run_dir: Path) -> str:
    pred = _load(run_dir, "sum_check", "summary.csv")
    gt   = _load(run_dir, "sum_check_ground_truth", "summary.csv")
    if pred is None:
        return "_Results not found._\n"

    blurb = ("Checks that each parent variable equals the sum of its direct children. "
             "The model is expected to fail — the failure rate quantifies how much the "
             "emulator violates IAM accounting identities.")

    n_pass = pred.get("Pass_Count", pd.Series([0])).sum() if "Pass_Count" in pred.columns else 0
    n_fail = pred.get("Fail_Count", pd.Series([0])).sum() if "Fail_Count" in pred.columns else 0
    total  = n_pass + n_fail
    lines = [blurb, f"\n**Predictions:** {n_pass:,} / {total:,} scenario-timesteps pass "
             f"({_pct(n_pass, total)})"]

    if gt is not None:
        gt_pass = gt.get("Pass_Count", pd.Series([0])).sum()
        gt_fail = gt.get("Fail_Count", pd.Series([0])).sum()
        gt_tot  = gt_pass + gt_fail
        lines.append(f"**Ground truth:** {gt_pass:,} / {gt_tot:,} pass ({_pct(gt_pass, gt_tot)})")

    return "\n".join(lines) + "\n"


def section_regional(run_dir: Path) -> str:
    pred = _load(run_dir, "regional_consistency", "summary.csv")
    gt   = _load(run_dir, "regional_consistency_ground_truth", "summary.csv")
    if pred is None:
        return "_Results not found or no regional groupings present in this dataset._\n"

    blurb = "Checks that predicted World values equal the sum of subregion predictions."

    if "PASS" in pred.columns and "FAIL" in pred.columns:
        n_pass = pred["PASS"].sum()
        total  = n_pass + pred["FAIL"].sum()
        tbl = pd.DataFrame([{
            "Source": "Predictions",
            "Pass": f"{n_pass:,}",
            "Fail": f"{pred['FAIL'].sum():,}",
            "Pass (%)": f"{_pct(n_pass, total)}",
        }])
        if gt is not None and "PASS" in gt.columns:
            gt_pass = gt["PASS"].sum()
            gt_total = gt_pass + gt["FAIL"].sum()
            tbl = pd.concat([tbl, pd.DataFrame([{
                "Source": "Ground truth",
                "Pass": f"{gt_pass:,}",
                "Fail": f"{gt['FAIL'].sum():,}",
                "Pass (%)": f"{_pct(gt_pass, gt_total)}",
            }])], ignore_index=True)
        return blurb + "\n\n" + _md_table(tbl) + "\n"

    return blurb + "\n\n" + _md_table(pred.head(10)) + "\n"


def section_bounds(run_dir: Path) -> str:
    pred = _load(run_dir, "bounds_check", "summary.csv")
    gt   = _load(run_dir, "bounds_check_ground_truth", "summary.csv")
    if pred is None:
        return "_Results not found._\n"

    blurb = ("Checks predictions against hard physical lower bounds (energy variables ≥ 0) "
             "and empirical per-variable bounds derived from ground truth.")

    if "PASS" in pred.columns and "FAIL" in pred.columns:
        n_pass = pred["PASS"].sum()
        total  = n_pass + pred["FAIL"].sum()
        lines  = [blurb,
                  f"\n**Predictions:** {n_pass:,} / {total:,} scenario-variable-timesteps pass "
                  f"({_pct(n_pass, total)})"]
        if gt is not None and "PASS" in gt.columns:
            gt_pass = gt["PASS"].sum()
            gt_tot  = gt_pass + gt["FAIL"].sum()
            lines.append(f"**Ground truth:** {gt_pass:,} / {gt_tot:,} pass ({_pct(gt_pass, gt_tot)})")
        return "\n".join(lines) + "\n"

    return blurb + "\n\n" + _md_table(pred.head(5)) + "\n"


def section_correlations(run_dir: Path, fig_dir: Path) -> tuple[str, list]:
    summary = _load(run_dir, "inter_variable_correlation", "summary.csv")
    fig_src  = run_dir / "inter_variable_correlation" / "figures"
    if summary is None:
        return "_Results not found._\n", []

    blurb = ("Pearson r² correlation matrices between all predicted variables at key years, "
             "compared against AR6 ground truth. Lower mean |Δr²| indicates better preservation "
             "of inter-variable relationships.")

    blocks = [blurb]
    if "Mean_abs_diff_r2" in summary.columns:
        blocks.append(_md_table(summary[["Year","N_variables","Mean_abs_diff_r2"]]))

    figs = []
    if fig_src.exists():
        for year in [2030, 2050, 2100]:
            src = fig_src / f"correlations_{year}.png"
            if src.exists():
                dst = fig_dir / f"correlations_{year}.png"
                import shutil; shutil.copy2(src, dst)
                figs.append(f"figures/correlations_{year}.png")
                blocks.append(f"### {year}\n\n![Inter-variable correlations {year}](figures/correlations_{year}.png)")

    return "\n\n".join(blocks) + "\n", figs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate validation report")
    parser.add_argument("--run_id",  required=True, help="Run identifier")
    parser.add_argument("--title",   default=None,  help="Optional report title")
    parser.add_argument("--out_dir", default=None,  help="Results directory (default: results/)")
    args = parser.parse_args()

    results_base = Path(args.out_dir) / args.run_id if args.out_dir else RESULTS_DIR / args.run_id
    if not results_base.exists():
        print(f"ERROR: No results found at {results_base}")
        print("Run validate.py first.")
        sys.exit(1)

    report_dir = REPORTS_DIR / args.run_id
    fig_dir    = report_dir / "figures"
    report_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    title = args.title or f"Validation Report: {args.run_id}"
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'='*60}")
    print(f"  Generating report for: {args.run_id}")
    print(f"  Reading from: {results_base}")
    print(f"  Output: {report_dir / 'report.md'}")
    print(f"{'='*60}\n")

    # Overview table
    CHECKS = [
        ("check_plausibility",         "Growth rate plausibility"),
        ("sum_check",                  "Hierarchy sum check"),
        ("regional_consistency",       "Regional consistency"),
        ("bounds_check",               "Physical bounds"),
        ("hard_historical_constraints","Hard historical constraints"),
        ("soft_future_constraints",    "Soft future constraints"),
        ("inter_variable_correlation", "Inter-variable correlation"),
    ]
    overview_rows = [_overview_row(results_base, name, label) for name, label in CHECKS]
    overview_tbl  = _md_table(pd.DataFrame(overview_rows))

    # Sections
    sec_plaus  = section_plausibility(results_base)
    sec_sum    = section_sum_check(results_base)
    sec_reg    = section_regional(results_base)
    sec_bounds = section_bounds(results_base)
    sec_hh     = section_constraint_check(
        results_base, "hard_historical_constraints",
        "Hard Historical Constraints",
        ("Checks World-level predictions at 2020 against the historical anchor values "
         "used in the AR6 scenario vetting process (Nicholls et al. 2022, Table 11). "
         "Status: PASS = within IP range, WARN = within outer tolerance, "
         "FAIL = outside outer tolerance. "
         "Belongs to the **historical and domain knowledge comparison** validation family."),
    )
    sec_sf     = section_constraint_check(
        results_base, "soft_future_constraints",
        "Soft Future Constraints",
        ("Checks World-level predictions at specific future years against domain-knowledge "
         "plausibility bounds from the AR6 vetting process (Table 11). Not used as hard "
         "exclusion criteria in AR6 but flagged as potentially problematic. Warranted via "
         "the constraint-violation argument. "
         "Belongs to the **historical and domain knowledge comparison** validation family."),
    )
    sec_corr, corr_figs = section_correlations(results_base, fig_dir)

    report = f"""# {title}

**Run ID:** `{args.run_id}`
**Generated:** {now}
**Results:** `results/{args.run_id}/`

---

## Overview

{overview_tbl}

---

## 1. Growth Rate Plausibility

_Period-on-period growth rates checked against empirically-derived bounds from
the ground truth. Violations indicate trajectories with implausible dynamics._

{sec_plaus}

---

## 2. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children.
The model is expected to fail — the failure rate quantifies how much the
emulator violates IAM accounting identities._

{sec_sum}

---

## 3. Regional Consistency

_Checks that predicted World values equal the sum of subregion predictions
(R5 / R6 / R10 groupings). Only datasets with regional breakdowns are checked._

{sec_reg}

---

## 4. Physical Bounds Check

_Checks predictions against hard physical lower bounds and empirical bounds
derived from ground truth._

{sec_bounds}

---

## 5. Hard Historical Constraints

{sec_hh}

---

## 6. Soft Future Constraints

{sec_sf}

---

## 7. Inter-variable Correlations

_Pearson r² between all variable pairs at years 2030, 2050, and 2100.
A well-calibrated emulator should preserve the correlation structure of the
parent simulation. Methodology follows Li et al. (2025) Fig. 4._

{sec_corr}
"""

    out_path = report_dir / "report.md"
    out_path.write_text(report)
    print(f"  Report written to: {out_path}")
    if corr_figs:
        print(f"  Figures: {len(corr_figs)} saved to {fig_dir}")


if __name__ == "__main__":
    main()
