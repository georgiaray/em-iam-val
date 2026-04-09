# Li et al. Validation — VAE (li_vae_01)

**Run ID:** `li_vae_01`
**Generated:** 2026-04-09 15:52
**Results path:** `results/xgb/li_vae_01/`

---

## Overview

| Check | Metric | Predictions | Ground Truth |
| --- | --- | --- | --- |
| Hierarchy Sum Check | Scenario-region pass rate | 0.0% | 29.5% |
|  | Mean relative error | 1979.419% | 26.303% |
| Growth Rate Plausibility | Timestep violation rate | 2.0% | 1.9% |
| Physical Bounds Check | Timestep violation rate | 2.00% | 1.72% |

---

## 1. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children
at every timestep. Predictions are **expected to fail** this check — the failure
rate quantifies how much the model violates the sum constraint. Compare to the
ground truth pass rate to understand baseline data consistency._

### Pass Rates by Parent Variable

| Parent Variable | Scenario-regions | Pass rate (%) | Mean error (%) | Max error (%) |
| --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity | 30000 | 0.0000 | 1979.4190 | 48874.3009 |

### Error Distribution

![Sum check error distribution](figures/sum_check_error_dist.png)

### Mean Error by Year

![Sum check error by year](figures/sum_check_error_by_year.png)

### Error Percentile Comparison — Predictions vs Ground Truth

| Percentile | Predictions (%) | Ground truth (%) |
| --- | --- | --- |
| p50 | 1456.6875 | 15.9965 |
| p75 | 2146.2802 | 43.3961 |
| p90 | 3833.5010 | 54.7023 |
| p95 | 5538.8209 | 60.3917 |
| p99 | 8133.2140 | 65.0777 |

### Example Failure

_The median failing scenario (by mean error) is shown below to illustrate a typical hierarchy violation._

#### Example failure — predictions

**Scenario:** VAE | gen_03379 | World | C1234  
**Parent variable:** Secondary Energy|Electricity  
**Mean error:** 1456.81%  (median failing scenario)

| Year | Parent value | Sum of children | Difference | Error (%) |
| --- | --- | --- | --- | --- |
| 2020.0 | 2.525 | 187.912 | -185.387 | 7341.11 |
| 2030.0 | 9.094 | 213.977 | -204.883 | 2252.97 |
| 2040.0 | 26.088 | 257.249 | -231.161 | 886.09 |
| 2050.0 | 46.829 | 331.08 | -284.252 | 607.01 |
| 2060.0 | 67.985 | 420.165 | -352.18 | 518.03 |
| 2070.0 | 101.82 | 564.521 | -462.7 | 454.43 |
| 2080.0 | 146.3 | 716.311 | -570.011 | 389.62 |
| 2090.0 | 197.342 | 864.468 | -667.126 | 338.05 |
| 2100.0 | 220.682 | 935.611 | -714.93 | 323.96 |

#### Example failure — ground truth

**Scenario:** COFFEE 1.1 | EN_NPi2020_1800f | World | C5  
**Parent variable:** Primary Energy  
**Mean error:** 35.06%  (median failing scenario)

| Year | Parent value | Sum of children | Difference | Error (%) |
| --- | --- | --- | --- | --- |
| 2010.0 | 489.143 | 417.293 | 71.85 | 14.69 |
| 2020.0 | 546.316 | 462.767 | 83.549 | 15.29 |
| 2030.0 | 565.654 | 507.196 | 58.458 | 10.33 |
| 2040.0 | 605.474 | 519.901 | 85.574 | 14.13 |
| 2050.0 | 641.068 | 509.227 | 131.841 | 20.57 |
| 2060.0 | 685.043 | 479.318 | 205.725 | 30.03 |
| 2070.0 | 755.438 | 455.189 | 300.248 | 39.74 |
| 2080.0 | 844.417 | 363.234 | 481.183 | 56.98 |
| 2090.0 | 921.917 | 255.004 | 666.913 | 72.34 |
| 2100.0 | 975.388 | 229.295 | 746.093 | 76.49 |

---

## 2. Growth Rate Plausibility

_For each predicted trajectory, checks that the 5-year period-on-period growth rate
falls within the 1st–99th percentile range observed in the AR6 test-set ground truth.
Empirical bounds are derived per variable._

**Total timesteps evaluated:** 3,840,000  
**Violations:** 76,800 (2.00%)  
**Median severity** (violations only): 0.060 bound-widths  

**Ground truth — violation rate:** 1.94%  
**Ground truth — median severity:** 0.067 bound-widths  
_(+0.06pp difference: predictions vs ground truth)_

### Violation Rate by Variable

![Plausibility violations by variable](figures/plausibility_violations_by_variable.png)

### Empirical Bounds Used (AR6 test-set percentiles)

