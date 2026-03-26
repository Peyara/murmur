# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 0B: GCP Provisioning** — COMPLETE. trigger_ref experiment done (no native ID — temporal correlation is the design). PR #10 merged. All sprint specs updated with findings cascade. Ready for Sprint 1.

## Last Completed Milestone

Sprint 0B close (2026-03-26): trigger_ref experiment, cloud-agnostic inspector, inspect-interpret agent, 5 broken assumptions cascaded across all docs, peyara-standards v2.0 (3 new R&D disciplines). 121 tests green.

## GCP Sandbox Status (all live)

Cloud Scheduler firing every 5 min (hello-world container — to be replaced in Sprint 1 Day 0). 9 GCP APIs enabled. Audit logs flowing to GCS bucket. Scheduler/Cloud Run logs available via Cloud Logging API but NOT in GCS sink yet.

## Open Blockers / Questions

1. Multi-format parser architecture — dispatcher vs single module (Sprint 1 design decision)
2. correlation_confidence as CanonicalEvent field — Sprint 1 design decision
3. Sink expansion vs Cloud Logging API fetcher — Sprint 1 design decision
4. EXFIL_RISK pattern tuning — pending from issue #2
5. known_initiators.json needs real scheduler SA via env var

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md` (includes Day 0 activity generator, ingestion foundation, observation-first validation)
- **R&D report:** `docs/rd_reports/2026-03-25_trigger_ref_discovery.md` (trigger_ref evidence, architecture implications)
- **MVP strategy:** `docs/mvp_strategy.md` (updated data flow, causal chain, critical decisions)
- **Peyara standards:** `~/Desktop/Peyara/CLAUDE.md` (v2.0 — observe first, no confirmation bias, learning loop, objectivity over agreement)
- **Latest learnings:** `LEARNINGS.md` (most recent entry at top)

## What To Do Next

1. Sprint 1A Day 0: Deploy real Cloud Run worker (reads secret + GCS), maintenance script (hourly key rotation + IAM), manual human activity
2. Sprint 1A Day 0: Run inspector on 24h of real activity BEFORE writing detection code
3. Sprint 1A Days 1-2: Build multi-format parser dispatcher + temporal-identity correlator
4. Sprint 1A Days 3-7: World model + scoring + provenance scaffold
5. Sprint 1B: Observation-first validation (bias check criteria included)
