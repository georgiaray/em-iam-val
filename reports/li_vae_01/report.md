# Validation Report: li_vae_01

**Run ID:** `li_vae_01`
**Generated:** 2026-05-05 14:46
**Results:** `results/li_vae_01/`

---

## Overview

| Check | Key metric | GT available | Status |
| --- | --- | --- | --- |
| Growth rate plausibility | mean pass rate 83.5% | ✓ | nan |
| Hierarchy sum check | mean pass rate 0.0% | ✓ | nan |
| Regional consistency | — | — | not run |
| Physical bounds | pass rate 76.0% | ✓ | nan |
| Hard historical constraints | pass rate 96.7% | ✓ | nan |
| Soft future constraints | pass rate 96.6% | ✓ | nan |
| Inter-variable correlation | mean \|Δr²\| 0.1383 | ✗ | nan |

---

## 1. Growth Rate Plausibility

_Period-on-period growth rates checked against empirically-derived bounds from
the ground truth. Violations indicate trajectories with implausible dynamics._

Period-on-period growth rates checked against empirically-derived bounds from the ground truth data. Violations indicate trajectories with implausible dynamics.

**Predictions:**

| Scenario_Category | Pass_Count | Fail_Count | Pass (%) |
| --- | --- | --- | --- |
| C1234 | 1033478 | 246522 | 80.7000 |
| C56 | 1069506 | 210494 | 83.6000 |
| C78 | 1101829 | 178171 | 86.1000 |

**Ground truth** (different category labelling — shown separately):

| Scenario_Category | Pass_Count | Fail_Count | Pass (%) |
| --- | --- | --- | --- |
| C3 | 50511 | 1360 | 97.4000 |
| C5 | 34892 | 644 | 98.2000 |
| C6 | 15897 | 287 | 98.2000 |
| C7 | 26617 | 381 | 98.6000 |
| C4 | 25988 | 466 | 98.2000 |
| C1 | 14998 | 646 | 95.9000 |
| C2 | 21240 | 785 | 96.4000 |
| C8 | 4461 | 163 | 96.5000 |


---

## 2. Hierarchy Sum Check

_Checks that predicted parent variables equal the sum of their direct children.
The model is expected to fail — the failure rate quantifies how much the
emulator violates IAM accounting identities._

Checks that each parent variable equals the sum of its direct children. The model is expected to fail — the failure rate quantifies how much the emulator violates IAM accounting identities.

**Predictions:** 0 / 270,000 scenario-timesteps pass (0.0%)
**Ground truth:** 8,424 / 11,960 pass (70.4%)


---

## 3. Regional Consistency

_Checks that predicted World values equal the sum of subregion predictions
(R5 / R6 / R10 groupings). Only datasets with regional breakdowns are checked._

_Results not found or no regional groupings present in this dataset._


---

## 4. Physical Bounds Check

_Checks predictions against hard physical lower bounds and empirical bounds
derived from ground truth._

Checks predictions against hard physical lower bounds (energy variables ≥ 0) and empirical per-variable bounds derived from ground truth.

**Predictions:** 3,282,722 / 4,320,000 scenario-variable-timesteps pass (76.0%)
**Ground truth:** 225,028 / 228,266 pass (98.6%)


---

## 5. Hard Historical Constraints

Checks World-level predictions at 2020 against the historical anchor values used in the AR6 scenario vetting process (Nicholls et al. 2022, Table 11). Status: PASS = within IP range, WARN = within outer tolerance, FAIL = outside outer tolerance. Belongs to the **historical and domain knowledge comparison** validation family.

| Sub-check | N | Pass (%) | Warn (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- | --- |
| ccs_2020 | 30000 | 96.7000 | 3.0000 | 0.2000 | 98.2000 | 0.3000 |


_Skipped (required variables absent): co2_eip_2020: ['Emissions|CO2'], ch4_2020: ['Emissions|CH4'], co2_change_2010_2020: ['Emissions|CO2'], primary_energy_2020: ['Primary Energy'], nuclear_energy_2020: ['Primary Energy|Nuclear'], solar_wind_2020: ['Primary Energy|Solar', 'Primary Energy|Wind']_


---

## 6. Soft Future Constraints

Checks World-level predictions at specific future years against domain-knowledge plausibility bounds from the AR6 vetting process (Table 11). Not used as hard exclusion criteria in AR6 but flagged as potentially problematic. Warranted via the constraint-violation argument. Belongs to the **historical and domain knowledge comparison** validation family.

| Sub-check | N | Pass (%) | Fail (%) | GT Pass (%) | GT Fail (%) |
| --- | --- | --- | --- | --- | --- |
| ccs_2030 | 30000 | 95.4000 | 4.6000 | 91.3000 | 8.7000 |
| nuclear_electricity_2030 | 30000 | 97.8000 | 2.2000 | 94.1000 | 5.9000 |


_Skipped (required variables absent): co2_not_negative_2030: ['Emissions|CO2'], ch4_2040: ['Emissions|CH4']_


---

## 7. Inter-variable Correlations

_Pearson r² between all variable pairs at years 2030, 2050, and 2100.
A well-calibrated emulator should preserve the correlation structure of the
parent simulation. Methodology follows Li et al. (2025) Fig. 4._

Pearson r² correlation matrices between all predicted variables at key years, compared against AR6 ground truth. Lower mean |Δr²| indicates better preservation of inter-variable relationships.

| Year | N_variables | Mean_abs_diff_r2 |
| --- | --- | --- |
| 2030.0000 | 16.0000 | 0.1460 |
| 2050.0000 | 16.0000 | 0.1468 |
| 2100.0000 | 16.0000 | 0.1220 |

### 2030

![Inter-variable correlations 2030](figures/correlations_2030.png)

### 2050

![Inter-variable correlations 2050](figures/correlations_2050.png)

### 2100

![Inter-variable correlations 2100](figures/correlations_2100.png)

