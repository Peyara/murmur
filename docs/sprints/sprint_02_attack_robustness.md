# Sprint 2: Attack Generator + Robustness Validation

## Hypothesis

Are the physics-informed signals (sigma_coarse, invariants, novelty, bridge_new, delta_F) robust across varied attack strategies? Or do they only catch the obvious burst attacks we hand-crafted in Sprint 1?

## Prerequisites

Sprint 1 complete. Signal validation gate passed. sigma_coarse produces meaningful variance on real data. Core detector working. Multi-log ingestion + temporal-identity correlation operational (trigger_ref derived, not parsed).

## Stack Layers

- **Validation/Testing:** parameterized attack generator, robustness analysis
- **Scoring (analysis):** examining which signals fire on which strategies

## Duration: 3-4 days

---

## Why This Sprint Matters

The 6-scenario benchmark from Sprint 1 is circular validation: we designed attacks to match the theory, then confirmed the theory detects them. This proves the math works, not that the framing is right.

Real attackers vary their strategies: slow vs fast, single vs multi-actor, direct vs indirect zone paths, with or without timing evasion. If sigma_coarse only catches obvious bursts, the physics thesis is weaker than claimed.

The parameterized attack generator systematically covers the strategy space without requiring RL infrastructure. It answers: "across what range of attack behaviors do these signals hold?"

---

## Deliverables

### Parameterized Attack Generator

- [ ] `src/validation/attack_generator.py`: generates synthetic CanonicalEvent sequences from parameters:

  **Parameters:**
  | Parameter | Values | What it tests |
  |---|---|---|
  | `speed` | slow (1 event/5min), medium (1/min), fast (5/min) | Timing detection sensitivity |
  | `spread` | single_actor, multi_actor (2-4 actors) | Coordination detection |
  | `zone_path` | direct (IDENTITY->SECRET), indirect (IDENTITY->DATA->SECRET), full_chain (CONTROL->IDENTITY->SECRET->DATA->EXFIL) | Zone traversal patterns |
  | `evasion` | none, timing_jitter (random delays), pattern_mimicry (match normal rate/timing), split_actions (spread across windows) | Evasion strategy |
  | `closure` | none (leave doors open), partial (close some), full (close all) | Closure signal testing |
  | `objective` | secret_access, key_exfil, compute_persist, data_exfil | Attack goal |

- [ ] Generator produces valid CanonicalEvent sequences with correct zone mappings, action types, and timestamps
- [ ] Each generated trajectory includes metadata: parameter settings, expected zone path, expected signals that should fire

### Attack Corpus

- [ ] Generate 30-50 diverse trajectories from parameter grid:
  - 3 speeds x 2 spreads x 3 zone_paths x 4 evasions = 72 combinations (sample 30-50)
  - Plus 5 targeted edge cases:
    - Extremely slow ratchet (1 event per window, across 6 windows)
    - Multi-actor convergence on single secret
    - Zone path that avoids EXFIL_RISK entirely
    - Perfect timing mimicry of registered sanctioned pattern
    - Single-event attack (just one secret access by novel actor)

### Robustness Analysis

- [ ] Run full detector (invariants + sigma_coarse + novelty + bridge + delta_F + fusion) against all trajectories
- [ ] For each trajectory, record:
  - fusion_raw score
  - Which signals fired (sigma_coarse, invariants, novelty, bridge, delta_F)
  - Signal magnitudes
  - Whether it would be detected at current threshold

- [ ] Produce robustness report:
  - [ ] Detection rate by parameter:
    - By speed (slow/med/fast)
    - By spread (single/multi)
    - By zone_path
    - By evasion strategy
    - By closure behavior
  - [ ] Which signals are most robust (fire across most strategies)?
  - [ ] Which signals are most fragile (only fire on specific strategies)?
  - [ ] Which attack parameter combinations evade detection? Why?
  - [ ] Are there signal blind spots (entire strategy classes that produce low fusion_raw)?

### Tests

- [ ] Generator produces valid events (zone mappings correct, timestamps ordered, action types valid)
- [ ] Generated trajectories inject correctly into DuckDB
  - Note: synthetic events bypass the temporal-identity correlation pipeline. trigger_ref is set directly on CanonicalEvent for attack/benign scenarios. Correlation is an ingestion concern tested in Sprint 1, not re-validated here.
- [ ] Scoring pipeline handles synthetic events identically to real events
- [ ] Robustness report generation runs without errors

---

## Gate

- [ ] >80% detection rate across the full parameter grid (attack trajectories producing residual_risk above threshold)
- [ ] No entire parameter class with 0% detection (every speed, spread, and zone_path has at least some detection)
- [ ] Blind spots documented: which specific combinations evade, and why
- [ ] At least 2 insights about signal behavior that weren't obvious from Sprint 1

