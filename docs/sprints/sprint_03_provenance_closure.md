# Sprint 3: Provenance + Closure + Full Fusion

## Hypothesis

Does provenance subtraction (residual_risk = total signal - authorized signal) reduce false positives on legitimate orchestration without losing detection of real attacks? Does workflow closure add detection specificity?

## Prerequisites

Sprint 1 + 2 complete. Core signals validated on real data. Robustness validated across attack parameter grid. We know which attacks the physics signals catch and which they miss.

## Stack Layers

- **Provenance (full):** pattern matching, trigger chain, residual risk computation
- **Scoring (closure):** closure_ratio, orphaned_privilege_score
- **Policy:** risk_energy(), shadow suggestions, confidence modifier

## Duration: 5-6 days

---

## Why This Sprint Matters

After Sprint 1-2, we have a detector that fires on coordinated activity. But legitimate orchestration (CI/CD, scheduled jobs, agent swarms) also produces coordinated activity. Without provenance subtraction, the detector has unacceptable false positives.

This sprint adds the two mechanisms that make the detector *usable*:
1. **Provenance:** subtract what's authorized, score only the residual
2. **Closure:** legitimate workflows close their loops, attackers don't

Together, these transform Murmur from "anomaly detector" to "authorized world model."

---

## Deliverables

### Provenance Layer (full integration)

- [ ] `src/provenance/patterns.py` (extend from Sprint 1 scaffold):
  - Pattern matching: all 4 components (actor 0.30, zone sequence 0.35, time window 0.20, rate 0.15)
  - CLI: `register-pattern` with full parameter set
  - Register 2+ real patterns from sandbox (normal-worker, any Cloud Scheduler jobs)

- [ ] `src/provenance/trigger_chain.py` (extend):
  - Full trigger chain resolution with known_initiators set
  - Populate known_initiators.json from actual sandbox Cloud Scheduler/Build IDs
  - Integration test: real scheduled event -> trigger chain resolves -> provenance_level = WEAK

- [ ] `src/provenance/residual.py` (extend):
  - Full residual risk formula:
    ```
    discount_multiplier = {STRONG: 1.0, WEAK: 0.6, NONE: 0.0}[provenance_level]
    base_residual = fusion_raw * (1.0 - discount_multiplier * pattern_match_score)
    trigger_penalty = 0.0 if trigger_chain_resolved else 0.3 * inv_score
    residual_risk = base_residual + trigger_penalty
    ```
  - Provenance explanation string per actor per window (human-readable: "Matched pattern 'nightly_pipeline' with score 0.91, WEAK provenance via Cloud Scheduler trigger")

### Closure Module

- [ ] `src/score/closure.py`:
  - **closure_ratio:** count(closed_openings) / count(total_openings)
    - Opening-closing pairs (Tier 1 / short-window):
      - IAM_SET_POLICY -> IAM_POLICY_STABLE_CONFIRM (24h)
      - IAM_IMPERSONATE -> session_cleanup (4h)
      - COMPUTE_METADATA_CHANGE -> metadata_stable_confirm (2h)
    - Tier 2 (long-window, reports "insufficient data" until 30 days):
      - IAM_CREATE_KEY -> IAM_DELETE_KEY (720h)
  - **orphaned_privilege_score:** sensitivity-weighted unclosed resources
    - SA_KEY: 5.0, IAM_POLICY: 4.0, IMPERSONATION: 4.0, SECRET: 3.0
    - Score = sensitivity * (0.5 if not used for expected purpose + 1.0 if not revoked)
  - `opening_closing_pairs` DuckDB table populated

### Full Fusion Pipeline

