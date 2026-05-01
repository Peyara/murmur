# Sprint 2 — Baseline Embedding & Threshold Recalibration (run output)

Generated: 2026-04-30 21:51

Grid trajectories (in baseline): **50**  |  Edge cases (in baseline): **5**

Current thresholds (residual_risk): WATCH ≥ 0.20, MEDIUM ≥ 0.34, HIGH ≥ 0.45

Recalibrated: WATCH ≥ 0.428, MEDIUM ≥ 0.494, HIGH ≥ 0.636  _(source: grid_p75=0.428, benign_p95=0.375)_

## Gate Summary

- **Detection rate (current thresholds, attack-in-benign):** 92.0%
- **Detection rate (recalibrated thresholds, attack-in-benign):** 30.0%
- **Blind-spot count (current):** 4
- **Blind-spot count (recalibrated):** 35
- **Benign FP floor (P95 residual_risk on benign-only run):** 0.375  _(WATCH bound: 0.375)_

## Detection Rate by Parameter (attack-in-benign + recalibrated)


### By speed

| speed | n | detection rate |
|---|---|---|
| fast | — | 33.3% |
| medium | — | 33.3% |
| slow | — | 23.5% |

### By spread

| spread | n | detection rate |
|---|---|---|
| multi_actor | — | 8.7% |
| single_actor | — | 48.1% |

### By zone_path

| zone_path | n | detection rate |
|---|---|---|
| direct | — | 11.1% |
| full_chain | — | 58.8% |
| indirect | — | 20.0% |

### By evasion

| evasion | n | detection rate |
|---|---|---|
| none | — | 11.1% |
| pattern_mimicry | — | 30.8% |
| split_actions | — | 20.0% |
| timing_jitter | — | 53.8% |

### By closure

| closure | n | detection rate |
|---|---|---|
| full | — | 20.0% |
| none | — | 22.2% |
| partial | — | 58.3% |

### By objective

| objective | n | detection rate |
|---|---|---|
| compute_persist | — | 25.0% |
| data_exfil | — | 28.6% |
| key_exfil | — | 30.8% |
| secret_access | — | 33.3% |

## Signal Fire Rate (attack-in-benign)

| Signal | Fire rate | Mean max activation | Benign-only fire rate |
|--------|-----------|---------------------|------------------------|
| inv_score | 96.0% | 4.740 | 44.6% |
| novelty_score | 40.0% | 1.210 | 32.2% |
| sigma_coarse | 0.0% | 0.000 | 5.0% |
| bridge_new | 100.0% | 3.560 | 81.0% |
| delta_f | 0.0% | 0.000 | 5.0% |
| closure_gap | 100.0% | 1.000 | 30.6% |
| orphaned_priv | 0.0% | 0.000 | 8.3% |

## Benign-Only Residual Distribution

- n=(121 (window, actor) pairs)
- P50: 0.157
- P75: 0.289
- P90: 0.349
- P95: 0.375
- P99: 0.597
- max: 0.696

## Prediction Divergence

| Signal | Predicted+Fired | Predicted+Silent | Unpredicted+Fired | Unpredicted+Silent |
|--------|------------------|-------------------|--------------------|---------------------|
| inv_score | 48 | 2 | 0 | 0 |
| novelty_score | 20 | 30 | 0 | 0 |
| sigma_coarse | 0 | 10 | 0 | 40 |
| bridge_new | 35 | 0 | 15 | 0 |
| delta_f | 0 | 10 | 0 | 40 |
| closure_gap | 30 | 0 | 20 | 0 |
| orphaned_priv | 0 | 10 | 0 | 40 |

## Blind Spots — Trajectories Not Detected (recalibrated)

