# Closure Signal Ablation Report

**Date:** 2026-04-14
**DB:** `data/synth_test.duckdb` — 732 scored pairs
**Closure signals:** closure_gap (weight 0.10), orphaned_priv (weight 0.05) — total 0.15

## Method

- **Baseline:** current FUSION_WEIGHTS (closure_gap=0.10, orphaned_priv=0.05)
- **Ablation A (zero):** closure weights set to 0, renormalized to sum=1.0
- **Ablation B (redistribute):** closure weight redistributed proportionally

Weights after ablation:

| Signal | Baseline | Zero | Redistribute |
|--------|----------|------|--------------|
| inv_score | 0.17 | 0.2000 | 0.2000 |
| inv_count | 0.13 | 0.1529 | 0.1529 |
| novelty_score | 0.30 | 0.3529 | 0.3529 |
| sigma_coarse | 0.04 | 0.0471 | 0.0471 |
| bridge_new | 0.13 | 0.1529 | 0.1529 |
| delta_f | 0.08 | 0.0941 | 0.0941 |
| closure_gap | 0.10 | 0.0000 | 0.0000 |
| orphaned_priv | 0.05 | 0.0000 | 0.0000 |

## Closure Signal Activity

Before interpreting ablation, check if closure signals are even active:

- **closure_gap > 0** in 125/732 pairs (17.1%)
- **orphaned_priv > 0** in 79/732 pairs (10.8%)
- **closure_gap mean:** 0.1498, max: 1.0000
- **orphaned_priv mean:** 0.0181, max: 0.2867

## Results

### Fusion score distribution

| Metric | Baseline | Zero | Redistribute |
|--------|----------|------|--------------|
| Mean   | 0.122481 | 0.125405 | 0.125405 |
| Median | 0.079897 | 0.063408 | 0.063408 |
| Std    | 0.116122 | 0.128098 | 0.128098 |
| Max    | 0.623229 | 0.685761 | 0.685761 |

### Delta statistics (absolute)

| Metric | Zero | Redistribute |
|--------|------|--------------|
| Mean   | 0.027693 | 0.027693 |
| Median | 0.014099 | 0.014099 |
| Std    | 0.029699 | 0.029699 |
| Max    | 0.110392 | 0.110392 |

### Tier migrations

**Zero ablation** (26 pairs changed tier):

| From \ To | NORMAL | WATCH | MEDIUM | HIGH |
|---|---|---|---|---|
| NORMAL | 109 | . | . | . |
| WATCH | 24 | 594 | 2 | . |
| MEDIUM | . | . | 3 | . |
| HIGH | . | . | . | . |

**Redistribute ablation** (26 pairs changed tier):

| From \ To | NORMAL | WATCH | MEDIUM | HIGH |
|---|---|---|---|---|
| NORMAL | 109 | . | . | . |
| WATCH | 24 | 594 | 2 | . |
| MEDIUM | . | . | 3 | . |
| HIGH | . | . | . | . |

### Top 10 most-affected pairs (zero ablation)

