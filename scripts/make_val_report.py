"""
Validation report generator for ML-IAM predictions.

Reads the CSV outputs produced by run_all.py and generates a single Markdown
report with summary tables and figures, including side-by-side comparisons
between model predictions and AR6 ground truth wherever ground truth results
are available.

Must be run after run_all.py (or at least after the individual checks whose
results you want included). Missing check outputs are silently skipped with
a note in the report.

Usage:
    python make_val_report.py --run_id xgb_04
    python make_val_report.py --run_id xgb_04 --title "XGB run 04 — full variable set"

Output:
    reports/<run_id>/report.md
    reports/<run_id>/figures/*.png
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# Determine ml-iam root: read from environment, or default to ../ml-iam relative to this directory
_ml_iam_root = os.environ.get("ML_IAM_ROOT")
if not _ml_iam_root:
    _ml_iam_root = str(Path(__file__).resolve().parent.parent.parent / "ml-iam")
REPO_ROOT  = Path(_ml_iam_root)
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

# Load units lookup from ml-iam configs (best-effort; falls back to empty dict)
try:
    sys.path.insert(0, str(REPO_ROOT))
    from configs.data import UNITS_BY_OUTPUT as _UNITS_BY_OUTPUT
except Exception:
    _UNITS_BY_OUTPUT = {}


def var_units(variable: str) -> str:
    """Return the unit string for a variable, e.g. 'EJ/yr', or '' if unknown."""
    return _UNITS_BY_OUTPUT.get(variable, "")


# Consistent colour palette: predictions = blue, ground truth = orange
C_PRED = "#2c7bb6"
C_GT   = "#d7191c"
C_GRID = "#e5e5e5"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(results_base: Path, check: str, filename: str) -> Optional[pd.DataFrame]:
    path = results_base / check / filename
    if path.exists():
        return pd.read_csv(path)
    return None


def md_table(df: pd.DataFrame, fmt: Optional[dict] = None) -> str:
    """Render a DataFrame as a GitHub-flavoured Markdown table.

    Pipes inside cell values are escaped so that variable names like
    'Primary Energy|Coal' do not break the table structure.
    """
    def _escape(s: str) -> str:
        return s.replace("|", "\\|")

    fmt = fmt or {}
    cols = df.columns.tolist()
    header = "| " + " | ".join(_escape(str(c)) for c in cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for col in cols:
            val = row[col]
            if col in fmt:
                cells.append(_escape(fmt[col].format(val)))
            elif isinstance(val, float):
                cells.append(_escape(f"{val:.4f}"))
            else:
                cells.append(_escape(str(val)))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def save_fig(fig: plt.Figure, fig_dir: Path, name: str) -> str:
    """Save figure and return relative markdown path."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    path = fig_dir / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"figures/{name}.png"


GT_MISSING = "⚠ run `run_groundtruth.py`"


def _gt_missing_note(check_name: str) -> str:
    return (
        f"> **Ground truth results not found** for `{check_name}`. "
        f"Run `python run_groundtruth.py --run_id <run_id>` "
        f"to generate reference results for comparison."
    )


def style_ax(ax, title="", xlabel="", ylabel=""):
    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(labelsize=8)
    ax.yaxis.grid(True, color=C_GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)


# ---------------------------------------------------------------------------
# Example failure helpers
# ---------------------------------------------------------------------------

def _example_sum_failure(te_df: pd.DataFrame, sc_df: pd.DataFrame, label: str) -> str:
    """Pick the scenario closest to the median mean error and show its year-by-year breakdown.

    Shows: Year | <child 1> | <child 2> | … | Sum of children | Parent value | Difference | Error %
    """
    # Identify child-variable columns: anything beyond the fixed metadata columns
    _META_COLS = {
        "Model", "Scenario", "Region", "Scenario_Category", "Year",
        "parent_variable", "total", "sum_components", "zero_total",
        "abs_error", "passed_timestep",
    }
    child_cols = [c for c in te_df.columns if c not in _META_COLS]

    failing = sc_df[~sc_df["passed"]].copy()
    if failing.empty:
        return f"_No failures found in {label}._"

    # Pick the scenario nearest the median mean error — representative, not extreme
    median_err = failing["mean_error"].median()
    idx = (failing["mean_error"] - median_err).abs().idxmin()
    row = failing.loc[idx]

    model    = row.get("Model",    "—")
    scenario = row.get("Scenario", "—")
    region   = row.get("Region",   "—")
    cat      = row.get("Scenario_Category", "—")
    parent   = row.get("parent_variable",   "—")

    # Pull the year-by-year rows for this scenario
    mask = (
        (te_df["Scenario"] == scenario) &
        (te_df["Region"]   == region)   &
        (te_df.get("parent_variable", pd.Series(parent, index=te_df.index)) == parent)
    )
    if "Model" in te_df.columns:
        mask &= (te_df["Model"] == model)

    rows_ts = te_df[mask].sort_values("Year")
    if rows_ts.empty:
        return f"_Could not locate timestep rows for example scenario in {label}._"

    # Build table: Year, then one column per child, then aggregates
    units = var_units(parent)
    units_suffix = f" ({units})" if units else ""
    tbl_dict = {"Year": rows_ts["Year"].values}
    # Use shortened child names (last segment after |) for readability
    for child in child_cols:
        if child in rows_ts.columns:
            short = child.split("|")[-1].strip()
            tbl_dict[short] = rows_ts[child].round(3).values
    tbl_dict[f"Sum of children{units_suffix}"] = rows_ts["sum_components"].round(3).values
    tbl_dict[f"Parent value{units_suffix}"]    = rows_ts["total"].round(3).values
    tbl_dict["Difference"]                     = (rows_ts["total"] - rows_ts["sum_components"]).round(3).values
    tbl_dict["Error (%)"]                      = (rows_ts["abs_error"] * 100).round(2).values

    tbl = pd.DataFrame(tbl_dict)

    header = (
        f"**Scenario:** {model} | {scenario} | {region} | {cat}  \n"
        f"**Parent variable:** {parent}  \n"
        f"**Mean error:** {row['mean_error_pct']:.2f}%  (median failing scenario)"
    )
    return f"#### Example failure — {label}\n\n{header}\n\n" + md_table(
        tbl, fmt={c: "{}" for c in tbl.columns}
    )


