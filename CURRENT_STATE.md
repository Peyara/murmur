# Murmur — Current State

> Resume point for new sessions. Read this first.

## Active work

**Physics-signal falsification bake-off** (`bakeoff/`). Autonomous session 2026-07-03 produced an
**INTERIM verdict: strong KILL-lean** on the physics irreversibility signal. See
`bakeoff/DECISION_MEMO.md` (the single deliverable) and `bakeoff/AUTONOMOUS_SESSION_LOG.md` (every
judgment call I took while you were out, for review).

## Headline finding

On a balanced dev landscape (20 campaigns/flavor, LOTL present):
- **P1e (excess/nonadiabatic EP) is structurally blind to living-off-the-land** (×0.01 vs benign) —
  LOTL preserves the actor's own edge distribution, so `D_KL(window‖baseline)≈0` by construction.
- **P2 (flux) discriminates nothing** — benign housekeeping is maximal.
- P1e's only strong win (ServiceAccountHijack ×7.55) coincides with a **landscape leak** a dumb shallow
  cheat detector also catches (AUC-PR 0.70) → not evidence of independent physics value.
- The reformulation *did* solve its confound (benign housekeeping → 0.000), but that revealed the signal
  has nothing left to catch.

## Not yet done (blocks a FINAL gated verdict)

1. **De-rig the landscape.** Fairness gate FAILS: shallow features (`edge_diversity_ratio`, degree)
   separate SA-hijack (0.70) and cred-theft (0.54). Generator must equalize those between attacks and
   their hard-negative twins. (LOTL's physics-death does NOT depend on this — it's robust.)
2. **Build B1 (Hopper-core) + per-instance detection@budget.** The gated criterion is "physics beats B1
   by ≥5pp." Prediction after both: **KILL**.

## What's built and working (reusable regardless of verdict)

- `bakeoff/worldgen/` — balanced per-flavor campaign generator (attack-instance = eval unit), anonymizer,
  hard negatives. `bakeoff/detectors/` — P1e (excess-EP), P2 (flux), P1 (legacy KL). `bakeoff/harness/` —
  per-instance eval + `dev_read.py`. `bakeoff/audits/` — instance-grouped leakage red-team, fairness,
  grep-leak. `bakeoff/PREDICTIONS.md` (frozen predictions + physics-formulation decision), `SCOPE.md`
  (anti-sprawl contract), `SANDBOX_CONTRACT.md`.

## Next move (recommended)

De-rig landscape → build B1 → run the gated comparison. If KILL confirmed, execute the `src/` deletion
list in DECISION_MEMO §6 (physics.py, Schnakenberg in graph.py, sigma_coarse/delta_f + fusion weights,
theory docs). Committed on `gut-renovation` (not pushed).

## Branch

`gut-renovation` — holds the bake-off + this session's commits. Not pushed; push/PR left for review.
