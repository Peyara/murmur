# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — IN PROGRESS. Session A complete (ingestion foundation). PR #11 merged. Session B (activity generator deployment) and Session C (24h observation) remain.

## Last Completed Milestone

Sprint 1A Session A (2026-03-26): Multi-format ingestion pipeline (3 parsers, correlator, multi-prefix fetch), ACTION_MAP 13→22, hydration period design, infrastructure tagging. 210 tests green. GCS sink expanded.

## GCP Sandbox Status

Cloud Scheduler firing every 5 min (hello-world — to be replaced in Session B). 9 GCP APIs enabled. GCS sink now captures all 3 log types (audit + scheduler + Cloud Run). Scheduler/Cloud Run logs accumulating since sink expansion.

## Open Blockers / Questions

1. Activity generator not yet deployed (Session B) — blocks 24h observation
2. Correlation confidence weights need calibration against real data (Session C)
3. Auto-discovery of service_worker_map — Sprint 2-3 scope
4. Self-learning parser — Sprint 2-3 scope, issue to be created
5. Schema migration for existing DuckDB files — track for Sprint 3
6. EXFIL_RISK pattern tuning — pending from issue #2
7. known_initiators.json needs real scheduler SA from deployed environment

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **MVP strategy:** `docs/mvp_strategy.md` (includes hydration/onboarding section)
- **Latest learnings:** `LEARNINGS.md` (Sprint 1A Session A entry at top)
- **Correlator design:** `src/ingest/correlate.py` (temporal-identity correlation + hydration validation)
- **Peyara standards:** `~/Desktop/Peyara/CLAUDE.md` (v2.0)

## What To Do Next

1. **Session B:** Deploy activity generator — Cloud Run normal-worker (reads secret + GCS), maintenance script (hourly), cleanup cron (daily). Create GCS buckets, maintenance SA, scheduler jobs.
2. **Session B:** Verify all 3 log types flowing to GCS sink from new services.
3. **Session C (after 24h):** Run inspector on accumulated multi-format data. Observe real patterns. Calibrate correlation confidence weights.
4. **Session D+:** World model (windowing, zone flux), scoring (invariants, sigma_coarse), provenance scaffold — informed by Session C observations.