def _example_plausibility_failure(viol_df: pd.DataFrame, label: str) -> str:
    """Pick the most severe growth-rate violation and show its context."""
    violations = viol_df[viol_df["violation"]].copy()
    if violations.empty:
        return f"_No violations found in {label}._"

    sev = violations["severity"].replace([np.inf, -np.inf], np.nan).dropna()
    if sev.empty:
        return f"_No finite-severity violations found in {label}._"

    idx  = sev.idxmax()
    row  = violations.loc[idx]

    direction = (
        "above upper bound" if row["growth_rate"] > row["upper_bound"]
        else "below lower bound"
    )

    units = var_units(row["Variable"])
    units_suffix = f" ({units})" if units else ""
    detail = pd.DataFrame([{
        "Variable":                  row["Variable"],
        "Units":                     units,
        "Scenario":                  row.get("Scenario", "—"),
        "Region":                    row.get("Region",   "—"),
        "Category":                  row.get("Scenario_Category", "—"),
        "Year":                      int(row["Year"]),
        f"Previous value{units_suffix}": round(float(row["Value_lag5"]), 3),
        f"Current value{units_suffix}":  round(float(row["Value"]),     3),
        "Growth rate":               round(float(row["growth_rate"]), 4),
        "Lower bound":               round(float(row["lower_bound"]), 4),
        "Upper bound":               round(float(row["upper_bound"]), 4),
        "Direction":                 direction,
        "Severity (bw)":             round(float(row["severity"]),   3),
    }])

    header = f"**Most severe violation** (severity = bound-widths outside the allowed range)"
    return f"#### Example violation — {label}\n\n{header}\n\n" + md_table(
        detail, fmt={c: "{}" for c in detail.columns}
    )


def _example_bounds_failure(viol_df: pd.DataFrame, label: str) -> str:
    """Pick the most extreme bounds violation (largest % deviation from the breached bound)."""
    violations = viol_df[viol_df["violation"]].copy()
    if violations.empty:
        return f"_No violations found in {label}._"

    # Compute deviation as % of the bound that was breached.
    # When the bound is near zero, relative % is meaningless — use absolute difference instead
    # (returned as a negative number so it sorts below genuine relative deviations).
    _BOUND_TOL = 1e-3
    def _pct_dev(row):
        if row["below_lower"] and pd.notna(row["lower_bound"]):
            if abs(row["lower_bound"]) > _BOUND_TOL:
                return abs((row["Value"] - row["lower_bound"]) / row["lower_bound"]) * 100
            return 0.0  # near-zero bound: don't rank by relative %
        if row["above_upper"] and pd.notna(row["upper_bound"]):
            if abs(row["upper_bound"]) > _BOUND_TOL:
                return abs((row["Value"] - row["upper_bound"]) / row["upper_bound"]) * 100
            return 0.0
        return 0.0

    violations["_pct_dev"] = violations.apply(_pct_dev, axis=1)
    idx = violations["_pct_dev"].idxmax()
    row = violations.loc[idx]

    direction = "below lower bound" if row["below_lower"] else "above upper bound"
    bound_val = row["lower_bound"] if row["below_lower"] else row["upper_bound"]

    dev_str = (
        f"{row['_pct_dev']:.2f}"
        if row["_pct_dev"] > 0
        else "N/A (near-zero bound)"
    )
    units = var_units(row["Variable"])
    detail = pd.DataFrame([{
        "Variable":      row["Variable"],
        "Units":         units,
        "Scenario":      row.get("Scenario", "—"),
        "Region":        row.get("Region",   "—"),
        "Category":      row.get("Scenario_Category", "—"),
        "Year":          int(row["Year"]),
        f"Value ({units})":         round(float(row["Value"]),      3),
        f"Bound breached ({units})":round(float(bound_val),         3),
        "Direction":     direction,
        f"Lower bound ({units})":   round(float(row["lower_bound"]), 3) if pd.notna(row["lower_bound"]) else "—",
        f"Upper bound ({units})":   round(float(row["upper_bound"]), 3) if pd.notna(row["upper_bound"]) else "—",
        "Deviation (%)": dev_str,
    }])

    header = f"**Most extreme violation** (largest % deviation from the breached bound)"
    return f"#### Example violation — {label}\n\n{header}\n\n" + md_table(
        detail, fmt={c: "{}" for c in detail.columns}
    )


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def section_overview(
    results_base: Path,
    checks_run: list,
) -> str:
    rows = []

    # Sum check
    pred_sc = load(results_base, "sum_check", "scenario_summary.csv")
    gt_sc   = load(results_base, "sum_check_ground_truth", "scenario_summary.csv")
    if pred_sc is not None:
        pr = 100 * pred_sc["passed"].mean()
        me = pred_sc["mean_error_pct"].mean()
        gt_pr = f'{100 * gt_sc["passed"].mean():.1f}%' if gt_sc is not None else GT_MISSING
        gt_me = f'{gt_sc["mean_error_pct"].mean():.3f}%' if gt_sc is not None else GT_MISSING
        rows.append({
            "Check": "Hierarchy Sum Check",
            "Metric": "Scenario-region pass rate",
            "Predictions": f"{pr:.1f}%",
            "Ground Truth": gt_pr,
        })
        rows.append({
            "Check": "",
            "Metric": "Mean relative error",
            "Predictions": f"{me:.3f}%",
            "Ground Truth": gt_me,
        })

    # Growth rate
    viol    = load(results_base, "plausibility",              "growth_rate_violations.csv")
    gt_viol = load(results_base, "plausibility_ground_truth", "growth_rate_violations.csv")
    if viol is not None:
        vr    = 100 * viol["violation"].mean()
        gt_vr = f'{100 * gt_viol["violation"].mean():.1f}%' if gt_viol is not None else GT_MISSING
        rows.append({
            "Check": "Growth Rate Plausibility",
            "Metric": "Timestep violation rate",
            "Predictions": f"{vr:.1f}%",
            "Ground Truth": gt_vr,
        })

    # Regional consistency
    pred_rc = load(results_base, "regional_consistency",              "scenario_summary.csv")
    gt_rc   = load(results_base, "regional_consistency_ground_truth", "scenario_summary.csv")
    if pred_rc is not None:
        pr    = 100 * pred_rc["passed"].mean()
        gt_pr = f'{100 * gt_rc["passed"].mean():.1f}%' if gt_rc is not None else GT_MISSING
        rows.append({
            "Check": "Regional Consistency",
            "Metric": "Scenario × variable pass rate",
            "Predictions": f"{pr:.1f}%",
            "Ground Truth": gt_pr,
        })

    # Bounds
    pred_bc = load(results_base, "bounds_check",              "scenario_summary.csv")
    gt_bc   = load(results_base, "bounds_check_ground_truth", "scenario_summary.csv")
    if pred_bc is not None:
        vr    = 100 * pred_bc["n_violations"].sum() / (pred_bc["n_timesteps"].sum() or 1)
        gt_vr = (
            f'{100 * gt_bc["n_violations"].sum() / (gt_bc["n_timesteps"].sum() or 1):.2f}%'
            if gt_bc is not None else GT_MISSING
        )
        rows.append({
            "Check": "Physical Bounds Check",
            "Metric": "Timestep violation rate",
            "Predictions": f"{vr:.2f}%",
            "Ground Truth": gt_vr,
        })

    # Inter-variable correlations (mean |Δr²| across years)
    pred_path = results_base / "predictions" / "predictions_long.csv"
    gt_path   = results_base / "predictions" / "groundtruth_long.csv"
    if pred_path.exists() and gt_path.exists():
        try:
            pred_long = pd.read_csv(pred_path)
            gt_long   = pd.read_csv(gt_path)
            diffs = []
            for year in [2030, 2050, 2100]:
                def _cmat(df, y):
                    sub = df[df["Year"] == y]
                    if sub.empty:
                        return None
                    w = sub.pivot_table(
                        index=["Model", "Scenario", "Region"],
                        columns="Variable", values="Value", aggfunc="first"
                    ).dropna(axis=1, how="all")
                    return (w.corr(method="pearson") ** 2) if w.shape[1] >= 2 else None
                pm = _cmat(pred_long, year)
                gm = _cmat(gt_long,   year)
                if pm is not None and gm is not None:
                    common = [v for v in pm.columns if v in gm.columns]
                    diff = (pm.loc[common, common] - gm.loc[common, common]).abs()
                    mask = np.triu(np.ones(diff.shape, dtype=bool), k=1)
                    diffs.append(diff.values[mask].mean())
            if diffs:
                mean_diff = np.mean(diffs)
                rows.append({
                    "Check": "Inter-variable Correlations",
                    "Metric": "Mean |Δr²| vs ground truth",
                    "Predictions": f"{mean_diff:.4f}",
                    "Ground Truth": "0.0000 (reference)",
                })
        except Exception:
            pass

    if not rows:
        return "_No check results found._"

    df = pd.DataFrame(rows)
    return md_table(df, fmt={c: "{}" for c in df.columns})