### If Gate Fails

- If detection <80% but >60%: document which strategies fail, consider whether Sprint 3 provenance/closure will catch them (some attacks may only be catchable via unclosed loops, not physics signals alone)
- If detection <60%: signals need redesign. Consider adding Phase 2 signals (target_convergence, eddy_score) before proceeding. Re-evaluate the physics thesis.
- If specific evasion strategies consistently succeed: document as inputs for post-MVP RL co-evolution

---

## Execution Plan (added 2026-04-27, Session Q)

### Pivot Context

`docs/mvp_strategy_phase_b.md` declares Phase B (learned representations) **conditional on Sprint 2's hypothesis passing** — physics signals achieving ≥80% detection across the parameterized attack grid. The Sprint 2 *spec* exists; the *grid was never built*. PR #34 (`large_scale.py`) sweeps `seeds × actor_counts × attack_ratios × windows` — different axes; characterizes the residual_risk *distribution* but does not vary attack *strategy*. So the Phase B pivot condition is currently unverified.

**Decision:** Build Sprint 2's grid first (3-4 days). Only commit to Phase B B1 (TGN+TPP, 4-6 weeks) after the gate is evaluated on real attack-strategy axes. Sprint 3 (provenance + closure) is deferred.

This plan is the resume point. Pick up at the first unchecked Phase below.

### Phase 1 — Attack Generator (`src/validation/attack_generator.py`) ✅ Session R

- [x] Define `AttackParams` dataclass with axes from the spec table: `speed`, `spread`, `zone_path`, `evasion`, `closure`, `objective`
- [x] Implement `generate_attack(params: AttackParams, seed: int) -> AttackTrajectory` that produces deterministic, valid CanonicalEvent sequences (renamed from `generate_trajectory` to avoid collision with `src/synthetic/__init__.py`)
  - Zone mappings correct per `src/schema.py:34-40` and `src/ingest/parser.py:29-63` (note: spec said `src/world/zones.py` and `src/ingest/canonical.py` — those are stale paths)
  - Action types valid; timestamps strictly ordered; intervals matching `speed`
  - `trigger_ref` set directly on synthetic events (per spec line 85 — bypass correlation pipeline)
  - Each trajectory carries metadata: param settings, expected zone path, expected signals (predicted before observation as confirmation-bias guard)
- [x] `tests/test_attack_generator.py`: 25 tests covering validity, determinism, evasion behaviors, closure balancing, multi-actor distinctness, expected-signals predictions, DB injection. All passing.

### Phase 2 — Robustness Harness (`src/validation/robustness.py`) ✅ Session R

- [x] `param_grid()` enumerator: stratified sample over 72 base combinations (3 speeds × 2 spreads × 3 zone_paths × 4 evasions); guarantees ≥1 sample per (speed, evasion) cell. closure + objective randomized per sample.
- [x] 5 hand-crafted edge cases (slow_ratchet, multi_actor_convergence, exfil_avoiding, perfect_mimicry, minimal_direct).
- [x] Per-trajectory scoring: direct `insert_event` → world-model build → closure discovery → fusion + residual_risk; thresholds from `config/settings.py` (4.5/3.4/2.0 ÷ 10).
- [x] `RobustnessReport.to_markdown()`: detection rate per param axis, signal fire rate + mean max activation, prediction divergence table (confirmation-bias guard), blind-spot enumeration, edge-case results.
- [x] CLI exposure: `murmur robustness --grid-size N --seed S --parallel P --output PATH`. 11 tests passing.

### Phase 3 — Run + Report ✅ Session R

- [x] Ran grid: 50 trajectories + 5 edge cases. Output at `docs/rd_reports/2026-04-27_sprint2_robustness.md`.
- [x] Cross-reference: the per-window FN rate from PR #34 (~68% at MEDIUM threshold) and the per-trajectory FN rate here (~60%) are roughly consistent. Both harnesses see the same threshold-sensitivity behavior — residual_risk for many attack regimes lands in the [0.15, 0.25] band, right around the WATCH threshold of 0.20.

### Phase 4 — Gate Decision (write decision into Findings Log + CURRENT_STATE)

| Outcome | Detection Rate | Next Move |
|---|---|---|
| **PASS** | ≥80% across grid, no class with 0% | Phase B B1 is justified — start TGN+TPP scaffolding |
| **BORDERLINE** | 60-80% | Document failure modes; some may need Sprint 3 closure (deferred) rather than learned layer; partial Phase B may still be the right move if failures cluster on regimes where representations help |
| **FAIL** | <60% | Physics thesis weaker than claimed. Re-evaluate before either Sprint 3 or Phase B. Consider Phase 2 signals (`target_convergence`, `eddy_score`) per spec line 101 |
| **CLASS-WIPE** | Any single param class at 0% | That class is a blind spot regardless of overall rate — document and decide whether to fill (Sprint 3 / Phase B / new signal) |

