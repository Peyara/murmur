# Sprint 1: Core Detection + Signal Validation

## Hypothesis

Do zone flux + sigma_coarse + invariants produce meaningful signal on real GCP audit logs? Can we distinguish injected attacks from normal scheduled activity using physics-informed signals?

## Prerequisites

Sprint 0 complete. Real audit logs flowing into DuckDB. trigger_ref working (native or fallback).

## Stack Layers

- **World Model:** windowing, zone flux graph, edge tracking
- **Scoring:** invariants, physics (sigma_coarse), novelty, basic fusion
- **Provenance (scaffold):** pattern registry, pattern match, trigger chain, residual risk

## Duration: 6-7 days (including 2-day validation gate)

---

## Phase 1A: Core Detection Build (4-5 days)

### Deliverables

**World Model Layer:**
- [ ] `src/world/window.py`: 15-min windowing, actor_windows table, edges_window table
- [ ] `src/world/graph.py`: Zone flux 6x6 matrix computation per window, net currents, bridge detection

**Scoring Layer (Phase 1 signals):**
- [ ] `src/score/invariants.py`: All 10 invariants + inv_score computation
  - INV_001: IAM policy change outside deploy window (sev 5)
  - INV_002: Service account key created (sev 5)
  - INV_003: Key created by novel actor (sev 5)
  - INV_004: Impersonation token generated (sev 4)
  - INV_005: Impersonation rate spike (sev 5)
  - INV_006: Secret accessed by new actor (sev 5)
  - INV_007: Secret access within 15 min of policy change (sev 5)
  - INV_008: KMS decrypt by new actor (sev 4)
  - INV_009: Compute metadata change (sev 5)
  - INV_010: New cross-zone edge to SECRET or EXFIL_RISK (sev 5)
- [ ] `src/score/physics.py`: sigma_coarse (Schnakenberg entropy production on 6x6 zone flux)
- [ ] `src/score/novelty.py`: novelty_score (weighted new actor-target edges), bridge_new (new cross-zone edges)
- [ ] delta_F (danger potential change), burst_per_min, breadth_entropy
- [ ] `src/score/fusion.py`: Basic fusion using Phase 1 signals only, with signal normalization

**Provenance Layer (scaffold):**
- [ ] `src/provenance/patterns.py`: sanctioned_patterns table, compute_pattern_match (4 components: actor, zone sequence, time window, rate)
- [ ] `src/provenance/trigger_chain.py`: resolve_trigger_chain with cycle detection and max-depth
- [ ] `src/provenance/signature.py`: verify_signature stub (always returns unverified)
- [ ] `src/provenance/residual.py`: compute_residual_risk with NONE/WEAK discount
- [ ] CLI: `register-pattern`, `list-patterns`, `deactivate-pattern`, `show-trigger-chain`
- [ ] 1+ real sanctioned pattern registered from sandbox `normal-worker`

**Benchmark (initial):**
- [ ] 6 core scenarios defined in `data/benchmark/`:
  - S01: Key creation + secret access (5 min apart)
  - S04: Slow ratchet over 45 min (policy -> key -> secret -> data -> exfil)
  - S07: CONTROL -> IDENTITY -> SECRET chain across 3 actors
  - B01: Full deploy (Cloud Build -> IAM -> service -> confirmed)
  - B02: Secrets rotation (scheduler -> create key -> update -> revoke)
  - S13: Activity matching pattern but trigger_ref NULL, NONE provenance
- [ ] `benchmark --corpus` CLI command
- [ ] `score --window-minutes 15` CLI command

**Tests:**
- [ ] One test per invariant (10 tests) with hand-crafted event sequences
- [ ] Parser edge cases: missing fields, unknown action types, malformed JSON
- [ ] Trigger chain: resolved, unresolved, cycle detection, max-depth
- [ ] Pattern match: exact, partial, no match, inactive pattern
- [ ] Fusion: known-input/known-output with hand-calculated values
- [ ] Residual risk: NONE and WEAK provenance with various match scores

### Gate

`pytest` green. 6-scenario benchmark: S01/S04/S07 produce residual_risk above threshold, B01/B02 below threshold, S13 medium.

---

## Phase 1B: Signal Validation Gate (2 days)

**This is the most important gate in the project. Do not proceed without answering these questions.**

### Activities

1. Deploy scoring pipeline to GCP VM via systemd. Run continuously 24-48h on real sandbox logs.
2. Measure and document:
   - [ ] Zone flux matrix shape on real data: how sparse? Which zone pairs have non-zero flux?
   - [ ] sigma_coarse distribution: what values during active windows? During quiet windows? Is variance meaningful?
   - [ ] Invariant false positives: do any invariants fire on normal Cloud Scheduler activity? (Must be zero)
   - [ ] pattern_match_score for registered normal-worker pattern: is it >0.7?
   - [ ] Distribution of fusion_raw values over 24h: mean, std, min, max, percentiles
   - [ ] Distribution of residual_risk values: same
   - [ ] Parse failures or unexpected log formats found
3. Generate diverse sandbox activity if the zone flux matrix is too sparse:
   - Manual IAM operations
   - Secret access via gcloud CLI
   - Service account creation
   - At minimum: produce events in 4+ of 6 zones
4. Inject scripted attack (S01: key creation + secret access via manual API calls)
5. Verify attack produces elevated residual_risk

### Validation Criteria (ALL must be met to proceed)

- [ ] Parse rate >90% on real logs
- [ ] sigma_coarse shows measurable variance between active and quiet windows
- [ ] Registered sanctioned pattern produces pattern_match_score >0.7 for normal-worker
- [ ] Injected attack produces residual_risk >= 2x normal window average
- [ ] Zero invariant false positives on baseline scheduled activity

### If Validation Fails

Debug and fix. Common issues:
- Zone mapping wrong: events landing in unexpected zones
- Flux matrix all zeros: not enough cross-zone events (generate more diverse activity)
- sigma_coarse trivially zero: Schnakenberg formula getting zero flux (check matrix computation)
- Pattern match too low: pattern definition doesn't match real behavior (adjust pattern)

**Do NOT proceed to Sprint 2 until this gate passes.**

### Findings Log

_Updated as validation runs:_

---

## Files Created/Modified

| File | Purpose |
|---|---|
| `src/world/window.py` | 15-min windowing |
| `src/world/graph.py` | Zone flux matrix |
| `src/score/invariants.py` | 10 invariants |
| `src/score/physics.py` | sigma_coarse |
| `src/score/novelty.py` | novelty_score, bridge_new |
| `src/score/fusion.py` | Basic fusion pipeline |
| `src/provenance/patterns.py` | Pattern registry + matching |
| `src/provenance/trigger_chain.py` | Trigger chain resolution |
| `src/provenance/signature.py` | Signature verification stub |
| `src/provenance/residual.py` | Residual risk computation |
| `data/benchmark/S01.jsonl` through `S13.jsonl` | Benchmark scenarios |
| `data/benchmark/B01.jsonl`, `B02.jsonl` | Benign scenarios |
| `tests/test_invariants.py` | Invariant tests |
| `tests/test_physics.py` | Physics signal tests |
| `tests/test_provenance.py` | Provenance tests |
| `tests/test_fusion.py` | Fusion tests |
