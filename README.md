# em-iam-val: A Validation Framework for IAM Emulation Studies

A modular, study-agnostic validation framework for assessing the physical plausibility and internal consistency of emulated Integrated Assessment Model (IAM) scenarios.

This framework is developed as part of a research project establishing validation standards for the emerging field of IAM emulation — the use of machine learning to reproduce or generate IAM scenario outputs. It is designed to be applicable across different emulation approaches and has been applied to two published emulation studies:

- **[ML-IAM v1.0](https://egusphere.copernicus.org/preprints/2026/egusphere-2025-5305/)** (Shin et al., 2026) — XGBoost-based supervised regression emulator
- **[Deep-IAM](https://zenodo.org/)** (Li et al.) — generative deep learning emulator (VAE / CGAN / RCGAN)

---

## Repository structure

```
em-iam-val/
├── scripts/        # Validation check scripts and runner
├── reports/        # Generated markdown reports and figures (per run)
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## Prerequisites

The framework currently loads model artifacts (predictions, scalers, processed data) from an adjacent ml-iam installation. By default it expects ml-iam to live at `../ml-iam` relative to this repository. If your ml-iam installation is elsewhere, set:

```bash
export ML_IAM_ROOT=/path/to/ml-iam
```

You will also need to have completed at least one training run in ml-iam so that cached predictions and data exist under `ml-iam/results/`.

---

## Installation

Everything runs inside a single Poetry environment. No separate conda or virtual environment is needed.

```bash
cd em-iam-val
poetry install
poetry shell
```

---

## Usage

### Shin et al. (ML-IAM / XGBoost)

Run all checks for a completed ml-iam run and generate a report:

```bash
python scripts/run_all.py --run_id xgb_04 --report
```

Run checks and generate a report in separate steps:

```bash
python scripts/run_all.py --run_id xgb_04
python scripts/make_val_report.py --run_id xgb_04
```

Run an individual check:

```bash
python scripts/check_plausibility.py --run_id xgb_04
python scripts/sum_check.py --run_id xgb_04
python scripts/regional_consistency.py --run_id xgb_04
python scripts/bounds_check.py --run_id xgb_04
```

Run all checks then generate the ground truth reference comparison:

```bash
python scripts/run_all.py --run_id xgb_04
python scripts/run_groundtruth.py --run_id xgb_04
python scripts/make_val_report.py --run_id xgb_04
```

### Li et al. (Deep-IAM / generative)

Run the full validation suite (generated outputs + ground truth reference + report):

```bash
python scripts/run_li_all.py --run_id li_vae_01 --model vae --report
python scripts/run_li_all.py --run_id li_cgan_01 --model cgan --report
python scripts/run_li_all.py --run_id li_rcgan_01 --model rcgan --report
```

Run only the ground truth reference pass:

```bash
python scripts/run_li_groundtruth.py --run_id li_gt_01 --report
```

If the Li et al. data is not in the default location (`../Li-emulation/Policy-Generative Model`), pass the path explicitly:

```bash
python scripts/run_li_all.py --run_id li_vae_01 --model vae --li_path /path/to/Li-emulation/Policy-Generative\ Model
```

**Note on applicable checks:** The Li et al. dataset is World-level only, so `regional_consistency` does not apply and is not run. Growth-rate checks use 10-year timesteps rather than the 5-year timesteps used for Shin. These differences are flagged in the report.

Reports are written to `reports/<run_id>/report.md`. Check result CSVs are written to `ml-iam/results/xgb/<run_id>/` alongside the model artifacts they describe.

---

## Checks

### `check_plausibility.py` — Growth Rate Plausibility Check

**What it does:**
For each generated (predicted) trajectory (scenario × region × variable), computes the 5-year period-on-period growth rate:

```
g_y = (x_y - x_{y-5}) / x_{y-5}
```

The AR6 test-set ground truth is used solely to derive empirical reference bounds (by default the 1st/99th percentiles of observed growth rates per variable). These bounds represent what physically plausible growth looks like in real IAM data. The check then flags any timestep in the generated predictions where the growth rate falls outside those bounds.

**Required model outputs:** Any combination of output variables. Only meaningful for variables that change over time.

**Required data:** AR6 test-set ground truth loaded automatically from the run's cached `processed_data.parquet` — used only to derive reference bounds.

**Key options:**

| Flag | Default | Description |
|---|---|---|
| `--percentile` | `1.0` | Lower tail percentile (upper = 100 − percentile). Use `5` for stricter bounds. |
| `--by_category` | off | Also break down violations by scenario category (C1–C8) |

**Outputs** (`ml-iam/results/xgb/<run_id>/plausibility/`):
- `report.txt`
- `growth_rate_violations.csv`
- `empirical_bounds.csv`

---

### `sum_check.py` — Hierarchy Sum Check

**What it does:**
Automatically discovers all parent-child variable relationships in the run's target set using the `|` separator convention (e.g. `Secondary Energy|Electricity` is a parent of `Secondary Energy|Electricity|Solar`). For each parent, verifies that the predicted parent value equals the sum of its direct children at every timestep:

```
error = |parent - sum_of_children| / |parent|
```

A scenario passes if `error < 1.2%` at every timestep for every parent variable. We expect predictions to fail this check — that failure is the signal, demonstrating that the model has no hard constraint enforcing the sum relationship. Most useful when compared against the same check run on the AR6 ground truth (`--use_ground_truth`), which should mostly pass.

**Required model outputs:** At least one parent variable and at least one of its direct children must both be in the run's targets.

**Required data:** Only the run's cached predictions. No ground truth needed to evaluate the constraint.

**Key options:**

| Flag | Default | Description |
|---|---|---|
| `--threshold` | `0.012` | Maximum allowed relative error per timestep (1.2%) |
| `--abs_floor` | `1.0` | Minimum absolute parent value for relative error to be computed |
| `--use_ground_truth` | off | Check AR6 ground truth instead of predictions |

**Outputs** (`ml-iam/results/xgb/<run_id>/sum_check/`):
- `report.txt`
- `scenario_summary.csv`
- `timestep_errors.csv`

---

### `regional_consistency.py` — Regional Consistency Check

**What it does:**
Verifies that predicted values for the `World` region equal the sum of predicted values across all subregions in a complete regional grouping (R5, R6, or R10):

```
error = |World - sum_of_subregions| / |World|
```

For each (Model, Scenario), the check auto-detects which groupings have full coverage. Only complete groupings are checked — scenarios with partial regional coverage are skipped with the coverage count reported.

**Required model outputs:** Any target variables where World and subregional predictions both exist.

**Required data:** Only the run's cached predictions.

**Regional groupings:**
- `R5` — R5ASIA, R5LAM, R5MAF, R5OECD90+EU, R5REF
- `R6` — R6AFRICA, R6ASIA, R6LAM, R6MIDDLE_EAST, R6OECD90+EU, R6REF
- `R10` — R10AFRICA, R10CHINA+, R10EUROPE, R10INDIA+, R10LATIN_AM, R10MIDDLE_EAST, R10NORTH_AM, R10PAC_OECD, R10REF_ECON, R10REST_ASIA, R10ROWO

**Key options:**

| Flag | Default | Description |
|---|---|---|
| `--threshold` | `0.012` | Maximum allowed relative error per timestep (1.2%) |
| `--abs_floor` | `1.0` | Minimum absolute World value for relative error to be computed |
| `--grouping` | all | Restrict to a single grouping: `R5`, `R6`, or `R10` |
| `--use_ground_truth` | off | Check AR6 ground truth instead of predictions |

**Outputs** (`ml-iam/results/xgb/<run_id>/regional_consistency/`):
- `report.txt`
- `scenario_summary.csv`
- `timestep_errors.csv`

---

### `bounds_check.py` — Physical Bounds Check

**What it does:**
Checks predicted values against hard physical bounds and, optionally, empirical bounds derived from the AR6 test-set ground truth.

**Hard physical bounds** are defined in `PHYSICAL_BOUNDS` at the top of the script. Energy generation variables must be non-negative. Emissions have no hard lower bound because CDR scenarios can produce negative net emissions.

**Empirical bounds** (on by default) are derived per-variable from the AR6 test-set ground truth at the chosen percentile range, representing the envelope of values seen in real IAM data. Combined with physical bounds by taking the more restrictive of the two on each side.

**Required model outputs:** Any target variables listed in `PHYSICAL_BOUNDS`, or any variable if empirical bounds are enabled.

**Required data:** AR6 ground truth required unless `--no_empirical` is set.

**Key options:**

| Flag | Default | Description |
|---|---|---|
| `--no_empirical` | off | Disable empirical bounds — use physical bounds only |
| `--percentile` | `1.0` | Tail percentile for empirical bounds |
| `--use_ground_truth` | off | Check AR6 ground truth instead of predictions |

**Outputs** (`ml-iam/results/xgb/<run_id>/bounds_check/`):
- `report.txt`
- `scenario_summary.csv`
- `violations.csv`
- `bounds_used.csv`

---

### `export_predictions.py` — Predictions Export

**What it does:**
Exports model predictions and AR6 ground truth in long (tidy) format as CSVs. Called automatically by `run_all.py` after all checks complete. Can also be run standalone.

The exported CSVs have columns: `Model, Scenario, Region, Scenario_Category, Year, Variable, Value`.

**Required data:** A completed ml-iam run with cached predictions and processed data.

**Outputs** (`ml-iam/results/xgb/<run_id>/predictions/`):
- `predictions_long.csv`
- `groundtruth_long.csv`

---

### `make_val_report.py` — Validation Report Generator

**What it does:**
Reads the CSV outputs from all completed checks and generates a single Markdown report with summary tables and figures, including side-by-side comparisons between model predictions and AR6 ground truth wherever ground truth results are available.

Must be run after `run_all.py` (or after whichever individual checks you want included). Missing check outputs are silently skipped.

The report contains five sections:

1. **Hierarchy Sum Check** — whether parent variables equal the sum of their children
2. **Growth Rate Plausibility** — whether 5-year growth rates stay within AR6 bounds
3. **Regional Consistency** — whether World values equal the sum of subregion values
4. **Physical Bounds Check** — whether values stay within physical and empirical bounds
5. **Inter-variable Correlations** — Pearson r² matrices at 2030, 2050, 2100, comparing predictions against AR6 ground truth (mirrors Li et al. 2025 Fig. 4)

**Required data:** CSV outputs from the individual checks under `ml-iam/results/xgb/<run_id>/`, plus `predictions/predictions_long.csv` (from `export_predictions.py`) for section 5.

**Key options:**

| Flag | Default | Description |
|---|---|---|
| `--title` | `"Validation Report: <run_id>"` | Optional custom report title |

**Outputs** (`reports/<run_id>/`):
- `report.md`
- `figures/*.png`

---

## Adding a new check

1. Create `scripts/<your_check>.py` with a `main()` function that accepts `--run_id` at minimum. Set `REPO_ROOT` using the `ML_IAM_ROOT` pattern at the top of the file (copy from any existing check).
2. Add an entry to the `CHECKS` registry in `scripts/run_all.py`:
   ```python
   CHECKS = [
       ...
       ("your_check", "Description of your check"),
   ]
   ```
3. Add a corresponding `--no-<your_check>` flag to `run_all.py` if you want it to be skippable.
4. Document it in this README following the same structure as the existing checks. Be explicit about whether the check uses AR6 ground truth (as a reference only) or purely the generated predictions.

---

## Terminology

- **AR6 test set** (`y_test`) — the withheld 10% of AR6 scenarios used to evaluate model accuracy. Real, observed IAM data. Used in some checks as a reference to derive empirical bounds or thresholds, but never the thing being validated.
- **Predictions** (`preds`) — the synthetic scenarios generated by the model. What every check is evaluating. The question asked is always: are the generated predictions physically plausible?

---

## Citation

If you use this framework, please also cite the emulation study whose artifacts you are validating.

For ML-IAM (Shin et al.):

```bibtex
@article{egusphere-2025-5305,
  AUTHOR  = {Shin, Y. and Lee, C. and Kim, E. and Myung, J. and Park, K. and Ha, J. and Choi, M.-Y. and Kim, B. and Ka, H. W. and Woo, J.-H. and Oh, A. and McJeon, H.},
  TITLE   = {ML-IAM v1.0: Emulating Integrated Assessment Models With Machine Learning},
  JOURNAL = {EGUsphere},
  VOLUME  = {2026},
  YEAR    = {2026},
  PAGES   = {1--24},
  DOI     = {10.5194/egusphere-2025-5305}
}
```

---

## License

MIT. See [LICENSE](LICENSE).

The AR6 scenario data used by this pipeline has its own separate license and must be obtained and used in compliance with the [IIASA AR6 license](https://data.ene.iiasa.ac.at/ar6/#/license).
