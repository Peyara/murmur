# Phase 2 Design Summary (Frozen)

**Date:** 2026-07-03  
**Status:** Design complete; frozen contracts ready for Phase 2 implementation  
**Executor:** Downstream Claude Code session (Phase 2 implementer)

---

## Overview

Phase 2 is the **design and contract specification** for world generation and fairness audits in the Murmur physics-signal falsification plan. This document summarizes what has been frozen.

---

## Frozen Deliverables

### 1. Data Contracts (worldgen/model.py)

✅ **RawEvent** (frozen dataclass)
- Generator-side, with labels (zone, archetype, attack_type, is_attack)
- Never shown to detectors
- Fully immutable and hashable

✅ **AnonymizedEvent** (frozen dataclass)
- Detector-visible, no labels, hashed IDs, opaque tokens
- Compatible with Trajectory.Transition (bakeoff/common/trajectory.py)
- Critical invariant: NO zone, NO archetype, NO attack fields

✅ **Actor** (frozen dataclass)
- Nine archetype kinds (Developer, DataAnalyst, ..., BreakGlassAdmin)
- Generator-side only
- Includes role_change_time for archetype transitions

✅ **WorldConfig** (frozen dataclass)
- population_size: [200, 500]
- archetype_mixture: weighted distribution, ≥3 instances of archetypes 4–9
- horizon_days: [60, 90]
- event_rate_lambda: tuned so each actor >> 80 transitions
- attack_mix: probability distribution over five attack types
- zone_labels: ≥6 zones (IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN)
- action_vocab: ≥6 actions (auth, read, write, invoke, grant, assume)

✅ **GroundTruth** & **GroundTruthLabel** (immutable)
- (actor_hash, t_window_start, t_window_end, attack_type) tuples
- Evaluator-side only
- Rolling-window schema (per locked decision §0)

✅ **AnonymizedMapping** (evaluator-side only)
- Salt, actor_hashes, resource_hashes, action_tokens, jitter_amounts
- Never serialized; never shown to detectors

✅ **World** (complete snapshot)
- Fully determined by (config, seed)
- Byte-identical regeneration guaranteed
- Methods: to_detector_visible_dict(), to_evaluator_visible_dict()

### 2. Worldgen Function Signatures (Frozen Stubs)

✅ **benign.py::build_archetype(kind, actor_id, config, seed) → List[RawEvent]**
- Nine benign archetype generators (one per ArchetypeKind)
- Returns events with is_attack=False, attack_type=None
- Must produce >> 80 transitions per actor (locked decision §0)
- Deterministic per seed

✅ **attacks.py::inject_attack(attack_type, victim_actor, world_events, config, seed) → (events, labels)**
- Five attack type injectors (CredentialTheftLateral, SlowExfiltration, SmashAndGrab, LivingOffTheLand, ServiceAccountHijack)
- Overlays on existing actors; modifies world_events in-place
- Returns ground-truth labels (unhashed actor_id, t_start, t_end, attack_type)
- Deterministic per seed

✅ **hard_negatives.py::ensure_hard_negatives(world) → world**
- Three hard-negative injectors: ETL twin, on-call storm, novelty flood
- Modifies world.raw_events in-place
- All events: is_attack=False, attack_type=None
- Deterministic

✅ **anonymize.py::anonymize(raw_events, seed, jitter_window=30) → (List[AnonymizedEvent], AnonymizedMapping)**
- Converts RawEvent → AnonymizedEvent
- Hashes actor and resource IDs (salted HMAC-SHA256)
- Maps action_type → opaque tokens
- Jitters timestamps deterministically
- Strips all labels (zone, archetype, is_attack, attack_type)

✅ **world.py::generate(config, seed) → World**
- Full orchestration:
  1. Initialize actor population
  2. Generate benign trajectories
  3. Inject attacks (50% probability)
  4. Inject hard negatives
  5. Anonymize
  6. Return World
- Fully deterministic
- Validates per-actor transition count ≥ 80