| Variable | Lower bound | Upper bound |
| --- | --- | --- |
| Carbon Sequestration\|CCS | -0.5850 | 29.2822 |
| Emissions\|Kyoto Gases | -2.9730 | 0.2174 |
| Final Energy\|Liquids | -0.3624 | 0.2336 |
| Primary Energy\|Coal | -0.5697 | 0.2189 |
| Primary Energy\|Gas | -0.8223 | 0.5690 |
| Primary Energy\|Oil | -0.3716 | 0.3893 |
| Secondary Energy\|Electricity | -0.0725 | 6.0635 |
| Secondary Energy\|Electricity\|Biomass | -0.4991 | 1.9926 |
| Secondary Energy\|Electricity\|Coal | -0.0732 | 0.4337 |
| Secondary Energy\|Electricity\|Gas | -0.4507 | 2.9002 |
| Secondary Energy\|Electricity\|Geothermal | -0.0073 | 0.5259 |
| Secondary Energy\|Electricity\|Hydro | -0.9614 | 5.1969 |
| Secondary Energy\|Electricity\|Nuclear | -0.4553 | 1.2345 |
| Secondary Energy\|Electricity\|Oil | -0.0449 | 3.0933 |
| Secondary Energy\|Electricity\|Solar | -0.9358 | 1.4531 |
| Secondary Energy\|Electricity\|Wind | -0.7247 | 0.7271 |

### Severity Distribution

_Severity = how many bound-widths the growth rate exceeds the limit._

![Plausibility severity](figures/plausibility_severity_dist.png)

### Violation Rate by Scenario Category

| Category | Timesteps | Violations | Violation rate (%) |
| --- | --- | --- | --- |
| C1234 | 1280000 | 41641 | 3.2500 |
| C78 | 1280000 | 21687 | 1.6900 |
| C56 | 1280000 | 13472 | 1.0500 |

### Example Violation

_The most severe violation (highest severity in bound-widths) is shown below._

#### Example violation — predictions

**Most severe violation** (severity = bound-widths outside the allowed range)

| Variable | Scenario | Region | Category | Year | Previous value | Current value | Growth rate | Lower bound | Upper bound | Direction | Severity (bw) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Emissions\|Kyoto Gases | gen_00821 | World | C1234 | 2100 | 0.041 | -2004.938 | -48883.2857 | -2.973 | 0.2174 | below lower bound | 15321.179 |

#### Example violation — ground truth

**Most severe violation** (severity = bound-widths outside the allowed range)

| Variable | Scenario | Region | Category | Year | Previous value | Current value | Growth rate | Lower bound | Upper bound | Direction | Severity (bw) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity | EN_NPi2020_800 | World | C3 | 2020 | 0.0 | 0.05 | 82458089.2752 | -0.0252 | 0.5641 | above upper bound | 139918689.859 |

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

**Timesteps checked:** 4,320,000  
**Violations:** 86,400 (2.000%)  
**Fully clean scenario-regions:** 438,789 / 480,000

### Bounds Applied

| Variable | Lower bound | Upper bound |
| --- | --- | --- |
| Carbon Sequestration\|CCS | 3.378 | 2.733e+04 |
| Final Energy\|Liquids | 42.26 | 327.5 |
| Primary Energy\|Gas | 0.6339 | 492.3 |
| Primary Energy\|Oil | 31.26 | 367.1 |
| Primary Energy\|Coal | 5.235 | 311.5 |
| Secondary Energy\|Electricity\|Nuclear | 1.532 | 129.6 |
| Secondary Energy\|Electricity\|Hydro | 7.815e-05 | 8.625 |
| Secondary Energy\|Electricity | 1.436 | 331.6 |
| Secondary Energy\|Electricity\|Oil | 4.761 | 232.8 |
| Secondary Energy\|Electricity\|Coal | 12.26 | 54.3 |
| Secondary Energy\|Electricity\|Gas | 0.02859 | 6.425 |
| Secondary Energy\|Electricity\|Wind | 0.5396 | 121 |
| Secondary Energy\|Electricity\|Solar | 0.008665 | 102.8 |
| Secondary Energy\|Electricity\|Biomass | 0.1094 | 48.41 |
| Secondary Energy\|Electricity\|Geothermal | 94.1 | 595.8 |
| Emissions\|Kyoto Gases | -8461 | 1.052e+05 |

### Violations by Variable

![Bounds violations by variable](figures/bounds_violations_by_variable.png)

### Predictions vs Ground Truth

| Source | Timesteps | Violations | Violation rate |
| --- | --- | --- | --- |
| Predictions | 4,320,000 | 86,400 | 2.000% |
| Ground truth | 228,266 | 3,936 | 1.724% |

_Predictions show +0.276 pp more violations than ground truth._

### Violation Rate by Variable — Predictions vs Ground Truth

![Bounds violation rate pred vs GT](figures/bounds_violation_rate_pred_vs_gt.png)

### Example Violation

_The most extreme violation (largest % deviation from the breached bound) is shown below._

#### Example violation — predictions

**Most extreme violation** (largest % deviation from the breached bound)

| Variable | Scenario | Region | Category | Year | Value | Bound breached | Direction | Lower bound | Upper bound | Deviation (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Secondary Energy\|Electricity\|Hydro | gen_18935 | World | C56 | 2090 | 0.0 | 0.0 | below lower bound | 0.0 | 8.625 | 100.0 |

#### Example violation — ground truth

**Most extreme violation** (largest % deviation from the breached bound)

| Variable | Scenario | Region | Category | Year | Value | Bound breached | Direction | Lower bound | Upper bound | Deviation (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Primary Energy\|Oil | EN_INDCi2030_1000 | World | C3 | 2010 | 1302.528 | 361.722 | above upper bound | 1.544 | 361.722 | 260.09 |