| Window | Actor | Baseline | Ablated | Delta | Tier | Top 3 signals |
|--------|-------|----------|---------|-------|------|---------------|
| 2026-01-16 00:00 | worker-sa-15@synth-project.iam | 0.1126 | 0.0022 | -0.1104 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.011, sigma_coarse=0.002 |
| 2026-01-15 23:00 | worker-sa-15@synth-project.iam | 0.1124 | 0.0022 | -0.1102 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.011, sigma_coarse=0.002 |
| 2026-01-15 22:30 | worker-sa-15@synth-project.iam | 0.1123 | 0.0022 | -0.1101 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.010, sigma_coarse=0.002 |
| 2026-01-15 17:30 | worker-sa-15@synth-project.iam | 0.1112 | 0.0022 | -0.1090 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.009, sigma_coarse=0.002 |
| 2026-01-15 16:45 | worker-sa-15@synth-project.iam | 0.1111 | 0.0022 | -0.1088 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.009, sigma_coarse=0.002 |
| 2026-01-15 20:00 | worker-sa-4@synth-project.iam. | 0.1105 | 0.0022 | -0.1082 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.009, sigma_coarse=0.002 |
| 2026-01-15 15:00 | worker-sa-4@synth-project.iam. | 0.1096 | 0.0022 | -0.1074 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.008, sigma_coarse=0.002 |
| 2026-01-15 11:45 | worker-sa-15@synth-project.iam | 0.1095 | 0.0022 | -0.1073 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.008, sigma_coarse=0.002 |
| 2026-01-15 20:15 | worker-sa-4@synth-project.iam. | 0.1166 | 0.0094 | -0.1072 | WATCH | closure_gap=0.100, orphaned_priv=0.009, delta_f=0.005 |
| 2026-01-15 11:30 | worker-sa-15@synth-project.iam | 0.1094 | 0.0022 | -0.1072 | WATCH→NORMAL | closure_gap=0.100, orphaned_priv=0.008, sigma_coarse=0.002 |

## Interpretation

### Does closure add independent detection value?

If zero and redistribute produce **similar** deltas, the effect is purely
from weight redistribution. If zero produces **larger** deltas or different
tier migrations, closure carries independent signal.

- Zero ablation mean delta: 0.027693
- Redistribute mean delta: 0.027693
- Ratio: 1.00x (>1 means closure has independent value)

### Tier stability

- Zero: 26/732 pairs changed tier (3.6%)
- Redistribute: 26/732 changed (3.6%)

## Conclusion

Closure signal impact is primarily from weight redistribution.

**Signal activity:** closure_gap active in 17.1% of pairs, orphaned_priv in 10.8%.
Low activity means the signal hasn't had enough data to exercise closure patterns — the ablation may not be representative of steady-state behavior.

**Recommendation:** Review the tier migration tables and top-10 affected
pairs to determine if the pairs that change tier are ones where closure
*should* matter (attack scenarios with unclosed privilege grants)
vs. ones where it's noise.

## Role-Based Analysis

### Fusion score by role

| Role | Count | Baseline Mean | Zero Mean | Redist Mean | Baseline Std |
|------|-------|---------------|-----------|-------------|--------------|
| attacker | 99 | 0.1856 | 0.1649 | 0.1649 | 0.1449 |
| admin | 30 | 0.1191 | 0.1401 | 0.1401 | 0.0995 |
| scheduler | 40 | 0.1164 | 0.1370 | 0.1370 | 0.0973 |
| deployer | 30 | 0.1137 | 0.1337 | 0.1337 | 0.1013 |
| worker | 533 | 0.1119 | 0.1159 | 0.1159 | 0.1096 |

### Attacker vs Worker Gap

Gap = attacker_mean / worker_mean. A gap of 1.70 means attackers average 70% higher fusion scores.

| Scenario | Gap (ratio) | Change from Baseline | % of Gap |
|----------|-------------|----------------------|----------|
| Baseline | 1.659 (+65.9%) | — | — |
| Zero ablation | 1.423 (+42.3%) | -23.5pp | -35.7% |
| Redistribute | 1.423 (+42.3%) | -23.5pp | -35.7% |

### Closure Signal Activation by Role

| Role | Count | Closure Gap Active | Orphaned Priv Active |
|------|-------|--------------------|----------------------|
| attacker | 99 | 58.6% | 21.2% |
| admin | 30 | 0.0% | 0.0% |
| scheduler | 40 | 0.0% | 0.0% |
| deployer | 30 | 0.0% | 0.0% |
| worker | 533 | 12.6% | 10.9% |

### Tier Stability by Role (Zero Ablation)

| Role | Count | Tier Changes | % Changed |
|------|-------|--------------|-----------|
| attacker | 99 | 9 | 9.1% |
| admin | 30 | 0 | 0.0% |
| scheduler | 40 | 0 | 0.0% |
| deployer | 30 | 0 | 0.0% |
| worker | 533 | 17 | 3.2% |
