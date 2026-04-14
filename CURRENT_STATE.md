# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Post-MVP Validation** — synthetic generator hardened, pipeline fully wired, MVP thesis validated on synthetic data.

## Last Completed Milestone

Session O (2026-04-14): MVP thesis validated. Physics + provenance both contribute to 70% attacker/worker residual gap. Closure pipeline wired (was dead code). Trigger chain resolution added. PRs #27-30 merged.

## GCP Sandbox Status

- User considering disabling billing (recommended over deleting project)
- Not needed for current work — all validation runs locally on synthetic data

## Open Blockers / Questions

1. **Closure re-ablation needed** — prior result (1.8% activity) invalidated. With 10.8% orphaned_privilege activation, re-ablation should show independent signal value.
2. **Deployer/admin/scheduler trigger resolution = 0%** — unique job IDs per invocation fail corroboration. May need identity-based resolution path.
3. **Directionality gap confirmed** — pair miner found reverse patterns (DELETE→CREATE). Needs causal filter before scaling.
4. **Large-scale validation deferred** — all signals active; 1,000+ trajectory run is meaningful now.
5. **install.sh idempotency bug** — repeated runs duplicate hooks (carried from prior session)

## Files to Read for Context

- **R&D validation report:** `docs/rd_reports/2026-04-14_synthetic_validation_observation.md`
- **Temporal evidence report:** `docs/rd_reports/2026-04-13_temporal_profile_evidence.md`
- **Synthetic generator:** `src/synthetic/` (actors, temporal, workflows, provenance, composer)
- **Closure pipeline:** `src/score/closure.py` (now wired into ingest via fetch.py)
- **Trigger chain:** `src/provenance/trigger_chain.py` (Cloud Scheduler path resolution added)
- **Post-MVP roadmap:** `docs/post_mvp_roadmap.md` (Phase 0 complete)

## What To Do Next

1. **Re-run closure ablation** — orphaned_privilege is now 10.8% active (was 0%). Prior ablation invalidated. Most informative next step.
2. **Fix deployer/scheduler trigger resolution** — identity-based resolution path alongside corroboration
3. **Run large-scale validation** — 1,000+ trajectories through full pipeline, signal quality analysis
4. **Address directionality gap** — causal filter for pair mining (Thread 3)