### 3. Audit Function Signatures (Frozen Stubs)

✅ **audits/fairness_audit.py::run(worlds) → FairnessAuditResult**
- Six gates:
  1. Zone count: K-S test (α=0.01) between attack and clean
  2. Node degree: K-S test between attack and clean
  3. Per-zone volumes: K-S test between attack and clean
  4. Attack path length: within benign IQR [Q1, Q3]
  5. Per-edge rarity: attack edges matched by hard-negative benign edges (±1 decile)
  6. Determinism: regenerate worlds, verify byte-identical

✅ **audits/leakage_redteam.py::run(worlds) → LeakageRedTeamResult**
- Train shallow logistic regression (world-level features only)
- Predict attack vs. benign windows
- Metric: AUC-PR (primary; not ROC-AUC)
- Pass criterion: AUC-PR ≤ no-skill baseline (with 95% CI)
- If CI above no-skill: landscape rigged (KILL)

✅ **audits/grep_leak_check.py::run(worlds) → GrepLeakCheckResult**
- Scan detector-visible artifacts for forbidden strings:
  - Zone names (IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN)
  - Archetype names (Developer, DataAnalyst, ...)
  - Attack names (CredentialTheftLateral, ...)
  - Attack markers (is_attack, attack_type, EXFIL, ATTACK, ANOMALY)
- Pass criterion: no matches

### 4. Documentation

✅ **worldgen/WORLDGEN_CONTRACT.md**
- Complete specification of all contracts, guarantees, invariants
- Detailed archetype and attack definitions
- Hard-negative specifications
- Fairness audit gates
- Testing checklist
- Hand-off requirements

---

## Locked Decisions (Non-Negotiable)

### Decision 1: Rolling-Window Physics Scoring
**Source:** PREDICTIONS.md Correction 2

Physics is scored over **per-actor rolling windows of the last N ≥ 80 transitions**, NOT fixed 15-min clock windows. This decouples physics from the 15-min granularity that caused data starvation in Phase 1.

**Implication for Phase 2:** Simulation horizon and event_rate_lambda MUST be tuned so **each actor accumulates >> 80 transitions** (aim for 200–500 per active actor). This is verified in fairness_audit.

### Decision 2: Fairness-Gate Stratification
**Source:** §4.3 + §1 outcome definitions

The requirement "cheat detector at chance" (§4.3) is:
- **STRICT** for subtle attacks: living-off-the-land, slow exfil, service_account_hijack
- **EXEMPT** for easy anchor: smash_and_grab (aggregate-visible, sanity check)

This resolves the apparent contradiction between §4.3 and §3.2.

---

## Epistemic Guardrails (Mandatory)

✅ **Anonymization Strictness:**
- Detectors see ONLY AnonymizedEvent (never RawEvent, never AnonymizedMapping, never GroundTruth)
- Grep-level check: no zone/archetype/attack names in detector artifacts

✅ **Ground-Truth Confidentiality:**
- (actor_hash, time_window, attack_type) labels are evaluator-side only
- No label information leaks to detectors

✅ **Determinism:**
- Every world fully determined by (config, seed)
- Regeneration must be byte-identical (tested in fairness_audit §6)

✅ **No Absolute-FP Language:**
- This phase builds the landscape and proves it is fair
- It does NOT run detectors P1/P2/B1 (that is Phase 3+)
- Any result is "necessary bar, not sufficient — pending real-data confirmation"

---

## Dependencies Decision

**Added:** scikit-learn (v1.9.0)

**Rationale:** Audits require:
- scipy.stats for K-S tests (included with scipy, pulled in by sklearn)
- sklearn.linear_model for logistic regression (leakage red-team)
- sklearn.metrics for AUC-PR computation

**NOT added to generator:** Generator uses only numpy (deterministic, lightweight, no ML overhead).

**Justification:** Audits are evaluation/validation harnesses (not product code), so sklearn dependency is justified and documented.

---

## What Phase 2 Implementer Receives

