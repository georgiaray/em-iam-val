"""
Validation report generator.

Reads results from results/<run_id>/ and generates a Markdown report
with summary tables and figures, matching the original report style.

Usage:
    python make_val_report.py --run_id shin_01
    python make_val_report.py --run_id li_vae_01 --title "Li VAE validation"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

REPO_ROOT   = Path(__file__).resolve().parent
RESULTS_DIR = REPO_ROOT / "results"
REPORTS_DIR = REPO_ROOT / "reports"

C_PRED = "#2c7bb6"
C_GT   = "#d7191c"
C_GRID = "#e5e5e5"
GT_MISSING = "⚠ run validate.py with --ground_truth"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(run_dir: Path, check: str, filename: str) -> Optional[pd.DataFrame]:
    path = run_dir / check / filename
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()  # file exists but is empty (e.g. no results for this check)


def md_table(df: pd.DataFrame, fmt: Optional[dict] = None) -> str:
    def _esc(s): return str(s).replace("|", "\\|")
    fmt = fmt or {}
    cols = df.columns.tolist()
    header = "| " + " | ".join(_esc(str(c)) for c in cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for col in cols:
            val = row[col]
            if col in fmt:
                cells.append(_esc(fmt[col].format(val)))
            elif isinstance(val, float):
                cells.append(_esc(f"{val:.4f}"))
            else:
                cells.append(_esc(str(val)))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def save_fig(fig: plt.Figure, fig_dir: Path, name: str) -> str:
    fig_dir.mkdir(parents=True, exist_ok=True)
    path = fig_dir / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"figures/{name}.png"


def style_ax(ax, title="", xlabel="", ylabel=""):
    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(labelsize=8)
    ax.yaxis.grid(True, color=C_GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)


def _gt_missing_note(check_name: str) -> str:
    return (
        f"> **Ground truth results not found** for `{check_name}`. "
        f"Re-run `validate.py` with `--ground_truth` to generate comparison results."
    )


# ---------------------------------------------------------------------------
# Example failure helpers
# ---------------------------------------------------------------------------

def _example_sum_failure(te: pd.DataFrame, sc: pd.DataFrame, label: str) -> str:
    """Show year-by-year breakdown with individual children for the median failing scenario."""
    failing = sc[~sc["passed"]]
    if failing.empty:
        return f"_No failures found in {label}._"

    median_err = failing["mean_error"].median()
    idx = (failing["mean_error"] - median_err).abs().idxmin()
    row = failing.loc[idx]

    mask = (
        (te["Model"]    == row["Model"]) &
        (te["Scenario"] == row["Scenario"]) &
        (te["Region"]   == row["Region"]) &
        (te["parent_variable"] == row["parent_variable"])
    )
    ts = te[mask].sort_values("Year")
    if ts.empty:
        return f"_Could not locate timestep rows for example scenario in {label}._"

    # Identify child variable columns (anything that's not a metadata column)
    meta_cols = {"Model","Scenario","Region","Year","Parent",
                 "Parent_Value","Children_Sum","Residual","Tolerance","Status",
                 "abs_error","passed_timestep","parent_variable","total",
                 "sum_components","zero_total"}
    child_cols = [c for c in ts.columns if c not in meta_cols]

    tbl_dict = {"Year": ts["Year"].values}
    # Individual children (use short name after last |)
    for child in child_cols:
        short = child.split("|")[-1].strip()
        tbl_dict[short] = ts[child].round(3).values
    tbl_dict["Sum of children"] = ts["Children_Sum"].round(3).values
    tbl_dict["Parent value"]    = ts["Parent_Value"].round(3).values
    tbl_dict["Error (%)"]       = (ts["abs_error"] * 100).round(2).values
    tbl_dict["Status"]          = ts["Status"].values

    tbl = pd.DataFrame(tbl_dict)
    header = (
        f"**Scenario:** {row['Model']} | {row['Scenario']} | {row['Region']}  \n"
        f"**Parent variable:** {row['parent_variable']}  \n"
        f"**Mean error:** {row['mean_error_pct']:.2f}%  (median failing scenario)"
    )
    return f"#### Example failure — {label}\n\n{header}\n\n" + md_table(
        tbl, fmt={c: "{}" for c in tbl.columns}
    )


def _example_plausibility_failure(viol: pd.DataFrame, label: str) -> str:
    """Show the most extreme growth rate violation."""
    violations = viol[viol["violation"]].copy()
    if violations.empty:
        return f"_No violations found in {label}._"

    violations["abs_gr"] = violations["Growth_Rate"].abs().replace([np.inf, -np.inf], np.nan)
    worst = violations.dropna(subset=["abs_gr"]).nlargest(1, "abs_gr")
    if worst.empty:
        return f"_No finite-severity violations found in {label}._"

    row = worst.iloc[0]
    tbl = pd.DataFrame([{
        "Variable":    row["Variable"],
        "Scenario":    row.get("Scenario", "—"),
        "Region":      row.get("Region", "—"),
        "Year (from)": int(row["Year_From"]) if "Year_From" in row.index else "—",
        "Year (to)":   int(row["Year"]),
        "Growth rate": f"{row['Growth_Rate']:+.4f}",
    }])
    header = "**Most extreme growth rate violation**"
    return f"#### Example violation — {label}\n\n{header}\n\n" + md_table(
        tbl, fmt={c: "{}" for c in tbl.columns}
    )


def _example_bounds_failure(viol: pd.DataFrame, label: str) -> str:
    """Show the most extreme bounds violation."""
    if viol is None or viol.empty:
        return f"_No violations found in {label}._"

    worst = viol.nlargest(1, "Value") if (viol["above_upper"]).any() \
        else viol.nsmallest(1, "Value")
    if worst.empty:
        return f"_No violations found in {label}._"

    row = worst.iloc[0]
    tbl = pd.DataFrame([{
        "Variable":       row["Variable"],
        "Scenario":       row.get("Scenario", "—"),
        "Region":         row.get("Region", "—"),
        "Year":           int(row["Year"]),
        "Value":          round(float(row["Value"]), 4),
        "Units":          row.get("Units", "—"),
        "Violation type": row.get("Violation_Type", "—"),
    }])
    header = "**Most extreme bounds violation**"
    return f"#### Example violation — {label}\n\n{header}\n\n" + md_table(
        tbl, fmt={c: "{}" for c in tbl.columns}
    )


# ---------------------------------------------------------------------------
# Column adapters — convert new CSV format to the shapes each section expects
# ---------------------------------------------------------------------------

def _adapt_sum_results(df: pd.DataFrame, threshold: float = 0.012) -> tuple:
    """From new results.csv → (scenario_summary, timestep_errors) in old format."""
    if df is None or df.empty:
        return None, None
    df = df.copy()
    # Rows where |parent| < abs_floor are excluded from the mean (set to NaN),
    # matching the old behaviour — dividing by a near-zero denominator produces
    # meaningless huge relative errors.
    abs_floor = 1.0
    df["abs_error"] = np.where(
        df["Parent_Value"].abs() < abs_floor,
        np.nan,
        df["Residual"] / df["Parent_Value"].abs(),
    )
    df["passed_timestep"] = df["Status"] == "PASS"
    df["parent_variable"] = df["Parent"]
    df["total"] = df["Parent_Value"]
    df["sum_components"] = df["Children_Sum"]
    df["zero_total"] = df["Parent_Value"].abs() < 1.0
    IDX = ["Model", "Scenario", "Region"]
    sc = (
        df.groupby(IDX + ["parent_variable"])
        .agg(
            n_timesteps=("abs_error", "count"),
            mean_error=("abs_error", "mean"),
            max_error=("abs_error", "max"),
            n_failed_timesteps=("passed_timestep", lambda x: (~x).sum()),
        )
        .reset_index()
    )
    sc["passed"] = sc["mean_error"] < threshold
    sc["mean_error_pct"] = sc["mean_error"] * 100
    sc["max_error_pct"]  = sc["max_error"]  * 100
    return sc, df


def _adapt_plausibility(df: pd.DataFrame, bounds: pd.DataFrame = None):
    """From new results.csv → violation DataFrame in old format."""
    if df is None or df.empty:
        return None
    df = df.copy()
    df["violation"] = df["Status"] == "FAIL"
    df["severity"]  = np.nan  # not stored in new format
    df["Year"]      = df["Year_To"]
    if bounds is not None and "Lower_Bound" in bounds.columns:
        df = df.merge(
            bounds.rename(columns={"Lower_Bound": "lower_bound", "Upper_Bound": "upper_bound"}),
            on="Variable", how="left"
        )
        mask = df["violation"]
        lo = df.loc[mask, "lower_bound"]
        hi = df.loc[mask, "upper_bound"]
        gr = df.loc[mask, "Growth_Rate"]
        width = (hi - lo).replace(0, np.nan)
        df.loc[mask, "severity"] = (
            (gr - hi).clip(lower=0) + (lo - gr).clip(lower=0)
        ) / width
    else:
        df["lower_bound"] = np.nan
        df["upper_bound"] = np.nan
    return df


def _adapt_regional(df: pd.DataFrame):
    """From new results.csv → scenario_summary in old format."""
    if df is None or df.empty:
        return None
    df = df.copy()
    # Exclude SKIP rows (World near zero) and near-zero World values from
    # relative error calculations — dividing by a near-zero denominator produces
    # meaningless huge percentages (e.g. CO2 crossing zero in net-zero scenarios).
    abs_floor = 1.0
    df = df[df["Status"] != "SKIP"].copy()
    df["passed"] = df["Status"] == "PASS"
    df["rel_error"] = np.where(
        df["World_Value"].abs() < abs_floor,
        np.nan,
        df["Residual"] / df["World_Value"].abs(),
    )
    df["grouping"] = df["Grouping"]
    IDX = ["Model", "Scenario", "Region"]
    sc = (
        df.groupby(IDX + ["grouping", "Variable"])
        .agg(
            passed=("passed", "all"),
            mean_error_pct=("rel_error", lambda x: x.mean() * 100),
            max_error_pct=("rel_error", lambda x: x.max() * 100),
        )
        .reset_index()
    )
    return sc


def _adapt_bounds(df: pd.DataFrame):
    """From new results.csv → (scenario_summary, violations) in old format."""
    if df is None or df.empty:
        return None, None
    df = df.copy()
    df["violation"]   = df["Status"] == "FAIL"
    df["below_lower"] = df["Violation_Type"].str.contains("lower", case=False, na=False)
    df["above_upper"] = df["Violation_Type"].str.contains("upper", case=False, na=False)
    IDX = ["Model", "Scenario", "Region", "Variable"]
    sc = (
        df.groupby(IDX)
        .agg(
            n_timesteps=("violation", "count"),
            n_violations=("violation", "sum"),
            n_below_lower=("below_lower", "sum"),
            n_above_upper=("above_upper", "sum"),
        )
        .reset_index()
    )
    sc["passed"] = sc["n_violations"] == 0
    viol = df[df["violation"]]
    return sc, viol


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def _fmt_pr(val):
    """Format a pass rate float as a percentage string."""
    return f"{val:.1f}%" if val is not None else GT_MISSING


def _simple_table(rows: list) -> str:
    """Build a small markdown table from a list of dicts, dropping all-'—' columns."""
    df = pd.DataFrame(rows).fillna("—")
    df = df.loc[:, (df != "—").any(axis=0)]
    return md_table(df, fmt={c: "{}" for c in df.columns})


def _constraint_table(raw: pd.DataFrame, gt_raw: pd.DataFrame, has_warn: bool) -> str:
    """Per-sub-check table with Pass/Warn/Fail for constraint checks (5 & 6)."""
    by_c = raw.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
    for col in ("PASS", "WARN", "FAIL"):
        if col not in by_c.columns:
            by_c[col] = 0
    by_c["total"] = by_c["PASS"] + by_c.get("WARN", 0) + by_c["FAIL"]

    gt_lookup = {}
    if gt_raw is not None and not gt_raw.empty:
        gt_by_c = gt_raw.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
        for col in ("PASS", "WARN", "FAIL"):
            if col not in gt_by_c.columns:
                gt_by_c[col] = 0
        gt_by_c["total"] = gt_by_c["PASS"] + gt_by_c.get("WARN", 0) + gt_by_c["FAIL"]
        for _, r in gt_by_c.iterrows():
            t = r["total"]
            gt_lookup[r["constraint_name"]] = {
                "PASS": f"{100*r['PASS']/t:.1f}%" if t else "—",
                "WARN": f"{100*r.get('WARN',0)/t:.1f}%" if t else "—",
                "FAIL": f"{100*r['FAIL']/t:.1f}%" if t else "—",
            }

    rows = []
    for _, sub_row in by_c.iterrows():
        c = sub_row["constraint_name"]
        t = sub_row["total"]
        gt = gt_lookup.get(c, {})
        entry = {
            "Sub-check":   c,
            "Pass (%)":    f"{100*sub_row['PASS']/t:.1f}%" if t else "—",
            "Fail (%)":    f"{100*sub_row['FAIL']/t:.1f}%" if t else "—",
            "GT Pass (%)": gt.get("PASS", GT_MISSING),
            "GT Fail (%)": gt.get("FAIL", GT_MISSING),
        }
        if has_warn:
            entry["Warn (%)"]    = f"{100*sub_row.get('WARN',0)/t:.1f}%" if t else "—"
            entry["GT Warn (%)"] = gt.get("WARN", "—")
            # Reorder to put Warn between Pass and Fail
            entry = {k: entry[k] for k in
                     ["Sub-check","Pass (%)","Warn (%)","Fail (%)","GT Pass (%)","GT Warn (%)","GT Fail (%)"]}
        rows.append(entry)

    return _simple_table(rows)


def section_overview(run_dir: Path) -> str:
    """One small table per check, stacked vertically."""
    blocks = []

    # 1. Hierarchy Sum Check
    sc_raw    = load(run_dir, "sum_check", "results.csv")
    gt_sc_raw = load(run_dir, "sum_check_ground_truth", "results.csv")
    if sc_raw is not None:
        sc,    _ = _adapt_sum_results(sc_raw)
        gt_sc, _ = _adapt_sum_results(gt_sc_raw) if gt_sc_raw is not None else (None, None)
        tbl = _simple_table([
            {"Metric": "Pass rate",
             "Predictions": _fmt_pr(100 * sc["passed"].mean()),
             "Ground Truth": _fmt_pr(100 * gt_sc["passed"].mean()) if gt_sc is not None else GT_MISSING},
            {"Metric": "Mean relative error",
             "Predictions": f'{sc["mean_error_pct"].mean():.3f}%',
             "Ground Truth": f'{gt_sc["mean_error_pct"].mean():.3f}%' if gt_sc is not None else GT_MISSING},
        ])
        blocks.append("**1. Hierarchy Sum Check**\n\n" + tbl)

    # 2. Growth Rate Plausibility
    pl_raw    = load(run_dir, "check_plausibility", "results.csv")
    gt_pl_raw = load(run_dir, "check_plausibility_ground_truth", "results.csv")
    if pl_raw is not None:
        viol = _adapt_plausibility(pl_raw)
        if viol is not None:
            gt_pr = GT_MISSING
            if gt_pl_raw is not None:
                gt_viol = _adapt_plausibility(gt_pl_raw)
                if gt_viol is not None:
                    gt_pr = _fmt_pr(100 * (1 - gt_viol["violation"].mean()))
            tbl = _simple_table([
                {"Metric": "Pass rate (timesteps)",
                 "Predictions": _fmt_pr(100 * (1 - viol["violation"].mean())),
                 "Ground Truth": gt_pr},
            ])
            blocks.append("**2. Growth Rate Plausibility**\n\n" + tbl)

    # 3. Regional Consistency
    rc_raw    = load(run_dir, "regional_consistency", "results.csv")
    gt_rc_raw = load(run_dir, "regional_consistency_ground_truth", "results.csv")
    if rc_raw is not None and not rc_raw.empty:
        rc = _adapt_regional(rc_raw)
        if rc is not None:
            gt_pr = GT_MISSING
            if gt_rc_raw is not None and not gt_rc_raw.empty:
                gt_rc = _adapt_regional(gt_rc_raw)
                if gt_rc is not None:
                    gt_pr = _fmt_pr(100 * gt_rc["passed"].mean())
            tbl = _simple_table([
                {"Metric": "Pass rate (scenario × variable)",
                 "Predictions": _fmt_pr(100 * rc["passed"].mean()),
                 "Ground Truth": gt_pr},
            ])
            blocks.append("**3. Regional Consistency**\n\n" + tbl)
    elif rc_raw is not None and rc_raw.empty:
        blocks.append("**3. Regional Consistency**\n\n_No complete regional groupings in this dataset._")

    # 4. Physical Bounds Check
    bc_raw    = load(run_dir, "bounds_check", "results.csv")
    gt_bc_raw = load(run_dir, "bounds_check_ground_truth", "results.csv")
    if bc_raw is not None:
        bc, _ = _adapt_bounds(bc_raw)
        if bc is not None:
            total  = bc["n_timesteps"].sum()
            n_viol = bc["n_violations"].sum()
            pr     = 100 * (1 - n_viol / total) if total else 100.0
            gt_pr  = GT_MISSING
            if gt_bc_raw is not None:
                gt_bc, _ = _adapt_bounds(gt_bc_raw)
                if gt_bc is not None:
                    gt_t  = gt_bc["n_timesteps"].sum()
                    gt_pr = _fmt_pr(100 * (1 - gt_bc["n_violations"].sum() / gt_t)) if gt_t else GT_MISSING
            tbl = _simple_table([
                {"Metric": "Pass rate (timesteps)",
                 "Predictions": _fmt_pr(pr),
                 "Ground Truth": gt_pr},
            ])
            blocks.append("**4. Physical Bounds Check**\n\n" + tbl)

    # 5. Hard Historical Constraints
    hh_raw    = load(run_dir, "hard_historical_constraints", "results.csv")
    gt_hh_raw = load(run_dir, "hard_historical_constraints_ground_truth", "results.csv")
    if hh_raw is not None and not hh_raw.empty:
        tbl = _constraint_table(hh_raw, gt_hh_raw, has_warn=True)
        blocks.append("**5. Hard Historical Constraints** _(PASS = within IP range, WARN = within outer tolerance)_\n\n" + tbl)

    # 6. Soft Future Constraints
    sf_raw    = load(run_dir, "soft_future_constraints", "results.csv")
    gt_sf_raw = load(run_dir, "soft_future_constraints_ground_truth", "results.csv")
    if sf_raw is not None and not sf_raw.empty:
        tbl = _constraint_table(sf_raw, gt_sf_raw, has_warn=False)
        blocks.append("**6. Soft Future Constraints**\n\n" + tbl)

    # 7. Verpoort constraints
    vc_raw    = load(run_dir, "sci_checks", "results.csv")
    gt_vc_raw = load(run_dir, "sci_checks_ground_truth", "results.csv")
    if vc_raw is not None and not vc_raw.empty:
        tbl = _constraint_table(vc_raw, gt_vc_raw, has_warn=True)
        blocks.append("**7. SCI Vetting Checks**\n\n" + tbl)

    # 8. Inter-variable Correlations
    corr_sum = load(run_dir, "inter_variable_correlation", "summary.csv")
    if corr_sum is not None and "Mean_abs_diff_r2" in corr_sum.columns:
        mean_diff = corr_sum["Mean_abs_diff_r2"].mean()
        tbl = _simple_table([
            {"Metric": "Mean |Δr²| vs ground truth",
             "Predictions": f"{mean_diff:.4f}",
             "Ground Truth": "0.0000 (reference)"},
        ])
        blocks.append("**7. Inter-variable Correlations**\n\n" + tbl)

    return "\n\n".join(blocks) if blocks else "_No check results found._"


# ---------------------------------------------------------------------------
# Sum check section
# ---------------------------------------------------------------------------

def section_sum_check(run_dir: Path, fig_dir: Path) -> tuple:
    sc_raw = load(run_dir, "sum_check", "results.csv")
    gt_sc_raw = load(run_dir, "sum_check_ground_truth", "results.csv")

    if sc_raw is None:
        return "_Sum check results not found. Run `validate.py` first._\n", []

    sc, te = _adapt_sum_results(sc_raw)
    gt_sc, gt_te = _adapt_sum_results(gt_sc_raw) if gt_sc_raw is not None else (None, None)

    blocks  = [] if gt_sc is not None else [_gt_missing_note("sum_check")]
    figures = []

    # Pass rate table
    tbl_data = (
        sc.groupby("parent_variable")
        .agg(
            n_scenario_regions=("passed", "count"),
            pass_rate_pct=("passed", lambda x: 100 * x.mean()),
            mean_error_pct=("mean_error_pct", "mean"),
            max_error_pct=("max_error_pct", "max"),
        )
        .reset_index()
        .rename(columns={
            "parent_variable": "Parent Variable",
            "n_scenario_regions": "Scenario-regions",
            "pass_rate_pct": "Pass rate (%)",
            "mean_error_pct": "Mean error (%)",
            "max_error_pct": "Max error (%)",
        })
    )
    blocks.append("### Pass Rates by Parent Variable\n\n" + md_table(tbl_data))

    # Figure: error distribution
    fig, ax = plt.subplots(figsize=(7, 3.5))
    max_bin = min(te["abs_error"].quantile(0.99) * 1.1, 1.0)
    bins = np.linspace(0, max_bin, 60)
    ax.hist(te["abs_error"].clip(upper=max_bin), bins=bins, color=C_PRED, alpha=0.7, label="Predictions", density=True)
    if gt_te is not None:
        ax.hist(gt_te["abs_error"].clip(upper=max_bin), bins=bins, color=C_GT, alpha=0.6, label="Ground truth", density=True)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    style_ax(ax, title="Sum Check — Error Distribution",
             xlabel="|parent − sum_children| / |parent|", ylabel="Density")
    if gt_te is not None:
        ax.legend(fontsize=8)
    fig.tight_layout()
    rel = save_fig(fig, fig_dir, "sum_check_error_dist")
    figures.append(rel)
    blocks.append(f"### Error Distribution\n\n![Sum check error distribution]({rel})")

    # Figure: mean error by year
    if "Year" in te.columns:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        for parent in te["parent_variable"].dropna().unique():
            sub = te[te["parent_variable"] == parent]
            by_year = sub.groupby("Year")["abs_error"].mean() * 100
            ax.plot(by_year.index, by_year.values, marker="o", markersize=3,
                    color=C_PRED, linewidth=1.5, label=f"Pred: {parent.split('|')[-1]}")
        if gt_te is not None and "Year" in gt_te.columns:
            for parent in gt_te["parent_variable"].dropna().unique():
                sub = gt_te[gt_te["parent_variable"] == parent]
                by_year = sub.groupby("Year")["abs_error"].mean() * 100
                ax.plot(by_year.index, by_year.values, marker="o", markersize=3,
                        color=C_GT, linestyle="--", linewidth=1.5, label=f"GT: {parent.split('|')[-1]}")
        ax.yaxis.set_major_formatter(mticker.PercentFormatter())
        style_ax(ax, title="Sum Check — Mean Error by Year", xlabel="Year", ylabel="Mean relative error (%)")
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        rel = save_fig(fig, fig_dir, "sum_check_error_by_year")
        figures.append(rel)
        blocks.append(f"### Mean Error by Year\n\n![Sum check error by year]({rel})")

    # GT percentile comparison
    if gt_sc is not None:
        pcts = [50, 75, 90, 95, 99]
        tbl = pd.DataFrame({
            "Percentile": [f"p{p}" for p in pcts],
            "Predictions (%)": [f"{np.percentile(sc['mean_error_pct'].dropna(), p):.4f}" for p in pcts],
            "Ground truth (%)": [f"{np.percentile(gt_sc['mean_error_pct'].dropna(), p):.4f}" for p in pcts],
        })
        blocks.append("### Error Percentile Comparison — Predictions vs Ground Truth\n\n"
                      + md_table(tbl, fmt={c: "{}" for c in tbl.columns}))

    # Example failures
    blocks.append(
        "### Example Failure\n\n"
        "_The median failing scenario (by mean error) is shown below._\n\n"
        + _example_sum_failure(te, sc, "predictions")
    )
    if gt_sc is not None and gt_te is not None:
        blocks.append(_example_sum_failure(gt_te, gt_sc, "ground truth"))

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------
# Plausibility section
# ---------------------------------------------------------------------------

def section_plausibility(run_dir: Path, fig_dir: Path) -> tuple:
    pl_raw   = load(run_dir, "check_plausibility", "results.csv")
    bnd_raw  = load(run_dir, "check_plausibility", "summary.csv")  # has Pass_Rate by category
    gt_raw   = load(run_dir, "check_plausibility_ground_truth", "results.csv")

    if pl_raw is None:
        return "_Growth rate plausibility results not found. Run `validate.py` first._\n", []

    viol    = _adapt_plausibility(pl_raw)
    gt_viol = _adapt_plausibility(gt_raw) if gt_raw is not None else None

    blocks  = [] if gt_viol is not None else [_gt_missing_note("check_plausibility")]
    figures = []

    # Summary stats
    total  = len(viol)
    n_viol = viol["violation"].sum()
    vr     = 100 * n_viol / total if total else 0.0
    summary = (
        f"**Total timesteps evaluated:** {total:,}  \n"
        f"**Violations:** {int(n_viol):,} ({vr:.2f}%)"
    )
    if gt_viol is not None:
        gt_total = len(gt_viol)
        gt_nviol = gt_viol["violation"].sum()
        gt_vr    = 100 * gt_nviol / gt_total if gt_total else 0.0
        summary += (
            f"  \n\n**Ground truth — violation rate:** {gt_vr:.2f}%  \n"
            f"_({vr - gt_vr:+.2f}pp difference: predictions vs ground truth)_"
        )
    blocks.append(summary)

    # Figure: violation rate by variable
    def _by_var(df):
        return (
            df.groupby("Variable")
            .agg(total=("violation", "count"), violations=("violation", "sum"))
            .reset_index()
            .assign(**{"rate_%": lambda d: 100 * d["violations"] / d["total"]})
        )

    by_var = _by_var(viol).sort_values("rate_%", ascending=True)
    gt_by_var = _by_var(gt_viol) if gt_viol is not None else None

    fig, ax = plt.subplots(figsize=(7, max(3, len(by_var) * 0.55)))
    y_pos = np.arange(len(by_var))
    bar_h = 0.4 if gt_by_var is not None else 0.6
    ax.barh(y_pos, by_var["rate_%"], height=bar_h, color=C_PRED, alpha=0.8, label="Predictions")
    if gt_by_var is not None:
        gt_rates = gt_by_var.set_index("Variable").reindex(by_var["Variable"])["rate_%"].fillna(0)
        ax.barh(y_pos + bar_h, gt_rates.values, height=bar_h, color=C_GT, alpha=0.7, label="Ground truth")
    ax.set_yticks(y_pos + (bar_h / 2 if gt_by_var is not None else 0))
    ax.set_yticklabels(by_var["Variable"], fontsize=8)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    if gt_by_var is not None:
        ax.legend(fontsize=8)
    style_ax(ax, title="Growth Rate Violations by Variable", xlabel="Violation rate (%)")
    fig.tight_layout()
    rel = save_fig(fig, fig_dir, "plausibility_violations_by_variable")
    figures.append(rel)
    blocks.append(f"### Violation Rate by Variable\n\n![Plausibility violations by variable]({rel})")

    # Example violations
    blocks.append(
        "### Example Violation\n\n"
        "_The most extreme growth rate violation is shown below._\n\n"
        + _example_plausibility_failure(viol, "predictions")
    )
    if gt_viol is not None:
        blocks.append(_example_plausibility_failure(gt_viol, "ground truth"))

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------
# Regional consistency section
# ---------------------------------------------------------------------------

def section_regional(run_dir: Path, fig_dir: Path) -> tuple:
    rc_raw    = load(run_dir, "regional_consistency",              "results.csv")
    gt_rc_raw = load(run_dir, "regional_consistency_ground_truth", "results.csv")

    if rc_raw is None:
        return ("_Regional consistency results not found. Run `validate.py` first, "
                "or skip if your run has no multi-region scenarios._\n"), []

    # Empty file means the check ran but found no complete regional groupings
    if rc_raw.empty:
        return ("_No complete regional groupings found in this dataset. The check requires "
                "all subregions in a grouping (R5/R6/R10) to have data for the same "
                "scenario-variable-year combinations. This dataset has partial regional "
                "coverage only._\n"), []

    rc    = _adapt_regional(rc_raw)
    gt_rc = _adapt_regional(gt_rc_raw) if (gt_rc_raw is not None and not gt_rc_raw.empty) else None

    blocks  = [] if gt_rc is not None else [_gt_missing_note("regional_consistency")]
    figures = []

    def _grouping_table(df):
        return (
            df.groupby("grouping")
            .agg(
                total=("passed", "count"),
                passed=("passed", "sum"),
                mean_error_pct=("mean_error_pct", "mean"),
                max_error_pct=("max_error_pct", "max"),
            )
            .reset_index()
            .assign(**{"pass_rate_%": lambda d: 100 * d["passed"] / d["total"]})
        )

    pred_grp = _grouping_table(rc)
    tbl = pred_grp[["grouping","total","passed","pass_rate_%","mean_error_pct","max_error_pct"]].copy()
    tbl.columns = ["Grouping","Total","Passed","Pass rate (%)","Mean error (%)","Max error (%)"]
    blocks.append("### Pass Rates by Regional Grouping — Predictions\n\n" + md_table(tbl))

    if gt_rc is not None:
        gt_grp = _grouping_table(gt_rc)
        gt_tbl = gt_grp[["grouping","total","passed","pass_rate_%","mean_error_pct","max_error_pct"]].copy()
        gt_tbl.columns = tbl.columns
        blocks.append("### Pass Rates by Regional Grouping — Ground Truth\n\n" + md_table(gt_tbl))

    # Figure: pass rate by variable per grouping
    if "Variable" in rc.columns:
        var_grp = (
            rc.groupby(["grouping","Variable"])
            .agg(total=("passed","count"), passed=("passed","sum"))
            .reset_index()
        )
        var_grp["pass_rate_%"] = 100 * var_grp["passed"] / var_grp["total"]
        groupings = var_grp["grouping"].unique()

        fig, axes = plt.subplots(
            1, len(groupings),
            figsize=(5 * len(groupings), max(3.5, len(var_grp["Variable"].unique()) * 0.4)),
            sharey=True,
        )
        if len(groupings) == 1:
            axes = [axes]

        for ax, g in zip(axes, sorted(groupings)):
            sub = var_grp[var_grp["grouping"] == g].sort_values("pass_rate_%")
            ax.barh(sub["Variable"], sub["pass_rate_%"], color=C_PRED, alpha=0.8, label="Predictions")
            if gt_rc is not None and "Variable" in gt_rc.columns:
                gt_vg = (
                    gt_rc[gt_rc["grouping"] == g]
                    .groupby("Variable").agg(total=("passed","count"), passed=("passed","sum"))
                    .reset_index()
                )
                gt_vg["pass_rate_%"] = 100 * gt_vg["passed"] / gt_vg["total"]
                gt_vg = gt_vg.set_index("Variable").reindex(sub["Variable"]).reset_index()
                ax.barh(np.arange(len(sub)) + 0.3, gt_vg["pass_rate_%"].fillna(0),
                        height=0.3, color=C_GT, alpha=0.7, label="Ground truth")
            ax.xaxis.set_major_formatter(mticker.PercentFormatter())
            style_ax(ax, title=f"{g}", xlabel="Pass rate (%)")
            ax.set_xlim(0, 105)
            if ax == axes[-1]:
                ax.legend(fontsize=7)

        fig.suptitle("Regional Consistency — Pass Rate by Variable", fontsize=11, fontweight="bold")
        fig.tight_layout()
        rel = save_fig(fig, fig_dir, "regional_consistency_by_variable")
        figures.append(rel)
        blocks.append(f"### Pass Rate by Variable\n\n![Regional consistency by variable]({rel})")

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------
# Bounds check section
# ---------------------------------------------------------------------------

def section_bounds(run_dir: Path, fig_dir: Path) -> tuple:
    bc_raw    = load(run_dir, "bounds_check",              "results.csv")
    gt_bc_raw = load(run_dir, "bounds_check_ground_truth", "results.csv")

    if bc_raw is None:
        return "_Bounds check results not found. Run `validate.py` first._\n", []

    bc, viol    = _adapt_bounds(bc_raw)
    gt_bc, _    = _adapt_bounds(gt_bc_raw) if gt_bc_raw is not None else (None, None)

    blocks  = [] if gt_bc is not None else [_gt_missing_note("bounds_check")]
    figures = []

    total  = bc["n_timesteps"].sum()
    n_viol = bc["n_violations"].sum()
    vr     = 100 * n_viol / total if total else 0.0
    n_clean = bc["passed"].sum()
    blocks.append(
        f"**Timesteps checked:** {total:,}  \n"
        f"**Violations:** {int(n_viol):,} ({vr:.3f}%)  \n"
        f"**Fully clean scenario-regions:** {int(n_clean):,} / {len(bc):,}"
    )

    # Figure: violations by variable
    by_var = (
        bc.groupby("Variable")
        .agg(n_violations=("n_violations","sum"), n_timesteps=("n_timesteps","sum"),
             n_below=("n_below_lower","sum"), n_above=("n_above_upper","sum"))
        .reset_index()
    )
    by_var["rate_%"] = 100 * by_var["n_violations"] / by_var["n_timesteps"]
    by_var = by_var.sort_values("n_violations", ascending=True)

    if by_var["n_violations"].sum() > 0:
        fig, ax = plt.subplots(figsize=(7, max(3, len(by_var) * 0.45)))
        ax.barh(by_var["Variable"], by_var["n_below"], color=C_PRED, alpha=0.8, label="Below lower bound")
        ax.barh(by_var["Variable"], by_var["n_above"], left=by_var["n_below"],
                color=C_GT, alpha=0.7, label="Above upper bound")
        style_ax(ax, title="Bounds Violations by Variable", xlabel="Number of violating timesteps")
        ax.legend(fontsize=8)
        fig.tight_layout()
        rel = save_fig(fig, fig_dir, "bounds_violations_by_variable")
        figures.append(rel)
        blocks.append(f"### Violations by Variable\n\n![Bounds violations by variable]({rel})")
    else:
        blocks.append("### Violations by Variable\n\n✓ No violations detected across any variable.")

    # GT comparison table + paired bar
    if gt_bc is not None:
        gt_total = gt_bc["n_timesteps"].sum()
        gt_nviol = gt_bc["n_violations"].sum()
        gt_vr    = 100 * gt_nviol / gt_total if gt_total else 0.0
        diff_pp  = vr - gt_vr
        sign     = "+" if diff_pp >= 0 else ""
        tbl = pd.DataFrame([
            {"Source": "Predictions", "Timesteps": f"{total:,}", "Violations": f"{int(n_viol):,}", "Violation rate": f"{vr:.3f}%"},
            {"Source": "Ground truth", "Timesteps": f"{gt_total:,}", "Violations": f"{int(gt_nviol):,}", "Violation rate": f"{gt_vr:.3f}%"},
        ])
        blocks.append(
            f"### Predictions vs Ground Truth\n\n"
            + md_table(tbl, fmt={c: "{}" for c in tbl.columns})
            + f"\n\n_Predictions show {sign}{diff_pp:.3f} pp more violations than ground truth._"
        )

        if "Variable" in gt_bc.columns and by_var["n_violations"].sum() > 0:
            gt_bv = (
                gt_bc.groupby("Variable")
                .agg(n_violations=("n_violations","sum"), n_timesteps=("n_timesteps","sum"))
                .reset_index()
            )
            gt_bv["rate_%"] = 100 * gt_bv["n_violations"] / gt_bv["n_timesteps"]
            merged = by_var[["Variable","rate_%"]].merge(
                gt_bv[["Variable","rate_%"]].rename(columns={"rate_%":"gt_rate_%"}),
                on="Variable", how="left",
            ).sort_values("rate_%", ascending=True)

            fig, ax = plt.subplots(figsize=(7, max(3, len(merged) * 0.45)))
            y = np.arange(len(merged))
            ax.barh(y, merged["rate_%"], height=0.4, color=C_PRED, alpha=0.8, label="Predictions")
            ax.barh(y + 0.4, merged["gt_rate_%"].fillna(0), height=0.4, color=C_GT, alpha=0.7, label="Ground truth")
            ax.set_yticks(y + 0.2)
            ax.set_yticklabels(merged["Variable"], fontsize=8)
            ax.xaxis.set_major_formatter(mticker.PercentFormatter())
            style_ax(ax, title="Bounds Violation Rate — Predictions vs Ground Truth", xlabel="Violation rate (%)")
            ax.legend(fontsize=8)
            fig.tight_layout()
            rel = save_fig(fig, fig_dir, "bounds_violation_rate_pred_vs_gt")
            figures.append(rel)
            blocks.append(f"### Violation Rate by Variable — Predictions vs Ground Truth\n\n![Bounds violation rate pred vs GT]({rel})")

    # Example violations
    if viol is not None and not viol.empty:
        blocks.append(
            "### Example Violation\n\n"
            "_The most extreme bounds violation is shown below._\n\n"
            + _example_bounds_failure(viol, "predictions")
        )
    gt_viol_df = load(run_dir, "bounds_check_ground_truth", "results.csv")
    if gt_viol_df is not None:
        _, gt_viol_raw = _adapt_bounds(gt_viol_df)
        if gt_viol_raw is not None and not gt_viol_raw.empty:
            blocks.append(_example_bounds_failure(gt_viol_raw, "ground truth"))

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------
# Hard historical constraints section
# ---------------------------------------------------------------------------

def section_hard_historical(run_dir: Path) -> str:
    pred = load(run_dir, "hard_historical_constraints", "results.csv")
    gt   = load(run_dir, "hard_historical_constraints_ground_truth", "results.csv")
    skipped_path = run_dir / "hard_historical_constraints" / "skipped.txt"

    if pred is None:
        return "_Hard historical constraints results not found. Run `validate.py` first._\n"

    blocks = []

    # Build summary table per constraint
    for col in ("PASS", "WARN", "FAIL"):
        if col not in pred.columns:
            pred[col if col in pred.columns else col] = 0

    summary = pred.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
    for col in ("PASS", "WARN", "FAIL"):
        if col not in summary.columns:
            summary[col] = 0
    summary["N"] = summary["PASS"] + summary.get("WARN", 0) + summary["FAIL"]
    summary["Pass (%)"]  = (100 * summary["PASS"] / summary["N"].replace(0, np.nan)).round(1)
    if "WARN" in summary.columns and summary["WARN"].sum() > 0:
        summary["Warn (%)"] = (100 * summary["WARN"] / summary["N"].replace(0, np.nan)).round(1)
    summary["Fail (%)"]  = (100 * summary["FAIL"] / summary["N"].replace(0, np.nan)).round(1)

    if gt is not None:
        gt_sum = gt.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
        for col in ("PASS", "FAIL"):
            if col not in gt_sum.columns:
                gt_sum[col] = 0
        gt_sum["N_gt"] = gt_sum["PASS"] + gt_sum.get("FAIL", 0)
        gt_sum["GT Pass (%)"] = (100 * gt_sum["PASS"] / gt_sum["N_gt"].replace(0, np.nan)).round(1)
        gt_sum["GT Fail (%)"] = (100 * gt_sum["FAIL"] / gt_sum["N_gt"].replace(0, np.nan)).round(1)
        summary = summary.merge(gt_sum[["constraint_name","GT Pass (%)","GT Fail (%)"]], on="constraint_name", how="left")

    cols = ["constraint_name","N","Pass (%)"]
    if "Warn (%)" in summary.columns:
        cols.append("Warn (%)")
    cols += ["Fail (%)"]
    if "GT Pass (%)" in summary.columns:
        cols += ["GT Pass (%)","GT Fail (%)"]
    tbl = summary[cols].rename(columns={"constraint_name": "Sub-check"})
    blocks.append(md_table(tbl.fillna("—")))

    if skipped_path.exists():
        txt = skipped_path.read_text().strip()
        if txt:
            blocks.append(f"\n_Skipped sub-checks (required variables absent): {txt.replace(chr(10),', ')}_")

    unit_warn_path = run_dir / "hard_historical_constraints" / "unit_warnings.txt"
    if unit_warn_path.exists():
        txt = unit_warn_path.read_text().strip()
        if txt:
            for line in txt.splitlines():
                blocks.append(f'\n<p style="color:red;font-weight:bold">⚠️ {line}</p>')

    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Soft future constraints section
# ---------------------------------------------------------------------------

def section_soft_future(run_dir: Path) -> str:
    pred = load(run_dir, "soft_future_constraints", "results.csv")
    gt   = load(run_dir, "soft_future_constraints_ground_truth", "results.csv")
    skipped_path = run_dir / "soft_future_constraints" / "skipped.txt"

    if pred is None:
        return "_Soft future constraints results not found. Run `validate.py` first._\n"

    blocks = []
    summary = pred.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
    for col in ("PASS", "FAIL"):
        if col not in summary.columns:
            summary[col] = 0
    summary["N"] = summary["PASS"] + summary["FAIL"]
    summary["Pass (%)"] = (100 * summary["PASS"] / summary["N"].replace(0, np.nan)).round(1)
    summary["Fail (%)"] = (100 * summary["FAIL"] / summary["N"].replace(0, np.nan)).round(1)

    if gt is not None:
        gt_sum = gt.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
        for col in ("PASS", "FAIL"):
            if col not in gt_sum.columns:
                gt_sum[col] = 0
        gt_sum["N_gt"] = gt_sum["PASS"] + gt_sum["FAIL"]
        gt_sum["GT Pass (%)"] = (100 * gt_sum["PASS"] / gt_sum["N_gt"].replace(0, np.nan)).round(1)
        gt_sum["GT Fail (%)"] = (100 * gt_sum["FAIL"] / gt_sum["N_gt"].replace(0, np.nan)).round(1)
        summary = summary.merge(gt_sum[["constraint_name","GT Pass (%)","GT Fail (%)"]], on="constraint_name", how="left")

    cols = ["constraint_name","N","Pass (%)","Fail (%)"]
    if "GT Pass (%)" in summary.columns:
        cols += ["GT Pass (%)","GT Fail (%)"]
    tbl = summary[cols].rename(columns={"constraint_name": "Sub-check"})
    blocks.append(md_table(tbl.fillna("—")))

    if skipped_path.exists():
        txt = skipped_path.read_text().strip()
        if txt:
            blocks.append(f"\n_Skipped sub-checks (required variables absent): {txt.replace(chr(10),', ')}_")

    unit_warn_path = run_dir / "soft_future_constraints" / "unit_warnings.txt"
    if unit_warn_path.exists():
        txt = unit_warn_path.read_text().strip()
        if txt:
            for line in txt.splitlines():
                blocks.append(f'\n<p style="color:red;font-weight:bold">⚠️ {line}</p>')

    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Verpoort constraints section
# ---------------------------------------------------------------------------

def section_sci_checks(run_dir: Path) -> str:
    """Verpoort et al. (2025) IAMC vetting criteria."""
    pred = load(run_dir, "sci_checks", "results.csv")
    gt   = load(run_dir, "sci_checks_ground_truth", "results.csv")
    skipped_path = run_dir / "sci_checks" / "skipped.csv"

    if pred is None:
        return "_Verpoort constraints results not found. Run `validate.py` first._\n"

    blocks = []

    summary = pred.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
    for col in ("PASS", "WARN", "FAIL"):
        if col not in summary.columns:
            summary[col] = 0
    summary["N"] = summary["PASS"] + summary.get("WARN", 0) + summary["FAIL"]
    summary["Pass (%)"] = (100 * summary["PASS"] / summary["N"].replace(0, np.nan)).round(1)
    if "WARN" in summary.columns and summary["WARN"].sum() > 0:
        summary["Warn (%)"] = (100 * summary["WARN"] / summary["N"].replace(0, np.nan)).round(1)
    summary["Fail (%)"] = (100 * summary["FAIL"] / summary["N"].replace(0, np.nan)).round(1)

    if gt is not None and not gt.empty:
        gt_sum = gt.groupby("constraint_name")["status"].value_counts().unstack(fill_value=0).reset_index()
        for col in ("PASS", "WARN", "FAIL"):
            if col not in gt_sum.columns:
                gt_sum[col] = 0
        gt_sum["N_gt"] = gt_sum["PASS"] + gt_sum.get("WARN", 0) + gt_sum["FAIL"]
        gt_sum["GT Pass (%)"] = (100 * gt_sum["PASS"] / gt_sum["N_gt"].replace(0, np.nan)).round(1)
        gt_sum["GT Fail (%)"] = (100 * gt_sum["FAIL"] / gt_sum["N_gt"].replace(0, np.nan)).round(1)
        summary = summary.merge(gt_sum[["constraint_name", "GT Pass (%)", "GT Fail (%)"]],
                                on="constraint_name", how="left")

    cols = ["constraint_name", "N", "Pass (%)"]
    if "Warn (%)" in summary.columns:
        cols.append("Warn (%)")
    cols.append("Fail (%)")
    if "GT Pass (%)" in summary.columns:
        cols += ["GT Pass (%)", "GT Fail (%)"]
    tbl = summary[cols].rename(columns={"constraint_name": "Sub-check"})
    blocks.append(md_table(tbl.fillna("—")))

    if skipped_path.exists():
        sk = pd.read_csv(skipped_path)
        if not sk.empty:
            skipped_list = sk.apply(lambda r: f"{r['constraint']} ({r['reason']})", axis=1).tolist()
            blocks.append(f"\n_Not run: {', '.join(skipped_list)}_")

    unit_warn_path = run_dir / "sci_checks" / "unit_warnings.csv"
    if unit_warn_path.exists():
        uwdf = pd.read_csv(unit_warn_path)
        if not uwdf.empty:
            for _, row in uwdf.iterrows():
                blocks.append(f'\n<p style="color:red;font-weight:bold">⚠️ {row["warning"]}</p>')

    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Correlations section  (uses pre-generated figures from inter_variable_correlation/)
# ---------------------------------------------------------------------------

def section_correlations(run_dir: Path, fig_dir: Path) -> tuple:
    corr_dir = run_dir / "inter_variable_correlation"
    src_figs = corr_dir / "figures"
    summary  = load(run_dir, "inter_variable_correlation", "summary.csv")

    if not corr_dir.exists():
        return "_Inter-variable correlation results not found. Run `validate.py` first._\n", []

    blocks = [
        "Inter-variable Pearson r² matrices at years 2030, 2050, and 2100, "
        "comparing model predictions against AR6 ground truth. "
        "Values close to the ground truth indicate the emulator preserves "
        "real-world variable relationships. "
        "Methodology follows Li et al. (2025) Fig. 4."
    ]
    figures = []

    for year in [2030, 2050, 2100]:
        src = src_figs / f"correlations_{year}.png"
        if src.exists():
            dst = fig_dir / f"correlations_{year}.png"
            shutil.copy2(src, dst)
            rel = f"figures/correlations_{year}.png"
            figures.append(rel)
            # Determine if GT was available (diff matrix exists)
            has_gt = (corr_dir / f"diff_corr_{year}.csv").exists()
            caption = (
                "_Left: predictions. Centre: AR6 ground truth. "
                "Right: difference (blue = predictions underestimate correlation, red = overestimate)._"
                if has_gt else "_Predictions correlation matrix (no ground truth available)._"
            )
            blocks.append(f"### {year}\n\n{caption}\n\n![Inter-variable correlations {year}]({rel})")

    if summary is not None and "Mean_abs_diff_r2" in summary.columns:
        tbl = summary[["Year","N_variables","Mean_abs_diff_r2"]].copy()
        tbl.columns = ["Year","N variables","Mean |Δr²| (off-diagonal)"]
        blocks.append(
            "### Summary: Mean Absolute Difference in r²\n\n"
            "_Average absolute difference between predictions and ground truth correlation matrices "
            "(off-diagonal pairs only). Lower is better._\n\n"
            + md_table(tbl, fmt={c: "{}" for c in tbl.columns})
        )

    return "\n\n".join(blocks) + "\n", figures


# ---------------------------------------------------------------------------
# Error metrics section  (reconstruction only)
# ---------------------------------------------------------------------------

def section_error_metrics(run_dir: Path, fig_dir: Path) -> tuple:
    """
    Portrait plot (Variable × Region nRMSE heatmap) plus headline summary
    table and temporal drift chart. Only present for reconstruction runs.
    """
    summary   = load(run_dir, "error_metrics", "summary.csv")
    by_vr     = load(run_dir, "error_metrics", "results.csv")
    by_vy     = load(run_dir, "error_metrics", "by_variable_year.csv")
    portrait  = load(run_dir, "error_metrics", "portrait_matrix.csv")

    if summary is None:
        return (
            "_Error metrics results not found. Run `validate.py` with "
            "`--method_type reconstruction` to generate them._\n",
            [],
        )

    blocks  = []
    figures = []

    # Headline summary table
    cols = ["Variable", "Units", "Mean_nRMSE", "Mean_RMSE", "Mean_MAE", "Mean_R2", "Mean_Bias"]
    cols = [c for c in cols if c in summary.columns]
    tbl  = summary[cols].copy()
    tbl.columns = [
        c.replace("Mean_", "").replace("_", " ") for c in cols
    ]
    blocks.append(
        "### Per-variable Summary\n\n"
        "_Metrics averaged over all regions. nRMSE = RMSE / mean(|ground truth|) — "
        "dimensionless, comparable across variables. Lower is better._\n\n"
        + md_table(tbl)
    )

    # Portrait plot — Variable × Region nRMSE heatmap
    if portrait is not None and not portrait.empty:
        portrait = portrait.set_index("Variable") if "Variable" in portrait.columns else portrait
        # Drop columns that are entirely NaN
        portrait = portrait.dropna(axis=1, how="all").dropna(axis=0, how="all")

        if not portrait.empty:
            n_vars    = len(portrait)
            n_regions = len(portrait.columns)
            fig_h     = max(3.0, n_vars * 0.55)
            fig_w     = max(4.0, n_regions * 1.1 + 2.0)

            fig, ax = plt.subplots(figsize=(fig_w, fig_h))
            data    = portrait.values.astype(float)

            # Cap display at 2.0 so outlier regions don't wash out the colour scale
            vmax = min(np.nanmax(data), 2.0)
            im   = ax.imshow(data, aspect="auto", cmap="YlOrRd",
                             vmin=0, vmax=vmax, interpolation="nearest")

            ax.set_xticks(range(n_regions))
            ax.set_xticklabels(portrait.columns, rotation=45, ha="right", fontsize=8)
            ax.set_yticks(range(n_vars))
            ax.set_yticklabels(portrait.index, fontsize=8)

            # Annotate cells with nRMSE values
            for i in range(n_vars):
                for j in range(n_regions):
                    val = data[i, j]
                    if not np.isnan(val):
                        txt_col = "white" if val > vmax * 0.65 else "black"
                        ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                                fontsize=7, color=txt_col)

            cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
            cbar.set_label("nRMSE", fontsize=8)
            cbar.ax.tick_params(labelsize=7)
            if vmax < np.nanmax(data):
                cbar.ax.set_title("(capped at 2.0)", fontsize=6, loc="left")

            ax.set_title("Portrait Plot — Normalised RMSE by Variable × Region",
                         fontsize=10, fontweight="bold", pad=10)
            fig.tight_layout()

            rel = save_fig(fig, fig_dir, "error_metrics_portrait")
            figures.append(rel)
            blocks.append(
                f"### Portrait Plot (Variable × Region)\n\n"
                f"_Normalised RMSE for each variable-region pair. "
                f"nRMSE > 1.0 (dark red) means prediction error exceeds the typical magnitude "
                f"of the ground truth for that pair. Cells capped at 2.0 for display._\n\n"
                f"![Portrait plot]({rel})"
            )

    # Temporal drift chart — mean nRMSE by year
    if by_vy is not None and not by_vy.empty and "Year" in by_vy.columns:
        variables = by_vy["Variable"].unique()
        fig, ax = plt.subplots(figsize=(8, max(3.5, len(variables) * 0.3)))

        cmap   = plt.get_cmap("tab10")
        colors = {v: cmap(i % 10) for i, v in enumerate(sorted(variables))}

        for var in sorted(variables):
            sub = by_vy[by_vy["Variable"] == var].sort_values("Year")
            if sub["nRMSE"].notna().sum() < 2:
                continue
            ax.plot(
                sub["Year"], sub["nRMSE"],
                marker="o", markersize=3, linewidth=1.5,
                color=colors[var],
                label=var.split("|")[-1],   # short label
            )

        ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6,
                   label="nRMSE = 1.0 (error = GT magnitude)")
        style_ax(ax, title="Temporal Drift — nRMSE by Year",
                 xlabel="Year", ylabel="nRMSE")
        ax.legend(fontsize=7, ncol=2, loc="upper left")
        fig.tight_layout()

        rel = save_fig(fig, fig_dir, "error_metrics_temporal_drift")
        figures.append(rel)
        blocks.append(
            f"### Temporal Drift\n\n"
            f"_nRMSE by year, aggregated over all regions and scenarios. "
            f"Rising values indicate autoregressive error accumulation over the projection horizon._\n\n"
            f"![Temporal drift]({rel})"
        )

    return "\n\n".join(blocks) + "\n", figures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate validation report")
    parser.add_argument("--run_id",  required=True)
    parser.add_argument("--title",   default=None)
    parser.add_argument("--out_dir", default=None, help="Results root dir (default: results/)")
    args = parser.parse_args()

    run_dir = Path(args.out_dir) / args.run_id if args.out_dir else RESULTS_DIR / args.run_id
    if not run_dir.exists():
        print(f"ERROR: No results at {run_dir}  —  run validate.py first.")
        sys.exit(1)

    report_dir = REPORTS_DIR / args.run_id
    fig_dir    = report_dir / "figures"
    report_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    title = args.title or f"Validation Report: {args.run_id}"
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'='*60}")
    print(f"  Generating report for: {args.run_id}")
    print(f"  Reading from: {run_dir}")
    print(f"  Output: {report_dir / 'report.md'}")
    print(f"{'='*60}\n")

    overview    = section_overview(run_dir)
    sc_body, sc_figs = section_sum_check(run_dir, fig_dir)
    pl_body, pl_figs = section_plausibility(run_dir, fig_dir)
    rc_body, rc_figs = section_regional(run_dir, fig_dir)
    bc_body, bc_figs = section_bounds(run_dir, fig_dir)
    hh_body          = section_hard_historical(run_dir)
    sf_body          = section_soft_future(run_dir)
    vc_body          = section_sci_checks(run_dir)
    co_body, co_figs = section_correlations(run_dir, fig_dir)
    em_body, em_figs = section_error_metrics(run_dir, fig_dir)

    all_figs = sc_figs + pl_figs + rc_figs + bc_figs + co_figs + em_figs
    print(f"  Figures generated: {len(all_figs)}")

    report = f"""# {title}

