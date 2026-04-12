# Closure Signal Ablation Report

**Date:** 2026-04-12
**DB:** `murmur.duckdb` — 2497 scored pairs
**Closure signals:** closure_gap (weight 0.10), orphaned_priv (weight 0.05) — total 0.15

## Method

- **Baseline:** current FUSION_WEIGHTS (closure_gap=0.10, orphaned_priv=0.05)
- **Ablation A (zero):** closure weights set to 0, remaining 8 signals renormalized to sum=1.0
- **Ablation B (redistribute):** closure weight (0.15) redistributed proportionally across remaining signals

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

- **closure_gap > 0** in 44/2497 pairs (1.8%)
- **orphaned_priv > 0** in 25/2497 pairs (1.0%)
- **closure_gap mean:** 0.0079, max: 1.0000
- **orphaned_priv mean:** 0.0048, max: 0.6029

## Results

### Fusion score distribution

| Metric | Baseline | Zero | Redistribute |
|--------|----------|------|--------------|
| Mean   | 0.038836 | 0.044470 | 0.044470 |
| Median | 0.002439 | 0.002861 | 0.002861 |
| Std    | 0.085000 | 0.098385 | 0.098385 |
| Max    | 0.784741 | 0.923225 | 0.923225 |

### Delta statistics (absolute)

| Metric | Zero | Redistribute |
|--------|------|--------------|
| Mean   | 0.007152 | 0.007152 |
| Median | 0.000430 | 0.000430 |
| Std    | 0.015149 | 0.015149 |
| Max    | 0.138484 | 0.138484 |

### Tier migrations

**Zero ablation** (38 pairs changed tier):

| From \ To | NORMAL | WATCH | MEDIUM | HIGH |
|---|---|---|---|---|
| NORMAL | 2044 | 4 | . | . |
| WATCH | 30 | 410 | 3 | . |
| MEDIUM | . | . | 5 | 1 |
| HIGH | . | . | . | . |

**Redistribute ablation** (38 pairs changed tier):

| From \ To | NORMAL | WATCH | MEDIUM | HIGH |
|---|---|---|---|---|
| NORMAL | 2044 | 4 | . | . |
| WATCH | 30 | 410 | 3 | . |
| MEDIUM | . | . | 5 | 1 |
| HIGH | . | . | . | . |

### Top 10 most-affected pairs (zero ablation)

| Window | Actor | Baseline | Ablated | Delta | Tier | Top 3 signals |
|--------|-------|----------|---------|-------|------|---------------|
| 2026-03-28 03:30 | maintenance-sa@project-1f4f13c | 0.7847 | 0.9232 | +0.1385 | MEDIUM→HIGH | novelty_score=0.300, inv_score=0.170, bridge_new=0.130 |
| 2026-04-03 21:15 | normal-worker-sa@project-1f4f1 | 0.6465 | 0.7606 | +0.1141 | MEDIUM | novelty_score=0.255, inv_score=0.170, bridge_new=0.104 |
| 2026-04-03 21:15 | attacker-sa@project-1f4f13c5-9 | 0.4965 | 0.5841 | +0.0876 | WATCH→MEDIUM | inv_score=0.170, novelty_score=0.105, bridge_new=0.104 |
| 2026-03-26 19:45 | normal-worker-sa@project-1f4f1 | 0.4724 | 0.5558 | +0.0834 | WATCH→MEDIUM | novelty_score=0.210, inv_score=0.170, bridge_new=0.052 |
| 2026-03-25 01:15 | samreen654@gmail.com | 0.0686 | 0.0022 | -0.0663 | WATCH→NORMAL | closure_gap=0.067, sigma_coarse=0.002, inv_score=0.000 |
| 2026-03-25 18:30 | samreen654@gmail.com | 0.0686 | 0.0022 | -0.0663 | WATCH→NORMAL | closure_gap=0.067, sigma_coarse=0.002, inv_score=0.000 |
| 2026-03-25 18:45 | samreen654@gmail.com | 0.0686 | 0.0022 | -0.0663 | WATCH→NORMAL | closure_gap=0.067, sigma_coarse=0.002, inv_score=0.000 |
| 2026-03-25 19:00 | samreen654@gmail.com | 0.0686 | 0.0022 | -0.0663 | WATCH→NORMAL | closure_gap=0.067, sigma_coarse=0.002, inv_score=0.000 |
| 2026-03-26 17:45 | samreen654@gmail.com | 0.0686 | 0.0022 | -0.0663 | WATCH→NORMAL | closure_gap=0.067, sigma_coarse=0.002, inv_score=0.000 |
| 2026-03-26 20:00 | samreen654@gmail.com | 0.0688 | 0.0026 | -0.0663 | WATCH→NORMAL | closure_gap=0.067, sigma_coarse=0.002, inv_score=0.000 |

## Interpretation

### Does closure add independent detection value?

If zero and redistribute produce **similar** deltas, the effect is purely from weight redistribution
(other signals absorb the freed weight). If zero produces **larger** deltas or different tier migrations,
closure carries independent signal.

- Zero ablation mean delta: 0.007152
- Redistribute mean delta: 0.007152
- Ratio: 1.00x (>1 means closure has independent value)

### Tier stability

- Zero: 38/2497 pairs changed tier (1.5%)
- Redistribute: 38/2497 pairs changed tier (1.5%)

## Conclusion

Closure signal impact is primarily from weight redistribution.

**Signal activity:** closure_gap is active in 1.8% of pairs, orphaned_priv in 1.0%.
Low activity means the signal hasn't had enough data to exercise closure patterns — the ablation may not be representative of steady-state behavior.

**Recommendation:** Review the tier migration tables and top-10 affected pairs to determine if the pairs
that change tier are ones where closure *should* matter (attack scenarios with unclosed privilege grants)
vs. ones where it's noise.
