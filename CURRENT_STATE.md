# Murmur — Current State

> This file is the resume point for new sessions. Read this first.

## Active Sprint

**Sprint 1A: Core Detection Build** — Sessions A-E complete. PR #16 merged. Provenance scaffold done. Benchmark + R&D review remaining.

## Last Completed Milestone

Session E (2026-03-31): Provenance scaffold — pattern matching, trigger chain, residual risk. Multi-format ingest fix. 14% discount validated on real data. 350 tests. PR #16 merged.

## GCP Sandbox Status (all live, accumulating data)

- Cloud Run `normal-worker` rev 3: reads secret + GCS, writes output. Every 5 min.
- Cloud Run `maintainer` rev 3: rotates secret, generates token, toggles IAM. Every hour.
- Scheduler jobs: trigger-normal-worker (5min), trigger-health-check (hourly), trigger-cleanup (daily), trigger-maintainer (hourly)
- SAs: normal-worker-sa, maintenance-sa, scheduler-sa
- Local snapshot: `data/real/` (refreshed 2026-03-31, includes maintainer events)

## Open Blockers / Questions

1. maintenance-sa not correlated — add `{"maintainer": "maintenance-sa@..."}` to service_worker_map
2. 14% discount vs expected 22% — pattern match varies per window, tune in Sprint 1B
3. Per-invariant suppression for pattern-matched activity — Sprint 2 enhancement
4. Schnakenberg skip-zero blind spot — Sprint 1B attack injection will validate
5. service-agent-manager INV_001 false positive — Sprint 1B allow-list fix

## Files to Read for Context

- **Sprint 1 spec:** `docs/sprints/sprint_01_core_detection.md`
- **Session E learnings:** `LEARNINGS.md` (top entry)
- **Provenance:** `src/provenance/residual.py`, `src/provenance/patterns.py`
- **Scoring:** `src/score/fusion.py`, `src/score/invariants.py`

## What To Do Next

1. **R&D review + benchmark session:** Create benchmark scenarios (S01/S04/S07/B01/B02/S13). Deep review of invariant fires, sigma distribution, score separation. Combine per memory note.
2. **Sprint 1B:** Attack injection, signal validation gate, EXFIL_RISK baseline.