**Run ID:** `{args.run_id}`
**Generated:** {now}
**Results:** `results/{args.run_id}/`

---

## Overview

{overview}

---

## 1. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children
at every timestep. Predictions are **expected to fail** this check — the failure
rate quantifies how much the model violates IAM accounting identities._

{sc_body}

---

## 2. Growth Rate Plausibility

_For each predicted trajectory, checks that period-on-period growth rates
fall within empirically-derived bounds from the ground truth data._

{pl_body}

---

## 3. Regional Consistency

_Checks that predicted World values equal the sum of predicted subregion values
(R5 / R6 / R10 groupings). Only applicable to datasets with regional breakdowns._

{rc_body}

---

## 4. Physical Bounds Check

_Checks predictions against hard physical lower bounds (energy variables ≥ 0)
and empirical per-variable bounds derived from ground truth._

{bc_body}

---

## 5. Hard Historical Constraints

_Checks World-level predictions at 2020 against AR6 vetting reference values
(Nicholls et al. 2022, Table 11). PASS = within IP range, WARN = within outer
tolerance, FAIL = outside outer tolerance. Belongs to the **historical and
domain knowledge comparison** validation family._

{hh_body}

---

## 6. Soft Future Constraints

_Checks World-level predictions at 2030–2040 against domain-knowledge
plausibility bounds from the AR6 vetting process (Table 11). Belongs to the
**historical and domain knowledge comparison** validation family._

