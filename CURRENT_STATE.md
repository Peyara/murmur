# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 2 — Attack Generator + Robustness Validation.** Reactivated Session Q because the Phase B pivot condition (>80% detection across parameterized attack-strategy grid) was never verified. Sprint 3 (provenance/closure) deferred until after the Sprint 2 gate.

## Last Completed Milestone

Session Q (2026-04-27): PR #34 merged — large-scale validation harness + threshold recalibration (HIGH 8.0→4.5, MED 5.0→3.4, WATCH 3.0→2.0) + Session P LEARNINGS restore. Plan for Sprint 2 grid written into `docs/sprints/sprint_02_attack_robustness.md` "Execution Plan (Session Q)".

## Open Blockers / Questions

1. **Sprint 2 attack generator never built** — `src/validation/attack_generator.py` is the deliverable that gates Phase B. Pick up at Phase 1 of the Execution Plan in the sprint doc.
2. **Recalibrated thresholds may not generalize** — 4.5/3.4/2.0 were tuned on traffic-shape sweeps; Sprint 2's strategy grid is a different distribution.
3. **Sprint 3 Findings Log empty** — Sessions K/O/P findings need retroactive logging when Sprint 3 reactivates (after Sprint 2 gate).
4. **Actor-level alerting investigation queued** — 52% mean actor gap from PR #34 may be a stronger lever than per-window thresholds. Behind Sprint 2 gate.
5. **`session/2026-04-27-end` branch on origin** — contains `09d4852 "Session P-prep close"`, never merged. Decide: delete or land.

## Files to Read for Context

- **Sprint 2 spec + Execution Plan (resume here):** `docs/sprints/sprint_02_attack_robustness.md`
- **Phase B strategy:** `docs/mvp_strategy_phase_b.md` (gate: line 5)
- **Recalibration evidence:** `docs/rd_reports/2026-04-17_large_scale_validation_recalibrated.md`
- **Validation harness reference:** `src/validation/large_scale.py` (similar shape, different axes)
- **Synthetic generator (will be reused):** `src/synthetic/` (actors, temporal, workflows, provenance, composer)

## What To Do Next

1. **Branch `feature/sprint2-attack-grid` off main.**
2. **Phase 1 — Attack Generator.** Build `src/validation/attack_generator.py` per spec table (`speed × spread × zone_path × evasion × closure × objective`). Tests for validity + determinism.
3. **Phase 2 — Robustness Harness.** `src/validation/robustness.py` + `murmur robustness` CLI.
4. **Phase 3 — Run grid (~50 trajectories + 5 edge cases) → R&D report.**
5. **Phase 4 — Gate decision** (PASS / BORDERLINE / FAIL / CLASS-WIPE per Execution Plan table). Decision determines whether Phase B B1 is justified or Sprint 3 / redesign is the right next step.

Time budget: 3-4 days. If Phase 1 alone exceeds 2 days, stop and check assumptions.
