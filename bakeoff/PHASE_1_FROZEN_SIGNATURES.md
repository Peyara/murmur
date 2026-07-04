# Phase 1 Frozen Signatures — Physics Estimators

**Status:** FROZEN (do not modify without explicit design revision)  
**Date:** 2026-07-02  
**Purpose:** Specifications for P1 (KL-divergence) and P2 (flux-divergence) estimators.

---

## Overview

These are the FROZEN function signatures that downstream implementation must adhere to.
Modification of these signatures constitutes a design change and requires an explicit
review + justification before proceeding.

**Why frozen?** The estimator interface is the contract between:
1. Mechanism tests (which call these functions on constructed inputs)
2. Phase 2+ world generation (which produces Trajectory objects)
3. Phase 3+ baseline implementations (which need a stable interface)

Changing the interface mid-implementation cascades to all downstream work.

---

## Shared Input Type

**Module:** `bakeoff.common.trajectory`

```python
class Trajectory:
    """
    Time-ordered sequence of transitions for a single actor.
    Immutable. Provides state_space() and edges() introspection.
    
    Constructor: Trajectory(transitions: Sequence[Transition])
    Factories: from_state_visits(...), from_edge_multiset(...)
    Utilities: window(...), time_reversed(), truncate(...)
    """
    pass
```

See `bakeoff/common/trajectory.py` for full interface.

---

## P1: Forward/Reverse KL-Divergence

**File:** `bakeoff/detectors/p1_kl.py`

```python
def score(
    traj: Trajectory,
    *,
    alpha: float = 1.0,
) -> float:
    """
    Compute D_KL(forward ‖ reverse) for a trajectory.

    FROZEN SIGNATURE — do not change.

    Returns:
    --------
    float
        D_KL divergence, always >= 0.
        0 ≈ reversible (detailed balance)
        > 0 = irreversible (forward and reverse distributions diverge)

    Algorithm outline (full specification in docstring):
    1. Estimate forward transition distribution from trajectory:
       P_fwd(e) = (count[e] + alpha) / (total + alpha * |E|)
    2. Estimate reverse distribution from time-reversed trajectory:
       P_rev(e) = (count[e] in reversed traj + alpha) / (total + alpha * |E|)
    3. Compute D_KL(fwd || rev):
       D_KL = sum_e P_fwd(e) * log(P_fwd(e) / P_rev(e))

    Smoothing:
    - alpha = 1.0 (Laplace smoothing, pre-registered)
    - Pre-registered on synthetic chains ONLY, before any world data
    - Unseen edges get alpha pseudo-counts

    Pre-registered parameter (MUST NOT TUNE on world data):
    - alpha: default 1.0

    Edge parameters (NOT pre-registered, may vary):
    - None (all estimator behavior determined by alpha and trajectory)

    Implementation must:
    - Use natural logarithm (math.log)
    - Handle 0 * log(0/x) = 0 correctly
    - NOT normalize by trajectory length or state-space size
    - Raise ValueError if traj is empty
    """
```

### Mathematical Details

D_KL(forward ‖ reverse) is the Kullback-Leibler divergence of the reverse distribution
from the forward distribution. It measures how "surprised" the forward distribution is
by the reverse distribution.

**For a reversible system** (detailed balance, where forward and reverse rates are equal
for every edge), D_KL ≈ 0.

**For an irreversible system** (one-way flows, cycles), D_KL > 0.

---

## P2: Flux Divergence

**File:** `bakeoff/detectors/p2_flux.py`

```python
def score(
    traj: Trajectory,
    *,
    aggregation: Literal["l1", "max_edge"] = "l1",
) -> float:
    """
    Compute per-edge net probability flux and aggregate.

    FROZEN SIGNATURE — do not change.

    Returns:
    --------
    float
        Aggregated net flux, always >= 0.
        0 ≈ reversible (detailed balance)
        > 0 = irreversible (net probability flow)

    Algorithm outline (full specification in docstring):
    1. Count forward and reverse edge occurrences:
       fwd[e] = count in forward trajectory
       rev[e] = count in time-reversed trajectory
    2. Compute empirical flux per edge:
       P_fwd(e) = fwd[e] / total
       P_rev(e) = rev[e] / total
       net_flux(e) = P_fwd(e) - P_rev(e)
    3. Aggregate (primary or secondary):
       L1 norm (primary):
           score = sum_e |net_flux(e)|
       Max-edge (secondary, ablation):
           score = max_e |net_flux(e)|

    Smoothing:
    - NO smoothing applied (unlike P1)
    - Unseen reverse edges naturally contribute 0 to P_rev
    - This asymmetry is intentional (flux is directional)

    Pre-registered parameters (MUST NOT EXTEND):
    - aggregation: 'l1' (primary) or 'max_edge' (secondary ablation)
    - Only these two variants; custom aggregations forbidden

    Implementation must:
    - Use 'l1' as default and primary aggregation
    - Support 'max_edge' for ablation studies only
    - NOT add new aggregation variants without explicit design justification
    - NOT normalize by trajectory length or state-space size in this estimator
    - Raise ValueError if aggregation not in ('l1', 'max_edge')
    - Raise ValueError if traj is empty
    """
```

