# em-iam-val: A Validation Framework for IAM Emulation Studies

A modular, study-agnostic validation framework for assessing the physical plausibility and internal consistency of emulated Integrated Assessment Model (IAM) scenarios.

This framework is developed as part of a research project establishing validation standards for the emerging field of IAM emulation — the use of machine learning to reproduce or generate IAM scenario outputs. It is designed to be applicable across different emulation approaches and has been applied to two published emulation studies:

- **[ML-IAM v1.0](https://egusphere.copernicus.org/preprints/2026/egusphere-2025-5305/)** (Shin et al., 2026) — XGBoost-based supervised regression emulator
- **[Deep-IAM](https://zenodo.org/)** (Li et al.) — generative deep learning emulator (VAE / CGAN / RCGAN)

---

## Design

The framework has a strict two-layer architecture.

**Adapters** convert dataset-specific artifacts (model checkpoints, numpy arrays, etc.) into a canonical CSV format. They know about RunStore, numpy files, and unit conventions. They produce data and nothing else.

**Checks** consume canonical CSVs. They have no knowledge of where data came from. Each check exposes a `run(predictions, ground_truth, ...)` function that takes DataFrames and a standalone CLI that reads files.

This means any new emulation study can be validated by writing one adapter.

### Canonical format

All data is long-format CSV with these required columns:

```
Model, Scenario, Region, Scenario_Category, Year, Variable, Value, Units
```

The `Units` column is populated by adapters and read directly by `normalize_to_canonical()` before any check runs. No separate unit config is needed.

### Canonical units

| Dimension | Canonical unit |
|-----------|---------------|
| Energy | EJ |
| CO₂ | MtCO₂ |
| CH₄ | MtCH₄ |
| N₂O | MtN₂O |
| CO₂eq (Kyoto aggregates) | MtCO₂eq (not converted) |

---

## Repository structure

```
em-iam-val/
├── adapters/
│   ├── xgb_adapter.py          # ML-IAM (Shin et al.) → canonical CSV
│   └── li_adapter.py           # Deep-IAM (Li et al.) → canonical CSV
├── checks/
│   ├── utils.py                # Canonical format, normalization, shared helpers
│   ├── bounds_check.py
│   ├── check_plausibility.py
│   ├── hard_historical_constraints.py
│   ├── inter_variable_correlation.py
│   ├── regional_consistency.py
│   ├── soft_future_constraints.py
│   └── sum_check.py
├── adapted-data/               # Canonical CSVs written by adapters (gitignored)
├── results/                    # Check outputs per run_id (gitignored)
├── reports/                    # Generated reports
├── validate.py                 # Unified runner
├── pyproject.toml
└── README.md
```

---

## Installation

```bash
cd em-iam-val
poetry install
poetry shell
```

---

## Usage

### Step 1 — Adapt your data

Run the appropriate adapter once to convert model artifacts into canonical CSVs.

**Shin et al. (ML-IAM / XGBoost):**

```bash
python adapters/xgb_adapter.py --run_id xgb_04 --out_dir adapted-data/
```

Requires ml-iam at `../ml-iam` (or set `ML_IAM_ROOT=/path/to/ml-iam`). Produces `adapted-data/xgb_04_predictions.csv` and `adapted-data/xgb_04_ground_truth.csv`.

**Li et al. (Deep-IAM / generative):**

```bash
python adapters/li_adapter.py --model vae --run_id li_vae_01 --out_dir adapted-data/
```

Requires the Li-emulation repository at `../Li-emulation`. Produces `adapted-data/li_vae_01_predictions.csv` and `adapted-data/li_vae_01_ground_truth.csv`.

### Step 2 — Validate

```bash
# Shin et al.
python validate.py \
    --predictions adapted-data/xgb_04_predictions.csv \
    --ground_truth adapted-data/xgb_04_ground_truth.csv \
    --run_id xgb_04

# Li et al.
python validate.py \
    --predictions adapted-data/li_vae_01_predictions.csv \
    --ground_truth adapted-data/li_vae_01_ground_truth.csv \
    --run_id li_vae_01
```

Results are written to `results/<run_id>/<check_name>/`.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--only` | (all) | Run only these checks (space-separated names) |
| `--skip` | (none) | Skip these checks |
| `--percentile` | 1.0 | Tail percentile for empirical bounds |
| `--threshold` | 0.012 | Relative error tolerance for sum/regional checks |
| `--world_region` | World | Region label for global aggregate |
| `--by_category` | off | Break down plausibility violations by scenario category |
| `--report` | off | Generate a summary report after validation |

### Running a single check

Each check can be run directly:

```bash
python checks/bounds_check.py \
    --predictions adapted-data/xgb_04_predictions.csv \
    --ground_truth adapted-data/xgb_04_ground_truth.csv \
    --run_id xgb_04

python checks/hard_historical_constraints.py \
    --predictions adapted-data/li_vae_01_predictions.csv \
    --run_id li_vae_01
```

---

## Checks

### `check_plausibility` — Growth Rate Plausibility

Computes period-on-period growth rates for every trajectory and checks they fall within empirically-derived bounds from the ground truth data (default 1st/99th percentile of observed growth rates per variable). Flags any timestep where the predicted growth rate falls outside those bounds.

Required: any time-varying variables. If ground truth is not provided, bounds are derived from the predictions themselves.

**Key options:** `--percentile` (default 1.0), `--by_category`

---

### `sum_check` — Hierarchy Sum Check

Auto-discovers parent-child variable relationships using the `|` separator convention and verifies that each predicted parent equals the sum of its direct children:

```
error = |parent − Σ children| / |parent|
```

A scenario passes if the mean relative error is below the threshold (default 1.2%). Predictions are expected to fail — the failure rate is the signal.

**Key options:** `--threshold` (default 0.012), `--abs_floor` (default 1.0), `--pass_mode` (mean|all)

---

### `regional_consistency` — Regional Consistency Check

Checks that World values equal the sum of subregion values across complete R5, R6, and R10 groupings. Partial groupings are skipped. Not applicable to World-only datasets.

**Key options:** `--threshold` (default 0.012), `--grouping` (R5|R6|R10, default all)

---

### `bounds_check` — Physical Bounds Check

Two types of bounds:

- **Hard physical bounds** — energy generation variables cannot be negative.
- **Empirical bounds** — per-variable percentile range derived from ground truth (default 1st/99th percentile), representing the envelope of values seen in real IAM data. Disable with `--no_empirical`.

**Key options:** `--percentile` (default 1.0), `--no_empirical`

---

### `hard_historical_constraints` — Hard Historical Constraints

Checks World-level predictions at the 2020 reference year against the historical anchor values from the AR6 scenario vetting process (Nicholls et al. 2022, Table 11). Each scenario is classified as PASS (within inner IP-range), WARN (within outer tolerance but outside IP-range), or FAIL. Sub-checks are automatically skipped if required variables are absent.

| Sub-check | Variable(s) | Reference | Outer | IP-range |
|-----------|-------------|-----------|-------|---------|
| `co2_eip_2020` | `Emissions\|CO2` | 37,646 MtCO₂/yr | ±20% | ±10% |
| `ch4_2020` | `Emissions\|CH4` | 379 MtCH₄/yr | ±20% | ±20% |
| `co2_change_2010_2020` | `Emissions\|CO2` | 0–50% change | — | — |
| `ccs_2020` | `Carbon Sequestration\|CCS` | 0–250 MtCO₂/yr | — | 0–100 MtCO₂/yr |
| `primary_energy_2020` | `Primary Energy` | 578 EJ | ±20% | ±10% |
| `nuclear_energy_2020` | `Primary Energy\|Nuclear` | 9.77 EJ | ±30% | ±20% |
| `solar_wind_2020` | `Primary Energy\|Solar` + `\|Wind` | 8.51 EJ | ±50% | ±25% |

The nuclear and solar/wind checks use `Primary Energy` variables because the AR6 vetting was designed to detect primary energy accounting errors (direct vs thermal equivalent convention). `Secondary Energy|Electricity` is not an equivalent substitute.

If computed values appear implausibly scaled (median more than 100× off the reference), a unit mismatch warning is included in the output.

**Key options:** `--world_region` (default "World")

---

### `soft_future_constraints` — Soft Future Constraints

Checks World-level predictions at specific future years against domain-knowledge plausibility bounds from the AR6 vetting (Table 11). These criteria were flagged as potentially problematic in AR6 but not used as hard exclusion criteria. They are warranted here via the constraint-violation argument: the IAMs were themselves vetted against these criteria, so emulator violations represent emulation failures.

| Sub-check | Variable | Year | Criterion |
|-----------|---------|------|-----------|
| `co2_not_negative_2030` | `Emissions\|CO2` | 2030 | > 0 |
| `ccs_2030` | `Carbon Sequestration\|CCS` | 2030 | < 2,000 MtCO₂/yr |
| `nuclear_electricity_2030` | `Secondary Energy\|Electricity\|Nuclear` | 2030 | < 20 EJ/yr |
| `ch4_2040` | `Emissions\|CH4` | 2040 | 100–1,000 MtCH₄/yr |

**Key options:** `--world_region` (default "World")

---

### `inter_variable_correlation` — Inter-variable Correlation

Computes Pearson r² correlation matrices between all predicted variables at years 2030, 2050, and 2100, and compares against the ground truth correlation structure. A well-calibrated emulator should preserve the inter-variable relationships present in the parent simulation. Produces heatmap figures and a summary table of mean |Δr²| per year. Belongs to the **variance and covariance metrics** validation family.

**Key options:** `--years` (default 2030 2050 2100)

---

## Adding a new check

1. Create `checks/<your_check>.py`. The `run()` signature must be:
   ```python
   def run(predictions: pd.DataFrame, ground_truth: pd.DataFrame = None,
           out_dir: str = "results", run_id: str = "run", **kwargs) -> dict:
   ```
   Return dict keys: `check_name`, `passed`, `results`, `summary`, `unit_warnings`, `skipped`.

2. Add a `main()` with argparse that calls `normalize_to_canonical(load_csv(...))` before calling `run()`.

3. Register it in `validate.py`:
   ```python
   CHECKS = [
       ...
       ("your_check", "Human-readable description"),
   ]
   ```

## Adding a new dataset

Write one adapter in `adapters/<dataset>_adapter.py`. Its job: load whatever format your model uses, set the `Units` column correctly for each variable, write canonical CSVs. `normalize_to_canonical()` handles the rest.

---

## Notes on specific datasets

**Li et al. (Deep-IAM):**
- World-level only — `regional_consistency` skips cleanly with a message
- 10-year timesteps (2020–2100 for generated outputs; 2010–2100 for ground truth)
- Uses `Emissions|Kyoto Gases` (MtCO₂eq/yr) rather than individual CO₂ and CH₄ — checks requiring `Emissions|CO2` or `Emissions|CH4` are automatically skipped

**ML-IAM (Shin et al. / XGBoost):**
- Multi-region (up to 49 regions including World and R5/R6/R10 groupings)
- 5-year timesteps (2015–2100)
- `Primary Energy|*` stored as PJ/yr in the ml-iam config; `Secondary Energy|Electricity|*` labeled EJ/yr but actually stored as PJ/yr — the unit plausibility check will flag this when it runs

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
