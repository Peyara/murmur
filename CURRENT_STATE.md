# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 2.5 — Physics Signal Architecture Review.** Now evidence-grounded by a deep-research pass
(2026-07-01). Verdict: physics failure is most likely an **instrument mismatch** (Schnakenberg
cycle-current estimator is structurally wrong for acyclic attack flows), NOT an impoverished sandbox
and NOT a disproven thesis. Execution of the diagnostic (step 2) not yet started.

## Last Completed Milestone

**2026-07-01 (R&D):** Fresh-eyes physics review. Deep-research (5 angles, 21 sources) complete.
Report: `docs/rd_reports/2026-07-01_physics_signal_research.md`. Committed on branch `gut-renovation`
to pick up tomorrow. User has NOT finished reading the report yet.

## Open Blockers / Questions

1. **Read the report.** User paused mid-report — `docs/rd_reports/2026-07-01_physics_signal_research.md`
   §4 (the S=6 correction) and §6 (step-2 design) are the parts to finish.
2. **Step 2 = real-data observation** on real GCP benign traffic (no attack labels): measure (a) **edge
   reciprocity** [load-bearing — how often does i→j come with j→i?], (b) transition density per window
   vs the corrected S=6 floor (~20), (c) whether persistent cycle currents exist at all.
3. **Free check first:** disaggregate PR #37's 0%/5% by attack subclass (aggregation may mask a
   physics niche on cyclic-recon attacks). No new data needed.
4. **Likely endgame:** replace instrument (Sprint 2.5 Branch C) — a directed one-way flux / KL measure
   that scores acyclic exfil as maximally irreversible instead of undefined. Contingent on reciprocity.
5. **Global vs Peyara CLAUDE.md inconsistency** — global not amended this session; decide sync path.
6. **peyara-standards CLAUDE.md change uncommitted** (separate repo) — commit decision pending.

## Files to Read for Context

- **Resume here:** `docs/rd_reports/2026-07-01_physics_signal_research.md` (full synthesis + step-2 design).
- Raw research: `docs/rd_reports/2026-07-01_physics_research_raw.json`.
- Sprint spec: `docs/sprints/sprint_02_5_physics_review.md`.
- Physics source: `src/score/physics.py`, `src/world/graph.py:compute_zone_flux`.
- This session's learnings: `LEARNINGS.md` top entry.

## What To Do Next

1. Confirm mode — R&D. Branch `gut-renovation` is already checked out (findings committed there).
2. Finish reading the 2026-07-01 report (§4 S=6 correction, §6 step-2 design).
3. Run the FREE check: disaggregate PR #37 physics fire-rates by attack subclass.
4. Design + run step 2: real-GCP edge-reciprocity + density observation harness. Predict-then-observe.
5. Decide instrument-replacement (Branch C) based on the reciprocity result.

## Branch note

`gut-renovation` off `main` holds this session's report, raw research, and handoff files. The name
signals the intent: this may become a larger simplification/de-sprawl of the scoring stack, not just a
physics fix (closure_gap 3.3x + inv_score 2.2x carry the system; ~8 other signals underperform).
