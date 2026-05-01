# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 2 methodological cleanup complete (Session S, 2026-04-30, autonomous).** Sprint 3 (provenance/closure full integration) is **partially blocked** pending a "Sprint 2.5" signal architecture review. PR `auto/sprint2-baseline-recalibration` open for review.

## Last Completed Milestone

Session S: embedded attack trajectories in benign baseline + recalibrated thresholds against benign-only FP floor. Predict-then-observe rigor maintained — predictions committed before run.

**Headline verdict:** FAIL at safe FP thresholds (30% recalibrated detection, vs 92% misleading at original WATCH=0.20). Sprint 2's methodological-vs-architectural ambiguity is **resolved** with three findings:

1. Methodology was bad for closure_gap, novelty, bridge (now fire under baseline).
2. Physics signals (sigma_coarse, delta_f) are architecturally dead — 0% on attack across two harness configurations.
3. Separate finding: attack-vs-benign signal-vs-noise gap is too small. Attack P75=0.428, benign P95=0.375. Gap of 0.05 is not load-bearing.

Files: `src/validation/baseline_robustness.py` (~430 LOC), `tests/test_baseline_robustness.py` (9 tests), `src/cli.py` +`robustness-baseline` subcommand. 575 tests pass.

Reports:
- `docs/rd_reports/2026-04-30_sprint2_baseline_recalibration.md` — predictions + observations + verdict
- `docs/rd_reports/2026-04-30_sprint2_baseline_recalibration_run.md` — machine-generated grid output

## Open Blockers / Questions

1. **PR review needed.** `auto/sprint2-baseline-recalibration` open. Per autonomous mode failsafe, the agent did NOT merge. Review + decide on the recommendation tree branch.
2. **Recommendation tree branch: FAIL.** "Reframe; redesign needed before any new layer." Concrete moves: drop/replace sigma_coarse and delta_f, address signal-vs-noise gap, then revisit Sprint 3 / Phase B B1.
3. **Synthetic benign baseline may be over-noisy.** P95=0.375 is high. Open question: is real GCP sandbox traffic quieter? Testable on the existing GCP sandbox.
4. **bridge_new is barely discriminative** (81% benign / 100% attack). Worth ablating.
5. **closure_gap is the standout discriminator** (3.3x). Sprint 3's closure work is justified independently.
6. **Orphan branch `session/2026-04-27-Q-end`** (`09d4852`) still pending from Session Q. Not addressed this session.

## Files to Read for Context

- **Verdict + reasoning (resume here):** `docs/rd_reports/2026-04-30_sprint2_baseline_recalibration.md`.
- **Machine-generated grid output:** `docs/rd_reports/2026-04-30_sprint2_baseline_recalibration_run.md`.
- **New harness:** `src/validation/baseline_robustness.py` (~430 LOC).
- **Sprint 2 prior context:** `docs/rd_reports/2026-04-27_sprint2_robustness.md`.
- **Sprint 3 spec (deferred, not blocked):** `docs/sprints/sprint_03_provenance_closure.md`.

## What To Do Next

**Recommended path (not committed):**

1. **Review the open PR** (`auto/sprint2-baseline-recalibration`).
2. **Sprint 2.5 — Signal Architecture Review (proposed, ~2-3 day R&D pass):**
   - Ablate sigma_coarse, delta_f, bridge_new (low/no discrimination).
   - Evaluate per-actor calibration (actor-history-depth as confidence modifier).
   - Run against real GCP sandbox traffic to bound the synthetic FP floor.
   - Output: signal redesign plan or empirical confirmation that current signals suffice on real benign.
3. **Or proceed directly to Sprint 3** with eyes open: closure work is justified by closure_gap=3.3x discrimination; provenance integration is independent of the physics thesis. Decline Phase B B1 until signal review.

**Alternative paths:**
- **Proceed with Sprint 3 + Phase B B1 as originally scoped** — risk: building cross-actor/cross-window layers on top of weak per-actor signals compounds noise.
- **Reframe project entirely** — if signal architecture review concludes current signals can't generalize, the moment to revisit core hypotheses.

## Open the PR

PR `auto/sprint2-baseline-recalibration` opened by autonomous agent (Session S). Per autonomous mode failsafe, the agent did NOT merge. The PR is the review boundary.

Time spent this session: ~2 hours wall clock (autonomous, single agent).
