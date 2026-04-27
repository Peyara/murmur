# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Phase B kickoff prep** — Sprint 2 formal gate validation before committing to Phase B's 17-21 wk learned-representation track.

## Last Completed Milestone

Session P-prep (2026-04-27): peyara-standards installed locally; PR #32 merged adding `mvp_strategy_phase_b.md` + theory docs (`physics_foundations.md`, `schnakenberg_formalization.md`); original `mvp_strategy.md` renamed to `mvp_strategy_phase_a.md`. Forward queue (P-T) planned.

Prior: Session O (2026-04-14) — MVP thesis informally validated (70% attacker/worker residual gap on synthetic seed=42). PRs #27-31 merged.

## Open Blockers / Questions

1. **Sprint 2 formal gate not measured.** `src/validation/attack_generator.py` does not exist; the parameterized 30-50 trajectory grid + robustness report Sprint 2 specifies were never produced. Phase B's pivot condition (≥80% detection on grid) is informally met by Session O's 70% gap, but they're different metrics on different artifacts.
2. **Closure independence puzzle.** 2026-04-14 re-ablation showed zero vs redistribute deltas identical (1.00x ratio). Closure adds no independent fusion-level signal at current scale despite per-role activation differential (attackers 58.6% vs workers 12.6%). Cause unknown — weight calibration, signal redundancy, or threshold issue.
3. **Directionality gap (Thread 3).** Pair miner finds reverse patterns (DELETE→CREATE). Needs causal filter — RANK-style transition weights from `post_mvp_roadmap.md` 0.4 are the most concrete framing.
4. **Deployer/admin/scheduler trigger resolution = 0%.** Unique job IDs per invocation fail corroboration. Identity-based resolution path may be needed alongside corroboration.
5. **install.sh idempotency** (peyara-standards repo, carry-over from Session M) — repeated runs duplicate hooks within the same matcher.
6. **Git committer identity** — auto-derived `shamreens-mbp.mynetworksettings.com`, should be set to `pango.co`.

## Files to Read for Context

- **Phase B strategy:** `docs/mvp_strategy_phase_b.md` (B1 TGN encoder, B2 physics regularization, B3 provenance integration; conditional on Sprint 2 gate)
- **Phase A strategy:** `docs/mvp_strategy_phase_a.md` (Sprints 0-4)
- **Theory references:** `docs/theory/physics_foundations.md`, `docs/theory/schnakenberg_formalization.md`
- **Sprint 2 spec:** `docs/sprints/sprint_02_attack_robustness.md` (the unbuilt parameterized attack generator)
- **Closure ablation (1.00x ratio finding):** `docs/rd_reports/2026-04-14_closure_reablation.md`
- **Synthetic validation (Session O baseline):** `docs/rd_reports/2026-04-14_synthetic_validation_observation.md`
- **Post-MVP roadmap:** `docs/post_mvp_roadmap.md` (Phase 1.2 targeted signals, Phase 0.4 RANK-style weights)

## What To Do Next

**Session P — Sprint 2 formal gate validation.** Build `src/validation/attack_generator.py` per the sprint_02 spec (parameterized over speed × spread × zone_path × evasion × closure × objective). Generate the 30-50 trajectory grid + 5 edge cases. Run through the now-fully-wired pipeline. Produce robustness report (detection rate by parameter, signal blind spots). Decision gate at end:
- ≥80% → green-light Phase B B1
- 60-80% → Session Q (targeted Phase 1.2 signals against measured blind spots) before B1
- <60% → physics thesis needs rework

**Then queued:** Session Q (targeted signals, conditional) → R (closure independence + directionality gap) → S (1,000+ trajectory scale validation) → T (B1 kickoff or Sprint 4 dashboard, decision point).
