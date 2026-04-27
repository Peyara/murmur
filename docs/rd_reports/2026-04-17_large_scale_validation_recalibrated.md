# Large-Scale Validation Report

Generated: 2026-04-17 16:33

## Summary

- **Total runs:** 900
- **Total events processed:** 212,224
- **Mean gap:** 52.2% (std: 40.4%)
- **Median gap:** 48.8%
- **Worst gap (min discrimination):** -34.8%
- **Best gap (max discrimination):** 209.9%
- **Mean FP rate:** 0.119
- **Mean FN rate:** 0.674

## Parameter Sensitivity

### By Actor Count

| Actors | Mean Gap (%) |
|--------|-------------|
| 10 | 24.3 |
| 20 | 56.5 |
| 30 | 75.8 |

### By Attack Ratio

| Attack Ratio | Mean Gap (%) |
|-------------|-------------|
| 0.1 | 36.7 |
| 0.2 | 53.8 |
| 0.3 | 66.0 |

## Signal Reliability

Fraction of runs where each signal fires (activation > 0).

| Signal | Reliability | Mean Activation |
|--------|------------|-----------------|
| bridge_new | 1.00 | 0.839 |
| closure_gap | 1.00 | 0.254 |
| inv_score | 1.00 | 0.498 |
| novelty_score | 1.00 | 0.285 |
| orphaned_priv | 1.00 | 0.042 |
| trigger_resolved | 1.00 | 0.153 |
