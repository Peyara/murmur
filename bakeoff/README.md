# Murmur Physics-Signal Falsification Bake-off

**Status:** Phase 1 (Design/Mechanism Validation) — FROZEN  
**Date:** 2026-07-02  
**Plan:** docs/murmur_physics_falsification_plan.md (§0–10)

---

## Overview

This directory contains the implementation harness for deciding whether Murmur's per-actor
irreversibility signals (P1: forward/reverse KL divergence, P2: flux divergence, P3: ensemble,
H2: hybrid) earn their place in the detection stack or get cut.

The evaluation is **asymmetrically epistemic**:
- Synthetic results can KILL the physics signal (if it loses to baselines on fair landscapes)
- Synthetic results can only PROVISIONALLY PASS it (pending real-data confirmation in shadow-mode pilot)

Three possible outcomes:
1. **KILL**: Physics signals do not beat baseline on adversarially fair landscapes → cut the layer
2. **AUGMENT**: Physics survives only as a *feature* inside the context-gated baseline
3. **PROVISIONAL PASS**: Clears the necessary bar → next is shadow-mode GTM milestone

---

## Directory Structure

```
bakeoff/
├── common/
│   ├── __init__.py
│   └── trajectory.py           # Immutable Trajectory + Transition classes (FROZEN)
├── detectors/
│   ├── __init__.py
│   ├── p1_kl.py               # P1 estimator stub (FROZEN signature)
│   ├── p2_flux.py             # P2 estimator stub (FROZEN signature)
│   ├── p3_ensemble.py         # Phase 4: rank-average or stacking
│   ├── h2_hybrid.py           # Phase 4: physics-as-feature inside B1
│   ├── b0_rarity.py           # Phase 3: naive per-edge rarity
│   ├── b1_hopper.py           # Phase 3: Hopper-style rarity + causal context
│   └── b2_ml.py               # Phase 3: shallow ML baseline
├── mechanism_tests/
│   ├── __init__.py
│   ├── test_one_way_vs_loop.py         # Test 1 (Phase 1)
│   ├── test_ness_anchor.py             # Test 2 (Phase 1)
│   ├── test_reversal_sanity.py         # Tests 3a, 3b (Phase 1)
│   ├── test_convergence.py             # Test 4 (Phase 1)
│   └── test_subsampling_robustness.py  # Test 5 (Phase 1)
├── audits/
│   ├── __init__.py
│   ├── fairness_audit.py              # Structural equalization checks (§4.1, Phase 2)
│   ├── leakage_redteam.py             # Cheat detector validation (§4.3, Phase 2)
│   └── grep_leak_check.py             # Label leakage sweep (§4.2, Phase 2)
├── worldgen/
│   ├── __init__.py
│   ├── archetypes.py                  # Benign actor archetypes 1–9 (Phase 2)
│   ├── attacks.py                     # Attack overlays 1–5 (Phase 2)
│   ├── hard_negatives.py              # Hard-negative confounds (Phase 2)
│   ├── anonymizer.py                  # Label scrubbing (Phase 2)
│   └── generator.py                   # Top-level world construction (Phase 2)
├── harness/
│   ├── __init__.py
│   ├── runner.py                      # Orchestrate all detectors on a world (Phase 3+)
│   ├── evaluator.py                   # Alert budget ranking + detection rate (Phase 5)
│   └── bootstrap_ci.py                # Paired bootstrap CI for detector comparison (Phase 5)
├── configs/
│   ├── __init__.py
│   ├── world_config.py                # World + archetype + attack parameters (Phase 2)
│   ├── detector_config.py             # Detector hyperparameters (Phase 3+)
│   └── seed_manager.py                # Seed replay + splitting (Phase 1+)
├── reports/
│   ├── mechanism_test_results.md      # Phase 1 output (test 1–5 results)
│   ├── fairness_audit_log.md          # Phase 2 output (structural checks)
│   ├── dev_world_evaluation.md        # Phase 4 output (detector tuning results)
│   ├── held_out_evaluation.md         # Phase 5 output (final results + bootstrap CIs)
│   └── decision_memo.md               # Phase 6 output (decision + rationale)
├── PREDICTIONS.md                     # FROZEN: pre-registered mechanism test predictions (Phase 1)
├── FREEZE.md                          # Phase 4 gate: all hyperparameters + metric + budget
├── JUDGMENT_CALLS.md                  # Ambiguity resolutions (in baseline's favor)
├── README.md                          # This file
└── __init__.py
```

---

## Phase 1: Mechanism Validation (FROZEN — Design Complete)

### Deliverables (NOW, at start of Phase 1)

