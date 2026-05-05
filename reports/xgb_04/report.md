# Validation Report: xgb_04

**Run ID:** `xgb_04`
**Generated:** 2026-05-05 16:09
**Results:** `results/xgb_04/`

---

## Overview

**1. Hierarchy Sum Check**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Pass rate | 1.3% | 66.4% |
| Mean relative error | 6.538% | 1.365% |

**2. Growth Rate Plausibility**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Pass rate (timesteps) | 87.4% | 83.1% |

**4. Physical Bounds Check**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Pass rate (timesteps) | 96.3% | 98.4% |

**5. Hard Historical Constraints** _(PASS = within IP range, WARN = within outer tolerance)_

| Sub-check | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Warn (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| ch4_2020 | 88.8% | 0.0% | 11.2% | 88.8% | 0.0% | 11.2% |
| co2_change_2010_2020 | 100.0% | 0.0% | 0.0% | 100.0% | 0.0% | 0.0% |
| co2_eip_2020 | 53.9% | 40.4% | 5.6% | 49.4% | 43.8% | 6.7% |
| nuclear_energy_2020 | 69.7% | 20.2% | 10.1% | 69.7% | 20.2% | 10.1% |
| solar_wind_2020 | 55.1% | 9.0% | 36.0% | 49.4% | 15.7% | 34.8% |

**6. Soft Future Constraints**

| Sub-check | Pass (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- |
| ch4_2040 | 99.2% | 0.8% | 99.2% | 0.8% |
| co2_not_negative_2030 | 100.0% | 0.0% | 100.0% | 0.0% |
| nuclear_electricity_2030 | 0.0% | 100.0% | 0.0% | 100.0% |

**7. Inter-variable Correlations**

| Metric | Predictions | Ground Truth |
| --- | --- | --- |
| Mean \|Δr²\| vs ground truth | 0.0277 | 0.0000 (reference) |

---

## 1. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children
at every timestep. Predictions are **expected to fail** this check — the failure
rate quantifies how much the model violates IAM accounting identities._

### Pass Rates by Parent Variable

| Parent Variable | Scenario-regions | Pass rate (%) | Mean error (%) | Max error (%) |
| --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity | 1984 | 1.2601 | 6.5384 | 219.8757 |

### Error Distribution

![Sum check error distribution](figures/sum_check_error_dist.png)

### Mean Error by Year

![Sum check error by year](figures/sum_check_error_by_year.png)

### Error Percentile Comparison — Predictions vs Ground Truth

| Percentile | Predictions (%) | Ground truth (%) |
| --- | --- | --- |
| p50 | 5.0274 | 0.0025 |
| p75 | 7.9962 | 1.7538 |
| p90 | 12.1709 | 3.6437 |
| p95 | 16.4388 | 5.4734 |
| p99 | 27.9085 | 12.8627 |

### Example Failure

_The median failing scenario (by mean error) is shown below._

#### Example failure — predictions

**Scenario:** POLES ENGAGE | EN_INDCi2030_1000f_COV_NDCp | TUR  
**Parent variable:** Secondary Energy|Electricity  
**Mean error:** 5.07%  (median failing scenario)

| Year | Biomass | Coal | Gas | Geothermal | Hydro | Nuclear | Oil | Solar | Wind | Sum of children | Parent value | Error (%) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025 | 10.822 | 257.648 | 319.528 | 18.343 | 427.783 | 0.035 | 6.393 | 54.959 | 224.102 | 1319.613 | 1358.654 | 2.87 | FAIL |
| 2030 | 13.231 | 265.38 | 340.77 | 21.043 | 494.357 | 4.613 | 8.081 | 141.097 | 325.506 | 1614.078 | 1661.869 | 2.88 | FAIL |
| 2035 | 24.008 | 164.943 | 332.073 | 41.809 | 567.413 | 19.207 | 11.083 | 320.571 | 503.258 | 1984.364 | 1907.483 | 4.03 | FAIL |
| 2040 | 28.477 | 95.003 | 271.475 | 101.358 | 599.566 | 52.734 | 9.3 | 509.282 | 683.582 | 2350.778 | 2329.942 | 0.89 | PASS |
| 2045 | 47.279 | 76.425 | 222.682 | 157.881 | 601.505 | 75.889 | 5.824 | 603.128 | 903.232 | 2693.845 | 2785.21 | 3.28 | FAIL |
| 2050 | 73.653 | 65.346 | 191.038 | 190.944 | 613.918 | 133.621 | 4.096 | 779.486 | 1087.976 | 3140.077 | 3267.89 | 3.91 | FAIL |
| 2060 | 123.204 | 60.312 | 163.412 | 226.237 | 609.848 | 253.163 | 1.7 | 940.295 | 1351.034 | 3729.205 | 3853.846 | 3.23 | FAIL |
| 2070 | 148.595 | 63.065 | 105.138 | 234.01 | 612.08 | 367.124 | 2.147 | 1008.708 | 1339.211 | 3880.078 | 4165.657 | 6.86 | FAIL |
| 2080 | 181.048 | 62.515 | 78.949 | 230.836 | 614.795 | 461.569 | 1.364 | 963.684 | 1212.894 | 3807.653 | 4229.573 | 9.98 | FAIL |
| 2090 | 204.621 | 65.03 | 57.511 | 240.202 | 618.833 | 451.501 | 1.818 | 910.13 | 1176.593 | 3726.239 | 4112.924 | 9.4 | FAIL |
| 2100 | 195.279 | 59.552 | 36.68 | 269.176 | 615.787 | 449.037 | 1.278 | 828.325 | 1110.948 | 3566.062 | 3893.672 | 8.41 | FAIL |

#### Example failure — ground truth

**Scenario:** REMIND-MAgPIE 2.1-4.2 | EN_NPi2020_1200f | USA  
**Parent variable:** Secondary Energy|Electricity  
**Mean error:** 2.62%  (median failing scenario)

| Year | Biomass | Coal | Gas | Geothermal | Hydro | Nuclear | Oil | Solar | Wind | Sum of children | Parent value | Error (%) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015 | 324.1 | 4909.8 | 5872.0 | 98.0 | 1096.9 | 2640.7 | 278.1 | 136.4 | 730.4 | 16086.4 | 16086.5 | 0.0 | PASS |
| 2020 | 316.9 | 4252.6 | 6742.9 | 112.0 | 1204.2 | 2007.0 | 189.9 | 417.4 | 1275.7 | 16518.6 | 16519.2 | 0.0 | PASS |
| 2025 | 302.8 | 3343.2 | 6733.1 | 112.0 | 1325.7 | 1507.6 | 111.6 | 1422.5 | 2348.0 | 17206.5 | 17221.9 | 0.09 | PASS |
| 2030 | 279.2 | 1884.3 | 5461.1 | 112.0 | 1385.9 | 1030.7 | 36.3 | 3751.9 | 4516.3 | 18457.7 | 18565.5 | 0.58 | PASS |
| 2035 | 244.5 | 14.1 | 3220.2 | 112.0 | 1425.6 | 688.1 | 0.0 | 6353.8 | 7313.0 | 19371.3 | 19699.9 | 1.67 | FAIL |
| 2040 | 198.4 | 9.2 | 1218.7 | 111.9 | 1445.0 | 479.7 | 0.0 | 8548.6 | 9917.5 | 21929.0 | 22477.9 | 2.44 | FAIL |
| 2045 | 148.2 | 4.8 | 700.2 | 112.0 | 1447.3 | 295.5 | 0.0 | 10276.6 | 12118.8 | 25103.4 | 25813.9 | 2.75 | FAIL |
| 2050 | 125.7 | 1.5 | 784.6 | 112.0 | 1437.5 | 148.6 | 0.0 | 11721.5 | 13816.5 | 28147.9 | 28971.6 | 2.84 | FAIL |
| 2055 | 160.3 | 0.1 | 848.7 | 112.0 | 1420.2 | 56.2 | 0.0 | 12986.7 | 14950.1 | 30534.3 | 31449.2 | 2.91 | FAIL |
| 2060 | 238.9 | 0.1 | 869.0 | 112.0 | 1399.5 | 22.2 | 0.0 | 13991.5 | 15726.7 | 32359.9 | 33373.1 | 3.04 | FAIL |
| 2070 | 391.5 | 0.1 | 672.1 | 105.2 | 1351.8 | 1.7 | 0.0 | 15756.8 | 17411.3 | 35690.5 | 37139.5 | 3.9 | FAIL |
| 2080 | 491.4 | 0.1 | 301.9 | 112.0 | 1307.3 | 0.0 | 0.0 | 17195.7 | 18535.7 | 37944.1 | 39949.9 | 5.02 | FAIL |
| 2090 | 502.1 | 0.1 | 86.0 | 112.0 | 1285.0 | 0.0 | 0.0 | 18290.8 | 20123.0 | 40399.0 | 42797.4 | 5.6 | FAIL |
| 2100 | 427.3 | 0.1 | 0.1 | 112.0 | 1276.3 | 0.0 | 0.0 | 20730.4 | 21843.4 | 44389.6 | 47154.5 | 5.86 | FAIL |

---

## 2. Growth Rate Plausibility

_For each predicted trajectory, checks that period-on-period growth rates
fall within empirically-derived bounds from the ground truth data._

**Total timesteps evaluated:** 419,995  
**Violations:** 52,953 (12.61%)  

**Ground truth — violation rate:** 16.89%  
_(-4.29pp difference: predictions vs ground truth)_

### Violation Rate by Variable

![Plausibility violations by variable](figures/plausibility_violations_by_variable.png)

### Violation Rate by Scenario Category

| Category | Timesteps | Violations | Violation rate (%) |
| --- | --- | --- | --- |
| C2 | 48716 | 6770 | 13.9000 |
| C1 | 29697 | 4122 | 13.8800 |
| C3 | 123215 | 16981 | 13.7800 |
| C6 | 42883 | 5659 | 13.2000 |
| C4 | 60743 | 7832 | 12.8900 |
| C5 | 66880 | 7305 | 10.9200 |
| C7 | 34694 | 3524 | 10.1600 |
| C8 | 3097 | 280 | 9.0400 |
| no-climate-assessment | 10070 | 480 | 4.7700 |

### Example Violation

_The most extreme growth rate violation is shown below._

#### Example violation — predictions

**Most extreme growth rate violation**

| Variable | Scenario | Region | Category | Year (from) | Year (to) | Growth rate |
| --- | --- | --- | --- | --- | --- | --- |
| Emissions\|CO2 | EN_INDCi2030_900f_NDCp | World | C3 | 2070 | 2080 | -2677.9061 |

#### Example violation — ground truth

**Most extreme growth rate violation**

| Variable | Scenario | Region | Category | Year (from) | Year (to) | Growth rate |
| --- | --- | --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity\|Solar | EN_NPi2020_1000_COV | R10INDIA+ | C3 | 2020 | 2030 | +1719.5934 |

---

## 3. Regional Consistency

_Checks that predicted World values equal the sum of predicted subregion values
(R5 / R6 / R10 groupings). Only applicable to datasets with regional breakdowns._

_Regional consistency results not found. Run `validate.py` first, or skip if your run has no multi-region scenarios._


---

## 4. Physical Bounds Check

_Checks predictions against hard physical lower bounds (energy variables ≥ 0)
and empirical per-variable bounds derived from ground truth._

**Timesteps checked:** 457,691  
**Violations:** 17,041 (3.723%)  
**Fully clean scenario-regions:** 32,149 / 37,696

### Violations by Variable

![Bounds violations by variable](figures/bounds_violations_by_variable.png)

### Predictions vs Ground Truth

| Source | Timesteps | Violations | Violation rate |
| --- | --- | --- | --- |
| Predictions | 457,691 | 17,041 | 3.723% |
| Ground truth | 457,691 | 7,257 | 1.586% |

_Predictions show +2.138 pp more violations than ground truth._

### Violation Rate by Variable — Predictions vs Ground Truth

![Bounds violation rate pred vs GT](figures/bounds_violation_rate_pred_vs_gt.png)

### Example Violation

_The most extreme bounds violation is shown below._

#### Example violation — predictions

**Most extreme bounds violation**

| Variable | Scenario | Region | Category | Year | Value | Units | Violation type |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity | CEMICS-2.0-CDR8 | World | C1 | 2100 | 831072.3969 | EJ/yr | Above empirical upper bound (373710.01) |

#### Example violation — ground truth

**Most extreme bounds violation**

| Variable | Scenario | Region | Category | Year | Value | Units | Violation type |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity | EN_NPi2020_600f | World | C2 | 2100 | 829450.1 | EJ/yr | Above empirical upper bound (373710.01) |

---

## 5. Hard Historical Constraints

_Checks World-level predictions at 2020 against AR6 vetting reference values
(Nicholls et al. 2022, Table 11). PASS = within IP range, WARN = within outer
tolerance, FAIL = outside outer tolerance. Belongs to the **historical and
domain knowledge comparison** validation family._

| Sub-check | N | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| ch4_2020 | 89 | 88.8000 | 0.0000 | 11.2000 | 88.8000 | 11.2000 |
| co2_change_2010_2020 | 18 | 100.0000 | 0.0000 | 0.0000 | 100.0000 | 0.0000 |
| co2_eip_2020 | 89 | 53.9000 | 40.4000 | 5.6000 | 88.0000 | 12.0000 |
| nuclear_energy_2020 | 89 | 69.7000 | 20.2000 | 10.1000 | 87.3000 | 12.7000 |
| solar_wind_2020 | 89 | 55.1000 | 9.0000 | 36.0000 | 58.7000 | 41.3000 |


_Skipped sub-checks (required variables absent): ccs_2020: ['Carbon Sequestration|CCS'], primary_energy_2020: ['Primary Energy']_


---

## 6. Soft Future Constraints

_Checks World-level predictions at 2030–2040 against domain-knowledge
plausibility bounds from the AR6 vetting process (Table 11). Belongs to the
**historical and domain knowledge comparison** validation family._

| Sub-check | N | Pass (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- |
| ch4_2040 | 120 | 99.2000 | 0.8000 | 99.2000 | 0.8000 |
| co2_not_negative_2030 | 118 | 100.0000 | 0.0000 | 100.0000 | 0.0000 |
| nuclear_electricity_2030 | 118 | 0.0000 | 100.0000 | 0.0000 | 100.0000 |


_Skipped sub-checks (required variables absent): ccs_2030: ['Carbon Sequestration|CCS']_


<p style="color:red;font-weight:bold">⚠️ POSSIBLE UNIT MISMATCH: median 1.255e+04 is ~1046x higher than expected 12 EJ/yr. Check units for Secondary Energy|Electricity|Nuclear</p>


---

## 7. Inter-variable Correlations

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
| 2030.0 | 19.0 | 0.0219 |
| 2050.0 | 19.0 | 0.0261 |
| 2100.0 | 19.0 | 0.035 |

