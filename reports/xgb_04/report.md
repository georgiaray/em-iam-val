# Validation Report: xgb_04

**Run ID:** `xgb_04`
**Generated:** 2026-05-05 11:54
**Results path:** `results/xgb/xgb_04/`

---

## Overview

| Check | Metric | Predictions | Ground Truth |
| --- | --- | --- | --- |
| Hierarchy Sum Check | Scenario-region pass rate | 1.3% | 66.4% |
|  | Mean relative error | 6.538% | 1.365% |
| Growth Rate Plausibility | Timestep violation rate | 3.0% | 1.8% |
| Physical Bounds Check | Timestep violation rate | 3.72% | 1.59% |
| Inter-variable Correlations | Mean \|Δr²\| vs ground truth | 0.0277 | 0.0000 (reference) |

---

## 1. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children
at every timestep. Predictions are **expected to fail** this check — the failure
rate quantifies how much the model violates the sum constraint. Compare to the
ground truth pass rate to understand baseline data consistency._

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

_The median failing scenario (by mean error) is shown below to illustrate a typical hierarchy violation._

#### Example failure — predictions

**Scenario:** POLES ENGAGE | EN_INDCi2030_1000f_COV_NDCp | TUR | C3  
**Parent variable:** Secondary Energy|Electricity  
**Mean error:** 5.07%  (median failing scenario)