# ---------------------------------------------------------------------------

def section_sum_check(results_base: Path, fig_dir: Path) -> tuple[str, list]:
    pred_sc = load(results_base, "sum_check", "scenario_summary.csv")
    pred_te = load(results_base, "sum_check", "timestep_errors.csv")
    gt_sc   = load(results_base, "sum_check_ground_truth", "scenario_summary.csv")
    gt_te   = load(results_base, "sum_check_ground_truth", "timestep_errors.csv")

    if pred_sc is None:
        return "_Sum check results not found. Run `sum_check.py` first._", []

    if gt_sc is None:
        blocks = [_gt_missing_note("sum_check")]
    else:
        blocks = []
    has_parent = "parent_variable" in pred_sc.columns
    figures    = []

    # --- Pass rate table ---
    if has_parent:
        tbl_data = (
            pred_sc.groupby("parent_variable")
            .agg(
                n_scenario_regions=("passed", "count"),
                pass_rate_pct=("passed", lambda x: 100 * x.mean()),
                mean_error_pct=("mean_error_pct", "mean"),
                max_error_pct=("max_error_pct", "max"),
            )
            .reset_index()
            .rename(columns={
                "parent_variable":    "Parent Variable",
                "n_scenario_regions": "Scenario-regions",
                "pass_rate_pct":      "Pass rate (%)",
                "mean_error_pct":     "Mean error (%)",
                "max_error_pct":      "Max error (%)",
            })
        )
        blocks.append("### Pass Rates by Parent Variable\n\n" + md_table(tbl_data))
    else:
        pr  = 100 * pred_sc["passed"].mean()
        me  = pred_sc["mean_error_pct"].mean()
        mx  = pred_sc["max_error_pct"].max()
        tbl = pd.DataFrame([{
            "Source": "Predictions",
            "Scenario-regions": len(pred_sc),
            "Pass rate (%)": f"{pr:.1f}",
            "Mean error (%)": f"{me:.4f}",
            "Max error (%)": f"{mx:.4f}",
        }])
        if gt_sc is not None:
            tbl = pd.concat([tbl, pd.DataFrame([{
                "Source": "Ground truth",
                "Scenario-regions": len(gt_sc),
                "Pass rate (%)": f'{100 * gt_sc["passed"].mean():.1f}',
                "Mean error (%)": f'{gt_sc["mean_error_pct"].mean():.4f}',
                "Max error (%)": f'{gt_sc["max_error_pct"].max():.4f}',
            }])], ignore_index=True)
        blocks.append("### Pass Rates\n\n" + md_table(tbl, fmt={c: "{}" for c in tbl.columns}))

    # --- Figure 1: error distribution ---
    if pred_te is not None:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        bins = np.linspace(0, min(pred_te["abs_error"].quantile(0.99) * 1.1, 1.0), 60)
        ax.hist(pred_te["abs_error"].clip(upper=bins[-1]), bins=bins,
                color=C_PRED, alpha=0.7, label="Predictions", density=True)
        if gt_te is not None:
            ax.hist(gt_te["abs_error"].clip(upper=bins[-1]), bins=bins,
                    color=C_GT, alpha=0.6, label="Ground truth", density=True)
        ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
        style_ax(ax, title="Sum Check — Error Distribution",
                 xlabel="Relative error  |parent − sum_children| / |parent|",
                 ylabel="Density")
        ax.legend(fontsize=8)
        fig.tight_layout()
        rel = save_fig(fig, fig_dir, "sum_check_error_dist")
        figures.append(rel)
        blocks.append(f"### Error Distribution\n\n![Sum check error distribution]({rel})")

    # --- Figure 2: mean error by year ---
    if pred_te is not None and "Year" in pred_te.columns:
        group_col = "parent_variable" if "parent_variable" in pred_te.columns else None

        fig, ax = plt.subplots(figsize=(7, 3.5))

        def _plot_by_year(te, label, color, linestyle="-"):
            by_year = te.groupby("Year")["abs_error"].mean() * 100
            ax.plot(by_year.index, by_year.values, marker="o", markersize=3,
                    color=color, linestyle=linestyle, linewidth=1.5, label=label)

        # gt_te may come from an older run that pre-dates the parent_variable column
        gt_group_col = group_col if (gt_te is not None and group_col in gt_te.columns) else None

        if group_col:
            for parent in pred_te[group_col].unique():
                sub = pred_te[pred_te[group_col] == parent]
                short = parent.split("|")[-1]
                _plot_by_year(sub, f"Pred: {short}", C_PRED)
            if gt_te is not None:
                if gt_group_col:
                    for parent in gt_te[gt_group_col].dropna().unique():
                        sub = gt_te[gt_te[gt_group_col] == parent]
                        short = parent.split("|")[-1]
                        _plot_by_year(sub, f"GT: {short}", C_GT, linestyle="--")
                else:
                    _plot_by_year(gt_te, "Ground truth", C_GT, linestyle="--")
        else:
            _plot_by_year(pred_te, "Predictions", C_PRED)
            if gt_te is not None:
                _plot_by_year(gt_te, "Ground truth", C_GT, linestyle="--")

        ax.yaxis.set_major_formatter(mticker.PercentFormatter())
        style_ax(ax, title="Sum Check — Mean Error by Year",
                 xlabel="Year", ylabel="Mean relative error (%)")
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        rel = save_fig(fig, fig_dir, "sum_check_error_by_year")
        figures.append(rel)
        blocks.append(f"### Mean Error by Year\n\n![Sum check error by year]({rel})")

    # --- GT comparison table ---
    pcts = [50, 75, 90, 95, 99]
    if gt_sc is not None:
        tbl = pd.DataFrame({
            "Percentile": [f"p{p}" for p in pcts],
            "Predictions (%)": [f"{np.percentile(pred_sc['mean_error_pct'].dropna(), p):.4f}" for p in pcts],
            "Ground truth (%)": [f"{np.percentile(gt_sc['mean_error_pct'].dropna(), p):.4f}" for p in pcts],
        })
        blocks.append("### Error Percentile Comparison — Predictions vs Ground Truth\n\n"
                      + md_table(tbl, fmt={c: "{}" for c in tbl.columns}))

    # --- Example failures ---
    if pred_te is not None and pred_sc is not None:
        blocks.append(
            "### Example Failure\n\n"
            "_The median failing scenario (by mean error) is shown below "
            "to illustrate a typical hierarchy violation._\n\n"
            + _example_sum_failure(pred_te, pred_sc, "predictions")
        )
    if gt_te is not None and gt_sc is not None:
        blocks.append(_example_sum_failure(gt_te, gt_sc, "ground truth"))

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------