- [ ] `src/score/fusion.py` (replace basic fusion from Sprint 1):
  - All Phase 1 signals + closure signals
  - Signal normalization to comparable scales before weighting
  - Weights marked as "initial estimates" in code:
    ```
    fusion_raw = (
        w_inv * norm(inv_score) +
        w_sigma * norm(sigma_coarse) +
        w_novelty * norm(novelty_score) +
        w_bridge * norm(bridge_new) +
        w_delta * norm(delta_F) +
        w_orphan * norm(orphaned_privilege_score) +
        w_closure * norm(1.0 - closure_ratio) +
        w_burst * norm(burst_per_min) +
        w_breadth * norm(breadth_entropy)
    ) * context_factor
    ```
  - context_factor: provenance-conditional during incidents (0.7 for WEAK, 1.0 for NONE)
  - Coverage as confidence modifier (HIGH/MEDIUM/LOW), not score multiplier
  - Apply provenance layer -> residual_risk

### Policy Layer

- [ ] `src/policy/state.py`: PolicyState dataclass (reduced from 18-dim: only dimensions we actually compute in MVP)
- [ ] `src/policy/energy.py`: risk_energy() function
  - Provenance discount
  - Closure discount
  - Deploy window discount
  - Coverage confidence check
  - Thresholds: V > 8.0 ALERT_HIGH, > 5.0 ALERT_MED, > 3.0 WATCH, <= 3.0 NORMAL
- [ ] `src/policy/bandit.py`: shadow bandit logger (logs suggestions to policy_suggestions table, never auto-executes)
- [ ] Shadow action suggestions: isolate actor, revoke tokens, request review, increase monitoring

### Full Benchmark (expand to 18)

- [ ] Expand from 6 to 18 scenarios:
  - S01-S13: 13 attack scenarios (see original spec)
  - B01-B05: 5 benign orchestration scenarios
  - Each scenario has documented expected signals, expected residual_risk range, expected policy action
- [ ] Benchmark runs as part of pytest suite

### Tests

- [ ] Pattern match: full 4-component scoring with known inputs
- [ ] Trigger chain: real Cloud Scheduler event resolves to WEAK
- [ ] Residual risk: worked examples from original spec (on-schedule = 0.54, off-schedule = 7.38+)
- [ ] Closure: complete loop (ratio=1.0), incomplete (ratio<1.0), insufficient data (Tier 2)
- [ ] Orphaned privilege: SA key created but never revoked = 7.5
- [ ] Fusion: end-to-end with hand-calculated expected output
- [ ] risk_energy: known inputs -> known threshold classification
- [ ] Integration: raw JSON -> DuckDB -> scoring -> policy suggestion

---

## Gate

- [ ] 18-scenario benchmark: ALL passing
  - S01-S09: residual_risk > threshold (attacks detected)
  - S10: discounted but still elevated (attack during deploy window)
  - S11: low residual (on-schedule, matched pattern, WEAK provenance)
  - S12: high residual (off-schedule, no pattern, NONE provenance)
  - S13: medium residual (pattern match but no provenance)
  - B01-B05: below alert threshold (zero false positives on benign orchestration)
- [ ] B03 (incident response) specifically: fusion_raw elevated but residual_risk low after provenance + closure discount
- [ ] Run on real GCP data 48+ hours: zero false positives on registered patterns
- [ ] Provenance explanation readable and correct for all scored actors
- [ ] Closure signals producing non-trivial values on real data (at least for short-window pairs)

---

## Findings Log

_Updated as work progresses:_

---

## Files Created/Modified

| File | Purpose |
|---|---|
| `src/provenance/patterns.py` | Full pattern matching |
| `src/provenance/trigger_chain.py` | Full trigger chain |
| `src/provenance/residual.py` | Full residual risk |
| `src/score/closure.py` | Closure signals |
| `src/score/fusion.py` | Full fusion pipeline |
| `src/policy/state.py` | Policy state vector |
| `src/policy/energy.py` | Risk energy function |
| `src/policy/bandit.py` | Shadow bandit |
| `data/benchmark/S*.jsonl` | All 13 attack scenarios |
| `data/benchmark/B*.jsonl` | All 5 benign scenarios |
| `tests/test_closure.py` | Closure tests |
| `tests/test_pipeline.py` | Integration tests |
