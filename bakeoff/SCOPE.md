# bakeoff/ — Frozen Scope & Anti-Sprawl Contract

**Date:** 2026-07-03 · **Status:** BINDING on all phases from here forward.

> This session exists because Murmur sprawled (10 fusion signals, 11 invariants, 19 R&D reports,
> ~8 underperforming detectors). A falsification harness is a prime candidate to become the *next*
> sprawl. This contract prevents that. Anything not on the closed lists below requires an explicit
> one-line justification AND user sign-off. Extend before create. Delete before keep.

## Purpose (the ONLY thing this harness does)
Produce ONE decision — **KILL / AUGMENT / PROVISIONAL-PASS** — on the physics irreversibility signal,
per the criteria in `docs/murmur_physics_falsification_plan.md` §1. Not a platform. Not a library.
Not a permanent subsystem.

## CLOSED SETS (frozen — no additions without sign-off)
- **Detectors (7, final):** B0 rarity, B1 Hopper-core, B2 shallow-ML, P1 KL, P2 flux, P3 = rank-avg(P1,P2),
  H2 = B1 + P1/P2 features. Schnakenberg excluded (documented). **No new detectors, no new variants,
  no new aggregations** beyond the pre-registered ones (P2: l1 primary, max_edge ablation only).
- **Attacks (5):** credential_theft_lateral, slow_exfil, smash_and_grab, living_off_the_land, sa_hijack.
- **Benign archetypes (9)** and **hard negatives (3)** exactly as specified. No new types.
- **Metrics:** detection@fixed-budget (primary), AUC-PR, per-archetype FP composition, time-to-first-
  detection, per-attack breakdown. **No new metrics.** (ROC-AUC is banned — §6.1.)
- **Hyperparameters:** frozen in `FREEZE.md` before held-out evaluation. **No post-hoc knobs.**

## REPORT DISCIPLINE (fights R&D sprawl)
- **One deliverable: `DECISION_MEMO.md`.** Interim artifacts (`PREDICTIONS.md`, `reports/phase2_fairness.md`,
  mechanism results) are scratch that **fold into the memo** — they are not maintained as parallel
  narratives. When the memo is written, prune the scratch.
- Do NOT create a new report per idea. One memo, updated.

## THE BIAS IS TOWARD CUTTING
- Ties resolve to KILL. Burden of proof is on physics. A signal must add **≥5pp** lift or it dies.
- **If KILL:** the memo MUST include the explicit deletion list — which `src/` code leaves Murmur
  (`src/score/physics.py`, `sigma_coarse`/`delta_f`, Schnakenberg in `src/world/graph.py`, related
  fusion weights, theory docs). The purpose of this harness is to *enable a cut*, not to add scaffolding
  that outlives its question.
- **If PASS/AUGMENT:** exactly ONE new signal (P2 or the hybrid) enters Murmur and **replaces** the dead
  physics code — it does not stack on top of it.
- **After the decision:** `bakeoff/` is archived or removed. It is R&D scaffolding, not product.

## CONCEPT DISCIPLINE (Murmur-wide — the real gut-renovation)
- Physics is the **first** cut candidate, not the only one. The ~8 underperforming signals
  (`novelty`, `bridge_new`, etc.) are queued for the same KILL/keep treatment.
- **No new detection concepts enter Murmur** until the existing sprawl is trimmed. closure_gap (3.3×)
  and inv_score (2.2×) carry the system; the default answer to "add a signal" is no.

*If you (agent or human) find yourself adding a file, detector, metric, or report not listed above —
stop, and get one-line sign-off first.*