1. **bakeoff/common/trajectory.py** ✓
   - Immutable `Transition` and `Trajectory` classes
   - Constructors: `from_state_visits()`, `from_edge_multiset()`
   - Utilities: `state_space()`, `edges()`, `window()`, `time_reversed()`, `truncate()`

2. **bakeoff/detectors/p1_kl.py** ✓
   - **Signature (FROZEN):** `score(traj, *, alpha=1.0) -> float`
   - **Math (docstring):** D_KL(forward ‖ reverse) with Laplace smoothing
   - **Pre-registered alpha:** 1.0 (additive smoothing; NOT to be tuned on world data)
   - **Body:** NotImplementedError (implementation is Phase 1 downstream)

3. **bakeoff/detectors/p2_flux.py** ✓
   - **Signature (FROZEN):** `score(traj, *, aggregation='l1') -> float`
   - **Math (docstring):** per-edge net flux (P_fwd - P_rev), aggregated by L1 norm (primary) or max-edge
   - **Pre-registered aggregation:** 'l1' (NOT to be extended without explicit justification)
   - **Body:** NotImplementedError (implementation is Phase 1 downstream)

4. **bakeoff/PREDICTIONS.md** ✓
   - Pre-registered predictions for tests 1–5 (see below)
   - Confidence levels: HIGH for tests 1–3, MEDIUM for tests 4–5
   - Downstream predictions (Phase 4, recorded now for traceability)

### Acceptance Criteria for Phase 1 Gate

**Tests 1–3 MUST PASS before proceeding to Phase 2.**

| Test | Criterion | Status |
|------|-----------|--------|
| 1: One-way > loop | P1 and P2 both score one-way strictly > loop | REQUIRED |
| 2: NESS anchor | P1 > 0.1 and P2 > 0.2 (entropy rate ≈ 0, flux > 0) | REQUIRED |
| 3a: Reversal swap | D_KL(f\|\|r,T) ≈ D_KL(r\|\|f,rev(T)) | REQUIRED |
| 3b: Detailed balance | P1 ≈ 0 on reversible chains | REQUIRED |
| 4: Convergence | L_min ≤ 50 transitions (or flag if > 100) | MILESTONE OUTPUT |
| 5: Subsampling | Graceful degradation, var < 10% | FLAG IF FAILS; CONTINUE |

**Output:** Commit test results to `bakeoff/reports/mechanism_test_results.md` with the
convergence analysis (test 4) informing §3.1's simulation horizon.

---

## Phase 2: Worldgen + Fairness Audit (Downstream)

**Gate:** Leakage red-team (§4.3) finds nothing; fairness_audit green on 10 trial seeds.

**Deliverables (to be implemented):**
- Benign archetypes (9 types)
- Attack overlays (5 types)
- Hard-negative confounds
- Anonymizer (label scrubbing)
- Fairness audit (structural equalization + cheat detector)

---

## Phase 3: Baselines (Downstream)

**Gate:** On dev worlds, B1 > B0, and false positives dominated by archetypes 6–9 (confounds work).

**Deliverables (to be implemented):**
- B0: naive per-edge rarity
- B1: Hopper-style rarity + causal context (reimplement faithfully)
- B2: shallow ML baseline

---

## Phase 4: Physics + Hybrid on Dev Worlds (Downstream)

**Gate:** Relative-asymmetry formulation implemented; tuning complete; FREEZE.md committed.

**Deliverables (to be implemented):**
- P1/P2 implementations (bodies of stubs)
- P3: ensemble (rank-average or logistic stacking)
- H2: physics-as-feature (B1 + P1/P2 scores as input features)
- Tuning on dev worlds (10 seeds)

**Pre-Phase-4 design decision:**
- Relative formulation: `current_window_asymmetry - trailing_history_asymmetry`
- Absolute asymmetry as secondary ablation (for Phase 4/5 reporting)
- See §5.1 of physics_falsification_plan.md for rationale

---

## Phase 5: Held-Out Evaluation (Downstream)

**Gate:** Run once after FREEZE.md committed.

**Deliverables (to be implemented):**
- Generate N ≥ 20 fresh world seeds (held-out set)
- Run all detectors (B0, B1, B2, P1, P2, P3, H2) on each world
- Compute detection rate at fixed budget K (alerts/day)
- Bootstrap paired CIs on detection-rate differences
- Per-attack-archetype FP composition
- Alert-cause diagnostic breakdown

---

## Phase 6: Decision Memo (Downstream)

**Deliverable (to be written):**
- Outcome determination per §1 criteria (KILL / AUGMENT / PROVISIONAL PASS)
- Headline results table
- Per-attack-type breakdown
- FP composition (which archetypes generate false positives)
- **Living-off-the-land result called out explicitly**
- Limitations (synthetic ⇒ no absolute FP claims; PASS is provisional pending shadow pilot)
- Next action and exit strategy

