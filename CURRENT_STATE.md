# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 2.5 — Physics Signal Architecture Review.** Spec merged (PR #38, commit `78e7ac6`); execution not yet started. 2-3 day R&D pass with falsifier locked at ≥1.5x discrimination ratio before Day 1.

## Last Completed Milestone

Session S (2026-04-30, autonomous + R&D discussion): Sprint 2 methodological cleanup merged via PR #37 (commit `f21fd13`). Sprint 2.5 spec designed and merged via PR #38 (commit `78e7ac6`). Both PRs merged by user.

## Open Blockers / Questions

1. **Sprint 2.5 execution.** Branch `rd/sprint2-5-physics-review` off main. Day 1 = three diagnostic probes (bug/calibration/concept) on `sigma_coarse` and `delta_f`. **User-review checkpoint required between Day 1 and Day 2.**
2. **Predictions for Sprint 2.5 must be committed BEFORE Day 1.** Spec already lists prior probabilities (35/30/25/10 for bug/calibration/concept/refuted); these need to land in the new R&D report at sprint kickoff.
3. **Synthetic baseline noise.** Benign-only P95=0.375 in PR #37 may be a synthetic artifact. Testable on existing GCP sandbox. Deferred until Sprint 2.5 verdict to avoid mixing variables.
4. **Sprint 2.6 (proposed).** Same protocol applied to `novelty` and `bridge_new` (both 1.2x discrimination). Deferred until 2.5 protocol is validated.
5. **Sprint 3 (provenance/closure full integration).** Partially blocked. closure_gap (3.3x) is independently validated; closure work is justified.
6. **Phase B B1 (TGN/TPP).** Fully blocked pending Sprint 2.5 + 2.6.
7. **Worktree cleanup.** `/Users/shamreeniram/Desktop/Peyara/Murmur-baseline-recalib` worktree purpose fulfilled (both branches it held are merged). Recommend `git worktree remove` at next session start; branches stay per `feedback_keep_feature_branches`.
8. **Orphan branch `session/2026-04-27-Q-end`** (`09d4852`) still pending from Session Q.

## Files to Read for Context

- **Sprint 2.5 spec (resume here):** `docs/sprints/sprint_02_5_physics_review.md`.
- **Sprint 2 cleanup verdict:** `docs/rd_reports/2026-04-30_sprint2_baseline_recalibration.md` (predictions + observations + verdict).
- **Sprint 2 cleanup machine output:** `docs/rd_reports/2026-04-30_sprint2_baseline_recalibration_run.md`.
- **Baseline harness implementation:** `src/validation/baseline_robustness.py` (~430 LOC).
- **Sprint 3 spec (deferred, not blocked):** `docs/sprints/sprint_03_provenance_closure.md`.
- **Physics signal source (Sprint 2.5 target):** `src/score/physics.py`, `src/world/graph.py:compute_zone_flux`, `src/score/fusion.py` (sigma_coarse normalization).

## What To Do Next

**Recommended sequence for next session:**

1. Confirm mode — R&D (Sprint 2.5 execution involves discussion-shaped decisions, not autonomous-shaped).
2. Branch `rd/sprint2-5-physics-review` off latest main.
3. Write `docs/rd_reports/2026-05-XX_sprint2_5_physics_review.md` header with frozen predictions (copy from spec).
4. Day 1: implementation probe → calibration probe → concept probe. Stop at first failed probe.
5. Present Day 1 findings; user checkpoint; signoff on Day 2 path.
6. Day 2: single-shot fix.
7. Day 3: verdict per falsifier table; update CLAUDE.md framing; commit + PR.

**Alternate paths:**
- Skip Sprint 2.5 and proceed directly to Sprint 3 closure work — closure_gap discrimination justifies it independently. Risk: leaves the physics question unresolved and forces it later when bigger decisions are pending.
- Run real GCP sandbox baseline first to bound the synthetic FP floor — separate axis but informative. Better to do AFTER Sprint 2.5 verdict (mixing variables otherwise).

## Sprint 2.5 quick-reference

- **Falsifier:** ≥2.0x = standard weight; 1.5–2.0x = low weight; <1.5x = retire (set weight=0, amend CLAUDE.md framing to "aspirational").
- **Discrimination ratio = max(attack_fire/benign_fire, attack_mean/benign_mean)** on existing PR #37 data.
- **Default Branch C signal:** KL divergence between action-type distributions across consecutive windows.
- **Stop-and-rescope:** if Day 1 surprises, stop the sprint, don't expand.
