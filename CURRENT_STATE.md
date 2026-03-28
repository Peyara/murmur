# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — Sessions A+B+C COMPLETE. Session D target: world model + scoring layers.

## Last Completed Milestone

Sprint 1A Session C (2026-03-27): 24h real data inspection validated. 99.7% correlation accuracy on 1,513 events. Delegation chain extracted. 6 blind spots documented. PR #13 merged. 221 tests green.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 3: reads secret + GCS, writes output. Every 5 min.
- Scheduler jobs: trigger-normal-worker (5min), trigger-health-check (hourly), trigger-cleanup (daily POST)
- GCS sink: all 3 log types (audit + scheduler + cloudrun) → murmur-audit-logs-sandbox
- Local snapshot: `data/real/` (5 days, 3,415 entries, 166 files, gitignored)

## Open Blockers / Questions

1. 25 medium-confidence correlations (0.50-0.89) — investigate in Session D
2. EXFIL_RISK baseline: first-ever zone event = max novelty, or synthesize during attack injection?
3. `ReplaceService` -> ACTION_MAP as `COMPUTE_UPDATE` — Sprint 1B decision
4. Deploy Workflow 2 (maintainer) before or alongside Session D?
5. Schnakenberg zero-flux cell handling — confirm during physics.py implementation
6. Schema migration for existing DuckDB files: `ALTER TABLE events ADD COLUMN delegation_chain VARCHAR DEFAULT '[]';`
7. Detection latency: GCS sink batch vs Cloud Logging API — post-MVP
8. Self-learning parser — Sprint 2-3

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md` (includes Session C findings + parked items)
- **Session C RD report:** `docs/rd_reports/2026-03-27_session_c_24h_inspection.md`
- **Zone flux design notes:** `.claude/plans/eager-strolling-bumblebee.md` (tiered confidence strategy)
- **Latest learnings:** `LEARNINGS.md` (Session C + session-end meta-findings)
- **MVP strategy:** `docs/mvp_strategy.md`

## What To Do Next

1. **Session D:** Build world model layer — 15-min windowing (`src/world/window.py`), zone flux 6x6 matrix (`src/world/graph.py`) with observation counts per cell, edge tracking. Use tiered confidence design (Cold/Warm/Calibrated).
2. **Before or alongside Session D:** Deploy Workflow 2 (hourly maintainer — secret rotation, SA key management) to enrich IDENTITY/CONTROL zone baseline.
3. **Session D+:** Scoring layer — invariants, sigma_coarse (handle zero-flux cells), novelty scoring with confidence tiers, basic fusion.
4. **Sprint 1B:** Attack injection, EXFIL_RISK baseline, system_event parser, GCP SA allow-list.
