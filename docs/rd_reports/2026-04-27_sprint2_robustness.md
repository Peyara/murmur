# Sprint 2 — Attack-Strategy Robustness Report

Generated: 2026-04-27 21:45

Grid trajectories: **50**  |  Edge cases: **5**
Thresholds (residual_risk): HIGH ≥ 0.45, MEDIUM ≥ 0.34, WATCH ≥ 0.20 (scaled from settings.py [0,10] config).

## Gate Summary

- **Overall detection rate:** 40.0%
- **Blind-spot count (residual_risk < WATCH):** 30
- **Provisional gate verdict:** FAIL

## Detection Rate by Parameter


### By speed

| speed | n | detection rate |
|---|---|---|
| fast | — | 40.0% |
| medium | — | 44.4% |
| slow | — | 35.3% |

### By spread

| spread | n | detection rate |
|---|---|---|
| multi_actor | — | 8.7% |
| single_actor | — | 66.7% |

### By zone_path

| zone_path | n | detection rate |
|---|---|---|
| direct | — | 38.9% |
| full_chain | — | 47.1% |
| indirect | — | 33.3% |

### By evasion

| evasion | n | detection rate |
|---|---|---|
| none | — | 44.4% |
| pattern_mimicry | — | 53.8% |
| split_actions | — | 0.0% |
| timing_jitter | — | 69.2% |

### By closure

| closure | n | detection rate |
|---|---|---|
| full | — | 35.0% |
| none | — | 33.3% |
| partial | — | 58.3% |

### By objective

| objective | n | detection rate |
|---|---|---|
| compute_persist | — | 41.7% |
| data_exfil | — | 28.6% |
| key_exfil | — | 46.2% |
| secret_access | — | 38.9% |

## Signal Fire Rate (across grid)

| Signal | Fire rate | Mean max activation |
|--------|-----------|---------------------|
| inv_score | 96.0% | 4.740 |
| novelty_score | 40.0% | 1.210 |
| sigma_coarse | 0.0% | 0.000 |
| bridge_new | 40.0% | 0.720 |
| delta_f | 0.0% | 0.000 |
| closure_gap | 0.0% | 0.000 |
| orphaned_priv | 0.0% | 0.000 |

## Prediction Divergence (confirmation-bias guard)

Per signal: how predictions in `expected_signals` lined up with what fired. Divergence is the finding — predictions were committed before observation.

| Signal | Predicted+Fired | Predicted+Silent | Unpredicted+Fired | Unpredicted+Silent |
|--------|------------------|-------------------|--------------------|---------------------|
| inv_score | 48 | 2 | 0 | 0 |
| novelty_score | 20 | 30 | 0 | 0 |
| sigma_coarse | 0 | 10 | 0 | 40 |
| bridge_new | 20 | 15 | 0 | 15 |
| delta_f | 0 | 10 | 0 | 40 |
| closure_gap | 0 | 30 | 0 | 20 |
| orphaned_priv | 0 | 10 | 0 | 40 |

## Blind Spots — Trajectories Not Detected