| Label | speed | spread | zone_path | evasion | closure | objective | residual_risk_max |
|-------|-------|--------|-----------|---------|---------|-----------|--------------------|
| grid:0 | slow | multi_actor | direct | none | full | data_exfil | 0.324 |
| grid:1 | slow | multi_actor | direct | timing_jitter | none | compute_persist | 0.324 |
| grid:2 | slow | single_actor | direct | pattern_mimicry | full | compute_persist | 0.380 |
| grid:3 | slow | single_actor | full_chain | split_actions | full | secret_access | 0.389 |
| grid:4 | medium | multi_actor | indirect | none | full | compute_persist | 0.324 |
| grid:5 | medium | multi_actor | direct | timing_jitter | full | key_exfil | 0.324 |
| grid:6 | medium | multi_actor | direct | pattern_mimicry | full | compute_persist | 0.128 |
| grid:7 | medium | single_actor | full_chain | split_actions | partial | secret_access | 0.355 |
| grid:8 | fast | multi_actor | direct | none | full | data_exfil | 0.128 |
| grid:10 | fast | multi_actor | indirect | pattern_mimicry | partial | key_exfil | 0.177 |
| grid:11 | fast | single_actor | indirect | split_actions | none | key_exfil | 0.381 |
| grid:12 | medium | multi_actor | direct | split_actions | none | compute_persist | 0.415 |
| grid:14 | slow | multi_actor | full_chain | pattern_mimicry | none | key_exfil | 0.324 |
| grid:15 | fast | multi_actor | full_chain | pattern_mimicry | none | secret_access | 0.177 |
| grid:17 | slow | single_actor | indirect | split_actions | full | compute_persist | 0.415 |
| grid:19 | fast | multi_actor | direct | pattern_mimicry | none | data_exfil | 0.324 |
| grid:20 | slow | multi_actor | full_chain | none | full | compute_persist | 0.415 |
| grid:21 | medium | multi_actor | indirect | pattern_mimicry | partial | data_exfil | 0.324 |
| grid:23 | medium | multi_actor | full_chain | pattern_mimicry | none | compute_persist | 0.410 |
| grid:26 | fast | multi_actor | indirect | timing_jitter | none | key_exfil | 0.423 |
| grid:28 | fast | single_actor | direct | split_actions | none | key_exfil | 0.324 |
| grid:29 | medium | single_actor | direct | timing_jitter | partial | key_exfil | 0.423 |
| grid:31 | medium | multi_actor | indirect | split_actions | none | secret_access | 0.324 |
| grid:34 | medium | single_actor | indirect | split_actions | none | secret_access | 0.389 |
| grid:35 | medium | single_actor | direct | none | full | key_exfil | 0.397 |
| grid:36 | slow | multi_actor | indirect | timing_jitter | full | secret_access | 0.324 |
| grid:39 | fast | multi_actor | direct | split_actions | none | secret_access | 0.315 |
| grid:40 | slow | single_actor | indirect | none | none | key_exfil | 0.410 |
| grid:43 | slow | multi_actor | full_chain | timing_jitter | full | secret_access | 0.324 |
| grid:44 | slow | single_actor | direct | none | full | secret_access | 0.410 |

_(... 5 more blind spots truncated)_

## Edge Cases (attack-in-benign)

| Label | residual_risk_max | tier (current) | tier (recal) | n_events | signals fired |
|-------|--------------------|-----------------|---------------|----------|----------------|
| edge:slow_ratchet | 0.428 | MEDIUM | WATCH | 5 | inv_score,bridge_new,closure_gap |
| edge:multi_actor_convergence | 0.324 | WATCH | NORMAL | 3 | inv_score,bridge_new,closure_gap |
| edge:exfil_avoiding | 0.507 | HIGH | MEDIUM | 3 | inv_score,novelty_score,bridge_new,closure_gap |
| edge:perfect_mimicry | 0.440 | MEDIUM | WATCH | 3 | inv_score,novelty_score,bridge_new,closure_gap |
| edge:minimal_direct | 0.410 | MEDIUM | NORMAL | 2 | inv_score,novelty_score,bridge_new,closure_gap |

## Provisional Gate Verdict (recalibrated): **FAIL**
