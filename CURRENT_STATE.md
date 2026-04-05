# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1B: Signal Validation Gate** — Phase 3 PASS. Attack injection validated.

## Last Completed Milestone

Session I (2026-04-03): Live attack injection against GCP sandbox. 4 attack scenarios executed. 3 MEDIUM-tier detections. INV_011 fired on impersonated credential. sigma_coarse spiked 16x. Zero false positives. MVP signal validation gate: PASS.

## GCP Sandbox Status

- Cloud Run `normal-worker` + `maintainer`: active, generating benign baseline
- Live DB: `murmur.duckdb` — 18,792 events, 834 windows, 1,244 scored pairs
- Data through: 2026-04-03 22:55 UTC
- Feature branch: `feature/live-attack-injection` (uncommitted changes)

## Open Blockers / Questions

1. **Feature branch needs commit + PR** — checkpoint fix, orchestrator, plan doc, .gitignore update, test fix
2. **Attack D partial** — IAM grant detected but impersonated secret access failed (propagation delay). Retry or accept.
3. **23:00 UTC hour blob** — may contain additional events from cleanup/late propagation. Ingest next session.
4. **Slow ratchet cross-window analysis** — Attacks A/B/C landed in overlapping window (21:15). Analyze each window independently.
5. **CLI subprocess ingest bug** — orchestrator's `python -m src.cli` subprocess didn't ingest events. Direct import works. Debug for future runs.
6. **Cleanup verification** — confirm attacker-sa deleted, IAM bindings revoked, exfil bucket empty.
7. **burst_per_min redesign** — B+C approach designed, parked for post-MVP.

## Files to Read for Context

- **Phase 3 plan:** `docs/phase3_attack_injection_plan.md`
- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **Session I learnings:** `LEARNINGS.md` (top entry)
- **Baseline snapshot:** `data/attack_results/baseline_snapshot.json`
- **Execution log:** `data/attack_results/phase3_execution.log`
- **Orchestrator:** `scripts/attack_orchestrator.py`

## What To Do Next

1. **Commit + PR** for feature/live-attack-injection branch (checkpoint fix, orchestrator, plan doc)
2. **Verify cleanup** — check attacker-sa, IAM bindings, exfil bucket state
3. **Ingest 23:00 UTC hour** — pull latest GCS data, check for remaining attack events
4. **Deep analysis** of attack results — per-window signal decomposition, slow ratchet trajectory
5. **Write Phase 3 R&D report** — `docs/rd_reports/` with full findings, signal validation summary
6. **Sprint 2 planning** — UI + API layer, now that signal validation is complete