| Label | speed | spread | zone_path | evasion | closure | objective | residual_risk_max |
|-------|-------|--------|-----------|---------|---------|-----------|--------------------|
| grid:1 | slow | multi_actor | direct | timing_jitter | none | compute_persist | 0.198 |
| grid:0 | slow | multi_actor | direct | none | full | data_exfil | 0.198 |
| grid:3 | slow | single_actor | full_chain | split_actions | full | secret_access | 0.185 |
| grid:5 | medium | multi_actor | direct | timing_jitter | full | key_exfil | 0.198 |
| grid:4 | medium | multi_actor | indirect | none | full | compute_persist | 0.198 |
| grid:6 | medium | multi_actor | direct | pattern_mimicry | full | compute_persist | 0.002 |
| grid:7 | medium | single_actor | full_chain | split_actions | partial | secret_access | 0.185 |
| grid:8 | fast | multi_actor | direct | none | full | data_exfil | 0.002 |
| grid:10 | fast | multi_actor | indirect | pattern_mimicry | partial | key_exfil | 0.151 |
| grid:12 | medium | multi_actor | direct | split_actions | none | compute_persist | 0.185 |
| grid:11 | fast | single_actor | indirect | split_actions | none | key_exfil | 0.151 |
| grid:15 | fast | multi_actor | full_chain | pattern_mimicry | none | secret_access | 0.151 |
| grid:14 | slow | multi_actor | full_chain | pattern_mimicry | none | key_exfil | 0.198 |
| grid:17 | slow | single_actor | indirect | split_actions | full | compute_persist | 0.198 |
| grid:19 | fast | multi_actor | direct | pattern_mimicry | none | data_exfil | 0.198 |
| grid:20 | slow | multi_actor | full_chain | none | full | compute_persist | 0.185 |
| grid:21 | medium | multi_actor | indirect | pattern_mimicry | partial | data_exfil | 0.198 |
| grid:18 | medium | multi_actor | full_chain | split_actions | full | key_exfil | 0.198 |
| grid:25 | slow | multi_actor | full_chain | split_actions | partial | compute_persist | 0.198 |
| grid:28 | fast | single_actor | direct | split_actions | none | key_exfil | 0.198 |
| grid:31 | medium | multi_actor | indirect | split_actions | none | secret_access | 0.198 |
| grid:34 | medium | single_actor | indirect | split_actions | none | secret_access | 0.198 |
| grid:32 | fast | single_actor | full_chain | split_actions | none | key_exfil | 0.198 |
| grid:36 | slow | multi_actor | indirect | timing_jitter | full | secret_access | 0.198 |
| grid:39 | fast | multi_actor | direct | split_actions | none | secret_access | 0.185 |
| grid:43 | slow | multi_actor | full_chain | timing_jitter | full | secret_access | 0.198 |
| grid:45 | slow | single_actor | direct | split_actions | full | data_exfil | 0.198 |
| grid:46 | medium | single_actor | direct | split_actions | full | secret_access | 0.185 |
| grid:47 | slow | multi_actor | indirect | none | partial | secret_access | 0.198 |
| grid:48 | fast | multi_actor | indirect | split_actions | none | secret_access | 0.198 |

## Edge Cases (hand-crafted blind-spot probes)

| Label | residual_risk_max | tier | n_events | n_windows | signals fired |
|-------|--------------------|------|----------|------------|----------------|
| edge:slow_ratchet | 0.198 | NORMAL | 5 | 5 | inv_score |
| edge:multi_actor_convergence | 0.198 | NORMAL | 3 | 1 | inv_score |
| edge:exfil_avoiding | 0.381 | MEDIUM | 3 | 1 | inv_score,novelty_score,bridge_new |
| edge:perfect_mimicry | 0.340 | WATCH | 3 | 1 | inv_score,novelty_score,bridge_new |
| edge:minimal_direct | 0.284 | WATCH | 2 | 1 | inv_score,novelty_score,bridge_new |

---

## Findings & Interpretation (added 2026-04-27, Session R)

### Headline gate verdict

**FAIL with two CLASS-WIPE patterns.** Per the Sprint 2 gate decision table (sprint doc lines 144-148):

- Overall detection rate: **40%** (FAIL: <60%)
- `split_actions` evasion: **0% detected** (CLASS-WIPE)
- `multi_actor` spread: **8.7% detected** (effective CLASS-WIPE)

The next move per the table for FAIL: "Re-evaluate physics thesis before either Sprint 3 or Phase B. Consider Phase 2 signals (target_convergence, eddy_score) per spec line 101."

### Threshold sensitivity is the load-bearing finding

26 of 30 blind spots cluster at residual_risk = 0.151–0.198 — **just below** the WATCH threshold of 0.20. Two outliers sit at 0.002 (no signal fired at all).

| Detection threshold | Detection rate |
|---|---|
| 0.20 (current WATCH) | 40% |
| 0.19 | ~88% (28 of 30 blind spots flip to WATCH) |
| 0.34 (current MEDIUM) | ~30% |
| 0.45 (current HIGH) | ~10% |

This means the recalibrated thresholds (4.5/3.4/2.0 on [0,10] scale, divided by 10), tuned on PR #34's `seeds × actor_counts × attack_ratios × windows` distribution, **do not generalize** to the attack-strategy distribution. This was assumption check #2 in the plan — confirmed.

The signals ARE differentiating attacks; the threshold isn't catching them. Grid verdict is partly a calibration artifact.

### Physics signals are silent on attack-only trajectories

`sigma_coarse` and `delta_f` — the literal physics thesis — fire on **0% of grid trajectories**. `closure_gap` and `orphaned_priv` — 0%. The 96% inv_score fire rate means classical invariants are doing essentially all the detection work. The "physics-informed" framing is currently inaccurate at scale.