---

## Key Design Principles

### Epistemic Discipline (§0)

- **Never report absolute FP rates** from synthetic data
- **Synthetic can KILL; can only provisionally PASS**
- **Degrees-of-freedom enforcement** (§7): three-way split (mechanism → dev → held-out)
- **Ambiguity resolves in baseline's favor** (level playing field for physics to prove itself)

### Anti-Cheat Controls (§4)

- **Structural equalization** (§4.1): attack and benign worlds not statistically separable
- **No label leakage** (§4.2): detector sees only anonymized logs
- **Leakage red-team** (§4.3): train dumb cheat detector; must come in at chance
- **Determinism** (§4.4): every world from (config, seed), byte-identical on replay

### Pitfall Checklist (§9)

Re-read at every phase gate:
- [ ] Am I anywhere reporting absolute FP rate?
- [ ] Can any detector see zone names, archetype labels, or generator internals?
- [ ] Did the cheat detector really come out at chance?
- [ ] Is B1 as strong as possible (Hopper-faithful)?
- [ ] Are benign one-way flows (ETL, backups, break-glass) in EVERY world?
- [ ] Is physics score relative to actor's own history (with absolute as ablation only)?
- [ ] Does LOTL attack have zero per-edge rarity signal?
- [ ] Any post-freeze change? Then held-out seeds are burned.
- [ ] Does every result carry the "necessary bar, not sufficient" caveat?

---

## Frozen Interfaces (Phase 1)

### P1 KL-Divergence

```python
def score(traj: Trajectory, *, alpha: float = 1.0) -> float:
    """
    D_KL(forward ‖ reverse) for trajectory.
    
    alpha = 1.0 (Laplace smoothing, pre-registered, NOT to be tuned on world data)
    """
    ...
```

**Math:**
- Forward distribution P_fwd(e) = (count[e] + alpha) / (total + alpha * |E|)
- Reverse distribution P_rev(e) from time-reversed trajectory
- D_KL(fwd ‖ rev) = Σ_e P_fwd(e) * log(P_fwd(e) / P_rev(e))

### P2 Flux Divergence

```python
def score(traj: Trajectory, *, aggregation: Literal["l1", "max_edge"] = "l1") -> float:
    """
    Per-edge net flux aggregated by L1 norm (primary) or max-edge.
    
    aggregation = 'l1' (pre-registered primary, NOT to be extended)
    """
    ...
```

**Math:**
- Per-edge flux: net_flux(e) = P_fwd(e) - P_rev(e)
- Primary (L1): Σ_e |net_flux(e)|
- Secondary (max-edge): max_e |net_flux(e)|

---

## Usage: Building the Trajectory Representation

```python
from bakeoff.common import Trajectory, Transition

# From state visits (uniform time spacing):
traj = Trajectory.from_state_visits(
    actor="user@example.com",
    states=["IDENTITY", "COMPUTE", "DATA", "COMPUTE"],
    actions=["auth", "invoke", "read", "invoke"],
    start_time=0.0,
    dt=1.0
)

# From explicit transitions:
trans = [
    Transition(t=0.0, actor="user@example.com", src="IDENTITY", dst="COMPUTE", action="auth"),
    Transition(t=1.0, actor="user@example.com", src="COMPUTE", dst="DATA", action="read"),
]
traj = Trajectory(trans)

# From edge multiset (for mechanism tests):
traj = Trajectory.from_edge_multiset(
    actor="test",
    edges=[("A", "B", "move"), ("B", "C", "move"), ("B", "A", "move")],
    start_time=0.0,
    dt=1.0
)

# Access:
for trans in traj:
    print(f"{trans.src} --{trans.action}--> {trans.dst}")
print(f"Trajectory has {len(traj)} transitions")
print(f"State space: {traj.state_space()}")

# Utilities:
reversed_traj = traj.time_reversed()
windowed = traj.window(t_start=1.0, t_end=5.0)
truncated = traj.truncate(10)
```

---

## Next Action

**Phase 1 Implementation (downstream agent):**
1. Implement `bakeoff/detectors/p1_kl.py::score()` and `bakeoff/detectors/p2_flux.py::score()`
2. Implement mechanism tests 1–5 using the frozen Trajectory interface
3. Run tests; all of 1–3 must pass; record test 4 output (convergence analysis)
4. Commit results to `bakeoff/reports/mechanism_test_results.md`
5. Proceed to Phase 2 if all gates pass

---

*Frozen: 2026-07-02 — Phase 1 Design Complete*
