# Phase 1 Mechanism Tests — Pre-Registered Predictions

**Date:** 2026-07-02  
**Phase:** 1 (Mechanism validation, §6.3 of murmur_physics_falsification_plan.md)  
**Status:** FROZEN — these predictions are made BEFORE any implementation or test execution.

---

## Epistemic Frame

Phase 1 tests **validation question #1: mechanism correctness** on constructed inputs.
No world generation, no attack/benign overlays, no synthesis. Pure estimator validation.

The predictions below reflect the theoretical properties of D_KL-divergence and flux asymmetry
on the specific constructed landscapes described in §6.3. Each prediction includes:
- **Hypothesis**: what the test should observe
- **Confidence**: HIGH / MEDIUM / LOW
- **Rationale**: why we expect this outcome
- **Pass threshold**: the decision rule for the mechanism test

---

## Test 1: One-Way vs. Loop

**Hypothesis:**  
P1 and P2 both assign *strictly higher* scores to a one-directional path than to a closed loop
of equal length and equal edge count.

**Constructed input:**
- Loop: A → B → C → A → B → C (3 edges, traversed twice)
- One-way: A → B → C → D → E → F (6 distinct edges, each traversed once)

Actually, for equal-length and equal-edge-count comparison:
- Loop (3 edges): A → B → C → A → B → C → A → B → C (9 transitions, revisit all edges 3× forward)
- One-way (3 transitions): A → B → C → D → E → F (5 transitions, all forward, terminal state F never revisited backward)

**Better construction:**
- Loop: A → B → A → B → A → B (2 edges, 5 transitions, cyclic)
- One-way: A → B → C → D → E → F (5 edges, 5 transitions, acyclic, each edge traversed once)

In the loop:
- Forward: P_fwd(A↔B) = 0.5 each direction
- Reverse (time-reversed): P_rev(A↔B) = 0.5 each direction (by symmetry)
- D_KL(fwd ‖ rev) ≈ 0 (detailed balance holds)
- Flux: net_flux(A→B) ≈ 0, net_flux(B→A) ≈ 0

In the one-way:
- Forward: P_fwd(A→B) = 0.2, P_fwd(B→C) = 0.2, ..., P_fwd(E→F) = 0.2 (uniform over 5 edges)
- Reverse: P_rev(A→B) ≈ 0, P_rev(B→A) = 0.2, P_rev(C→B) = 0.2, ..., P_rev(F→E) = 0.2
  (time-reversed, the path becomes F → E → D → C → B → A)
- D_KL(fwd ‖ rev) > 0 (forward distribution is concentrated on forward edges, reverse on reverse edges)
- Flux: net_flux(A→B) ≈ 0.2, net_flux(B→C) ≈ 0.2, ..., net_flux(E→F) ≈ 0.2
  (all edges have positive flux; L1 ≈ 1.0)

**Confidence:** HIGH  
**Rationale:** This is the foundational property of irreversibility measures. If P1/P2 fail here,
the implementation is fundamentally broken.

**Pass threshold:**
- P1(one-way) > P1(loop), with difference > 0.1 in D_KL absolute units
- P2(one-way) > P2(loop), with difference > 0.2 in L1 norm absolute units
- Both pass: PROCEED
- Either fails: FIX IMPLEMENTATION, re-run test 1 only

---

## Test 2: NESS Anchor (Non-Equilibrium Steady State)

**Hypothesis:**  
Construct a 3-state non-equilibrium steady state with constant occupation probabilities but
nonzero cycle flux (A → B → C → A, with occupation π_A = π_B = π_C = 1/3 but unequal edge rates).

Shannon-entropy rate of change ≈ 0 (because H(t) ≈ 0 if occupations are constant).
Yet D_KL and flux divergence should read *strongly positive* (because the flux is not balanced).

This tests that P1/P2 discriminate based on directedness, not surprise-reduction.

**Constructed input:**
- A → B (forward rate 0.3, reverse rate 0.1)
- B → C (forward rate 0.3, reverse rate 0.1)
- C → A (forward rate 0.3, reverse rate 0.1)
- Reverse direction: B → A (0.1), C → B (0.1), A → C (0.1)

Steady-state occupation: π = (1/3, 1/3, 1/3) by symmetry.
Cycle flux: forward flux 0.3 / 3 ≈ 0.1 per edge (steady state).
Total in/out per node balanced (steady state confirmed).

Entropy rate: dH/dt ≈ 0 (occupations constant).