### Branch + PR Plan

- Branch: `feature/sprint2-attack-grid` off latest `main` (post-PR #34)
- Commit shape: (1) attack_generator + tests, (2) robustness harness + CLI, (3) grid run output + R&D report
- Single PR — easier to review the gate evidence as a unit
- After PR merges: write Sprint 2 Findings Log, update CURRENT_STATE.md with gate verdict and resume point (Phase B B1 / Sprint 3 / redesign)

### Estimated Time

3-4 days, tracked against this plan. If Phase 1 alone exceeds 2 days, stop and check assumptions — generator simplicity is a forcing function.

### What's Deferred Until After This Gate

- Sprint 3 (provenance + closure) — explicitly deferred per user direction 2026-04-27
- Phase B B1 (TGN encoder + TPP intensity head) — conditional on this gate
- Actor-level alerting investigation — orthogonal finding from PR #34, queue for after gate
- Directionality gap (causal filter for pair miner) — Sprint 3 work, deferred with it

---

## Findings Log

### Session R (2026-04-27): Sprint 2 grid run + gate verdict

**Gate verdict: FAIL with 2 CLASS-WIPE patterns.**

| Metric | Value | Gate threshold | Verdict |
|---|---|---|---|
| Overall detection rate | 40% | ≥80% | FAIL (<60%) |
| `split_actions` evasion class | 0% | >0% required | CLASS-WIPE |
| `multi_actor` spread class | 8.7% | >0% required | Effective CLASS-WIPE |
| Best class detection | `timing_jitter`: 69.2% | — | — |
| Worst class detection | `split_actions`: 0% | — | — |

**Three insights about signal behavior** (Sprint 2 spec required ≥2):

1. **Multi-actor coordination is invisible to per-actor signals.** novelty_score and bridge_new are computed per-actor; spreading work across 4 actors disperses each below detection. `multi_actor_convergence` edge case (M-Trends 22-second handoff archetype) produced residual_risk=0.198 — NORMAL tier. This is a structural limitation of per-actor scoring.

2. **Physics signals (sigma_coarse, delta_f) require benign baseline to activate.** Both fired on 0% of grid trajectories. Hypothesis: these are zone-flux *variance* signals that need a non-attack baseline to compute against. PR #34's harness mixes attackers + workers and produces non-zero physics signals; this attack-only harness produces zero. Cannot distinguish "physics is broken" from "physics needs baseline" without re-running with benign embedding.

3. **Threshold sits exactly at the strategy-grid noise floor.** 26 of 30 blind spots have residual_risk in [0.15, 0.20], just below WATCH=0.20. A 0.19 threshold would flip detection from 40% to ~88%. The recalibrated thresholds (PR #34) tuned on a different distribution; they are not a transferable signal of detection capability across distributions.

**Confirmation-bias guard outcome:**
Predictions in `expected_signals` were committed before the run. Divergence concentrated on the 4 signals that fire on 0% of trajectories (sigma_coarse, delta_f, closure_gap, orphaned_priv) — every single prediction for those 4 was wrong. inv_score and bridge_new predictions held up. The over-prediction pattern aligns with the "physics signals need baseline" hypothesis.

**Reframed reading of the FAIL:**
The failure modes (multi-actor coordination, cross-window split actions) are exactly the regimes that Phase B B1's TGN+TPP is designed to address. The strict gate verdict says re-evaluate physics thesis before any new layer. The charitable reading (BORDERLINE branch in the gate table) says partial Phase B is justified when failures cluster on representation-learning regimes. The methodological gap (no benign baseline) makes the strict-vs-charitable choice ambiguous until the harness is rerun with benign embedding.

**Recommended next move (R&D, not committed):**
1. Re-run robustness grid with benign-traffic baseline embedded; resolve "physics broken" vs "physics needs baseline" ambiguity.
2. Recalibrate thresholds on the strategy-grid distribution (P75/P90/P95 of residual_risk).
3. Then choose: Phase B B1 (if multi-actor + cross-window failures persist) vs Sprint 3 closure repair (if closure_gap was the missing piece) vs Phase 2 signals (target_convergence, eddy_score).

See full report: `docs/rd_reports/2026-04-27_sprint2_robustness.md`.

---

## Files Created/Modified

| File | Purpose |
|---|---|
| `src/validation/attack_generator.py` | Parameterized attack generation |
| `src/validation/robustness.py` | Robustness analysis + reporting |
| `data/benchmark/attack_corpus/` | Generated attack trajectories |
| `tests/test_attack_generator.py` | Generator correctness tests |
