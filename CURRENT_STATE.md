# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1B: Signal Validation Gate** — COMPLETE. All work merged to main.
**Sprint 2: UI + API** — Not yet started. Needs sprint spec.

## Last Completed Milestone

Session J (2026-04-05): Signal assessment + weight rebalance + Sprint 1B gate PASS. PR #20 merged. 14/15 gate criteria met. 20.8x attack/normal separation. burst_per_min and breadth_entropy dropped (harmful signals). 395 tests green.

## GCP Sandbox Status

- Cloud Run `normal-worker` + `maintainer`: active, generating baseline
- Live DB: `murmur.duckdb` — 21,837 events, 994 windows, 1,487 scored pairs
- Data through: 2026-04-05 14:55 UTC
- Tier distribution: HIGH 1, MEDIUM 7, WATCH 7, NORMAL 1,472

## Open Blockers / Questions

1. **Sprint 2 spec needed** — UI + API layer (FastAPI + React + D3.js). No spec written yet.
2. **Attack D partial** — IAM grant detected but impersonated access failed (propagation). Accept or retry.
3. **Slow ratchet cross-window analysis** — Attack C windows overlapped with A/B. Independent analysis needed.
4. **CLI subprocess ingest bug** — orchestrator `python -m src.cli` subprocess didn't ingest. Direct import works.
5. **Physics experiment** — proposal at `docs/rd_reports/physics_signal_experiment_proposal.md`. When to run?
6. **Post-MVP ML roadmap** — Level 2 (per-actor profiles) is the priority. Needs data + design.

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **Phase 3 plan:** `docs/phase3_attack_injection_plan.md`
- **Physics experiment:** `docs/rd_reports/physics_signal_experiment_proposal.md`
- **Session J learnings:** `LEARNINGS.md` (top entry)
- **Fusion weights:** `src/score/fusion.py` (5 active signals, 2 zeroed)
- **Post-MVP roadmap:** `docs/post_mvp_roadmap.md`

## What To Do Next

1. **Write Sprint 2 spec** — FastAPI API + React+D3 dashboard. Define endpoints, components, gate criteria.
2. **Decide on physics experiment timing** — before Sprint 2 or deferred?
3. **Start Sprint 2 implementation** — API layer first, then frontend.
