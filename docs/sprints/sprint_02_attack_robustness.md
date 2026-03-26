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

## Findings Log

_Updated as analysis runs:_

---

## Files Created/Modified

| File | Purpose |
|---|---|
| `src/validation/attack_generator.py` | Parameterized attack generation |
| `src/validation/robustness.py` | Robustness analysis + reporting |
| `data/benchmark/attack_corpus/` | Generated attack trajectories |
| `tests/test_attack_generator.py` | Generator correctness tests |