D_KL: 
- P_fwd(A→B) = 0.3 / 0.9 ≈ 0.33 (forward direction dominates)
- P_rev(A→B) = 0.1 / 0.3 ≈ 0.33 (reverse direction)
- But the reverse trajectory reads B → A, C → B, A → C, with same 0.33 each
- D_KL(fwd ‖ rev): forward edges (A→B, B→C, C→A) have P_fwd ≈ 0.33 each
  reverse edges (B→A, C→B, A→C) have P_rev ≈ 0.33 each
- These are NOT the same edges in reverse; D_KL will penalize the mismatch.

Wait, I need to be more careful. Let me reconsider.

A NESS with cycle flux means:
- Forward cycle A → B → C → A has nonzero net flux
- Reverse cycle A ← B ← C ← A has equal magnitude but opposite flux

So in time-reversal:
- Forward distribution becomes: A → C, B → A, C → B (the reverse edges)
- Reverse distribution becomes: A → B, B → C, C → A (the forward edges)

If forward and reverse are NOT symmetric, D_KL will be nonzero.

Better construction: 
- Trajectory: A → B → C → A → B → C → ... (n repetitions of the cycle)
- This has cycle flux forward, zero cycle flux backward (no reverse edges visited)
- Forward distribution: P_fwd(A→B) = P_fwd(B→C) = P_fwd(C→A) = 1/3
- Reverse distribution: reversed trajectory is ...C→B→A→C→B→A, so P_rev(C→B) = P_rev(B→A) = P_rev(A→C) = 1/3
- D_KL: forward edges have P_fwd = 1/3, zero P_rev. Reverse edges have P_rev = 1/3, zero P_fwd.
- D_KL(fwd ‖ rev) = sum_e (1/3) * log((1/3) / 0) where forward edges, plus zero where reverse.
- This is actually infinite because of the log(1/0) term (unless we smooth).

With smoothing (alpha = 1.0):
- P_fwd(A→B) = (1 + 1) / (3 + 1*6) ≈ 2/9
- P_rev(A→B) = (0 + 1) / (3 + 1*6) ≈ 1/9
- D_KL ≈ (2/9) * log(2/1) * 3 (for 3 forward edges) ≈ 0.23 * 3 ≈ 0.69

**Confidence:** HIGH  
**Rationale:** A NESS is the canonical case where entropy rate is zero but flux is nonzero.
P1/P2 should capture this, unlike Shannon entropy.

**Pass threshold:**
- P1(NESS) > 0.1 (strongly positive D_KL)
- P2(NESS) > 0.2 (L1 flux significant)
- Both pass: PROCEED
- Either fails: FIX IMPLEMENTATION, re-run test 2 only

---

## Test 3: Reversal Sanity and Detailed Balance

**Hypothesis (3a — Reversal swap):**  
Time-reversing a trajectory swaps D_KL(forward ‖ reverse) ↔ D_KL(reverse ‖ forward).
That is: D_KL(fwd ‖ rev) on trajectory T equals D_KL(rev ‖ fwd) on time-reversed(T).

**Constructed input:**
- T: A → B → C → D (asymmetric one-way path)
- T_reversed: D ← C ← B ← A (time-reversed)

For T:
- P_fwd: A→B=0.25, B→C=0.25, C→D=0.25, D→A=0, ...
- P_rev (reversed): D→C=0.25, C→B=0.25, B→A=0.25, A→D=0, ...
- D_KL(fwd ‖ rev) large (forward edges absent in reverse distribution)

For T_reversed:
- P_fwd (time-reversed): D→C=0.25, C→B=0.25, B→A=0.25, A→D=0, ...
- P_rev (double-reversed, back to original order): A→B=0.25, B→C=0.25, C→D=0.25, D→A=0, ...
- D_KL(fwd ‖ rev) = same value (forward and reverse swapped positions)

**Confidence:** HIGH  
**Rationale:** This is a mathematical property of D_KL and time-reversal symmetry.

**Pass threshold:**
- |D_KL(fwd ‖ rev, T) - D_KL(rev ‖ fwd, T_reversed)| < 0.01 (numerical precision)
- PROCEED if true

**Hypothesis (3b — Detailed balance):**  
A truly reversible trajectory (detailed-balance chain, where forward and reverse distributions
are identical) must score D_KL ≈ 0 in expectation.

