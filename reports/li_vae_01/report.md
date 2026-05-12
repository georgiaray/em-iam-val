# Validation Report: li_vae_01

**Run ID:** `li_vae_01`
**Generated:** 2026-05-08 11:23
**Results:** `results/li_vae_01/`

---

## Overview

**1. Hierarchy Sum Check**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Pass rate | 0.0% | 58.9% |
| Mean relative error | 2019.856% | 10.095% |

**2. Growth Rate Plausibility**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Pass rate (timesteps) | 78.1% | 88.5% |

**3. Regional Consistency**

_No complete regional groupings in this dataset._

**4. Physical Bounds Check**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Pass rate (timesteps) | 76.0% | 98.5% |

**5. Hard Historical Constraints** _(PASS = within IP range, WARN = within outer tolerance)_

| Sub-check | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Warn (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| ccs_2020 | 96.7% | 3.0% | 0.2% | 98.2% | 1.4% | 0.3% |

**6. Soft Future Constraints**

| Sub-check | Pass (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- |
| ccs_2030 | 95.3% | 4.7% | 91.3% | 8.7% |
| nuclear_electricity_2030 | 97.8% | 2.2% | 94.1% | 5.9% |

**7. SCI Vetting Checks**

| Sub-check | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Warn (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| hist_primary_coal | 61.5% | 0.0% | 38.5% | 97.9% | 0.0% | 2.1% |
| hist_primary_gas | 59.8% | 0.0% | 40.2% | 98.6% | 0.0% | 1.4% |
| hist_primary_oil | 44.0% | 0.0% | 56.0% | 97.3% | 0.0% | 2.7% |
| longterm_ccs_2035 | 92.8% | 7.2% | 0.0% | 87.5% | 12.5% | 0.0% |
| longterm_ccs_2040 | 89.3% | 10.7% | 0.0% | 82.3% | 17.7% | 0.0% |
| nearterm_ccs | 35.0% | 43.7% | 21.3% | 11.6% | 55.6% | 32.8% |

**7. Inter-variable Correlations**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Mean \|Δr²\| vs ground truth | 0.1383 | 0.0000 (reference) |

---

## 1. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children
at every timestep. Predictions are **expected to fail** this check — the failure
rate quantifies how much the model violates IAM accounting identities._

### Pass Rates by Parent Variable

| Parent Variable | Scenario-regions | Pass rate (%) | Mean error (%) | Max error (%) |
| --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity | 30000 | 0.0000 | 2019.8564 | 44942.0074 |

### Error Distribution

![Sum check error distribution](figures/sum_check_error_dist.png)

### Mean Error by Year

![Sum check error by year](figures/sum_check_error_by_year.png)

### Error Percentile Comparison — Predictions vs Ground Truth

| Percentile | Predictions (%) | Ground truth (%) |
| --- | --- | --- |
| p50 | 1495.9180 | 0.8424 |
| p75 | 2251.1809 | 1.8139 |
| p90 | 3837.0541 | 3.3668 |
| p95 | 5033.2191 | 5.8508 |
| p99 | 8124.1684 | 11.4583 |

### Example Failure

_The median failing scenario (by mean error) is shown below._

#### Example failure — predictions

**Scenario:** VAE | gen_00564 | World  
**Parent variable:** Secondary Energy|Electricity  
**Mean error:** 1495.91%  (median failing scenario)

| Year | Biomass | Coal | Gas | Geothermal | Hydro | Nuclear | Oil | Solar | Wind | Sum of children | Parent value | Error (%) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2020 | 0.925 | 14.262 | 0.356 | 98.92 | 1.134 | 9.679 | 5.007 | 30.298 | 33.192 | 193.773 | 2.437 | 7852.31 | FAIL |
| 2030 | 2.71 | 21.842 | 2.067 | 139.837 | 0.658 | 17.451 | 29.438 | 8.101 | 43.212 | 265.316 | 14.544 | 1724.26 | FAIL |
| 2040 | 2.607 | 24.43 | 5.013 | 218.944 | 0.23 | 26.204 | 61.463 | 6.767 | 54.595 | 400.253 | 29.574 | 1253.41 | FAIL |
| 2050 | 5.053 | 26.135 | 6.368 | 283.121 | 0.015 | 36.92 | 95.815 | 2.212 | 47.566 | 503.205 | 61.003 | 724.88 | FAIL |
| 2060 | 8.702 | 27.015 | 6.183 | 360.243 | 0.002 | 48.977 | 147.844 | 0.482 | 23.297 | 622.745 | 93.905 | 563.16 | FAIL |
| 2070 | 7.873 | 27.382 | 6.328 | 449.639 | 0.001 | 61.345 | 198.231 | 0.07 | 6.534 | 757.403 | 138.044 | 448.67 | FAIL |
| 2080 | 7.015 | 27.89 | 6.305 | 537.763 | 0.0 | 78.756 | 224.607 | 0.012 | 2.307 | 884.654 | 186.446 | 374.48 | FAIL |
| 2090 | 7.167 | 28.42 | 6.357 | 617.081 | 0.0 | 82.924 | 238.591 | 0.018 | 1.418 | 981.976 | 249.8 | 293.1 | FAIL |
| 2100 | 6.954 | 30.01 | 6.44 | 695.818 | 0.0 | 78.719 | 247.571 | 0.019 | 0.49 | 1066.019 | 324.121 | 228.9 | FAIL |

#### Example failure — ground truth

**Scenario:** REMIND-MAgPIE 2.1-4.2 | EN_NPi2020_1000_COV | World  
**Parent variable:** Secondary Energy|Electricity  
**Mean error:** 2.13%  (median failing scenario)

| Year | Biomass | Coal | Gas | Geothermal | Hydro | Nuclear | Oil | Solar | Wind | Sum of children | Parent value | Error (%) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2010 | 1.195 | 30.167 | 18.091 | 0.325 | 12.741 | 9.547 | 3.646 | 0.298 | 2.046 | 78.055 | 78.055 | 0.0 | PASS |
| 2020 | 2.085 | 30.63 | 22.894 | 0.872 | 19.519 | 8.022 | 2.12 | 3.386 | 5.484 | 95.013 | 95.024 | 0.01 | PASS |
| 2030 | 2.811 | 18.38 | 26.784 | 1.319 | 23.104 | 7.132 | 0.523 | 28.017 | 21.927 | 129.996 | 130.736 | 0.57 | PASS |
| 2040 | 2.721 | 0.506 | 18.014 | 1.336 | 25.322 | 7.254 | 0.02 | 58.072 | 57.697 | 170.943 | 174.113 | 1.82 | FAIL |
| 2050 | 2.836 | 0.019 | 9.687 | 1.312 | 26.881 | 6.952 | 0.0 | 85.272 | 97.497 | 230.456 | 236.125 | 2.4 | FAIL |
| 2060 | 3.924 | 0.008 | 7.802 | 1.276 | 28.131 | 6.085 | 0.0 | 114.508 | 131.631 | 293.366 | 301.445 | 2.68 | FAIL |
| 2070 | 5.423 | 0.013 | 8.919 | 1.252 | 29.082 | 5.281 | 0.0 | 147.842 | 159.81 | 357.622 | 368.555 | 2.97 | FAIL |
| 2080 | 6.729 | 0.025 | 9.78 | 1.233 | 29.834 | 4.884 | 0.0 | 180.22 | 177.243 | 409.948 | 423.964 | 3.31 | FAIL |
| 2090 | 7.568 | 0.032 | 9.855 | 1.183 | 30.648 | 5.882 | 0.0 | 205.703 | 192.284 | 453.154 | 470.327 | 3.65 | FAIL |
| 2100 | 8.195 | 0.03 | 9.835 | 1.23 | 31.316 | 8.621 | 0.0 | 232.592 | 207.765 | 499.583 | 519.97 | 3.92 | FAIL |

---

## 2. Growth Rate Plausibility

_For each predicted trajectory, checks that period-on-period growth rates
fall within empirically-derived bounds from the ground truth data._

**Total timesteps evaluated:** 3,840,000  
**Violations:** 841,261 (21.91%)  

**Ground truth — violation rate:** 11.54%  
_(+10.37pp difference: predictions vs ground truth)_

### Violation Rate by Variable

![Plausibility violations by variable](figures/plausibility_violations_by_variable.png)

### Example Violation

_The most extreme growth rate violation is shown below._

#### Example violation — predictions

**Most extreme growth rate violation**

| Variable | Scenario | Region | Year (from) | Year (to) | Growth rate |
| --- | --- | --- | --- | --- | --- |
| Emissions\|Kyoto Gases | gen_13214 | World | 2090 | 2100 | -2974.3899 |

#### Example violation — ground truth

**Most extreme growth rate violation**

| Variable | Scenario | Region | Year (from) | Year (to) | Growth rate |
| --- | --- | --- | --- | --- | --- |
| Carbon Sequestration\|CCS | R2p1_SSP5-PkBudg900 | World | 2020 | 2030 | +1083.6932 |

---

## 3. Regional Consistency

_Checks that predicted World values equal the sum of predicted subregion values
(R5 / R6 / R10 groupings). Only applicable to datasets with regional breakdowns._

_No complete regional groupings found in this dataset. The check requires all subregions in a grouping (R5/R6/R10) to have data for the same scenario-variable-year combinations. This dataset has partial regional coverage only._


---

## 4. Physical Bounds Check

_Checks predictions against hard physical lower bounds (energy variables ≥ 0)
and empirical per-variable bounds derived from ground truth._

**Timesteps checked:** 4,320,000  
**Violations:** 1,037,278 (24.011%)  
**Fully clean scenario-regions:** 332,609 / 480,000

### Violations by Variable

![Bounds violations by variable](figures/bounds_violations_by_variable.png)

### Predictions vs Ground Truth

| Source | Timesteps | Violations | Violation rate |
| --- | --- | --- | --- |
| Predictions | 4,320,000 | 1,037,278 | 24.011% |
| Ground truth | 222,820 | 3,238 | 1.453% |

_Predictions show +22.558 pp more violations than ground truth._

### Violation Rate by Variable — Predictions vs Ground Truth

![Bounds violation rate pred vs GT](figures/bounds_violation_rate_pred_vs_gt.png)

### Example Violation

_The most extreme bounds violation is shown below._

#### Example violation — predictions

**Most extreme bounds violation**

| Variable | Scenario | Region | Year | Value | Units | Violation type |
| --- | --- | --- | --- | --- | --- | --- |
| Emissions\|Kyoto Gases | gen_20075 | World | 2090 | 154553.6562 | MtCO2eq/yr | Above empirical upper bound (100010.08) |

#### Example violation — ground truth

**Most extreme bounds violation**

| Variable | Scenario | Region | Year | Value | Units | Violation type |
| --- | --- | --- | --- | --- | --- | --- |
| Emissions\|Kyoto Gases | SSP5-Baseline | World | 2080 | 155970.0094 | MtCO2eq/yr | Above empirical upper bound (100010.08) |

---

## 5. Hard Historical Constraints

_Checks World-level predictions at 2020 against AR6 vetting reference values
(Nicholls et al. 2022, Table 11). PASS = within IP range, WARN = within outer
tolerance, FAIL = outside outer tolerance. Belongs to the **historical and
domain knowledge comparison** validation family._

| Sub-check | N | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| ccs_2020 | 30000 | 96.7000 | 3.0000 | 0.2000 | 99.7000 | 0.3000 |


_Skipped sub-checks (required variables absent): co2_eip_2020: ['Emissions|CO2'], ch4_2020: ['Emissions|CH4'], co2_change_2010_2020: ['Emissions|CO2'], primary_energy_2020: ['Primary Energy'], nuclear_energy_2020: ['Primary Energy|Nuclear'], solar_wind_2020: ['Primary Energy|Solar', 'Primary Energy|Wind']_


---

## 6. Soft Future Constraints

_Checks World-level predictions at 2030–2040 against domain-knowledge
plausibility bounds from the AR6 vetting process (Table 11). Belongs to the
**historical and domain knowledge comparison** validation family._

| Sub-check | N | Pass (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- |
| ccs_2030 | 30000 | 95.4000 | 4.6000 | 91.3000 | 8.7000 |
| nuclear_electricity_2030 | 30000 | 97.8000 | 2.2000 | 94.1000 | 5.9000 |


_Skipped sub-checks (required variables absent): co2_not_negative_2030: ['Emissions|CO2'], ch4_2040: ['Emissions|CH4']_


---

## 7. SCI Vetting Checks

_Scenario vetting criteria from Verpoort et al. (2025), the IAMC's published
successor to the AR6 vetting criteria. Checks CO₂ EIP against CEDS-2025 data
at four anchor years (2010–2025), and CCS feasibility at 2030, 2035, and 2040.
Status: PASS = within medium-concern bounds, WARN = within strong-concern bounds,
FAIL = outside strong-concern (exclusion-level) bounds._

| Sub-check | N | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| hist_primary_coal | 120000 | 61.5000 | 0.0000 | 38.5000 | 97.9000 | 2.1000 |
| hist_primary_gas | 120000 | 59.8000 | 0.0000 | 40.2000 | 98.6000 | 1.4000 |
| hist_primary_oil | 120000 | 44.0000 | 0.0000 | 56.0000 | 97.3000 | 2.7000 |
| longterm_ccs_2035 | 30000 | 92.8000 | 7.2000 | 0.0000 | 87.5000 | 0.0000 |
| longterm_ccs_2040 | 30000 | 89.3000 | 10.7000 | 0.0000 | 82.3000 | 0.0000 |
| nearterm_ccs | 30000 | 35.0000 | 43.7000 | 21.3000 | 11.6000 | 32.8000 |


_Not run: hist_co2_eip (['Emissions|CO2'])_


---

## 8. Inter-variable Correlations

_Pearson r² between all variable pairs at years 2030, 2050, and 2100 — comparing
predictions against AR6 ground truth. A well-calibrated emulator should preserve
the correlations present in real IAM data. Methodology follows Li et al. (2025) Fig. 4._

Inter-variable Pearson r² matrices at years 2030, 2050, and 2100, comparing model predictions against AR6 ground truth. Values close to the ground truth indicate the emulator preserves real-world variable relationships. Methodology follows Li et al. (2025) Fig. 4.

### 2030

_Left: predictions. Centre: AR6 ground truth. Right: difference (blue = predictions underestimate correlation, red = overestimate)._

![Inter-variable correlations 2030](figures/correlations_2030.png)

### 2050

_Left: predictions. Centre: AR6 ground truth. Right: difference (blue = predictions underestimate correlation, red = overestimate)._

![Inter-variable correlations 2050](figures/correlations_2050.png)

### 2100

_Left: predictions. Centre: AR6 ground truth. Right: difference (blue = predictions underestimate correlation, red = overestimate)._

![Inter-variable correlations 2100](figures/correlations_2100.png)

### Summary: Mean Absolute Difference in r²

_Average absolute difference between predictions and ground truth correlation matrices (off-diagonal pairs only). Lower is better._

| Year | N variables | Mean \|Δr²\| (off-diagonal) |
| --- | --- | --- |
| 2030.0 | 16.0 | 0.146 |
| 2050.0 | 16.0 | 0.1468 |
| 2100.0 | 16.0 | 0.122 |