### Frozen ✅
- All data contracts (model.py): types, invariants, serialization methods
- All function signatures (benign.py, attacks.py, hard_negatives.py, anonymize.py, world.py, audits/*.py)
- All invariants and guarantees
- Both locked decisions
- Complete test checklist
- Full documentation (WORLDGEN_CONTRACT.md)

### NOT Frozen ❌
- Algorithm details (how to sample dwell times? which distributions?)
- Parameter tuning (smoothing, jitter window, event rate λ exact value)
- Optimization choices
- Implementation code

---

## Key Design Choices Rationale

**Why frozen dataclasses?**
- Immutability enforces correctness (no accidental mutation post-generation)
- Hashability allows use in sets/dicts (for dedup, accounting)
- Type hints enable early error detection

**Why separate RawEvent and AnonymizedEvent?**
- Strict boundary between generator (has labels) and detector (no labels)
- Prevents accidental leakage via shared types
- Enables auditing (grep-check, red-team) on anonymized events specifically

**Why rolling-window scoring, not fixed 15-min?**
- Phase 1 learning: 15-min fixed windows left P1 data-starved (P1 needs ≥80 transitions; real IAM median 8–12 per 15-min window)
- Rolling windows decouple physics from the clock granularity
- Cost: cold-start blind spot for new actors (acceptable; novelty signals cover)

**Why three hard-negative types?**
- ETL twin: structural matching (path length, per-edge rarity)
- On-call storm: temporal confound (overlap with attack window)
- Novelty flood: behavioral confound (common benign novelty)
- Together, they test whether detectors conflate "anomalous" with "malicious"

**Why fairness gates BEFORE detector comparison?**
- Ensures landscape is adversarially fair before touching any detector
- If any gate fails, the generator is fixed, not the detector
- Prevents rigged bake-offs

---

## File Structure

```
bakeoff/
  worldgen/
    __init__.py                 # package exports
    model.py                    # frozen contracts (RawEvent, AnonymizedEvent, World, etc.)
    benign.py                   # build_archetype() stub
    attacks.py                  # inject_attack() stub
    hard_negatives.py           # ensure_hard_negatives() stub
    anonymize.py                # anonymize() stub
    world.py                    # generate() stub (orchestrator)
    WORLDGEN_CONTRACT.md        # complete specification
  
  audits/
    __init__.py                 # package exports
    fairness_audit.py           # run() for structural equalization + determinism
    leakage_redteam.py          # run() for shallow cheat detector
    grep_leak_check.py          # run() for label leakage scan
  
  configs/                       # [already exists] world + detector configs
  reports/                       # [already exists] output dir for audit results
  
  PREDICTIONS.md                # [already exists] Phase 1 predictions + locked decisions
  PHASE2_DESIGN_SUMMARY.md      # [this file] design recap
```

---

## Success Criteria (Phase 2 Completion)

By end of Phase 2, deliverables are:

✅ All six modules implemented (benign, attacks, hard_negatives, anonymize, world, audits)  
✅ 10 trial worlds generated, all audits pass  
✅ Per-actor transition count diagnostic: min, mean, max (aim: >> 80)  
✅ Determinism test: generate(config, seed) twice, bit-identical  
✅ Code compiles and passes type checking  
✅ Existing Phase 1 tests still pass (mechanism_tests, P1/P2 estimators)  
✅ Documentation: inline docstrings + WORLDGEN_CONTRACT.md  

---

## Hand-Off to Phase 3

Phase 3 (Baselines) will receive:
- Fully functional worldgen pipeline
- 10 trial worlds (attack/clean mixed)
- Anonymized event logs (detector-visible)
- Ground-truth labels (evaluator-side only)
- Verified fairness (all audits pass)

Phase 3 will:
1. Implement baselines (B0, B1, B2)
2. Test on dev worlds (10 seeds)
3. Produce tuned detector configs
4. Commit FREEZE.md before held-out evaluation

---

*Design frozen: 2026-07-03*  
*Awaiting Phase 2 implementation*