**Constructed input:**
- Random walk on a symmetric graph: A ↔ B ↔ C ↔ A, with each edge equally likely in both directions
- Trajectory sampled uniformly: A→B, B→A, B→C, C→B, C→A, A→C, ... (equal forward/reverse empirical counts)

For a long trajectory:
- P_fwd(A↔B) ≈ 0.33, P_rev(A↔B) ≈ 0.33 (symmetric)
- D_KL(fwd ‖ rev) ≈ 0

**Confidence:** HIGH  
**Rationale:** Detailed balance is the definition of reversibility. If P1 scores ≠ 0 here,
it is broken.

**Pass threshold:**
- P1(detailed_balance) < 0.01 (near zero)
- PROCEED if true

---

## Test 4: Estimator Convergence (Minimum Trajectory Length)

**Hypothesis:**  
There exists a finite minimum trajectory length L_min such that P1/P2 estimates stabilize
(within ±10% of their asymptotic value) for trajectories of length ≥ L_min.

This length must be **plausible for IAM audit logs** — i.e., something an actor can accumulate
in a reasonable observation window (order 10–100 transitions per window).

If L_min > 1000 transitions per actor-window, that is a KILL-relevant finding — the estimators
require too much data to be practical.

**Constructed input:**
- Known-asymmetry chain: A → B → C → A → B → C → ... (cyclic but with forward-direction bias,
  or a pure one-way chain A → B → C → ... → Z).
- Compute P1 and P2 for trajectory lengths 1, 2, 3, ..., 100
- Observe: at what length does the score stabilize?

**Confidence:** MEDIUM  
**Rationale:** Estimators need sufficient data to converge. The minimum length depends on
the state-space size and smoothing. We don't know a priori whether it's 5 or 500.

**Pass threshold:**
- L_min ≤ 50 (conservative upper bound for IAM windows)
- Score variance (across random subsamples of length L_min) < 20% of mean
- If L_min > 100: flag as POTENTIAL KILL, but continue to Phase 2 (world evaluation may show
  differently in realistic mixture)
- If L_min > 500: KILL-relevant finding, escalate to decision memo

---

## Test 5: Subsampling Robustness

**Hypothesis:**  
Dropping 10%, 30%, or 50% of events uniformly at random does not cause wild score fluctuations.
Scores should degrade gracefully (linearly proportional to remaining data), not chaotically.

**Constructed input:**
- Full trajectory of length 100
- Subsample at 90%, 70%, 50% retention rates
- Compute P1/P2 on each subsample
- Plot score vs. retention rate
- Check: is the plot smooth and monotonic, or noisy?

**Confidence:** MEDIUM  
**Rationale:** Real audit logs have gaps (buffering, sampling, retention windows).
Robustness to missing data is table-stakes.

**Pass threshold:**
- Score ratio between 90% and 50% retention is within [0.5, 0.9] of the full score
  (i.e., score is proportional to data, with graceful degradation)
- Variance of score over 5 random subsamples at each retention rate < 10% of mean
- If either fails: flag as POTENTIAL ISSUE, but do not block Phase 2 (world evaluation may
  show robustness in the presence of realistic noise/jitter)

---

## Downstream Predictions (Phase 4 and beyond — recorded now for closure)

These are **NOT** tested in Phase 1. Recorded here for traceability.

### P1 likely FAILS on living-off-the-land attacks (Phase 4 hypothesis)

**Why:** Living-off-the-land (LOTL) attacks use only edges that exist benignly in the actor's
own history, altering only sequencing/direction/rate. P1 is a per-window distribution-based
measure; it cannot distinguish "same edges, different order" unless the order itself produces
directionality asymmetry.

Example: ETL account normally does IDENTITY → SECRET → DATA → EXTERNAL.
LOTL variant: same edges, traversed backward or interleaved: EXTERNAL → DATA → SECRET → IDENTITY.
Per-window, both visit the same (src, dst, action) pairs. The transition distribution is identical.
D_KL ≈ 0.

**Mitigation:** P2 (flux-based) may catch this via sink accumulation (EXTERNAL visited but not exited),
but only if the LOTL significantly alters the edge direction (e.g., uses read on DATA heavily in
reverse, which is semiotically different from the benign direction).

### P2 may catch LOTL via sink accumulation

**Why:** Flux divergence is directional. If LOTL causes a resource (e.g., EXTERNAL) to accumulate
net inflow that wasn't there benignly, P2 will score positive.

### Ensemble (P1 + P2) concentrates value on LOTL

**Why:** P1 may miss it, but P2 catches some; rank-averaging or logistic stacking will learn to
upweight P2 on suspicious windows.