{sf_body}

---

## 7. SCI Vetting Checks

_Scenario vetting criteria from Verpoort et al. (2025), the IAMC's published
successor to the AR6 vetting criteria. Checks CO₂ EIP against CEDS-2025 data
at four anchor years (2010–2025), and CCS feasibility at 2030, 2035, and 2040.
Status: PASS = within medium-concern bounds, WARN = within strong-concern bounds,
FAIL = outside strong-concern (exclusion-level) bounds._

{vc_body}

---

## 8. Inter-variable Correlations

_Pearson r² between all variable pairs at years 2030, 2050, and 2100 — comparing
predictions against AR6 ground truth. A well-calibrated emulator should preserve
the correlations present in real IAM data. Methodology follows Li et al. (2025) Fig. 4._

{co_body}

---

## 9. Reconstruction Error Metrics

_Applies to reconstruction emulators only (1:1 correspondence between predicted
and ground truth scenarios). Normalised RMSE (nRMSE = RMSE / mean|ground truth|)
is dimensionless and comparable across variables. The portrait plot shows performance
across all variable-region pairs simultaneously. The temporal drift chart diagnoses
autoregressive error accumulation over the projection horizon._

{em_body}
"""

    out_path = report_dir / "report.md"
    out_path.write_text(report)
    print(f"\n  Report written to: {out_path}")
    if all_figs:
        print(f"  Figures saved:     {fig_dir}")


if __name__ == "__main__":
    main()