Two competing hypotheses:

1. **Methodological** — the harness scores attack-only trajectories with no benign baseline. `sigma_coarse` is zone-flux *variance* across windows; with no benign chatter to establish a baseline, every flux is "novel" and the variance computation degenerates. `closure_gap` requires elapsed settlement time which short trajectories don't accumulate. **Fix:** embed attacks in benign traffic for a fair test.

2. **Architectural** — the physics signals genuinely don't activate on attack patterns regardless of context. **Implication:** the physics thesis is weaker than claimed and Phase B B1 should be revisited from premise, not just direction.

The harness as-built cannot distinguish (1) from (2). Resolving this distinction is the gating question for Sprint 3 or Phase B B1.

### Confirmation-bias guard worked — and exposed three over-predictions

The Prediction Divergence table shows where `expected_signals` (committed before the run) diverged from observation:

| Signal | Predicted+Silent (over-prediction rate) | Reading |
|---|---|---|
| novelty_score | 30/50 (60%) | Half the predictions wrong — multi-actor disperses novelty across actors so per-actor novelty stays low |
| sigma_coarse | 10/10 (100%) | Every prediction wrong — needs cross-window flux variance |
| delta_f | 10/10 (100%) | Every prediction wrong — depends on sigma_coarse |
| closure_gap | 30/30 (100%) | Every prediction wrong — needs elapsed time + benign baseline |
| orphaned_priv | 10/10 (100%) | Every prediction wrong — same |

`bridge_new` and `inv_score` predictions held up well. The over-predictions are concentrated on the very signals that didn't fire — consistent with the "physics signals need benign baseline" hypothesis.

### Multi-actor blind spot — architectural, not methodological

Multi-actor convergence (M-Trends' canonical 22-second handoff pattern) was detected in 2 of 23 trajectories. Edge case `multi_actor_convergence` produced residual_risk=0.198 — NORMAL tier despite being the textbook coordinated attack.

Root cause: `novelty_score` and `bridge_new` are per-actor signals. Spreading work across 4 actors gives each actor only 25% of the trajectory, so per-actor novelty/bridge stay below detection. This is **exactly the regime that Phase B B1's TGN (temporal graph network) is designed to address** — cross-actor temporal correlation is the TGN's raison d'être.

### Split-actions blind spot — also architectural

Split-actions (one event per window across multiple windows) was detected in 0 of 13 trajectories. Edge case `slow_ratchet` (5 events × 5 windows) produced residual_risk=0.198. Root cause: window-scoped scoring cannot correlate events across windows. `bridge_new` requires same-window crossings.

Phase B B1's TPP (temporal point process) is the primary candidate for cross-window pattern detection.

### Reframed gate verdict

The literal verdict is FAIL+CLASS-WIPE. But the failure mode is **specifically** cross-actor and cross-window temporal correlation — the canonical use cases for Phase B B1's representation-learning layer.

This complicates the binary PASS/FAIL decision tree:

- **Strict reading:** FAIL → re-evaluate physics thesis before any new layer, including Phase B B1. Methodological clean-up first (benign baseline, threshold recalibration on this distribution).
- **Charitable reading:** the failure clusters on regimes where Phase B B1 is *designed* to help. The BORDERLINE branch in the gate table explicitly anticipates this: "partial Phase B may still be the right move if failures cluster on regimes where representations help."

Recommended path (R&D, not committed direction):

1. **Methodological cleanup first.** Re-run the grid with benign-traffic baseline embedded. If physics signals fire under that condition, the headline fail is a harness artifact and the BORDERLINE+charitable interpretation applies.
2. **Threshold re-tune on strategy distribution.** Compute P75/P90/P95 of residual_risk on this grid; set thresholds from the actual attack distribution.
3. **Then decide Phase B B1 vs Sprint 3 vs Phase 2 signals.** With cleaner data, the gate verdict will be unambiguous.

### Two insights about signal behavior (Sprint 2 spec gate item)

1. **Multi-actor coordination is invisible to per-actor signals.** Novelty and bridge are computed per-actor; coordinated attacks disperse activity below per-actor detection. This is a structural limitation, not a calibration one.

2. **Physics signals require benign baseline to activate.** Attack-only trajectories don't produce zone-flux variance worth measuring (`sigma_coarse=0` across all 50 trajectories). The "physics" detector is currently a noise-baseline detector, not a signal detector. This was hidden in PR #34 because that harness mixes attackers and workers.