### Mathematical Details

Net flux per edge measures the asymmetry of probability flow. In a system at detailed balance,
forward and reverse flux are equal on every edge, so net_flux ≈ 0 everywhere.

In an irreversible system (one-way chains, source-sink flows), net flux is positive on
forward-preferring edges and negative (or zero) on reverse-weak edges.

**Primary aggregation (L1 norm):**
Sum of absolute net fluxes. Captures total probability divergence from reversibility.

**Secondary aggregation (max-edge):**
Maximum absolute flux on any single edge. Detects extreme per-edge violations.

---

## Pre-Registered Hyperparameters (Frozen)

### P1 KL-Divergence

| Parameter | Value | Rationale | Tuning Allowed |
|-----------|-------|-----------|---|
| `alpha` (smoothing) | 1.0 | Laplace smoothing; standard in NLP + statistical mechanics. Selected on synthetic chains before world data. | NO — frozen on mechanism tests |

### P2 Flux Divergence

| Parameter | Value | Rationale | Tuning Allowed |
|-----------|-------|-----------|---|
| `aggregation` (primary) | 'l1' | L1 norm is interpretable (total probability divergence) and robust to outlier edges. Pre-registered; max-edge is secondary ablation only. | NO — frozen; only 'l1' and 'max_edge' allowed |

---

## Trajectory Type Contract

Both estimators consume `Trajectory` objects from `bakeoff.common.trajectory.Trajectory`.

**Immutable properties:**
- Single actor (all transitions must be from the same actor)
- Time-ordered (transitions in ascending `t`)
- Non-empty (at least one transition)

**Interface:**

```python
class Trajectory:
    # Properties
    @property
    def actor(self) -> str: ...
    
    @property
    def transitions(self) -> Tuple[Transition, ...]: ...
    
    # Sequence protocol
    def __len__(self) -> int: ...
    def __iter__(self): ...
    def __getitem__(self, index: int) -> Transition: ...
    
    # Introspection
    def state_space(self) -> FrozenSet[str]: ...
    def edges(self) -> Tuple[Tuple[str, str, str], ...]: ...
    
    # Transformation (for mechanism tests)
    def window(self, t_start: float, t_end: float) -> Trajectory: ...
    def time_reversed(self) -> Trajectory: ...
    def truncate(self, length: int) -> Trajectory: ...
```

---

## Mechanism Tests (Phase 1 Validation)

Both estimators will be validated against mechanism tests defined in `bakeoff/PREDICTIONS.md`:

1. **One-way vs. loop:** P1 and P2 score one-way path > equal-length loop
2. **NESS anchor:** Shannon-entropy rate ≈ 0 while P1/P2 > 0
3. **Reversal sanity:** D_KL(f||r, T) ≈ D_KL(r||f, T_reversed)
4. **Convergence:** Minimum trajectory length for stable estimates
5. **Subsampling robustness:** Graceful degradation with missing data

All tests 1–3 must pass before Phase 2 (world generation) proceeds.

---

## Usage Example

```python
from bakeoff.common import Trajectory
from bakeoff.detectors import p1_kl, p2_flux

# Construct a trajectory (e.g., from mechanism test)
traj = Trajectory.from_state_visits(
    actor="test_actor",
    states=["A", "B", "C", "D"],
    actions=["move", "move", "move"],
    start_time=0.0,
    dt=1.0
)

# Call P1 estimator
kl_score = p1_kl.score(traj, alpha=1.0)
print(f"P1 KL-divergence: {kl_score}")

# Call P2 estimator (L1 primary)
flux_l1 = p2_flux.score(traj, aggregation="l1")
print(f"P2 flux (L1): {flux_l1}")

# Call P2 estimator (max-edge ablation)
flux_max = p2_flux.score(traj, aggregation="max_edge")
print(f"P2 flux (max-edge): {flux_max}")
```

---

## Implementation Checklist (Downstream)

Before submission:
- [ ] Implement `p1_kl.score()` body (remove NotImplementedError)
- [ ] Implement `p2_flux.score()` body (remove NotImplementedError)
- [ ] Verify signature matches this document exactly
- [ ] Verify pre-registered parameters are NOT changed (alpha=1.0, aggregation='l1')
- [ ] Implement all mechanism tests (test_*.py)
- [ ] Run tests; all 1–3 must pass
- [ ] Record test 4 output (convergence analysis) to `bakeoff/reports/mechanism_test_results.md`
- [ ] Commit results before proceeding to Phase 2

---

## Change Control

**To modify these signatures:**
1. Clearly document the change rationale
2. Update this file and `bakeoff/PREDICTIONS.md` in lockstep
3. Re-run mechanism tests (all three must still pass)
4. Update any downstream implementation that depends on the changed signature
5. Document the change as a design decision in LEARNINGS.md

**Do NOT modify signatures mid-Phase-1 without explicit justification.**

---

*Frozen: 2026-07-02*