---

## Summary Table: Mechanism Test Pass/Fail Criteria

| Test | Estimator | Pass Criterion | Confidence | Action if Fail |
|------|-----------|----------------|------------|---|
| 1: One-way vs loop | P1 | score(oneway) > score(loop) by > 0.1 | HIGH | Fix implementation |
| 1: One-way vs loop | P2 | score(oneway) > score(loop) by > 0.2 | HIGH | Fix implementation |
| 2: NESS anchor | P1 | score > 0.1 | HIGH | Fix implementation |
| 2: NESS anchor | P2 | score > 0.2 | HIGH | Fix implementation |
| 3a: Reversal swap | P1 | |D_KL(f\|\|r,T) - D_KL(r\|\|f,rev(T))| < 0.01 | HIGH | Fix implementation |
| 3b: Detailed balance | P1 | score < 0.01 | HIGH | Fix implementation |
| 4: Convergence | P1, P2 | L_min ≤ 50, variance < 20% | MEDIUM | Flag if > 100; escalate if > 500 |
| 5: Subsampling | P1, P2 | Graceful degradation, var < 10% | MEDIUM | Flag as potential issue; continue |

---

## Implementation Freeze

**Before running tests:** Confirm that `bakeoff/detectors/p1_kl.py` and `bakeoff/detectors/p2_flux.py`
have the exact signatures defined in Phase 1 design, with alpha = 1.0 and aggregation = 'l1' as
pre-registered defaults.

**After tests 1–3 pass:** Commit test results and the convergence analysis (test 4 output) to
`bakeoff/reports/mechanism_test_results.md`. This is the gate for Phase 2 world generation.

---

*Predictions frozen: 2026-07-02*

---

# POST-RUN ADDENDUM (2026-07-02, after execution + human review)

> The frozen predictions above are NOT edited. This addendum records observed-vs-predicted
> divergence and corrections found in human review of the workflow output.

## Observed vs predicted

| Test | Predicted | Observed | Verdict |
|------|-----------|----------|---------|
| 1 One-way vs loop | one-way > loop, both estimators | P1 0.231 vs 0.017; P2 2.0 vs 0.222 | ✅ as predicted |
| 2 NESS anchor | entropy-rate≈0, P1/P2≫0 | rate 0.0; P1 1.005; P2 1.32 | ✅ as predicted |
| 3a Reversal | **[see correction]** | — | ⚠️ test was vacuous; corrected |
| 3b Detailed balance | ~0 | P1 0.0; P2 0.0 | ✅ as predicted |
| 4 Convergence | **L_min ≤ 50 to pass; >100 potential KILL** | **L_min = 80 (P1), 20 (P2)** | ⚠️ **fails frozen bar; see below** |
| 5 Subsampling | graceful/monotonic | monotonic; P1 range 0.21, P2 0.11 | ✅ as predicted |

**Estimator math confirmed correct on independent human recompute** (P1 = D_KL(forward‖transpose),
Laplace-smoothed; P2 = L1 net-flux). One-way P1=0.231 and P2=2.0 reproduced by hand.

## Correction 1 — Test 3a was vacuous (fixed 2026-07-02)
Original 3a scored a *detailed-balance* chain in both orientations and asserted equality; on a
reversible chain both scores are ~0, so it proved nothing (a direction-blind estimator passes it).
Rewritten to test on an *irreversible* one-way path: both KL orientations must exceed a 0.1
directionality floor (they do: 0.231 each). Non-vacuous.

## Correction 2 — Degrees-of-freedom violation on the convergence gate (FLAGGED, §7)
The frozen Test-4 bar (this file, above) is **L_min ≤ 50 to pass, >100 = potential KILL**. The
implementation (`test_mechanism.py`) silently used **>200 = kill**, and reported observed L_min=80 as
"plausible_for_iam." The pass criterion was moved post-hoc, converting a flag into a pass. Under the
**frozen** bar, L_min=80 does NOT cleanly pass.

## Correction 3 — Convergence contradicts measured real-data granularity
Independent of the frozen bar: our real benign DBs (murmur.duckdb / murmur_rd.duckdb) show
**median 11 / mean 17.7 transitions per 15-min window, ~1.48 actors/window → ~8–12 transitions per
actor per 15-min window.** P1 needs 80, P2 needs 20. So at 15-min granularity **P1 is data-starved
~7×, P2 is below the median.** Also: convergence was measured on a *3-state* chain; by Han et al.
(n ~ S²/log S), a realistic 6–7-zone graph needs MORE, so 80 is a floor, not a ceiling.

