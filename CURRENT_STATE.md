# Murmur — Current State

> Resume point for new sessions. Read this first.

## Active work

**Physics-signal falsification bake-off** (`bakeoff/`). Interim verdict reached and merged to `main`.

## Last completed milestone

**2026-07-04:** PR #39 merged to `main` — bake-off harness (attack-instance eval unit, balanced
per-flavor campaign generator, instance-grouped fairness gate, P1e excess-EP + P2 detectors, per-instance
eval), **interim KILL-lean verdict** (`bakeoff/DECISION_MEMO.md`), and current theory
(`docs/theory/detection_signal_theory.md`). Autonomous judgment calls logged in
`bakeoff/AUTONOMOUS_SESSION_LOG.md`.

## Open blockers / questions

1. **Landscape is RIGGED** — fairness gate fails: shallow features separate SA-hijack (0.70) & cred-theft
   (0.54). De-rig: equalize degree/edge-diversity between attacks and their hard-negative twins.
2. **No B1 baseline** — the gated criterion is "physics beats B1 (Hopper-core) by ≥5pp"; not built.
3. **External validity (biggest risk):** does "benign housekeeping → 0" survive noisy real data? Only a
   real-data shadow pilot resolves it.
4. **P1e is LOTL-blind** (structural) — a final instrument likely needs an order/rate/sequence measure.

## Files to read for context

- `bakeoff/DECISION_MEMO.md` — interim verdict + evidence + the `src/` deletion list (if KILL).
- `docs/theory/detection_signal_theory.md` — current understanding + open questions (§5).
- `bakeoff/PREDICTIONS.md` — frozen predictions + physics-formulation decision.
- `bakeoff/SCOPE.md` — anti-sprawl contract. `bakeoff/AUTONOMOUS_SESSION_LOG.md` — judgment calls.
- `LEARNINGS.md` (top entry) — this session.

## What to do next

**Branch off `main`** (e.g. `feature/bakeoff-b1-baseline`), then: (1) de-rig the landscape (blocker #1);
(2) build B1 Hopper-core + run the per-instance ≥5pp gated comparison; (3) render the FINAL verdict. If
KILL confirmed, execute DECISION_MEMO §6 (`src/` deletion) on its own branch + PR. Prediction: KILL.

## Branches

`main` = current baseline (PR #39 merged). `gut-renovation` kept (merged, not deleted).
