# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 2 — Attack-strategy gate evaluated. Verdict: FAIL with methodological caveat.** The grid was built and run as planned. Phase B B1 commitment is **not** justified by this evidence alone, but the failure modes (multi-actor + split_actions) cluster on regimes Phase B B1 is designed to address. Sprint 3 (provenance/closure) remains deferred.

## Last Completed Milestone

Session R (2026-04-27): Sprint 2 attack generator + robustness harness shipped. 50-trajectory grid + 5 edge cases run. Gate verdict: 40% detection (FAIL), with `split_actions: 0%` and `multi_actor: 8.7%` as CLASS-WIPE patterns. Branch `feature/sprint2-attack-grid` ready to PR (4 commits planned). 36 new tests, all passing. Report at `docs/rd_reports/2026-04-27_sprint2_robustness.md`.

## Open Blockers / Questions

1. **Methodological gap: physics signals (sigma_coarse, delta_f) fire 0% on attack-only trajectories.** Cannot distinguish "physics broken" vs "physics needs benign baseline" without re-running the grid with workers + scheduled-job traffic embedded. **This is the single most important question gating Phase B B1 vs redesign.**
2. **Threshold doesn't transfer across distributions.** 26 of 30 blind spots sit at residual_risk = 0.151–0.198, just below WATCH=0.20. Recalibration on the strategy-grid distribution is needed; until then, the gate verdict is partly a calibration artifact.
3. **Multi-actor coordination is invisible to per-actor signals.** Architectural finding — needs cross-actor representation (Phase B B1 TGN) or a `target_convergence` signal (Phase 2).
4. **Split-actions across windows defeats window-scoped scoring.** Architectural finding — needs cross-window representation (Phase B B1 TPP) or `eddy_score`.
5. **PR not yet opened.** Branch `feature/sprint2-attack-grid` is local + 1 commit ahead. Decide: open PR now or wait for benign-baseline re-run.
6. **Orphan branch `session/2026-04-27-end`** (`09d4852 "Session P-prep close"`) still pending from Session Q. Not addressed this session.

## Files to Read for Context

- **Gate verdict + analysis (resume here):** `docs/rd_reports/2026-04-27_sprint2_robustness.md` (especially the appended "Findings & Interpretation" section, lines 137-224).
- **Sprint 2 spec + Findings Log:** `docs/sprints/sprint_02_attack_robustness.md` (Findings Log section now populated with gate verdict).
- **Phase B strategy:** `docs/mvp_strategy_phase_b.md` (gate condition: line 5).
- **Generator:** `src/validation/attack_generator.py` (300 LOC, 25 tests).
- **Harness:** `src/validation/robustness.py` (380 LOC, 11 tests).
- **CLI:** `src/cli.py:457-498` (`murmur robustness` subcommand).

## What To Do Next

**Recommended path (not committed):**

1. **Build "robustness with baseline" harness variant.** Embed the attack trajectory in a benign-traffic stream (workers + scheduled jobs) and re-score. If sigma_coarse/delta_f activate non-zero under this condition, the FAIL verdict is mostly methodological and the BORDERLINE+charitable reading applies. Estimated: ~1 day off existing infrastructure (compose attack via attack_generator, embed via existing TrajectoryComposer benign generator).
2. **Recalibrate thresholds on strategy-grid distribution.** Compute P75/P90/P95 of residual_risk across the 50-trajectory grid + benign-baseline variant. Set thresholds from there, not from PR #34's distribution. ~2 hours.
3. **Re-run gate with both fixes.** If detection ≥ 60% post-cleanup, BORDERLINE → consider partial Phase B B1 (TGN-only, defer TPP). If still <60% with multi-actor or split-actions persisting, FAIL → physics thesis needs surgery before any new layer.
4. **Decide:** Phase B B1 (TGN+TPP) | Sprint 3 closure repair | Phase 2 signals (target_convergence, eddy_score) | redesign. The decision cleans up only after step 3.

**Alternative paths:**
- **Skip the methodological cleanup, take strict FAIL at face value.** Re-evaluate physics thesis from premise. Risk: throwing away signals that might work fine with proper baseline.
- **Open PR now with current evidence.** Get external review on the FAIL+caveat reading before deciding next move. Useful if a second opinion would change the path forward.

## Open the PR?

Before next session: decide whether to open PR for `feature/sprint2-attack-grid` immediately (gate evidence is shippable; review will sharpen the verdict reading) or hold until baseline-variant data lands (one PR with the full picture). Recommended: open now — the evidence is unit-reviewable, the next iteration is its own R&D pass.

Time spent this session: ~2.5 hours (under 3-4 day budget). Phase 1 took ~30 min (well under 2-day flag). Generator simplicity held as forcing function.