### Architectural consequence (decided in Phase 2, pre-registered here)
Do NOT score physics on fixed 15-min clock windows. Score P1/P2 over a **per-actor rolling window of
the last N ≥ L_min transitions** (decouples from the 15-min clock; gives estimators enough data).
Cost: physics contributes nothing until an actor accumulates N transitions (cold-start blind spot —
acceptable; new actors handled by novelty/other signals). Simulation horizon (§3.1) must give each
actor ≫ 80 transitions.

## Sharpened downstream prediction — P1's niche is narrow (pre-registered before Phase 4)
P1 now faces a **pincer**: (a) it needs ≥80 transitions to be stable, so it structurally **cannot
score fast/few-transition attacks** (smash-and-grab) from cold; and (b) as predicted, it is
**blind to living-off-the-land** (LOTL reuses the actor's own forward edges — directionality
preserved, so KL ≈ unchanged). P1's only viable niche is **slow, multi-transition, genuinely
directional** attacks (slow-exfil, lateral movement over many steps). **P2** (needs only 20;
catches sink accumulation via node-level divergence) is the more promising instrument and is
predicted to carry the ensemble. If neither P2 nor the H2 hybrid beats B1 on the hostile/LOTL
worlds, that is the KILL.

*(Note: an earlier draft of the downstream prediction mis-described LOTL as a path *reversal*
ending at IDENTITY — that would change directionality and be detectable. The spec's LOTL (§3.2#4)
preserves the forward path and alters rate/order/destination; that is the version that defeats P1.)*

*Addendum frozen: 2026-07-02 (post-run)*

---

# PHYSICS FORMULATION DECISION (2026-07-03)

Confirmed with the user (physicist by training): the full-throated physics attempt is the
*strongest* formulation, judged at the *same* strict bar (≥5pp lift vs B1, ties→KILL). Retaining
physics that only survives a weakened test = keeping a story, not a signal (= sprawl). So:

## Headline physics variant (replaces "absolute P1" as primary — NOT a new detector; scope intact)
**P1e — excess (nonadiabatic) entropy production.** Score = `D_KL(current rolling-window transition
distribution ‖ the actor's own trailing steady-state transition distribution)`. This grounds §5.1's
mandated relative score as the **Hatano–Sasa nonadiabatic EP**: benign automation is a nonequilibrium
steady state (NESS) whose persistent currents are **housekeeping** (large but structural → ~0 excess);
an attack **drives the actor off its own steady state** → positive **excess**. The rolling window is
N ≥ 80 transitions (locked decision 1).

Retained as secondary/ablation within the frozen 7: P1 (absolute forward/reverse KL), P2 (flux/sink
divergence — kept as the primary flux instrument), P3 = rank-avg(P1e, P2), H2 = B1 + {P1e, P2} features.

## Pre-registered predictions (BEFORE Phase 4)
- **P1e treats the hard negatives (ETL/backup/break-glass one-way benign) as ~0** (housekeeping) →
  far fewer FPs than absolute P1/P2. Confidence: HIGH. *(This is the whole point of the reformulation.)*
- **P1e catches living-off-the-land** (novel order + ~10× rate = departure from the baseline NESS →
  excess > 0) where absolute forward/reverse KL is blind. **This REVERSES the earlier "P1 dies on LOTL"
  prediction.** Confidence: MEDIUM (contingent on the rate/structure deviation being estimable with the
  per-actor data available in the rolling window).
- **P1e is MORE data-hungry** than P1 — it needs a stable trailing-baseline NESS estimate *and* a
  current window → cold-start / sparse-actor blind spot is worse. Risk, not prediction.
- **Crux (bar unchanged):** excess EP *is* a KL-from-own-baseline, and B1 is also "deviates from
  history." Does the thermodynamically-principled form deliver ≥5pp lift over B1's rarity+causal-context,
  or is it the same information in physics clothing? If no ≥5pp lift → **KILL** (physics real, no
  operational edge — a legitimate, physically-interesting negative).

## Deferred (anti-sprawl)
Large-deviation / fluctuation-theorem framing (rare current under the benign NESS rate function) —
noted as a possibly stronger instrument, DEFERRED. Not in scope unless P1e shows promise and the user
opts in. One physics variant on trial, not three.

*Physics decision frozen: 2026-07-03*