def section_plausibility(results_base: Path, fig_dir: Path) -> tuple[str, list]:
    viol    = load(results_base, "plausibility",              "growth_rate_violations.csv")
    bounds  = load(results_base, "plausibility",              "empirical_bounds.csv")
    gt_viol = load(results_base, "plausibility_ground_truth", "growth_rate_violations.csv")

    if viol is None:
        return "_Growth rate plausibility results not found. Run `check_plausibility.py` first._", []

    figures = []
    blocks  = []

    if gt_viol is None:
        blocks.append(_gt_missing_note("check_plausibility"))

    # --- Summary stats ---
    total  = len(viol)
    n_viol = viol["violation"].sum()
    vr     = 100 * n_viol / total if total else 0.0
    def _median_severity(df: pd.DataFrame) -> float:
        """Median severity of violation rows, with infinities stripped."""
        sev = df.loc[df["violation"], "severity"].replace([np.inf, -np.inf], np.nan).dropna()
        return float(sev.median()) if len(sev) else 0.0

    summary_lines = (
        f"**Total timesteps evaluated:** {total:,}  \n"
        f"**Violations:** {int(n_viol):,} ({vr:.2f}%)  \n"
        f"**Median severity** (violations only): "
        f"{_median_severity(viol):.3f} bound-widths"
    )
    if gt_viol is not None:
        gt_total  = len(gt_viol)
        gt_n_viol = gt_viol["violation"].sum()
        gt_vr     = 100 * gt_n_viol / gt_total if gt_total else 0.0
        summary_lines += (
            f"  \n\n**Ground truth — violation rate:** {gt_vr:.2f}%  \n"
            f"**Ground truth — median severity:** "
            f"{_median_severity(gt_viol):.3f} bound-widths  \n"
            f"_({vr - gt_vr:+.2f}pp difference: predictions vs ground truth)_"
        )
    blocks.append(summary_lines)

    # --- Figure: violation rate by variable, predictions vs GT ---
    def _viol_by_var(df):
        return (
            df.groupby("Variable")
            .agg(total=("violation", "count"), violations=("violation", "sum"))
            .reset_index()
            .assign(**{"rate_%": lambda d: 100 * d["violations"] / d["total"]})
        )

    by_var    = _viol_by_var(viol).sort_values("rate_%", ascending=True)
    gt_by_var = _viol_by_var(gt_viol) if gt_viol is not None else None

    fig, ax = plt.subplots(figsize=(7, max(3, len(by_var) * 0.55)))
    y_pos = np.arange(len(by_var))
    ax.barh(y_pos, by_var["rate_%"], height=0.4 if gt_by_var is not None else 0.6,
            color=C_PRED, alpha=0.8, label="Predictions")
    if gt_by_var is not None:
        gt_rates = gt_by_var.set_index("Variable").reindex(by_var["Variable"])["rate_%"].fillna(0)
        ax.barh(y_pos + 0.4, gt_rates.values, height=0.4,
                color=C_GT, alpha=0.7, label="Ground truth")
    ax.set_yticks(y_pos + (0.2 if gt_by_var is not None else 0))
    ax.set_yticklabels(by_var["Variable"], fontsize=8)
    ax.bar_label(ax.containers[0], fmt="%.1f%%", fontsize=6, padding=2)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    if gt_by_var is not None:
        ax.legend(fontsize=8)
    style_ax(ax, title="Growth Rate Violations by Variable",
             xlabel="Violation rate (%)", ylabel="")
    ax.set_xlim(0, by_var["rate_%"].max() * 1.2)
    fig.tight_layout()
    rel = save_fig(fig, fig_dir, "plausibility_violations_by_variable")
    figures.append(rel)
    blocks.append(f"### Violation Rate by Variable\n\n![Plausibility violations by variable]({rel})")

    # --- Bounds table ---
    if bounds is not None:
        tbl = bounds.copy()
        tbl.columns = ["Variable", "Lower bound", "Upper bound"]
        blocks.append("### Empirical Bounds Used (AR6 test-set percentiles)\n\n" + md_table(tbl))

    # --- Figure: severity distribution (violations only) ---
    sev = viol.loc[viol["violation"], "severity"].dropna()
    if len(sev) > 0:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.hist(sev.clip(upper=sev.quantile(0.99)), bins=50, color=C_PRED, alpha=0.8)
        style_ax(ax, title="Growth Rate — Violation Severity Distribution",
                 xlabel="Severity (bound-widths outside range)", ylabel="Count")
        fig.tight_layout()
        rel = save_fig(fig, fig_dir, "plausibility_severity_dist")
        figures.append(rel)
        blocks.append(f"### Severity Distribution\n\n"
                      f"_Severity = how many bound-widths the growth rate exceeds the limit._\n\n"
                      f"![Plausibility severity]({rel})")

    # --- Violation rate by scenario category ---
    if "Scenario_Category" in viol.columns:
        cat = (
            viol.groupby("Scenario_Category")
            .agg(total=("violation", "count"), violations=("violation", "sum"))
            .reset_index()
        )
        cat["rate_%"] = (100 * cat["violations"] / cat["total"]).round(2)
        cat = cat.sort_values("rate_%", ascending=False)
        cat.columns = ["Category", "Timesteps", "Violations", "Violation rate (%)"]
        blocks.append("### Violation Rate by Scenario Category\n\n" + md_table(cat))

    # --- Example failures ---
    blocks.append(
        "### Example Violation\n\n"
        "_The most severe violation (highest severity in bound-widths) is shown below._\n\n"
        + _example_plausibility_failure(viol, "predictions")
    )
    if gt_viol is not None:
        blocks.append(_example_plausibility_failure(gt_viol, "ground truth"))

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------

