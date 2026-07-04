# Physics Signal — Decision Memo (INTERIM)

**Date:** 2026-07-03 (autonomous session) · **Status:** INTERIM — strong KILL-lean, not yet the final
gated verdict (final requires a de-rigged landscape + the B1 baseline comparison; see §5).
**Single deliverable per `SCOPE.md`.** Supersedes the scratch reports.

---

## 1. Verdict (interim): physics is not earning its place

On a balanced dev landscape (20 campaigns/flavor, **LivingOffTheLand present**), the physics signals
(P1e excess-EP, P2 flux) **do not discriminate attacks from benign except where the landscape leaks a
trivial artifact.** The crown-jewel prediction is refuted. Lean: **KILL**, pending the two confirmations in §5.

## 2. The evidence (DEV read — `bakeoff/harness/dev_read.py`)

**P1e — excess/nonadiabatic EP (headline physics variant):**

| Flavor | P1e vs benign (0.145) | Read |
|---|---|---|
| ServiceAccountHijack | ×7.55 | Strong — **but** see §4: this flavor is landscape-leaked (a dumb cheat also catches it, AUC-PR 0.70). |
| SmashAndGrab | ×1.71 | Marginal (and it's the exempt easy anchor). |
| CredentialTheftLateral | ×1.35 | Marginal. |
| SlowExfiltration | ×1.16 | ~Noise. |
| **LivingOffTheLand** | **×0.01 (0.001)** | **DEAD — the decisive result.** |
| Housekeeping (ETL/backup) | 0.000 | ✓ Correctly ignored (the one prediction that held). |

**P2 — flux divergence:** no discrimination — benign ≥ attack across every flavor; housekeeping is
*maximal* (2.000). Absolute flux fires more on benign one-way automation than on attacks. Refuted.

## 3. The decisive finding (robust, physics-grounded)

**P1e is structurally blind to living-off-the-land.** LOTL reuses the actor's *own* edges (novel
order/rate, same edge set), so the window's transition *distribution* matches the actor's baseline
distribution → `D_KL(window ‖ baseline) ≈ 0` **by construction.** Excess-EP measures distributional
departure; LOTL preserves the distribution. This is architectural, not a tuning issue, and it is robust
to the landscape rigging (LOTL is the one flavor the rigging does *not* make easier).

This **refutes the 2026-07-03 reversal prediction** (that excess-EP would catch LOTL). The original
2026-07-01/02 prediction — physics blind to LOTL — holds for P1e as well as P1.

## 4. What the reformulation *did* buy (honest credit) — and why it's not enough

Excess-EP **did** solve the confound it was designed for: benign housekeeping (ETL/backup one-way NESS)
scores **0.000** — the "benign is also irreversible" problem is genuinely dissolved. But once
housekeeping is correctly zeroed, **the signal has nothing left to catch**: the honest attacks (LOTL)
preserve the actor's distribution and score ~0 too, and the only strong positive (SA-hijack) rides a
landscape leak. Solving the confound revealed the signal's emptiness rather than a hidden niche.

## 5. Two steps to a FINAL verdict (and the prediction)

The interim verdict is not yet the formal gated KILL, because:
1. **Landscape is RIGGED** (fairness gate FAILS): a shallow cheat separates SA-hijack (0.70) and
   cred-theft (0.54) via `edge_diversity_ratio`/degree. **Methodological blocker** — the generator must
   equalize degree/edge-diversity between attacks and their hard-negative twins before the non-LOTL
   flavors can be judged. (LOTL's physics-death does not depend on this.)
2. **No B1 baseline yet.** The gated criterion is "physics beats B1 (Hopper-core) by ≥5pp." Not built.

**Prediction (pre-registered):** after de-rigging, physics **KILL** — P1e's one niche (regular-SA
deviation) will be caught at least as well by B1's rarity+causal-context (a CI account suddenly hitting
SECRET→EXTERNAL is a rare directed edge), so physics adds no independent ≥5pp lift; and it is dead on LOTL.

## 6. If KILL is confirmed — `src/` deletion list (RECOMMENDATION for human execution; NOT auto-applied)

- `src/score/physics.py` (delta_f / sigma_coarse consumer)
- Schnakenberg entropy in `src/world/graph.py` (`schnakenberg_entropy`, the skip-rule block)
- `sigma_coarse` / `delta_f` columns + their fusion weights in the scoring stack
- The ~200 lines of Schnakenberg theory docs with no empirical support
- Murmur's differentiation then rests on provenance-subtraction + self-learning, with closure_gap (3.3×)
  and inv_score (2.2×) carrying detection — consistent with the `gut-renovation` de-sprawl thesis.

## 7. Caveats (do not overstate)
- DEV-only, exploratory; not the frozen held-out verdict.
- No baseline comparison yet (the actual gate).
- Landscape rigged for non-LOTL flavors → those separations are not yet trustworthy (LOTL is).
- Pre-registered hyperparameters, no tuning. Synthetic sandbox (no real-data confirmation).
- The harness itself (balanced allocation, instance-grouped fairness, P1e/P2, per-instance eval) is now
  built and working — that infrastructure is the reusable outcome even under KILL.