| Year | Biomass | Coal | Gas | Geothermal | Hydro | Nuclear | Oil | Solar | Wind | Sum of children (EJ/yr) | Parent value (EJ/yr) | Difference | Error (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025.0 | 10.822 | 257.648 | 319.528 | 18.343 | 427.783 | 0.035 | 6.393 | 54.959 | 224.102 | 1319.613 | 1358.654 | 39.041 | 2.87 |
| 2030.0 | 13.231 | 265.38 | 340.77 | 21.043 | 494.357 | 4.613 | 8.081 | 141.097 | 325.506 | 1614.078 | 1661.869 | 47.791 | 2.88 |
| 2035.0 | 24.008 | 164.943 | 332.073 | 41.809 | 567.413 | 19.207 | 11.083 | 320.571 | 503.258 | 1984.364 | 1907.483 | -76.88 | 4.03 |
| 2040.0 | 28.477 | 95.003 | 271.475 | 101.358 | 599.566 | 52.734 | 9.3 | 509.282 | 683.582 | 2350.778 | 2329.942 | -20.836 | 0.89 |
| 2045.0 | 47.279 | 76.425 | 222.682 | 157.881 | 601.505 | 75.889 | 5.824 | 603.128 | 903.232 | 2693.845 | 2785.21 | 91.365 | 3.28 |
| 2050.0 | 73.653 | 65.346 | 191.038 | 190.944 | 613.918 | 133.621 | 4.096 | 779.486 | 1087.976 | 3140.077 | 3267.89 | 127.814 | 3.91 |
| 2060.0 | 123.204 | 60.312 | 163.412 | 226.237 | 609.848 | 253.163 | 1.7 | 940.295 | 1351.034 | 3729.205 | 3853.846 | 124.642 | 3.23 |
| 2070.0 | 148.595 | 63.065 | 105.138 | 234.01 | 612.08 | 367.124 | 2.147 | 1008.708 | 1339.211 | 3880.078 | 4165.657 | 285.58 | 6.86 |
| 2080.0 | 181.048 | 62.515 | 78.949 | 230.836 | 614.795 | 461.569 | 1.364 | 963.684 | 1212.894 | 3807.653 | 4229.573 | 421.92 | 9.98 |
| 2090.0 | 204.621 | 65.03 | 57.511 | 240.202 | 618.833 | 451.501 | 1.818 | 910.13 | 1176.593 | 3726.239 | 4112.924 | 386.685 | 9.4 |
| 2100.0 | 195.279 | 59.552 | 36.68 | 269.176 | 615.787 | 449.037 | 1.278 | 828.325 | 1110.948 | 3566.062 | 3893.672 | 327.611 | 8.41 |

#### Example failure — ground truth

**Scenario:** REMIND-MAgPIE 2.1-4.2 | EN_NPi2020_1200f | USA | C4  
**Parent variable:** Secondary Energy|Electricity  
**Mean error:** 2.62%  (median failing scenario)

| Year | Biomass | Coal | Gas | Geothermal | Hydro | Nuclear | Oil | Solar | Wind | Sum of children (EJ/yr) | Parent value (EJ/yr) | Difference | Error (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015.0 | 324.1 | 4909.8 | 5872.0 | 98.0 | 1096.9 | 2640.7 | 278.1 | 136.4 | 730.4 | 16086.4 | 16086.5 | 0.1 | 0.0 |
| 2020.0 | 316.9 | 4252.6 | 6742.9 | 112.0 | 1204.2 | 2007.0 | 189.9 | 417.4 | 1275.7 | 16518.6 | 16519.2 | 0.6 | 0.0 |
| 2025.0 | 302.8 | 3343.2 | 6733.1 | 112.0 | 1325.7 | 1507.6 | 111.6 | 1422.5 | 2348.0 | 17206.5 | 17221.9 | 15.4 | 0.09 |
| 2030.0 | 279.2 | 1884.3 | 5461.1 | 112.0 | 1385.9 | 1030.7 | 36.3 | 3751.9 | 4516.3 | 18457.7 | 18565.5 | 107.8 | 0.58 |
| 2035.0 | 244.5 | 14.1 | 3220.2 | 112.0 | 1425.6 | 688.1 | 0.0 | 6353.8 | 7313.0 | 19371.3 | 19699.9 | 328.6 | 1.67 |
| 2040.0 | 198.4 | 9.2 | 1218.7 | 111.9 | 1445.0 | 479.7 | 0.0 | 8548.6 | 9917.5 | 21929.0 | 22477.9 | 548.9 | 2.44 |
| 2045.0 | 148.2 | 4.8 | 700.2 | 112.0 | 1447.3 | 295.5 | 0.0 | 10276.6 | 12118.8 | 25103.4 | 25813.9 | 710.5 | 2.75 |
| 2050.0 | 125.7 | 1.5 | 784.6 | 112.0 | 1437.5 | 148.6 | 0.0 | 11721.5 | 13816.5 | 28147.9 | 28971.6 | 823.7 | 2.84 |
| 2055.0 | 160.3 | 0.1 | 848.7 | 112.0 | 1420.2 | 56.2 | 0.0 | 12986.7 | 14950.1 | 30534.3 | 31449.2 | 914.9 | 2.91 |
| 2060.0 | 238.9 | 0.1 | 869.0 | 112.0 | 1399.5 | 22.2 | 0.0 | 13991.5 | 15726.7 | 32359.9 | 33373.1 | 1013.2 | 3.04 |
| 2070.0 | 391.5 | 0.1 | 672.1 | 105.2 | 1351.8 | 1.7 | 0.0 | 15756.8 | 17411.3 | 35690.5 | 37139.5 | 1449.0 | 3.9 |
| 2080.0 | 491.4 | 0.1 | 301.9 | 112.0 | 1307.3 | 0.0 | 0.0 | 17195.7 | 18535.7 | 37944.1 | 39949.9 | 2005.8 | 5.02 |
| 2090.0 | 502.1 | 0.1 | 86.0 | 112.0 | 1285.0 | 0.0 | 0.0 | 18290.8 | 20123.0 | 40399.0 | 42797.4 | 2398.4 | 5.6 |
| 2100.0 | 427.3 | 0.1 | 0.1 | 112.0 | 1276.3 | 0.0 | 0.0 | 20730.4 | 21843.4 | 44389.6 | 47154.5 | 2764.9 | 5.86 |

---

## 2. Growth Rate Plausibility

_For each predicted trajectory, checks that the 5-year period-on-period growth rate
falls within the 1st–99th percentile range observed in the AR6 test-set ground truth.
Empirical bounds are derived per variable._

**Total timesteps evaluated:** 419,995  
**Violations:** 12,786 (3.04%)  
**Median severity** (violations only): 0.257 bound-widths  

**Ground truth — violation rate:** 1.76%  
**Ground truth — median severity:** 0.148 bound-widths  
_(+1.28pp difference: predictions vs ground truth)_

### Violation Rate by Variable

![Plausibility violations by variable](figures/plausibility_violations_by_variable.png)

### Empirical Bounds Used (AR6 test-set percentiles)

| Variable | Lower bound | Upper bound |
| --- | --- | --- |
| Emissions\|CH4 | -0.3477 | 0.1688 |
| Emissions\|CO2 | -8.2397 | 0.5696 |
| Emissions\|N2O | -0.3593 | 0.1809 |
| Primary Energy\|Coal | -0.9983 | 1.6217 |
| Primary Energy\|Gas | -0.7501 | 0.8492 |
| Primary Energy\|Nuclear | -1.0000 | 2.1344 |
| Primary Energy\|Oil | -0.9504 | 0.5854 |
| Primary Energy\|Solar | -0.0949 | 7.8881 |
| Primary Energy\|Wind | -0.1478 | 8.9436 |
| Secondary Energy\|Electricity | -0.0910 | 0.6844 |
| Secondary Energy\|Electricity\|Biomass | -0.9989 | 10.3980 |
| Secondary Energy\|Electricity\|Coal | -1.0000 | 3.0881 |
| Secondary Energy\|Electricity\|Gas | -1.0000 | 1.6098 |
| Secondary Energy\|Electricity\|Geothermal | -0.4082 | 15.3420 |
| Secondary Energy\|Electricity\|Hydro | -0.1387 | 0.7377 |
| Secondary Energy\|Electricity\|Nuclear | -1.0000 | 2.0819 |
| Secondary Energy\|Electricity\|Oil | -1.0000 | 3.1086 |
| Secondary Energy\|Electricity\|Solar | -0.1054 | 9.0838 |
| Secondary Energy\|Electricity\|Wind | -0.1557 | 9.0326 |

### Severity Distribution

_Severity = how many bound-widths the growth rate exceeds the limit._

![Plausibility severity](figures/plausibility_severity_dist.png)

### Violation Rate by Scenario Category

| Category | Timesteps | Violations | Violation rate (%) |
| --- | --- | --- | --- |
| C6 | 42883 | 1490 | 3.4700 |
| C4 | 60743 | 2035 | 3.3500 |
| C2 | 48716 | 1603 | 3.2900 |
| C1 | 29697 | 930 | 3.1300 |
| C3 | 123215 | 3839 | 3.1200 |
| C5 | 66880 | 1865 | 2.7900 |
| C7 | 34694 | 906 | 2.6100 |
| C8 | 3097 | 79 | 2.5500 |
| no-climate-assessment | 10070 | 39 | 0.3900 |

### Example Violation

_The most severe violation (highest severity in bound-widths) is shown below._

#### Example violation — predictions

**Most severe violation** (severity = bound-widths outside the allowed range)

| Variable | Units | Scenario | Region | Category | Year | Previous value (EJ/yr) | Current value (EJ/yr) | Growth rate | Lower bound | Upper bound | Direction | Severity (bw) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity\|Geothermal | EJ/yr | EN_INDCi2030_1400_COV | R10INDIA+ | C4 | 2035 | -0.0 | 6.643 | 38613.9578 | -0.4082 | 15.342 | above upper bound | 2450.675 |

#### Example violation — ground truth

**Most severe violation** (severity = bound-widths outside the allowed range)

| Variable | Units | Scenario | Region | Category | Year | Previous value (EJ/yr) | Current value (EJ/yr) | Growth rate | Lower bound | Upper bound | Direction | Severity (bw) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity\|Wind | EJ/yr | EN_INDCi2030_3000f | ETH | C6 | 2050 | -0.0 | 90.0 | 49478023249920.0 | -0.1557 | 9.0326 | above upper bound | 5384918554126.189 |

---

## 3. Regional Consistency

_Checks that predicted World values equal the sum of predicted subregion values
(R5 / R6 / R10 groupings). Only checked for scenarios where a complete grouping
is present. Predictions are **expected to fail** if the model predicts regions
independently of World._

_Regional consistency results not found. Run `regional_consistency.py` first, or skip if your run has no multi-region scenarios._

---

## 4. Physical Bounds Check

_Checks predicted values against hard physical lower bounds (energy variables ≥ 0)
and empirical per-variable bounds derived from the AR6 test-set ground truth._

**Timesteps checked:** 457,691  
**Violations:** 17,041 (3.723%)  
**Fully clean scenario-regions:** 32,149 / 37,696

### Bounds Applied

| Variable | Units | Lower bound | Upper bound |
| --- | --- | --- | --- |
| Primary Energy\|Coal | PJ/yr | 0 | 1.885e+05 |
| Primary Energy\|Gas | PJ/yr | 22.05 | 2.006e+05 |
| Primary Energy\|Oil | PJ/yr | 0.2682 | 2.024e+05 |
| Primary Energy\|Solar | PJ/yr | 4.163 | 1.517e+05 |
| Primary Energy\|Wind | PJ/yr | 4.211 | 1.205e+05 |
| Primary Energy\|Nuclear | PJ/yr | 0 | 5.49e+04 |
| Emissions\|CO2 | Mt CO2/yr | -4362 | 4.188e+04 |
| Emissions\|CH4 | Mt CH4/yr | 0.4528 | 379 |
| Emissions\|N2O | Mt N2O/yr | 16.78 | 1.291e+04 |
| Secondary Energy\|Electricity | EJ/yr | 666.4 | 3.737e+05 |
| Secondary Energy\|Electricity\|Biomass | EJ/yr | 0 | 2.043e+04 |
| Secondary Energy\|Electricity\|Coal | EJ/yr | 0 | 4.069e+04 |
| Secondary Energy\|Electricity\|Gas | EJ/yr | 0 | 3.94e+04 |
| Secondary Energy\|Electricity\|Geothermal | EJ/yr | 0 | 4205 |
| Secondary Energy\|Electricity\|Hydro | EJ/yr | 1.834 | 3.401e+04 |
| Secondary Energy\|Electricity\|Nuclear | EJ/yr | 0 | 5.185e+04 |
| Secondary Energy\|Electricity\|Oil | EJ/yr | 0 | 3919 |
| Secondary Energy\|Electricity\|Solar | EJ/yr | 3.7 | 1.292e+05 |
| Secondary Energy\|Electricity\|Wind | EJ/yr | 3.609 | 1.176e+05 |

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

_The most extreme violation (largest % deviation from the breached bound) is shown below._

#### Example violation — predictions

**Most extreme violation** (largest % deviation from the breached bound)

| Variable | Units | Scenario | Region | Category | Year | Value (PJ/yr) | Bound breached (PJ/yr) | Direction | Lower bound (PJ/yr) | Upper bound (PJ/yr) | Deviation (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Primary Energy\|Oil | PJ/yr | DeepElec_SSP2_def_Budg900 | R10LATIN_AM | C1 | 2070 | -405.891 | 0.268 | below lower bound | 0.268 | 202427.081 | 151417.70 |

#### Example violation — ground truth

**Most extreme violation** (largest % deviation from the breached bound)

| Variable | Units | Scenario | Region | Category | Year | Value (PJ/yr) | Bound breached (PJ/yr) | Direction | Lower bound (PJ/yr) | Upper bound (PJ/yr) | Deviation (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Primary Energy\|Oil | PJ/yr | EN_NPi2020_300f | ZAF | C1 | 2100 | -129.975 | 0.268 | below lower bound | 0.268 | 202427.081 | 48555.28 |

---

## 5. Hard Historical Constraints

_Checks predicted values at the 2020 reference year against the historical anchor
values used in the AR6 scenario vetting process (Nicholls et al. 2022, Table 11).
Each sub-check has an outer tolerance (PASS/FAIL) and an inner IP-range tolerance
(WARN if within outer but outside inner). Sub-checks requiring absent variables are
skipped and listed below. Belongs to the **historical and domain knowledge comparison**
validation family._

| Sub-check | N | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| ch4_2020 | 89 | 88.8000 | 0.0000 | 11.2000 | 88.8000 | 11.2000 |
| co2_change_2010_2020 | 18 | 100.0000 | 0.0000 | 0.0000 | 100.0000 | 0.0000 |
| co2_eip_2020 | 89 | 53.9000 | 40.4000 | 5.6000 | 49.4000 | 6.7000 |
| nuclear_energy_2020 | 89 | 69.7000 | 20.2000 | 10.1000 | 69.7000 | 10.1000 |
| solar_wind_2020 | 89 | 55.1000 | 9.0000 | 36.0000 | 49.4000 | 34.8000 |


_Skipped sub-checks (required variables absent from this run): ccs_2020, primary_energy_2020_


---

## 6. Soft Future Constraints

_Checks predicted values at specific future years against domain-knowledge plausibility
bounds from the AR6 vetting process (Nicholls et al. 2022, Table 11). These were
flagged in AR6 as potentially problematic but not used as hard exclusion criteria.
Warranted here via the constraint-violation argument: the IAMs were themselves vetted
against these criteria. Belongs to the **historical and domain knowledge comparison**
validation family._

| Sub-check | N | Pass (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- |
| ch4_2040 | 120 | 99.2000 | 0.8000 | 99.2000 | 0.8000 |
| co2_not_negative_2030 | 118 | 100.0000 | 0.0000 | 100.0000 | 0.0000 |
| nuclear_electricity_2030 | 118 | 0.0000 | 100.0000 | 0.0000 | 100.0000 |


_Skipped sub-checks (required variables absent from this run): ccs_2030_


<p style="color:red;font-weight:bold">⚠️ nuclear_electricity_2030: ⚠️  POSSIBLE UNIT MISMATCH — median computed value (1.255e+04) is ~1046× higher than the expected reference (12 EJ/yr). Are you sure your units config is correct for Secondary Energy|Electricity|Nuclear?</p>



---

## 7. Inter-variable Correlations

_Pearson r² between all variable pairs at years 2030, 2050, and 2100 — comparing
predictions against AR6 ground truth. A well-calibrated emulator should preserve
the correlations present in real IAM data (e.g. coal consumption and GHG emissions
should remain positively correlated). Methodology follows Li et al. (2025) Fig. 4._

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

_Average absolute difference between predictions and ground truth correlation matrices (off-diagonal pairs only). Lower is better — 0 would mean perfect preservation of inter-variable relationships._

| Year | Mean \|Δr²\| (off-diagonal) |
| --- | --- |
| 2030 | 0.0219 |
| 2050 | 0.0261 |
| 2100 | 0.0350 |