def section_regional(results_base: Path, fig_dir: Path) -> tuple[str, list]:
    pred_sc = load(results_base, "regional_consistency", "scenario_summary.csv")
    gt_sc   = load(results_base, "regional_consistency_ground_truth", "scenario_summary.csv")

    if pred_sc is None:
        return ("_Regional consistency results not found. Run `regional_consistency.py` first, "
                "or skip if your run has no multi-region scenarios._"), []

    figures = []
    blocks  = []

    if gt_sc is None:
        blocks.append(_gt_missing_note("regional_consistency"))

    # --- By grouping table ---
    def _grouping_table(sc):
        return (
            sc.groupby("grouping")
            .agg(
                total=("passed", "count"),
                passed=("passed", "sum"),
                mean_error_pct=("mean_error_pct", "mean"),
                max_error_pct=("max_error_pct", "max"),
            )
            .reset_index()
            .assign(**{"pass_rate_%": lambda d: 100 * d["passed"] / d["total"]})
        )

    pred_grp = _grouping_table(pred_sc)
    tbl_data = pred_grp[["grouping", "total", "passed", "pass_rate_%",
                          "mean_error_pct", "max_error_pct"]].copy()
    tbl_data.columns = ["Grouping", "Total", "Passed", "Pass rate (%)",
                         "Mean error (%)", "Max error (%)"]
    blocks.append("### Pass Rates by Regional Grouping — Predictions\n\n"
                  + md_table(tbl_data))

    if gt_sc is not None:
        gt_grp = _grouping_table(gt_sc)
        tbl_gt = gt_grp[["grouping", "total", "passed", "pass_rate_%",
                          "mean_error_pct", "max_error_pct"]].copy()
        tbl_gt.columns = tbl_data.columns
        blocks.append("### Pass Rates by Regional Grouping — Ground Truth\n\n"
                      + md_table(tbl_gt))

    # --- Figure: pass rate bar chart by grouping & variable ---
    if "Variable" in pred_sc.columns:
        var_grp = (
            pred_sc.groupby(["grouping", "Variable"])
            .agg(total=("passed", "count"), passed=("passed", "sum"))
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
            if gt_sc is not None and "Variable" in gt_sc.columns:
                gt_sub = (
                    gt_sc[gt_sc["grouping"] == g]
                    .groupby("Variable")
                    .agg(total=("passed", "count"), passed=("passed", "sum"))
                    .reset_index()
                )
                gt_sub["pass_rate_%"] = 100 * gt_sub["passed"] / gt_sub["total"]
                gt_sub = gt_sub.set_index("Variable").reindex(sub["Variable"]).reset_index()
                ax.barh(
                    np.arange(len(sub)) + 0.3,
                    gt_sub["pass_rate_%"].fillna(0),
                    height=0.3, color=C_GT, alpha=0.7, label="Ground truth",
                )
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

def section_bounds(results_base: Path, fig_dir: Path) -> tuple[str, list]:
    pred_sc  = load(results_base, "bounds_check", "scenario_summary.csv")
    pred_viol = load(results_base, "bounds_check", "violations.csv")
    bounds   = load(results_base, "bounds_check", "bounds_used.csv")
    gt_sc    = load(results_base, "bounds_check_ground_truth", "scenario_summary.csv")

    if pred_sc is None:
        return "_Bounds check results not found. Run `bounds_check.py` first._", []

    figures = []
    blocks  = []

    if gt_sc is None:
        blocks.append(_gt_missing_note("bounds_check"))

    # --- Overview stats ---
    total = pred_sc["n_timesteps"].sum()
    n_viol = pred_sc["n_violations"].sum()
    vr = 100 * n_viol / total if total else 0.0
    n_clean = pred_sc["passed"].sum()
    blocks.append(
        f"**Timesteps checked:** {total:,}  \n"
        f"**Violations:** {int(n_viol):,} ({vr:.3f}%)  \n"
        f"**Fully clean scenario-regions:** {int(n_clean):,} / {len(pred_sc):,}"
    )

    # --- Bounds table ---
    if bounds is not None:
        tbl = bounds[["Variable", "lower_bound", "upper_bound"]].copy()
        tbl["Units"]       = tbl["Variable"].apply(var_units)
        tbl["lower_bound"] = tbl["lower_bound"].apply(lambda x: f"{x:.4g}" if pd.notna(x) else "—")
        tbl["upper_bound"] = tbl["upper_bound"].apply(lambda x: f"{x:.4g}" if pd.notna(x) else "—")
        tbl.columns = ["Variable", "Lower bound", "Upper bound", "Units"]
        tbl = tbl[["Variable", "Units", "Lower bound", "Upper bound"]]
        blocks.append("### Bounds Applied\n\n" + md_table(tbl, fmt={c: "{}" for c in tbl.columns}))

    # --- Figure: violation counts by variable (predictions) ---
    by_var = (
        pred_sc.groupby("Variable")
        .agg(
            n_violations=("n_violations", "sum"),
            n_timesteps=("n_timesteps", "sum"),
            n_below=("n_below_lower", "sum"),
            n_above=("n_above_upper", "sum"),
        )
        .reset_index()
    )
    by_var["rate_%"] = 100 * by_var["n_violations"] / by_var["n_timesteps"]
    by_var = by_var.sort_values("n_violations", ascending=True)

    if by_var["n_violations"].sum() > 0:
        fig, ax = plt.subplots(figsize=(7, max(3, len(by_var) * 0.45)))
        ax.barh(by_var["Variable"], by_var["n_below"],
                color=C_PRED, alpha=0.8, label="Below lower bound")
        ax.barh(by_var["Variable"], by_var["n_above"],
                left=by_var["n_below"],
                color=C_GT, alpha=0.7, label="Above upper bound")
        style_ax(ax, title="Bounds Violations by Variable",
                 xlabel="Number of violating timesteps", ylabel="")
        ax.legend(fontsize=8)
        fig.tight_layout()
        rel = save_fig(fig, fig_dir, "bounds_violations_by_variable")
        figures.append(rel)
        blocks.append(f"### Violations by Variable\n\n![Bounds violations by variable]({rel})")
    else:
        blocks.append("### Violations by Variable\n\n✓ No violations detected across any variable.")

    # --- GT comparison ---
    if gt_sc is not None:
        gt_total = gt_sc["n_timesteps"].sum()
        gt_viol  = gt_sc["n_violations"].sum()
        gt_vr    = 100 * gt_viol / gt_total if gt_total else 0.0
        diff_pp  = vr - gt_vr
        sign     = "+" if diff_pp >= 0 else ""
        tbl = pd.DataFrame([
            {"Source": "Predictions", "Timesteps": f"{total:,}",
             "Violations": f"{int(n_viol):,}", "Violation rate": f"{vr:.3f}%"},
            {"Source": "Ground truth", "Timesteps": f"{gt_total:,}",
             "Violations": f"{int(gt_viol):,}", "Violation rate": f"{gt_vr:.3f}%"},
        ])
        blocks.append(
            f"### Predictions vs Ground Truth\n\n"
            + md_table(tbl, fmt={c: "{}" for c in tbl.columns})
            + f"\n\n_Predictions show {sign}{diff_pp:.3f} pp more violations than ground truth._"
        )

        # Paired bar: violation rate by variable, predictions vs GT
        if "Variable" in gt_sc.columns and by_var["n_violations"].sum() > 0:
            gt_by_var = (
                gt_sc.groupby("Variable")
                .agg(n_violations=("n_violations", "sum"), n_timesteps=("n_timesteps", "sum"))
                .reset_index()
            )
            gt_by_var["rate_%"] = 100 * gt_by_var["n_violations"] / gt_by_var["n_timesteps"]
            merged_var = by_var[["Variable", "rate_%"]].merge(
                gt_by_var[["Variable", "rate_%"]].rename(columns={"rate_%": "gt_rate_%"}),
                on="Variable", how="left",
            ).sort_values("rate_%", ascending=True)

            fig, ax = plt.subplots(figsize=(7, max(3, len(merged_var) * 0.45)))
            y = np.arange(len(merged_var))
            ax.barh(y, merged_var["rate_%"], height=0.4, color=C_PRED, alpha=0.8, label="Predictions")
            ax.barh(y + 0.4, merged_var["gt_rate_%"].fillna(0),
                    height=0.4, color=C_GT, alpha=0.7, label="Ground truth")
            ax.set_yticks(y + 0.2)
            ax.set_yticklabels(merged_var["Variable"], fontsize=8)
            ax.xaxis.set_major_formatter(mticker.PercentFormatter())
            style_ax(ax, title="Bounds Violation Rate by Variable — Predictions vs Ground Truth",
                     xlabel="Violation rate (%)", ylabel="")
            ax.legend(fontsize=8)
            fig.tight_layout()
            rel = save_fig(fig, fig_dir, "bounds_violation_rate_pred_vs_gt")
            figures.append(rel)
            blocks.append(
                f"### Violation Rate by Variable — Predictions vs Ground Truth\n\n"
                f"![Bounds violation rate pred vs GT]({rel})"
            )

    # --- Example failures ---
    if pred_viol is not None:
        blocks.append(
            "### Example Violation\n\n"
            "_The most extreme violation (largest % deviation from the breached bound) "
            "is shown below._\n\n"
            + _example_bounds_failure(pred_viol, "predictions")
        )
    gt_viol_df = load(results_base, "bounds_check_ground_truth", "violations.csv")
    if gt_viol_df is not None:
        blocks.append(_example_bounds_failure(gt_viol_df, "ground truth"))

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------
# Hard historical constraints
# ---------------------------------------------------------------------------

def section_hard_historical(results_base: Path) -> str:
    """
    Summarise results from hard_historical_constraints.py.
    Reads all_results.csv and skipped.csv if present.
    """
    check_dir = results_base / "hard_historical_constraints"
    gt_dir    = results_base / "hard_historical_constraints_ground_truth"

    if not check_dir.exists():
        return "_Hard historical constraints results not found. Run `hard_historical_constraints.py` first._\n"

    blocks = []

    # Load results
    results_path = check_dir / "all_results.csv"
    if not results_path.exists():
        return "_Hard historical constraints: all_results.csv not found._\n"

    df = pd.read_csv(results_path)

    # Summary table per constraint
    summary = (
        df.groupby("constraint_name")["status"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ["PASS", "WARN", "FAIL"]:
        if col not in summary.columns:
            summary[col] = 0
    summary["total"] = summary[["PASS", "WARN", "FAIL"]].sum(axis=1)
    summary["pass_%"] = (100 * summary["PASS"] / summary["total"]).round(1)
    summary["warn_%"] = (100 * summary["WARN"] / summary["total"]).round(1)
    summary["fail_%"] = (100 * summary["FAIL"] / summary["total"]).round(1)

    # Ground truth comparison if available
    gt_df = None
    if gt_dir.exists() and (gt_dir / "all_results.csv").exists():
        gt_df = pd.read_csv(gt_dir / "all_results.csv")
        gt_summary = (
            gt_df.groupby("constraint_name")["status"]
            .value_counts()
            .unstack(fill_value=0)
            .reset_index()
        )
        for col in ["PASS", "WARN", "FAIL"]:
            if col not in gt_summary.columns:
                gt_summary[col] = 0
        gt_summary["total"] = gt_summary[["PASS", "WARN", "FAIL"]].sum(axis=1)
        gt_summary["gt_pass_%"] = (100 * gt_summary["PASS"] / gt_summary["total"]).round(1)
        gt_summary["gt_fail_%"] = (100 * gt_summary["FAIL"] / gt_summary["total"]).round(1)
        summary = summary.merge(
            gt_summary[["constraint_name", "gt_pass_%", "gt_fail_%"]],
            on="constraint_name", how="left"
        )

    # Render table
    tbl_cols = ["constraint_name", "total", "pass_%", "warn_%", "fail_%"]
    if gt_df is not None:
        tbl_cols += ["gt_pass_%", "gt_fail_%"]

    display = summary[tbl_cols].rename(columns={
        "constraint_name": "Sub-check",
        "total": "N",
        "pass_%": "Pass (%)",
        "warn_%": "Warn (%)",
        "fail_%": "Fail (%)",
        "gt_pass_%": "GT Pass (%)",
        "gt_fail_%": "GT Fail (%)",
    })
    blocks.append(md_table(display, fmt={"N": "{}"}))

    # Skipped checks
    skipped_path = check_dir / "skipped.csv"
    if skipped_path.exists():
        sk = pd.read_csv(skipped_path)
        if not sk.empty:
            skipped_list = ", ".join(sk["constraint_name"].tolist())
            blocks.append(
                f"\n_Skipped sub-checks (required variables absent from this run): "
                f"{skipped_list}_"
            )

    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Soft future constraints
# ---------------------------------------------------------------------------

def section_soft_future(results_base: Path) -> str:
    """
    Summarise results from soft_future_constraints.py.
    Reads all_results.csv and skipped.csv if present.
    """
    check_dir = results_base / "soft_future_constraints"
    gt_dir    = results_base / "soft_future_constraints_ground_truth"

    if not check_dir.exists():
        return "_Soft future constraints results not found. Run `soft_future_constraints.py` first._\n"

    results_path = check_dir / "all_results.csv"
    if not results_path.exists():
        return "_Soft future constraints: all_results.csv not found._\n"

    df = pd.read_csv(results_path)
    blocks = []

    summary = (
        df.groupby("constraint_name")["status"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ["PASS", "FAIL"]:
        if col not in summary.columns:
            summary[col] = 0
    summary["total"]  = summary[["PASS", "FAIL"]].sum(axis=1)
    summary["pass_%"] = (100 * summary["PASS"] / summary["total"]).round(1)
    summary["fail_%"] = (100 * summary["FAIL"] / summary["total"]).round(1)

    # Ground truth comparison
    gt_df = None
    if gt_dir.exists() and (gt_dir / "all_results.csv").exists():
        gt_df = pd.read_csv(gt_dir / "all_results.csv")
        gt_summary = (
            gt_df.groupby("constraint_name")["status"]
            .value_counts()
            .unstack(fill_value=0)
            .reset_index()
        )
        for col in ["PASS", "FAIL"]:
            if col not in gt_summary.columns:
                gt_summary[col] = 0
        gt_summary["total"]     = gt_summary[["PASS", "FAIL"]].sum(axis=1)
        gt_summary["gt_pass_%"] = (100 * gt_summary["PASS"] / gt_summary["total"]).round(1)
        gt_summary["gt_fail_%"] = (100 * gt_summary["FAIL"] / gt_summary["total"]).round(1)
        summary = summary.merge(
            gt_summary[["constraint_name", "gt_pass_%", "gt_fail_%"]],
            on="constraint_name", how="left"
        )

    tbl_cols = ["constraint_name", "total", "pass_%", "fail_%"]
    if gt_df is not None:
        tbl_cols += ["gt_pass_%", "gt_fail_%"]

    display = summary[tbl_cols].rename(columns={
        "constraint_name": "Sub-check",
        "total": "N",
        "pass_%": "Pass (%)",
        "fail_%": "Fail (%)",
        "gt_pass_%": "GT Pass (%)",
        "gt_fail_%": "GT Fail (%)",
    })
    blocks.append(md_table(display, fmt={"N": "{}"}))

    skipped_path = check_dir / "skipped.csv"
    if skipped_path.exists():
        sk = pd.read_csv(skipped_path)
        if not sk.empty:
            skipped_list = ", ".join(sk["constraint_name"].tolist())
            blocks.append(
                f"\n_Skipped sub-checks (required variables absent from this run): "
                f"{skipped_list}_"
            )

    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Inter-variable correlations
# ---------------------------------------------------------------------------

def section_correlations(results_base: Path, fig_dir: Path) -> tuple[str, list]:
    """
    Pearson r² correlation matrices between all predicted variables at key
    years (2030, 2050, 2100), compared side-by-side against AR6 ground truth.

    Mirrors Li et al. (2025) Figure 4 panels c–h.  Applicable to any emulator
    type: for supervised models (Shin) it shows whether the model preserves
    inter-variable relationships in the test set; for generative models (Li)
    it shows whether the generated distribution preserves them.

    Requires export_predictions.py to have been run first (produces
    predictions/predictions_long.csv and predictions/groundtruth_long.csv).
    """
    pred_path = results_base / "predictions" / "predictions_long.csv"
    gt_path   = results_base / "predictions" / "groundtruth_long.csv"

    if not pred_path.exists():
        return (
            "_Inter-variable correlation results not found. "
            "Run `export_predictions.py` (or `run_all.py`) first._"
        ), []

    pred_long = pd.read_csv(pred_path)
    gt_long   = pd.read_csv(gt_path) if gt_path.exists() else None

    all_vars = sorted(pred_long["Variable"].unique())
    short_labels = {v: v for v in all_vars}  # use full variable names

    YEARS = [2030, 2050, 2100]
    available_years = [y for y in YEARS if y in pred_long["Year"].values]
    if not available_years:
        return "_No data found at years 2030, 2050, or 2100._", []

    figures = []
    blocks  = []

    blocks.append(
        "Inter-variable Pearson r² matrices at years 2030, 2050, and 2100, "
        "comparing model predictions against AR6 ground truth. "
        "Values close to the ground truth indicate the emulator preserves "
        "real-world variable relationships. "
        "Methodology follows Li et al. (2025) Fig. 4."
    )

    def _corr_matrix(long_df: pd.DataFrame, year: int) -> pd.DataFrame | None:
        sub = long_df[long_df["Year"] == year]
        if sub.empty:
            return None
        wide = sub.pivot_table(
            index=["Model", "Scenario", "Region"],
            columns="Variable",
            values="Value",
            aggfunc="first",
        )
        # Keep only variables present for this year
        wide = wide.dropna(axis=1, how="all")
        if wide.shape[1] < 2:
            return None
        return wide.corr(method="pearson") ** 2  # r²

    def _plot_corr(ax, mat: pd.DataFrame, title: str, vmin=0, vmax=1):
        labels = [short_labels.get(v, v) for v in mat.columns]
        im = ax.imshow(mat.values, vmin=vmin, vmax=vmax,
                       cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(labels)))
        ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_title(title, fontsize=10, fontweight="bold", pad=6)
        # Annotate cells
        for i in range(len(labels)):
            for j in range(len(labels)):
                val = mat.values[i, j]
                if not np.isnan(val):
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                            fontsize=5.5,
                            color="black" if 0.2 < val < 0.8 else "white")
        return im

    for year in available_years:
        pred_mat = _corr_matrix(pred_long, year)
        gt_mat   = _corr_matrix(gt_long,   year) if gt_long is not None else None

        if pred_mat is None:
            continue

        n_panels = 3 if gt_mat is not None else 1
        fig, axes = plt.subplots(1, n_panels,
                                 figsize=(8 * n_panels, max(6, len(pred_mat) * 0.7)))
        if n_panels == 1:
            axes = [axes]

        im = _plot_corr(axes[0], pred_mat, f"Predictions — {year}")

        if gt_mat is not None:
            # Align columns/rows to predictions matrix
            common = [v for v in pred_mat.columns if v in gt_mat.columns]
            gt_aligned = gt_mat.loc[common, common]
            pred_aligned = pred_mat.loc[common, common]

            _plot_corr(axes[1], gt_aligned, f"AR6 Ground Truth — {year}")

            # Difference: predictions r² minus ground truth r² (signed)
            diff = pred_aligned.values - gt_aligned.values
            diff_df = pd.DataFrame(diff, index=common, columns=common)
            labels_common = [short_labels.get(v, v) for v in common]

            ax = axes[2]
            im2 = ax.imshow(diff_df.values, vmin=-1, vmax=1,
                            cmap="RdBu_r", aspect="auto")
            ax.set_xticks(range(len(labels_common)))
            ax.set_yticks(range(len(labels_common)))
            ax.set_xticklabels(labels_common, rotation=45, ha="right", fontsize=7)
            ax.set_yticklabels(labels_common, fontsize=7)
            ax.set_title(f"Difference (Pred − GT) — {year}",
                         fontsize=10, fontweight="bold", pad=6)
            for i in range(len(labels_common)):
                for j in range(len(labels_common)):
                    val = diff_df.values[i, j]
                    if not np.isnan(val):
                        ax.text(j, i, f"{val:+.2f}", ha="center", va="center",
                                fontsize=5.5, color="black")
            fig.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)

        fig.colorbar(im, ax=axes[0] if n_panels == 1 else axes[1],
                     fraction=0.046, pad=0.04)
        fig.suptitle(f"Inter-variable Pearson r² — {year}", fontsize=12,
                     fontweight="bold", y=1.02)
        fig.tight_layout()

        fname = f"correlations_{year}"
        rel = save_fig(fig, fig_dir, fname)
        figures.append(rel)
        blocks.append(
            f"### {year}\n\n"
            + (
                "_Left: predictions. Centre: AR6 ground truth. "
                "Right: difference (blue = predictions underestimate correlation, "
                "red = overestimate)._\n\n"
                if gt_mat is not None
                else "_Predictions correlation matrix (no ground truth available)._\n\n"
            )
            + f"![Inter-variable correlations {year}]({rel})"
        )

    # --- Summary table: mean absolute difference per variable pair ---
    if gt_long is not None and available_years:
        rows = []
        for year in available_years:
            pred_mat = _corr_matrix(pred_long, year)
            gt_mat   = _corr_matrix(gt_long,   year)
            if pred_mat is None or gt_mat is None:
                continue
            common = [v for v in pred_mat.columns if v in gt_mat.columns]
            diff = (pred_mat.loc[common, common] - gt_mat.loc[common, common]).abs()
            # Upper triangle only (exclude diagonal)
            mask = np.triu(np.ones(diff.shape, dtype=bool), k=1)
            mean_abs_diff = diff.values[mask].mean()
            rows.append({"Year": year,
                         "Mean |Δr²| (off-diagonal)": f"{mean_abs_diff:.4f}"})
        if rows:
            tbl = pd.DataFrame(rows)
            blocks.append(
                "### Summary: Mean Absolute Difference in r²\n\n"
                "_Average absolute difference between predictions and ground truth "
                "correlation matrices (off-diagonal pairs only). "
                "Lower is better — 0 would mean perfect preservation of "
                "inter-variable relationships._\n\n"
                + md_table(tbl, fmt={c: "{}" for c in tbl.columns})
            )

    return "\n\n".join(blocks), figures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a validation report from run_all.py outputs"
    )
    parser.add_argument("--run_id", required=True, help="Run ID, e.g. xgb_04")
    parser.add_argument(
        "--title", type=str, default=None,
        help="Optional report title (default: 'Validation Report: <run_id>')"
    )
    args = parser.parse_args()

    results_base = REPO_ROOT / "results" / "xgb" / args.run_id
    if not results_base.exists():
        print(f"ERROR: No results found at {results_base}")
        print("Run run_all.py first.")
        sys.exit(1)

    report_dir = REPORTS_DIR / args.run_id
    fig_dir    = report_dir / "figures"
    report_dir.mkdir(parents=True, exist_ok=True)

    title = args.title or f"Validation Report: {args.run_id}"
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'='*60}")
    print(f"  Generating validation report for run: {args.run_id}")
    print(f"  Output: {report_dir / 'report.md'}")
    print(f"{'='*60}\n")

    # Detect which checks have results
    checks_run = []
    for check in [
        "sum_check", "plausibility", "regional_consistency", "bounds_check",
        "hard_historical_constraints", "soft_future_constraints",
    ]:
        if (results_base / check).exists():
            checks_run.append(check)
            print(f"  Found: {check}/")
        else:
            print(f"  Missing (will be skipped): {check}/")

    # --- Build sections ---
    print("\n  Building sections...")

    overview = section_overview(results_base, checks_run)

    print("  Generating sum check section...")
    sc_body, sc_figs = section_sum_check(results_base, fig_dir)

    print("  Generating plausibility section...")
    pl_body, pl_figs = section_plausibility(results_base, fig_dir)

    print("  Generating regional consistency section...")
    rc_body, rc_figs = section_regional(results_base, fig_dir)

    print("  Generating bounds check section...")
    bc_body, bc_figs = section_bounds(results_base, fig_dir)

    print("  Generating hard historical constraints section...")
    hh_body = section_hard_historical(results_base)

    print("  Generating soft future constraints section...")
    sf_body = section_soft_future(results_base)

    print("  Generating inter-variable correlations section...")
    co_body, co_figs = section_correlations(results_base, fig_dir)

    all_figs = sc_figs + pl_figs + rc_figs + bc_figs + co_figs
    print(f"  Figures generated: {len(all_figs)}")

    # --- Assemble report ---
    report = f"""# {title}

**Run ID:** `{args.run_id}`
**Generated:** {now}
**Results path:** `results/xgb/{args.run_id}/`

---

## Overview

{overview}

---

## 1. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children
at every timestep. Predictions are **expected to fail** this check — the failure
rate quantifies how much the model violates the sum constraint. Compare to the
ground truth pass rate to understand baseline data consistency._

{sc_body}

---

## 2. Growth Rate Plausibility

_For each predicted trajectory, checks that the 5-year period-on-period growth rate
falls within the 1st–99th percentile range observed in the AR6 test-set ground truth.
Empirical bounds are derived per variable._

{pl_body}

---

## 3. Regional Consistency

_Checks that predicted World values equal the sum of predicted subregion values
(R5 / R6 / R10 groupings). Only checked for scenarios where a complete grouping
is present. Predictions are **expected to fail** if the model predicts regions
independently of World._

{rc_body}

---

## 4. Physical Bounds Check

_Checks predicted values against hard physical lower bounds (energy variables ≥ 0)
and empirical per-variable bounds derived from the AR6 test-set ground truth._

{bc_body}

---

## 5. Hard Historical Constraints

_Checks predicted values at the 2020 reference year against the historical anchor
values used in the AR6 scenario vetting process (Nicholls et al. 2022, Table 11).
Each sub-check has an outer tolerance (PASS/FAIL) and an inner IP-range tolerance
(WARN if within outer but outside inner). Sub-checks requiring absent variables are
skipped and listed below. Belongs to the **historical and domain knowledge comparison**
validation family._

{hh_body}

---

## 6. Soft Future Constraints

_Checks predicted values at specific future years against domain-knowledge plausibility
bounds from the AR6 vetting process (Nicholls et al. 2022, Table 11). These were
flagged in AR6 as potentially problematic but not used as hard exclusion criteria.
Warranted here via the constraint-violation argument: the IAMs were themselves vetted
against these criteria. Belongs to the **historical and domain knowledge comparison**
validation family._

{sf_body}

---

## 7. Inter-variable Correlations

_Pearson r² between all variable pairs at years 2030, 2050, and 2100 — comparing
predictions against AR6 ground truth. A well-calibrated emulator should preserve
the correlations present in real IAM data (e.g. coal consumption and GHG emissions
should remain positively correlated). Methodology follows Li et al. (2025) Fig. 4._

{co_body}
"""

    out_path = report_dir / "report.md"
    out_path.write_text(report)

    print(f"\n{'='*60}")
    print(f"  Report written to: {out_path}")
    if all_figs:
        print(f"  Figures saved to:  {fig_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
